from decimal import Decimal

from saleor.discount.utils import fetch_active_discounts
from saleor.product.models import ProductVariant, ProductVariantChannelListing


def get_variant_discounted_price(variant_id: int) -> Decimal:
    product_variant = ProductVariant.objects.get(pk=variant_id)
    pvcl = ProductVariantChannelListing.objects.get(variant=product_variant)
    discounts = fetch_active_discounts()

    discounted = product_variant.get_price(
        product=product_variant.product,
        collections=[],
        channel=pvcl.channel,
        channel_listing=pvcl,
        discounts=discounts
    )

    return discounted.amount.quantize(Decimal('.01'))
