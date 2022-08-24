from saleor.plugins.base_plugin import ConfigurationTypeField


DEFAULT_BUSINESS_RULES_CONFIGURATION = [
    {"name": "ruleset", "value": ""},
    {"name": "execute_order", "value": ""},
    {"name": "resolver", "value": ""},
    {"name": "executor", "value": ""},
    {"name": "rules", "value": ""}
]


DEFAULT_BUSINESS_RULES_CONFIG_STRUCTURE = {
    "ruleset": {
        "type": ConfigurationTypeField.STRING,
        "label": "Ruleset"
    },
    "execute_order": {
        "type": ConfigurationTypeField.STRING,
        "label": "Execute order"
    },
    "resolver": {
        "type": ConfigurationTypeField.STRING,
        "label": "Resolver"
    },
    "executor": {
        "type": ConfigurationTypeField.STRING,
        "label": "Executor"
    },
    "rules": {
        "type": ConfigurationTypeField.MULTILINE,
        "label": "Rules"
    }
}
