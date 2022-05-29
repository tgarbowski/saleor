import graphene

from django.core.exceptions import ValidationError

from ..core.mutations import ModelMutation
from ...invoice import events, models
from saleor.graphql.invoice.types import Invoice
from ...core.permissions import OrderPermissions
from ...invoice.error_codes import InvoiceErrorCode
from ..core.types.common import InvoiceError
from ..order.types import Order
from ...order import events as order_events
from saleor.order import OrderStatus
from saleor.graphql.invoice.utils import is_event_active_for_any_plugin
from .utils import get_receipt_payload, get_invoice_correct_payload
from ...core import JobStatus
from graphene.types.generic import GenericScalar
from saleor.plugins.invoicing.plugin import invoice_correction_request


class ExtReceiptRequest(ModelMutation):
    payload = GenericScalar()

    class Arguments:
        order_id = graphene.ID(
            required=True, description="ID of the order related to invoice."
        )

    class Meta:
        description = "Creates a ready to send invoice."
        model = models.Invoice
        object_type = Invoice
        permissions = (OrderPermissions.MANAGE_ORDERS,)
        error_type_class = InvoiceError
        error_type_field = "invoice_errors"

    @staticmethod
    def clean_order(order):
        if order.status != OrderStatus.FULFILLED:
            raise ValidationError(
                {
                    "orderId": ValidationError(
                        "Receipt can only by created when order is fulfilled.",
                        code=InvoiceErrorCode.INVALID_STATUS,
                    )
                }
            )

        if not order.billing_address:
            raise ValidationError(
                {
                    "orderId": ValidationError(
                        "Cannot create a receipt for order without billing address.",
                        code=InvoiceErrorCode.NOT_READY,
                    )
                }
            )

        current_invoice = models.Invoice.objects.filter(order=order).first()

        if current_invoice:
            raise ValidationError(
                {
                    "orderId": ValidationError(
                        "Invoice object already created.",
                        code=InvoiceErrorCode.INVALID_STATUS,
                    )
                }
            )

    @classmethod
    def perform_mutation(cls, _root, info, **data):
        order = cls.get_node_or_error(
            info, data["order_id"], only_type=Order, field="orderId"
        )
        cls.clean_order(order)

        if not is_event_active_for_any_plugin(
                "invoice_request", info.context.plugins.all_plugins
        ):
            raise ValidationError(
                {
                    "orderId": ValidationError(
                        "No app or plugin is configured to handle invoice requests.",
                        code=InvoiceErrorCode.NO_INVOICE_PLUGIN,
                    )
                }
            )

        payload = get_receipt_payload(order=order)

        invoice = models.Invoice.objects.create(
            order=order,
            private_metadata=payload
        )

        order_events.invoice_generated_event(
            order=order,
            user=info.context.user,
            app=info.context.app,
            invoice_number=""
        )

        events.invoice_requested_event(
            user=info.context.user,
            app=info.context.app,
            order=order,
            number=""
        )
        return ExtReceiptRequest(payload=payload, invoice=invoice)


class ExtReceiptInput(graphene.InputObjectType):
    receipt_number = graphene.String(description="External receipt number")
    metadata = GenericScalar()


class ExtReceiptUpdate(ModelMutation):
    class Arguments:
        id = graphene.ID(required=True, description="ID of an invoice to update.")
        input = ExtReceiptInput(
            required=True, description="Fields to use when updating an invoice."
        )

    class Meta:
        description = "Updates externally created receipt info."
        model = models.Invoice
        object_type = Invoice
        permissions = (OrderPermissions.MANAGE_ORDERS,)
        error_type_class = InvoiceError
        error_type_field = "invoice_errors"

    @classmethod
    def clean_input(cls, info, instance, data):
        receipt_number = data["input"].get("receipt_number")
        validation_errors = {}
        if not receipt_number:
            validation_errors["number"] = ValidationError(
                "Receipt number need to be set after update operation.",
                code=InvoiceErrorCode.NUMBER_NOT_SET,
            )

        if validation_errors:
            raise ValidationError(validation_errors)

        return data["input"]

    @classmethod
    def perform_mutation(cls, _root, info, **data):
        instance = cls.get_instance(info, **data)
        cleaned_input = cls.clean_input(info, instance, data)

        instance.update_invoice(
            number=cleaned_input.get("receipt_number")
        )
        instance.store_value_in_private_metadata({"metadata": cleaned_input.get("metadata")})
        instance.status = JobStatus.SUCCESS
        instance.save(update_fields=["number", "updated_at", "status", "private_metadata"])
        order_events.invoice_updated_event(
            order=instance.order,
            user=info.context.user,
            app=info.context.app,
            invoice_number=instance.number,
            url=instance.url,
            status=instance.status,
        )
        return ExtReceiptUpdate(invoice=instance)


class ExtInvoiceCorrectionRequest(ModelMutation):
    payload = GenericScalar()

    class Arguments:
        order_id = graphene.ID(
            required=True, description="ID of the order related to invoice."
        )

    class Meta:
        description = "Creates a ready to send invoice."
        model = models.Invoice
        object_type = Invoice
        permissions = (OrderPermissions.MANAGE_ORDERS,)
        error_type_class = InvoiceError
        error_type_field = "invoice_errors"

    @classmethod
    def perform_mutation(cls, _root, info, **data):
        order = cls.get_node_or_error(
            info, data["order_id"], only_type=Order, field="orderId"
        )
        # TODO: dodaj walidacje jak z innych invoice mutacji
        payload = {}
        last_invoice = models.Invoice.objects.filter(order=order).last()

        shallow_invoice = models.Invoice.objects.create(
            order=order,
            number=data.get("number"),
            private_metadata={},
            parent=last_invoice
        )

        invoice = invoice_correction_request(
            order=order, invoice=shallow_invoice, number=data.get("number")
        )

        return ExtInvoiceCorrectionRequest(payload=payload, invoice=invoice)
