import logging

from django.conf import settings

from saleor.plugins.base_plugin import BasePlugin, ConfigurationTypeField
from ..utils import get_supported_currencies
from ... import TransactionKind
from ...interface import GatewayConfig, GatewayResponse, PaymentData
from saleor.payment.interface import PaymentMethodInfo
from saleor.checkout.models import Checkout


logger = logging.getLogger(__name__)

GATEWAY_NAME = "Cod"


def require_active_plugin(fn):
    def wrapped(self, *args, **kwargs):
        previous = kwargs.get("previous_value", None)
        if not self.active:
            return previous
        return fn(self, *args, **kwargs)

    return wrapped


class CodGatewayPlugin(BasePlugin):
    """Cash on delivery"""
    PLUGIN_ID = "salingo.payments.cod"
    PLUGIN_NAME = GATEWAY_NAME
    DEFAULT_ACTIVE = False
    DEFAULT_CONFIGURATION = [
        {"name": "Store customers card", "value": False},
        {"name": "Automatic payment capture", "value": False},
        {"name": "Supported currencies", "value": settings.DEFAULT_CURRENCY}
    ]
    CONFIG_STRUCTURE = {
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
        }
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configuration = {item["name"]: item["value"] for item in self.configuration}
        self.config = GatewayConfig(
            gateway_name=GATEWAY_NAME,
            auto_capture=configuration["Automatic payment capture"],
            supported_currencies=configuration["Supported currencies"],
            connection_params={},
            store_customer=configuration["Store customers card"]
        )

    def _get_gateway_config(self):
        return self.config

    @require_active_plugin
    def process_payment(
        self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        checkout_token = payment_information.checkout_token
        checkout = Checkout.objects.get(token=checkout_token)
        shipping_method = checkout.shipping_method

        is_cod = shipping_method.get_value_from_metadata("cod")
        is_success = True if is_cod else False

        customer_name = "{} {}".format(
            payment_information.billing.first_name,
            payment_information.billing.last_name,
        )
        response = GatewayResponse(
            is_success=is_success,
            action_required=False,
            kind=TransactionKind.CAPTURE,
            amount=payment_information.amount,
            currency=payment_information.currency,
            transaction_id=payment_information.token or "",
            error=None,
            payment_method_info=PaymentMethodInfo(
                name=customer_name,
                type=self.PLUGIN_ID,
            ),
        )
        return response

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
