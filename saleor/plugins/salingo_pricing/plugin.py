from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import List

from django.core.exceptions import ValidationError

from saleor.salingo.business_rules import (
    BusinessRulesEvaluator, PriceEnum, BusinessRulesConfiguration, DEFAULT_BUSINESS_RULES_CONFIGURATION,
    DEFAULT_BUSINESS_RULES_CONFIG_STRUCTURE)
from saleor.plugins.error_codes import PluginErrorCode
from saleor.plugins.base_plugin import BasePlugin, ConfigurationTypeField
from saleor.plugins.models import PluginConfiguration


PluginConfigurationType = List[dict]


@dataclass
class SalingoPricingConfig(BusinessRulesConfiguration):
    price_per_kg: Decimal = None


class SalingoPricingPlugin(BasePlugin):
    PLUGIN_NAME = "Salingo pricing"
    PLUGIN_ID = "salingo_pricing"
    DEFAULT_ACTIVE = False
    PLUGIN_DESCRIPTION = ("Salingo pricing configuration")

    DEFAULT_CONFIGURATION = [
        {"name": "price_per_kg", "value": ""}
    ] + DEFAULT_BUSINESS_RULES_CONFIGURATION

    CONFIG_STRUCTURE = {
        "price_per_kg": {
            "type": ConfigurationTypeField.STRING,
            "label": "Price per kg"
        }
    }
    CONFIG_STRUCTURE.update(DEFAULT_BUSINESS_RULES_CONFIG_STRUCTURE)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        configuration = {item["name"]: item["value"] for item in self.configuration}

        self.config = SalingoPricingConfig(
            ruleset=configuration["ruleset"],
            execute_order=configuration["execute_order"],
            resolver=configuration["resolver"],
            executor=configuration["executor"],
            price_per_kg=configuration["price_per_kg"]
        )

    @classmethod
    def validate_plugin_configuration(self, plugin_configuration: "PluginConfiguration"):
        config = plugin_configuration.configuration
        yaml_rules = BusinessRulesEvaluator.get_value_by_name(config=config, name='rules')
        engine_rules = BusinessRulesEvaluator.get_rules(yaml_rules)
        prices = [rule['result'] for rule in engine_rules]

        for price in prices:
            self.validate_price(price)

        try:
            BusinessRulesEvaluator.validate_rules(engine_rules)
        except Exception as e:
            raise ValidationError(
                {
                    "rules": ValidationError(
                        "Invalid engine rule.",
                        code=PluginErrorCode.INVALID.value,
                    )
                }
            )

    @classmethod
    def validate_price(cls, price):
        if not isinstance(price, str):
            raise ValidationError(
                {
                    "rules": ValidationError(
                        "Invalid pricing result.",
                        code=PluginErrorCode.INVALID.value,
                    )
                }
            )

        try:
            result_price = Decimal(price[1:])
        except InvalidOperation:
            raise ValidationError(
                {
                    "rules": ValidationError(
                        "Invalid pricing result price.",
                        code=PluginErrorCode.INVALID.value,
                    )
                }
            )

        price_mode = price[:1]

        if price_mode not in [e.value for e in PriceEnum]:
            raise ValidationError(
                {
                    "rules": ValidationError(
                        "Invalid price mode.",
                        code=PluginErrorCode.INVALID.value,
                    )
                }
            )
