import os
import re
from datetime import datetime
from decimal import Decimal
from distutils.util import strtobool

import pytz
from django.conf import settings
from django.template.loader import get_template
from prices import Money, TaxedMoney
from weasyprint import HTML

from ...giftcard import GiftCardEvents
from ...giftcard.models import GiftCardEvent
from ...invoice.models import Invoice
from saleor.graphql.salingo.utils import get_invoice_correct_payload
from saleor.order.models import OrderLine
from saleor.payment.utils import price_from_minor_unit, price_to_minor_unit
from saleor.order import OrderStatus

MAX_PRODUCTS_WITH_TABLE = 3
MAX_PRODUCTS_WITHOUT_TABLE = 4
MAX_PRODUCTS_PER_PAGE = 13


def make_full_invoice_number(number=None, year=None, begin_number=None, prefix=None):
    now = datetime.now()
    current_year = int(now.strftime("%Y"))

    if begin_number:
        return f"{prefix}{begin_number}/{current_year}"
    if number is not None and current_year == year:
        new_number = (number or 0) + 1
        return f"{prefix}{new_number}/{current_year}"
    return f"{prefix}1/{current_year}"


def parse_invoice_dates(invoice):
    match = re.search(r"(\d+)/", invoice.number)
    number = int(match.group(1))
    year = int(invoice.number.rsplit('/', 1)[-1])

    return number, year


def generate_invoice_number(begin_number, prefix):
    last_invoice = Invoice.objects.filter(number__isnull=False, order__metadata__invoice=True).last()

    if not last_invoice or not last_invoice.number:
        return make_full_invoice_number(begin_number=begin_number, prefix=prefix)

    try:
        number, year = parse_invoice_dates(last_invoice)
        return make_full_invoice_number(number=number, year=year, prefix=prefix)
    except (IndexError, ValueError, AttributeError):
        return make_full_invoice_number()


def chunk_products(products, product_limit):
    """Split products to list of chunks.

    Each chunk represents products per page, product_limit defines chunk size.
    """
    chunks = []
    for i in range(0, len(products), product_limit):
        limit = i + product_limit
        chunks.append(products[i:limit])
    return chunks


def get_product_limit_first_page(products):
    if len(products) < MAX_PRODUCTS_WITHOUT_TABLE:
        return MAX_PRODUCTS_WITH_TABLE

    return MAX_PRODUCTS_WITHOUT_TABLE


def get_gift_cards_payment_amount(order):
    events = GiftCardEvent.objects.filter(
        type=GiftCardEvents.USED_IN_ORDER, parameters__order_id=order.id
    )
    total_paid = 0
    for event in events:
        balance = event.parameters["balance"]
        total_paid += Decimal(balance["old_current_balance"]) - Decimal(
            balance["current_balance"]
        )
    return Money(total_paid, order.currency)


def generate_invoice_pdf(invoice):
    font_path = os.path.join(
        settings.PROJECT_ROOT, "templates", "invoices", "inter.ttf"
    )

    all_products = invoice.order.lines.all()

    product_limit_first_page = get_product_limit_first_page(all_products)

    products_first_page = all_products[:product_limit_first_page]
    rest_of_products = chunk_products(
        all_products[product_limit_first_page:], MAX_PRODUCTS_PER_PAGE
    )
    order = invoice.order
    gift_cards_payment = get_gift_cards_payment_amount(order)
    creation_date = datetime.now(tz=pytz.utc)
    rendered_template = get_template("invoices/invoice.html").render(
        {
            "invoice": invoice,
            "creation_date": creation_date.strftime("%d %b %Y"),
            "order": order,
            "gift_cards_payment": gift_cards_payment,
            "font_path": f"file://{font_path}",
            "products_first_page": products_first_page,
            "rest_of_products": rest_of_products,
        }
    )
    return HTML(string=rendered_template).write_pdf(), creation_date


