from saleor.salingo.business_rules import BusinessRulesBasePlugin


class SalingoPricingPlugin(BusinessRulesBasePlugin):
    PLUGIN_NAME = "Salingo pricing"
    PLUGIN_ID = "salingo_pricing"
    DEFAULT_ACTIVE = False
    PLUGIN_DESCRIPTION = ("Salingo pricing configuration")
    # CONFIGURATION_PER_CHANNEL = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
