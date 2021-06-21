import graphene

from saleor.wms import models
from .utils import create_pdf_document, wms_products_report, wms_actions_report


def resolve_wms_documents(info, **_kwargs):
    qs = models.WMSDocument.objects.all()
    return qs


def resolve_wms_document(info, **_kwargs):
    if "number" in _kwargs:
        qs = models.WMSDocument.objects.filter(number=_kwargs.get("number")).first()
    if "id" in _kwargs:
        qs = models.WMSDocument.objects.filter(pk=_kwargs.get("id")).first()
    return qs


def resolve_wms_doc_positions(info, **_kwargs):
    qs = models.WMSDocPosition.objects.select_related('document').all()


def resolve_wms_document_pdf(info, **_kwargs):
    document_id = graphene.Node.from_global_id(_kwargs['id'])[1]
    file = create_pdf_document(document_id)

    return file


def resolve_wms_actions_report(info, **_kwargs):
    report = wms_actions_report(_kwargs['startDate'], _kwargs['endDate'])

    return report


def resolve_wms_products_report(info, **_kwargs):
    report = wms_products_report(_kwargs['startDate'], _kwargs['endDate'])

    return report
