import base64
from typing import List

import graphene
from weasyprint import HTML

from django.db.models import Sum, Count, Q, F
from django.template.loader import get_template

from saleor.wms.models import WmsDocument, WmsDocPosition
from saleor.order.models import Order, OrderLine


def create_pdf_document(document_id):
    document = WmsDocument.objects.select_related('warehouse', 'created_by', 'recipient').get(pk=document_id)
    document_positions = WmsDocPosition.objects.select_related(
        'product_variant').filter(document=document_id)
    translated_document_type = translate_document_type(document.document_type)
    deliverer = document.deliverer

    if isinstance(deliverer, dict):
        deliverer = ', '.join([f'{key}: {value}' for key, value in deliverer.items()])

    rendered_template = get_template('warehouse_document.html').render(
        {
            'document': document,
            'translated_document_type': translated_document_type,
            'document_positions': document_positions,
            'deliverer': deliverer
        }
    )
    file = HTML(string=rendered_template).write_pdf()
    encoded_file = base64.b64encode(file).decode('utf-8')

    return encoded_file


def translate_document_type(document_type):
    return {
        'GRN': 'Przyjęcie zewnętrzne (PZ)',
        'GIN': 'Wydanie zewnętrzne (WZ)',
        'IWM': 'Przesunięcie pomiędzy magazynami (MM) ',
        'FGTN': 'Przyjęcie wewnętrzne (PW)',
        'IO': 'Rozchód wewnętrzny (RW)'
    }[document_type]


def wms_actions_report(start_date, end_date):
    # Documents amount per document type
    documents = list(WmsDocument.objects.filter(
        created_at__gte=start_date, created_at__lte=end_date).values('document_type').annotate(
        amount=Count('document_type')
    ))
    # Quantities of different types document positions
    document_positions = list(WmsDocPosition.objects.values('document__document_type').annotate(
        quantity=Sum('quantity')
    ))

    for document, document_position in zip(documents, document_positions):
        document['quantity'] = document_position['quantity']
        document['document_type_translated'] = translate_document_type(document['document_type'])

    return documents


def wms_products_report(start_date, end_date):
    # Quantity of accepted and released goods
    accepted_and_released = list(WmsDocPosition.objects.filter(
        document__created_at__gte=start_date, document__created_at__lte=end_date,
        document__document_type__in=['GRN', 'FGTN', 'GIN', 'IO']).values('product_variant__product').annotate(
            released_quantity=Sum('quantity', filter=Q(document__document_type__in=['GIN', 'IO'])),
            accepted_quantity=Sum('quantity', filter=Q(document__document_type__in=['GRN', 'FGTN'])),
            product_id = F('product_variant__product'),
            product_name = F('product_variant__product__name')
    ))

    for product in accepted_and_released:
        product['product_id'] = graphene.Node.to_global_id('Product', product['product_id'])

    return accepted_and_released


def generate_warehouse_list(order_ids: List[int]) -> str:
    """Generates b64 encoded pdf warehouse list for orders in status READY_TO_FULFILL"""
    orders = Order.objects.filter(pk__in=order_ids).ready_to_fulfill()
    order_lines = OrderLine.objects.filter(order__in=orders).select_related(
        'variant', 'variant__product')
    wms_documents = WmsDocument.objects.filter(order__in=orders)
    order_document_mapping = {wms_document.order_id: wms_document.number for wms_document in wms_documents}
    warehouse_list = []

    for order_line in order_lines:
        warehouse_list.append(
            {
                "location": order_line.variant.private_metadata.get("location"),
                "sku": order_line.variant.sku,
                "name": order_line.variant.product.name,
                "number": order_document_mapping.get(order_line.order_id)
            }
        )

    warehouse_list = sort_warehouse_list_by_location(warehouse_list)

    rendered_template = get_template('warehouse_picking_list.html').render(
        {"warehouse_list": warehouse_list}
    )
    file = HTML(string=rendered_template).write_pdf()
    encoded_file = base64.b64encode(file).decode('utf-8')
    return encoded_file


def sort_warehouse_list_by_location(warehouse_list: List) -> List:
    """
    example locations: #L07K22, #R04K490, #R6K093
    1. Sort by L/R
    2. sort by part between L/R - K
    3. sort by part after K
    """
    # TODO: Currently we check case when location is "", we need to validate location properly
    positions_without_location = [position for position in warehouse_list if not position['location']]
    warehouse_list = [position for position in warehouse_list if position['location']]

    # Sort by part after K
    warehouse_list.sort(key=lambda d: (int(d['location'].split("K")[1])))
    # Sort by part between L/R - K
    warehouse_list.sort(
        key=lambda d: int(''.join(filter(str.isdigit, d['location'].split("K")[0])))
    )
    # Sort by L/R
    warehouse_list.sort(key=lambda d: d['location'][1])
    # Add positions with wrong locations to the end of list
    warehouse_list.extend(positions_without_location)

    return warehouse_list
