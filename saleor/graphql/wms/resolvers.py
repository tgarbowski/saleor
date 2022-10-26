import graphene

from saleor.wms import models
from saleor.order.models import Order
from .types import WmsDeliverer, WmsDocPosition, WmsDocument
from .utils import create_pdf_document, wms_products_report, wms_actions_report, \
    generate_encoded_pdf_documents, generate_encoded_pdf_document
from ..order.filters import OrderFilter


def resolve_wms_documents(info, **_kwargs):
    qs = models.WmsDocument.objects.all()
    return qs


def resolve_wms_document(info, **_kwargs):
    if "number" in _kwargs:
        qs = models.WmsDocument.objects.filter(number=_kwargs.get("number")).first()
    if "id" in _kwargs:
        qs = graphene.Node.get_node_from_global_id(info, _kwargs['id'], WmsDocument)
    return qs


def resolve_wms_doc_positions(info, **_kwargs):
    qs = models.WmsDocPosition.objects.select_related('document').all()

    return qs


def resolve_wms_doc_position(info, **_kwargs):
    return graphene.Node.get_node_from_global_id(info, _kwargs['id'], WmsDocPosition)


def resolve_wms_deliverers(info, **_kwargs):
    qs = models.WmsDeliverer.objects.all()
    return qs


def resolve_wms_deliverer(info, **_kwargs):
    return graphene.Node.get_node_from_global_id(info, _kwargs['id'], WmsDeliverer)


def resolve_wms_document_pdf(info, **_kwargs):
    wmsdocument_id = graphene.Node.to_global_id("WmsDocument", _kwargs['id'])
    document_id = graphene.Node.from_global_id(wmsdocument_id)[1]
    file = generate_encoded_pdf_document(document_id)
    return file


def resolve_wms_actions_report(info, **_kwargs):
    report = wms_actions_report(_kwargs['startDate'], _kwargs['endDate'])

    return report


def resolve_wms_products_report(info, **_kwargs):
    report = wms_products_report(_kwargs['startDate'], _kwargs['endDate'])

    return report
