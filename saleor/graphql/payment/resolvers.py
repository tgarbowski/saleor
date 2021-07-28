from .types import PaymentUrl
from ..core.utils import from_global_id_strict_type
from ..checkout.types import Checkout
from ...payment import gateway as payment_gateway, models
from ...payment.utils import fetch_customer_id
from ..utils.filters import filter_by_query_param
from ...plugins.manager import get_plugins_manager
from ...payment.gateways.payu.utils import generate_payu_redirect_url
from ...payment.utils import create_payment_information

PAYMENT_SEARCH_FIELDS = ["id"]


def resolve_client_token(user, gateway: str):
    customer_id = fetch_customer_id(user, gateway)
    return payment_gateway.get_client_token(gateway, customer_id)


def resolve_payments(info, query):
    queryset = models.Payment.objects.all().distinct()
    return filter_by_query_param(queryset, query, PAYMENT_SEARCH_FIELDS)


def resolve_generate_payment_url(info, **kwargs):
    checkout_id = from_global_id_strict_type(
        kwargs["checkout_id"], only_type=Checkout, field="checkout_id"
    )

    payment = models.Payment.objects.filter(checkout=checkout_id).first()
    manager = get_plugins_manager()
    plugin = manager.get_plugin(payment.gateway)
    config = plugin.get_payment_connection_params(plugin.configuration)
    redirect_url = generate_payu_redirect_url(config,
                                              create_payment_information(payment),
                                              checkout_id)
    return PaymentUrl(payment_url=redirect_url)
