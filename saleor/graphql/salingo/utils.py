import operator
import functools

from django.db.models import Max, Q

from saleor.payment.utils import price_to_minor_unit
from saleor.order.models import FulfillmentLine, OrderLine
from saleor.order.utils import get_voucher_discount_for_order


def get_receipt_payload(order):
    fulfilled_order_lines_ids, not_fulfilled_order_lines_ids = get_invoice_correct_payload(order=order)
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

    shipping_position = {
        "na": "TRANSPORT Usługa transportowa",
        "il": 1,
        "vtp": "23,00",
        "pr": price_to_minor_unit(value=order.shipping_price_gross_amount, currency='PLN')
    }
    lines_json.append(shipping_position)

    summary = {
        "to": price_to_minor_unit(value=order.total_gross_amount, currency='PLN')
    }

    payload = {
        "lines": lines_json,
        "summary": summary,
    }

    discount = get_voucher_discount_for_order(order)
    if discount.amount > 0:
        discount_position = [{
            "type": "bill",
            "discount": {
                "na": order.voucher.code,
                "rd": "true",
                "rw": price_to_minor_unit(value=discount.amount, currency="PLN")
            }
        }]
        payload["discounts"] = discount_position

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
