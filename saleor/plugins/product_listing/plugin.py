from ...order.models import Order, OrderLine
from ...product.models import ProductChannelListing, ProductVariant, Product
from ..base_plugin import BasePlugin
from ...warehouse.models import Stock


class ProductListingPlugin(BasePlugin):
    PLUGIN_ID = "product_listing"
    PLUGIN_NAME = "Product listing"
    DEFAULT_ACTIVE = True
    PLUGIN_DESCRIPTION = "Plugin for updating product visibility in product listing"
    CONFIGURATION_PER_CHANNEL = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


    def order_created(self, order: "Order", previous_value):
        order_lines = OrderLine.objects.filter(order=order)
        variant_ids = [order_line.variant_id for order_line in order_lines]
        variants = ProductVariant.objects.filter(pk__in=variant_ids).annotate_quantities()
        sold_variants = [variant.id for variant in variants
                         if variant.quantity == variant.quantity_allocated]
        product_ids = list(ProductVariant.objects.filter(pk__in=sold_variants).
                           values_list('product_id', flat=True))
        ProductChannelListing.objects.filter(product_id__in=product_ids).\
            update(visible_in_listings=False)



    def order_cancelled(self, order: "Order", previous_value):
        order_lines = OrderLine.objects.filter(order=order)
        variant_ids = [order_line.variant_id for order_line in order_lines]
        product_ids = list(ProductVariant.objects.filter(pk__in=variant_ids).
                           values_list('product_id', flat=True))
        ProductChannelListing.objects.filter(product_id__in=product_ids).\
            update(visible_in_listings=True)
