from django.db.models import F

from saleor.payment.utils import price_to_minor_unit
from saleor.order.models import OrderLine


def get_receipt_payload(order):
    lines_fulfilled = OrderLine.objects.filter(order=order, quantity_fulfilled=F('quantity'))
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
        "summary": summary
    }
    return payload
