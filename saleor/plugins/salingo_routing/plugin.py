from saleor.salingo.business_rules import BusinessRulesBasePlugin


class SalingoRoutingPlugin(BusinessRulesBasePlugin):
    PLUGIN_NAME = "Salingo routing"
    PLUGIN_ID = "salingo_routing"
    DEFAULT_ACTIVE = False
    DEFAULT_CONFIGURATION = []
    PLUGIN_DESCRIPTION = ("Salingo routing configuration")
    # CONFIGURATION_PER_CHANNEL = True
    CONFIG_STRUCTURE = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
