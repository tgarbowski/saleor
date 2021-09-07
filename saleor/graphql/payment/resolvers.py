from .types import PaymentUrl
from ..core.utils import from_global_id_or_error
from .types import Payment
from ...payment import gateway as payment_gateway, models
from ...payment.utils import fetch_customer_id
from ..utils.filters import filter_by_query_param
from ...plugins.manager import get_plugins_manager
from ...payment.gateways.payu.utils import generate_payu_redirect_url
from ...payment.utils import create_payment_information

PAYMENT_SEARCH_FIELDS = ["id"]

def resolve_payment_by_id(id):
    return models.Payment.objects.filter(id=id).first()

def resolve_client_token(user, gateway: str):
    customer_id = fetch_customer_id(user, gateway)
    return payment_gateway.get_client_token(gateway, customer_id)

def resolve_payments(info):
    return models.Payment.objects.all()


def resolve_generate_payment_url(info, **kwargs):
    payment_id = from_global_id_or_error(
        kwargs["payment_id"], only_type=Payment, field="payment_id"
    )

    payment = models.Payment.objects.filter(id=payment_id).first()
    manager = get_plugins_manager()
    plugin = manager.get_plugin(payment.gateway)
    config = plugin.get_payment_connection_params(plugin.configuration)
    redirect_url = generate_payu_redirect_url(config, create_payment_information(payment))
    return PaymentUrl(payment_url=redirect_url)