def generate_correction_invoice_pdf(invoice, order):
    font_path = os.path.join(
        settings.PROJECT_ROOT, "templates", "invoices", "inter.ttf"
    )

    fulfilled_order_lines, not_fulfilled_order_lines = get_invoice_correct_payload(
        order=order)

    all_order_lines = fulfilled_order_lines + not_fulfilled_order_lines

    all_products = OrderLine.objects.filter(id__in=all_order_lines)
    fulfilled_products = OrderLine.objects.filter(id__in=fulfilled_order_lines)
    not_fulfilled_products = OrderLine.objects.filter(id__in=not_fulfilled_order_lines)

    last_invoice = invoice.parent
    original_invoice = last_invoice.private_metadata.get("lines")
    merge_products = create_merge_products(fulfilled_products, not_fulfilled_products)
    # Calculate total price (corrected positions)
    positive_prices = [position['total_price'].gross.amount for position in merge_products]
    corrected_positions_summary = sum(positive_prices)

    if order.status != OrderStatus.RETURNED:
        corrected_positions_summary += order.shipping_price_gross_amount

    for position in original_invoice:
        position['pr'] = price_from_minor_unit(value=position['pr'], currency='PLN')

    original_invoice_sumary = last_invoice.private_metadata.get("summary")['to']
    original_invoice_sumary = price_from_minor_unit(value=original_invoice_sumary, currency='PLN')
    final_summary = corrected_positions_summary - original_invoice_sumary
    is_invoice = bool(strtobool(order.metadata.get("invoice")))

    # Delivery position
    shipment_quantity = 1 if order.status != OrderStatus.RETURNED else 0
    shipment = {
        "quantity": shipment_quantity,
        "price": order.shipping_price_gross_amount * shipment_quantity,
        "unit_price": order.shipping_price_gross_amount,
        "name": "TRANSPORT Usługa transportowa"
    }

    product_limit_first_page = get_product_limit_first_page(all_products)

    products_first_page = all_products[:product_limit_first_page]
    rest_of_products = chunk_products(
        all_products[product_limit_first_page:], MAX_PRODUCTS_PER_PAGE
    )
    order = invoice.order
    gift_cards_payment = get_gift_cards_payment_amount(order)
    creation_date = datetime.now(tz=pytz.utc)

    rec_payload = get_receipt_payload(merge_products, shipment, corrected_positions_summary)
    invoice.private_metadata = rec_payload
    invoice.save()

    rendered_template = get_template("invoices/correction_invoice.html").render(
        {
            "invoice": invoice,
            "creation_date": creation_date.strftime("%d %b %Y"),
            "order": order,
            "gift_cards_payment": gift_cards_payment,
            "font_path": f"file://{font_path}",
            "products_first_page": products_first_page,
            "rest_of_products": rest_of_products,
            "original_invoice": original_invoice,
            "merge_products": merge_products,
            "shipment": shipment,
            "original_invoice_sumary": original_invoice_sumary,
            "corrected_positions_summary": corrected_positions_summary,
            "is_invoice": is_invoice,
            "final_summary": final_summary
        }
    )
    return HTML(string=rendered_template).write_pdf(), creation_date


def create_merge_products(fulfilled_products, not_fulfilled_products):
    merge_products = []
    for fulfilled_product in fulfilled_products:
        merge_products.append(
            {
                "product_sku": fulfilled_product.product_sku,
                "unit_price": fulfilled_product.unit_price,
                "quantity": fulfilled_product.quantity,
                "total_price": fulfilled_product.total_price,
                "name": fulfilled_product.product_name
            }
        )

    for not_fulfilled_product in not_fulfilled_products:
        merge_products.append(
            {
                "product_sku": not_fulfilled_product.product_sku,
                "unit_price": not_fulfilled_product.unit_price,
                "quantity": 0,
                "total_price": get_zero_taxed_money_pln(),
                "name": not_fulfilled_product.product_name
            }
        )
    return merge_products


def get_receipt_payload(merge_products, shipping, corrected_positions_summary):
    lines_json = []

    for line_fulfilled in merge_products:
        line = {
            "na": line_fulfilled['name'],
            "il": line_fulfilled['quantity'],
            "vtp": "23,00",
            "pr": price_to_minor_unit(value=line_fulfilled['unit_price'].gross.amount,
                                      currency='PLN')
        }
        lines_json.append(line)

    shipping_position = {
        "na": "TRANSPORT Usługa transportowa",
        "il": 1,
        "vtp": "23,00",
        "pr": price_to_minor_unit(value=shipping['price'], currency='PLN')
    }
    lines_json.append(shipping_position)

    summary = {
        "to": price_to_minor_unit(value=corrected_positions_summary, currency='PLN')
    }

    payload = {
        "lines": lines_json,
        "summary": summary
    }
    return payload


def generate_correction_invoice_number(prefix, last_correction_invoice):
    try:
        number, year = parse_invoice_dates(last_correction_invoice)
        return make_full_invoice_number(number=number, year=year, prefix=prefix)
    except (IndexError, ValueError, AttributeError):
        return make_full_invoice_number(prefix=prefix)


def generate_correction_receipt_number(prefix, correction_receipt_count):
    now = datetime.now()
    current_year = int(now.strftime("%Y"))
    return make_full_invoice_number(number=correction_receipt_count, prefix=prefix, year=current_year)


def get_zero_taxed_money_pln():
    return TaxedMoney(
        net=Money(amount=0, currency='PLN'),
        gross=Money(amount=0, currency='PLN')
    )
