from decimal import Decimal

from measurement.measures import Weight
from pytest import approx

from saleor.salingo.business_rules import PricingExecutors
from saleor.salingo.megapack import Megapack
from saleor.product.models import Product, ProductChannelListing, ProductVariantChannelListing, ProductVariant
from saleor.channel.models import Channel


def test_calculate_price_weight_mode():
    validated_pricing_variables = PricingExecutors.get_validated_pricing_variables(
        current_price=Decimal(1.00),
        weight=Weight(kg=2),
        result='k12.40'
    )

    price = PricingExecutors.calculate_price(validated_pricing_variables)

    assert price == approx(Decimal(24.80))


def test_calculate_price_weight_null():
    validated_pricing_variables = PricingExecutors.get_validated_pricing_variables(
        current_price=Decimal(1.00),
        weight=None,
        result='k12.40'
    )

    assert validated_pricing_variables is None


def test_calculate_price_discount_mode():
    validated_pricing_variables = PricingExecutors.get_validated_pricing_variables(
        current_price=Decimal(10.00),
        weight=Weight(kg=2),
        result='d10'
    )

    price = PricingExecutors.calculate_price(validated_pricing_variables)

    assert price == approx(Decimal(9.00))


def test_calculate_price_item_mode():
    validated_pricing_variables = PricingExecutors.get_validated_pricing_variables(
        current_price=Decimal(25.99),
        weight=Weight(kg=2),
        result='i25.99'
    )

    price = PricingExecutors.calculate_price(validated_pricing_variables)

    assert price == approx(Decimal(25.99))


def test_megapack(product, product_type, category):
    megapack_product = Product.objects.create(
        name="Test product",
        slug="test-megapack-11",
        product_type=product_type,
        category=category,
    )
    variant = ProductVariant.objects.create(product=megapack_product, sku="asdasd")
    bundled_channel = Channel.objects.create(
        name="bundled",
        slug='bundled',
        currency_code="USD",
        default_country="US",
        is_active=True,
    )

    megapack = Megapack(megapack=megapack_product, megapack_sku='asdasd')
    megapack.create(['123'])

    assigned_variant = ProductVariant.objects.get(sku='123')
    product.refresh_from_db()
    megapack_product.refresh_from_db()


    assert product.get_value_from_metadata('bundle.id') == 'asdasd'
    assert ProductChannelListing.objects.filter(product=product, channel__slug='bundled').exists()
    assert ProductVariantChannelListing.objects.filter(variant=assigned_variant, channel__slug='bundled').exists()

    assert not ProductChannelListing.objects.filter(
        product=product,
        channel__name='Main Channel'
    ).exists()

    assert not ProductVariantChannelListing.objects.filter(
        variant=assigned_variant,
        channel__name='Main Channel'
    ).exists()

    skus = megapack_product.get_value_from_private_metadata('skus')
    assert assigned_variant.sku in skus

