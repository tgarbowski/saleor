from saleor.wms import models


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
