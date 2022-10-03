from decimal import Decimal

from saleor.discount.utils import fetch_active_discounts
from saleor.payment.utils import price_to_minor_unit
from saleor.product.models import ProductVariant, ProductVariantChannelListing
from saleor.discount.models import OrderDiscount
from saleor.order.models import Order


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


def get_manual_discounts_for_order(order: Order) -> [OrderDiscount]:
    return OrderDiscount.objects.filter(order_id=order, type="manual")


def get_order_discount_position(name: str, value: Decimal):
    discount_position = {
        "type": "bill",
        "discount": {
            "na": name,
            "rd": "true",
            "rw": price_to_minor_unit(value=value, currency="PLN")
        }
    }
    return discount_position
