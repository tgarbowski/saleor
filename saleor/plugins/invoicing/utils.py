import os
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from distutils.util import strtobool

import pytz
from django.conf import settings
from django.template.loader import get_template
from prices import Money
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
TWO_PLACES = Decimal("0.01")


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
    last_invoice = Invoice.objects.filter(
        number__isnull=False,
        order__metadata__invoice="true",
        parent__isnull=True
    ).last()

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


def generate_invoice_pdf(invoice, order):
    font_path = os.path.join(
        settings.PROJECT_ROOT, "templates", "invoices", "inter.ttf"
    )
    fulfilled_order_lines_ids, _ = get_invoice_correct_payload(order=order)
    fulfilled_order_lines = OrderLine.objects.filter(id__in=fulfilled_order_lines_ids)
    fulfilled_order_lines = get_order_line_positions(fulfilled_order_lines)

    shipment = get_shipment_position(quantity=1, gross_amount=order.shipping_price_gross_amount)
    fulfilled_order_lines.append(shipment)

    order_net_total = sum([position.total_price_net for position in fulfilled_order_lines])

    order_summary = create_positions_summary(order_net_total)
    product_limit_first_page = get_product_limit_first_page(fulfilled_order_lines)

    products_first_page = fulfilled_order_lines[:product_limit_first_page]
    rest_of_products = chunk_products(
        fulfilled_order_lines[product_limit_first_page:], MAX_PRODUCTS_PER_PAGE
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
            "shipment": shipment,
            "order_summary": order_summary
        }
    )
    return HTML(string=rendered_template).write_pdf(), creation_date


def generate_correction_invoice_pdf(invoice, order):
    font_path = os.path.join(
        settings.PROJECT_ROOT, "templates", "invoices", "inter.ttf"
    )
    fulfilled_order_lines, not_fulfilled_order_lines = get_invoice_correct_payload(order=order)
    fulfilled_products = OrderLine.objects.filter(id__in=fulfilled_order_lines)
    not_fulfilled_products = OrderLine.objects.filter(id__in=not_fulfilled_order_lines)

    merge_products = create_merge_products(fulfilled_products, not_fulfilled_products)
    corrected_positions_summary_net = sum([position.total_price_net for position in merge_products])
    shipping_price_net = gross_to_net(order.shipping_price_gross_amount)

    if order.status != OrderStatus.RETURNED:
        corrected_positions_summary_net += shipping_price_net
    # Original invoice
    original_invoice_payload = invoice.parent.private_metadata.get("lines")
    original_invoice = original_invoice_lines_to_lines(original_invoice_payload)
    original_positions_summary_net = sum([position.total_price_net for position in original_invoice])
    original_positions_summary = create_positions_summary(original_positions_summary_net)
    # Corrected invoice
    corrected_positions_summary = create_positions_summary(corrected_positions_summary_net)
    final_summary = corrected_positions_summary.total_gross_amount - original_positions_summary.total_gross_amount
    # Shipment
    shipment_quantity = 1 if order.status != OrderStatus.RETURNED else 0
    shipment = get_shipment_position(quantity=shipment_quantity, gross_amount=order.shipping_price_gross_amount)

    creation_date = datetime.now(tz=pytz.utc)
    rec_payload = get_receipt_payload(merge_products, shipment, corrected_positions_summary.total_gross_amount)
    invoice.private_metadata = rec_payload
    invoice.save()

    merge_products.append(shipment)

    rendered_template = get_template("invoices/correction_invoice.html").render(
        {
            "invoice": invoice,
            "creation_date": creation_date.strftime("%d %b %Y"),
            "order": order,
            "font_path": f"file://{font_path}",
            "original_invoice": original_invoice,
            "merge_products": merge_products,
            "shipment": shipment,
            "is_invoice": bool(strtobool(order.metadata.get("invoice"))),
            "final_summary": final_summary,
            "corrected_positions_summary": corrected_positions_summary,
            "original_positions_summary": original_positions_summary
        }
    )
    return HTML(string=rendered_template).write_pdf(), creation_date


