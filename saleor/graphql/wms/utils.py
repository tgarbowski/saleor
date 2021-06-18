import base64

from django.template.loader import get_template
from weasyprint import HTML

from saleor.wms.models import WMSDocument, WMSDocPosition


def create_pdf_document(document_id):
    document = WMSDocument.objects.select_related('warehouse', 'created_by', 'recipient').get(pk=document_id)
    document_positions = WMSDocPosition.objects.select_related(
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
