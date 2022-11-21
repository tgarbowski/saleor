from .meta.schema import MetadataQueries
from .payment.schema import PaymentQueries
from .product.schema import ProductMutations, ProductQueries
from .shipping.schema import ShippingMutations
from .wms.schema import WmsDocumentMutations, WmsDocumentQueries, WmsDocPositionQueries, WmsDelivererQueries
from .csv.schema import CsvMutations
from .invoice.schema import InvoiceMutations


class ExternalQueries(
    MetadataQueries,
    PaymentQueries,
    ProductQueries,
    WmsDocumentQueries,
    WmsDocPositionQueries,
    WmsDelivererQueries
):
    pass


class ExternalMutations(
    ProductMutations,
    ShippingMutations,
    WmsDocumentMutations,
    CsvMutations,
    InvoiceMutations
):
    pass
