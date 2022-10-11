from collections import defaultdict

from ...wms.models import WmsDocument
from ..core.dataloaders import DataLoader


class WmsDocumentsByOrderIdLoader(DataLoader):
    context_key = "wms_documents_by_order"

    def batch_load(self, keys):
        wms_documents = (
            WmsDocument.objects.using(self.database_connection_name)
            .filter(order_id__in=keys)
            .order_by("pk")
        )
        wms_documents_map = defaultdict(list)
        for wms_document in wms_documents.iterator():
            wms_documents_map[wms_document.order_id].append(wms_document)
        return [wms_documents_map.get(order_id, []) for order_id in keys]
