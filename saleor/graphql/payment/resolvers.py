from ..core.utils import from_global_id_or_error
from ...payment import models
from .types import PaymentUrl
from .types import Payment
from ...plugins.manager import get_plugins_manager
from ...payment.gateways.payu.utils import generate_payu_redirect_url
from ...payment.utils import create_payment_information


def resolve_payment_by_id(id):
    return models.Payment.objects.filter(id=id).first()


def resolve_payments(info):
    return models.Payment.objects.all()


def resolve_generate_payment_url(info, **kwargs):
    print(kwargs)
    value, payment_id = from_global_id_or_error(
        kwargs["payment_id"], only_type=Payment
    )
    payment = models.Payment.objects.filter(id=payment_id).first()
    manager = get_plugins_manager()
    plugin = manager.get_plugin(payment.gateway)
    config = plugin.get_payment_connection_params(plugin.configuration)
    redirect_url = generate_payu_redirect_url(config, create_payment_information(payment))
    return PaymentUrl(payment_url=redirect_url)
