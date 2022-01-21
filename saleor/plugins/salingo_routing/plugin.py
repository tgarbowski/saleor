from django.core.exceptions import ValidationError

from saleor.plugins.base_plugin import BasePlugin
from saleor.plugins.error_codes import PluginErrorCode
from saleor.plugins.models import PluginConfiguration
from saleor.salingo.business_rules import (
    DEFAULT_BUSINESS_RULES_CONFIGURATION, DEFAULT_BUSINESS_RULES_CONFIG_STRUCTURE,
    BusinessRulesConfiguration, BusinessRulesEvaluator)


class SalingoRoutingPlugin(BasePlugin):
    PLUGIN_NAME = "Salingo routing"
    PLUGIN_ID = "salingo_routing"
    DEFAULT_ACTIVE = False
    PLUGIN_DESCRIPTION = ("Salingo routing configuration")
    DEFAULT_CONFIGURATION = DEFAULT_BUSINESS_RULES_CONFIGURATION
    CONFIG_STRUCTURE = DEFAULT_BUSINESS_RULES_CONFIG_STRUCTURE

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configuration = {item["name"]: item["value"] for item in self.configuration}

        self.config = BusinessRulesConfiguration(
            ruleset=configuration["ruleset"],
            execute_order=configuration["execute_order"],
            resolver=configuration["resolver"],
            executor=configuration["executor"]
        )

    @classmethod
    def validate_plugin_configuration(self, plugin_configuration: "PluginConfiguration"):
        config = plugin_configuration.configuration
        configuration = {item["name"]: item["value"] for item in config}
        yaml_rules = configuration['rules']
        engine_rules = BusinessRulesEvaluator.get_rules(yaml_rules)

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
