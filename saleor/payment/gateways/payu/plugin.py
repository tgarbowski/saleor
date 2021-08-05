import logging
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.handlers.wsgi import WSGIRequest
from django.http import HttpResponse, HttpResponseNotFound

from saleor.plugins.base_plugin import BasePlugin, ConfigurationTypeField
from ..utils import get_supported_currencies
from .utils import get_client_token
from . import GatewayConfig, process_payment


logger = logging.getLogger(__name__)

GATEWAY_NAME = "PayU"
WEBHOOK_PATH = "/webhooks"
ADDITIONAL_ACTION_PATH = "/additional-actions"

from .webhooks import handle_webhook

if TYPE_CHECKING:
    from ...interface import GatewayResponse, PaymentData, TokenConfig


def require_active_plugin(fn):
    def wrapped(self, *args, **kwargs):
        previous = kwargs.get("previous_value", None)
        if not self.active:
            return previous
        return fn(self, *args, **kwargs)

    return wrapped


class PayuGatewayPlugin(BasePlugin):
    PLUGIN_ID = "salingo.payments.payu"
    PLUGIN_NAME = GATEWAY_NAME
    DEFAULT_ACTIVE = True
    DEFAULT_CONFIGURATION = [
        {"name": "PayUEndpoint", "value": None},
        {"name": "Store customers card", "value": False},
        {"name": "Automatic payment capture", "value": True},
        {"name": "Supported currencies", "value": settings.DEFAULT_CURRENCY},
        {"name": "Public API key", "value": None},
        {"name": "Secret API key", "value": None},
        {"name": "Continue URL", "value": None},
        {"name": "Second MD5 key", "value": None},
        {"name": "Notify URL", "value": None},
    ]
    CONFIG_STRUCTURE = {
        "PayUEndpoint": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Determines which payu version to use.",
            "label": "API URL",
        },
        "Store customers card": {
            "type": ConfigurationTypeField.BOOLEAN,
            "help_text": "Determines if Saleor should store cards.",
            "label": "Store customers card",
        },
        "Automatic payment capture": {
            "type": ConfigurationTypeField.BOOLEAN,
            "help_text": "Determines if Saleor should automaticaly capture payments.",
            "label": "Automatic payment capture",
        },
        "Supported currencies": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Determines currencies supported by gateway."
            " Please enter currency codes separated by a comma.",
            "label": "Supported currencies",
        },
        "Continue URL": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Determines url to redirect after payment execution",
            "label": "Continue URL"
        },
        "Notify URL": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Determines url to receive notifications",
            "label": "Notify URL"
        },
        "Public API key": {
            "type": ConfigurationTypeField.SECRET,
            "help_text": "Provide  public API key.",
            "label": "Id punktu płatności",
        },
        "Secret API key": {
            "type": ConfigurationTypeField.SECRET,
            "help_text": "Provide Stripe secret API key.",
            "label": "Client Secret",
        },
        "Second MD5 key": {
            "type": ConfigurationTypeField.SECRET,
            "help_text": "Provide Payu second MD5 key.",
            "label": "Second MD5 key",
        },
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configuration = {item["name"]: item["value"] for item in self.configuration}
        self.config = GatewayConfig(
            gateway_name=GATEWAY_NAME,
            auto_capture=configuration["Automatic payment capture"],
            supported_currencies=configuration["Supported currencies"],
            connection_params={
                "pos_id": configuration["Public API key"],
                "md5": configuration["Secret API key"],
                "continue_url": configuration["Continue URL"],
                "notify_url": configuration["Notify URL"],
                "api_url": configuration["PayUEndpoint"],
                "second_md5": configuration["Second MD5 key"]
            },
            store_customer=configuration["Store customers card"]
        )


    def webhook(self, request: WSGIRequest, path: str, previous_value) -> HttpResponse:
        config = self._get_gateway_config()
        if path.startswith(WEBHOOK_PATH):
            return handle_webhook(request, config)
        return HttpResponseNotFound()

    def _get_gateway_config(self):
        return self.config
    '''
    @require_active_plugin
    def authorize_payment(
        self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        raise NotImplementedError()

    @require_active_plugin
    def capture_payment(
        self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        raise NotImplementedError()

    @require_active_plugin
    def confirm_payment(
        self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        raise NotImplementedError()

    @require_active_plugin
    def refund_payment(
        self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        raise NotImplementedError()

    @require_active_plugin
    def void_payment(
        self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        raise NotImplementedError()
    '''
    @require_active_plugin
    def process_payment(
        self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        return process_payment(payment_information, self._get_gateway_config())

    @require_active_plugin
    def get_client_token(self, token_config: "TokenConfig", previous_value):
        return get_client_token()

    @require_active_plugin
    def get_supported_currencies(self, previous_value):
        config = self._get_gateway_config()
        return get_supported_currencies(config, GATEWAY_NAME)

    @require_active_plugin
    def get_payment_config(self, previous_value):
        config = self._get_gateway_config()
        connection_params = []
        for name, value in config.connection_params.items():
            connection_params.append({"field": name, "value": value})
        return [{"field": "store_customer_card", "value": config.store_customer}] + connection_params

    @require_active_plugin
    def get_payment_connection_params(self, previous_value):
        return self._get_gateway_config()

    @require_active_plugin
    def token_is_required_as_payment_input(self, previous_value):
        return False
