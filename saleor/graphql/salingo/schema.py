import graphene

from saleor.graphql.order.schema import OrderFilterInput
from saleor.graphql.utils import resolve_global_ids_to_primary_keys
from saleor.order.models import Order
from saleor.graphql.order.filters import OrderFilter
from saleor.graphql.wms.utils import generate_warehouse_list
from .mutations import ExtReceiptRequest, ExtReceiptUpdate, ExtInvoiceCorrectionRequest, ExtTallyCsv, ExtMigloCsv
from saleor.graphql.core.utils import from_global_id_or_error
from .types import PaymentUrl
from saleor.plugins.manager import get_plugins_manager
from saleor.graphql.payment.types import Payment
from saleor.payment.gateways.payu.utils import generate_payu_redirect_url
from saleor.payment.utils import create_payment_information
from saleor.payment import models



class ExternalQueries(graphene.ObjectType):
    warehouse_list_pdf = graphene.Field(
        graphene.String,
        order_ids=graphene.List(graphene.NonNull(graphene.ID)),
        filters=OrderFilterInput(),
        description='B64 encoded warehouse list pdf'
    )

    generate_payment_url = graphene.Field(
        PaymentUrl,
        description="Generates an url to redirect to payment gateway and complete payment",
        payment_id=graphene.Argument(
            graphene.ID,
            description="Payment ID.",
            required=True
        ),
        channel=graphene.String()
    )

    def resolve_warehouse_list_pdf(self, info, **kwargs):
        def get_order_ids(kwargs):
            global_order_ids = kwargs.get('order_ids')
            filters = kwargs.get('filters')

            if global_order_ids:
                return resolve_global_ids_to_primary_keys(ids=global_order_ids)[1]
            if filters:
                all_orders = Order.objects.all()
                filtered_orders = OrderFilter(
                    data=filters, queryset=all_orders
                ).qs
                return filtered_orders.values_list('id', flat=True)
            return []

        warehouse_list = generate_warehouse_list(order_ids=get_order_ids(kwargs))
        return warehouse_list

    def resolve_generate_payment_url(self, info, **kwargs):
        value, payment_id = from_global_id_or_error(
            kwargs["payment_id"], only_type=Payment
        )
        channel = kwargs["channel"]
        payment = models.Payment.objects.filter(id=payment_id).first()
        manager = get_plugins_manager()
        plugin = manager.get_plugin(plugin_id=payment.gateway, channel_slug=channel)
        config = plugin.get_payment_connection_params(plugin.configuration)
        redirect_url = generate_payu_redirect_url(config,
                                                  create_payment_information(payment))
        return PaymentUrl(payment_url=redirect_url)


class ExternalMutations(graphene.ObjectType):
    ext_receipt_request = ExtReceiptRequest.Field()
    ext_receipt_update = ExtReceiptUpdate.Field()
    ext_invoice_correction_request = ExtInvoiceCorrectionRequest.Field()
    ext_tally_csv = ExtTallyCsv.Field()
    ext_miglo_csv = ExtMigloCsv.Field()