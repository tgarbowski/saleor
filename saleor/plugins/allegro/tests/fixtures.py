from prices import Money
import pytest

from saleor.app.models import App, AppToken
from saleor.discount.models import Voucher, VoucherType, VoucherChannelListing


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
def external_order_app(permission_manage_orders):
    app = App.objects.create(name="orders", is_active=True)
    AppToken.objects.create(name='asd', auth_token='asd', app_id=app.pk)
    app.permissions.add(permission_manage_orders)
