from django.db.models import Exists, OuterRef

from saleor.wms.models import WmsDocument


def filter_wms_documents(qs, _, value):
    order_ids = WmsDocument.objects.all().values("order_id")
    lookup = Exists(order_ids.filter(order_id=OuterRef('id')))
    return qs.filter(lookup) if value else qs.exclude(lookup)