def create_merge_products(fulfilled_products, not_fulfilled_products):
    merge_products = []
    for fulfilled_product in fulfilled_products:
        merge_products.append(
            InvoicePosition(
                sku=fulfilled_product.product_sku,
                name=fulfilled_product.product_name,
                quantity=fulfilled_product.quantity,
                unit_price_net=gross_to_net(fulfilled_product.unit_price_gross.amount),
                total_price_net=gross_to_net(fulfilled_product.total_price_gross_amount),
                total_price_gross=fulfilled_product.total_price_gross_amount,
                vat=(fulfilled_product.total_price_gross - fulfilled_product.total_price_net).amount
            )
        )

    for not_fulfilled_product in not_fulfilled_products:
        merge_products.append(
            InvoicePosition(
                sku=not_fulfilled_product.product_sku,
                name=not_fulfilled_product.product_name,
                quantity=0,
                unit_price_net=gross_to_net(not_fulfilled_product.unit_price_gross.amount),
                total_price_net=gross_to_net(Decimal(0.00)),
                total_price_gross=gross_to_net(Decimal(0.00)),
                vat=(not_fulfilled_product.total_price_gross - not_fulfilled_product.total_price_net).amount.quantize(TWO_PLACES)
            )
        )
    return merge_products


def get_receipt_payload(merge_products, shipping, corrected_positions_summary):
    lines_json = []

    for line_fulfilled in merge_products:
        line = {
            "na": line_fulfilled.name,
            "il": line_fulfilled.quantity,
            "vtp": "23,00",
            "pr": price_to_minor_unit(value=line_fulfilled.total_price_gross, currency='PLN')
        }
        lines_json.append(line)

    shipping_position = {
        "na": "TRANSPORT Usługa transportowa",
        "il": shipping.quantity,
        "vtp": "23,00",
        "pr": price_to_minor_unit(value=shipping.total_price_gross, currency='PLN')
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


def gross_to_net(gross_amount):
    return (gross_amount / Decimal(1.23)).quantize(TWO_PLACES)


def net_to_gross(net_amount):
    return (net_amount * Decimal(1.23)).quantize(TWO_PLACES)


def calculate_vat(net_amount):
    return (net_amount * Decimal(0.23)).quantize(TWO_PLACES)


def get_shipment_position(quantity: int, gross_amount: Decimal) -> "InvoicePosition":
    return InvoicePosition(
        name="TRANSPORT Usługa transportowa",
        quantity=quantity,
        unit_price_net=gross_to_net(gross_amount),
        total_price_net=gross_to_net(gross_amount * quantity),
        total_price_gross=(gross_amount * quantity).quantize(TWO_PLACES),
        vat=calculate_vat(gross_to_net(gross_amount * quantity))
    )


def get_order_line_positions(order_lines: ["OrderLine"]) -> ["InvoicePosition"]:
    invoice_positions = []
    for order_line in order_lines:
        position = InvoicePosition(
            name=order_line.product_name,
            quantity=order_line.quantity,
            unit_price_net=gross_to_net(order_line.unit_price_gross.amount),
            total_price_net=gross_to_net(order_line.total_price_gross.amount),
            total_price_gross=(order_line.total_price_gross.amount).quantize(TWO_PLACES),
            vat=calculate_vat(gross_to_net(order_line.total_price_gross.amount))
        )
        invoice_positions.append(position)
    return invoice_positions


def original_invoice_lines_to_lines(original_invoice) -> ["InvoicePosition"]:
    positions = []
    for position in original_invoice:
        gross_amount = price_from_minor_unit(value=position['pr'], currency='PLN')
        invoice_position = InvoicePosition(
            name=position['na'],
            quantity=position['il'],
            unit_price_net=gross_to_net(gross_amount),
            total_price_net=gross_to_net(gross_amount),
            total_price_gross=gross_amount,
            vat=calculate_vat(gross_to_net(gross_amount))
        )
        positions.append(invoice_position)
    return positions


def create_positions_summary(net_amount: Decimal) -> "PositionsSummary":
    gross_amount = net_to_gross(net_amount)

    return PositionsSummary(
        total_net_amount=net_amount,
        total_gross_amount=gross_amount,
        vat=calculate_vat(net_amount)
    )


@dataclass
class InvoicePosition:
    name: str
    quantity: int
    unit_price_net: Decimal
    total_price_net: Decimal
    total_price_gross: Decimal
    vat: Decimal
    sku: str = None

@dataclass
class PositionsSummary:
    total_net_amount: Decimal
    total_gross_amount: Decimal
    vat: Decimal
