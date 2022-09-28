from prices import Money
import pytest

from saleor.app.models import App, AppToken
from saleor.discount.models import Voucher, VoucherType, VoucherChannelListing
from saleor.shipping.models import ShippingMethod, ShippingMethodChannelListing, ShippingMethodType
from saleor.order.models import Order, OrderOrigin
from saleor.graphql.tests.fixtures import ApiClient


@pytest.fixture
def smart_voucher(channel_USD):
    voucher = Voucher.objects.create(
        name='SMART',
        code="unique",
        type=VoucherType.SHIPPING,
        discount_value_type='percentage',
        apply_once_per_order=False
    )
    VoucherChannelListing.objects.create(
        voucher=voucher,
        channel=channel_USD,
        discount=Money(100, channel_USD.currency_code),
    )


@pytest.fixture
def external_order_app(db, permission_manage_orders):
    app = App.objects.create(name="orders", is_active=True)
    app.tokens.create(name="Default")
    app.permissions.add(permission_manage_orders)
    return app


@pytest.fixture
def allegro_shipping_method(shipping_zone, channel_USD):
    """allegro shipping method name in metadata"""
    method = ShippingMethod.objects.create(
        name="DHL",
        type=ShippingMethodType.PRICE_BASED,
        shipping_zone=shipping_zone,
        maximum_delivery_days=10,
        minimum_delivery_days=5,
        metadata={"allegro_name": "DHL"}
    )
    ShippingMethodChannelListing.objects.create(
        shipping_method=method,
        channel=channel_USD,
        minimum_order_price=Money(0, "USD"),
        price=Money(10, "USD"),
    )
    return method


@pytest.fixture
def allegro_order(customer_user, channel_USD):
    address = customer_user.default_billing_address.get_copy()
    order = Order.objects.create(
        billing_address=address,
        channel=channel_USD,
        currency=channel_USD.currency_code,
        shipping_address=address,
        user_email=customer_user.email,
        user=customer_user,
        origin=OrderOrigin.CHECKOUT,
        metadata={"allegro_order_id": "29738e61-7f6a-11e8-ac45-09db60ede9d6"}
    )
    return order


@pytest.fixture
def order_app_api_client(external_order_app):
    return ApiClient(app=external_order_app)
