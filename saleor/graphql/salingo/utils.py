import operator
import functools

from django.db import transaction
from django.db.models import Max, Q

from saleor.payment.utils import price_to_minor_unit
from saleor.order.models import FulfillmentLine, OrderLine
from saleor.order.utils import get_voucher_discount_for_order
from saleor.salingo.discounts import (
    get_manual_discounts_for_order,
    get_order_discount_position
)
from django.core.exceptions import ValidationError
from ...invoice.error_codes import InvoiceErrorCode
from ...plugins.wms.plugin import wms_document_create, wms_positions_bulk_create
from ...wms.models import WmsDocument


def get_receipt_payload(order):
    fulfilled_order_lines_ids, not_fulfilled_order_lines_ids = get_invoice_correct_payload(order=order)
    order_lines = list(OrderLine.objects.filter(order=order).values_list('id', flat=True))
    if len(fulfilled_order_lines_ids) + len(not_fulfilled_order_lines_ids) != len(order_lines):
        raise ValidationError(
            {
                "orderId": ValidationError(
                    "Receipt can only by created when order products are fulfilled or returned.",
                    code=InvoiceErrorCode.NO_INVOICE_PLUGIN,
                )
            }
        )
    lines_fulfilled = OrderLine.objects.filter(id__in=fulfilled_order_lines_ids)
    lines_json = []

    for line_fulfilled in lines_fulfilled:
        line = {
            "na": line_fulfilled.product_name,
            "il": line_fulfilled.quantity_fulfilled,
            "vtp": "23,00",
            "pr": price_to_minor_unit(value=line_fulfilled.total_price_gross_amount,
                                      currency='PLN')
        }
        lines_json.append(line)

    if not order.shipping_price_gross_amount == 0:
        shipping_position = {
            "na": "TRANSPORT Usługa transportowa",
            "il": 1,
            "vtp": "23,00",
            "pr": price_to_minor_unit(value=order.shipping_price_gross_amount,
                                      currency='PLN')
        }
        lines_json.append(shipping_position)

    summary = {
        "to": price_to_minor_unit(value=order.total_paid_amount, currency='PLN')
    }

    payload = {
        "lines": lines_json,
        "summary": summary,
    }
    discounts = []

    order_manual_discounts = get_manual_discounts_for_order(order)
    for order_discount in order_manual_discounts:
        discount_name = order_discount.reason or "Discount"
        discount_position = get_order_discount_position(discount_name,
                                                        order_discount.amount_value)
        discounts.append(discount_position)

    voucher = get_voucher_discount_for_order(order)
    if voucher.amount > 0:
        discount_position = get_order_discount_position(order.voucher.code,
                                                        voucher.amount)
        discounts.append(discount_position)

    payload["discounts"] = discounts
    return payload


def get_invoice_correct_payload(order):
    order_lines = list(OrderLine.objects.filter(order=order).values_list('id', flat=True))
    queryset = FulfillmentLine.objects.values('order_line_id').filter(order_line_id__in=order_lines).annotate(
        max_order=Max('fulfillment__fulfillment_order'))
    queryset = list(queryset)
    query = functools.reduce(
        operator.or_,
        (Q(order_line_id=record['order_line_id'], fulfillment__fulfillment_order=record['max_order']) for record in queryset)
    )
    # order lines in fulfillment status other than fulfilled eg. returned
    not_fulfilled = FulfillmentLine.objects.filter(query).exclude(fulfillment__status='fulfilled').values_list('order_line_id', flat=True)
    # order lines in fulfillment status: fulfilled
    fulfilled = FulfillmentLine.objects.filter(query).filter(
        fulfillment__status='fulfilled'
    ).values_list('order_line_id', flat=True)

    return list(fulfilled), list(not_fulfilled)


def generate_wms_documents(orders):
    for order in orders:
        # Check if there is already a wms document and delete if true
        wms_document = WmsDocument.objects.filter(order=order)
        if wms_document:
            return
        # Create GRN document
        with transaction.atomic():
            wms_document = wms_document_create(
                order=order,
                document_type='GIN'
            )
            wms_document.save()
            wms_positions_bulk_create(order=order, wms_document_id=wms_document.id)
