from dataclasses import dataclass
from decimal import Decimal

from saleor.plugins.base_plugin import BasePlugin, ConfigurationTypeField


@dataclass
class SalingoPricingGlobalConfig:
    price_per_kg: Decimal = None
    type_pricing: str = None
    brand_pricing: str = None
    material_pricing: str = None
    condition_pricing: str = None


class SalingoPricingGlobalPlugin(BasePlugin):
    PLUGIN_NAME = "Salingo pricing global"
    PLUGIN_ID = "salingo_pricing_global"
    DEFAULT_ACTIVE = True
    PLUGIN_DESCRIPTION = ("Salingo pricing global configuration")
    CONFIGURATION_PER_CHANNEL = False

    DEFAULT_CONFIGURATION = [
        {"name": "price_per_kg", "value": ""},
        {"name": "minimum_price", "value": ""},
        {"name": "type_pricing", "value": ""},
        {"name": "brand_pricing", "value": ""},
        {"name": "material_pricing", "value": ""},
        {"name": "condition_pricing", "value": ""}
    ]

    CONFIG_STRUCTURE = {
        "price_per_kg": {
            "type": ConfigurationTypeField.STRING,
            "label": "Price per kg"
        },
        "minimum_price": {
            "type": ConfigurationTypeField.STRING,
            "label": "Minimum price"
        },
        "type_pricing": {
            "type": ConfigurationTypeField.MULTILINE,
            "label": "Product type pricing"
        },
        "brand_pricing": {
            "type": ConfigurationTypeField.MULTILINE,
            "label": "Brand pricing"
        },
        "material_pricing": {
            "type": ConfigurationTypeField.MULTILINE,
            "label": "Material pricing"
        },
        "condition_pricing": {
            "type": ConfigurationTypeField.MULTILINE,
            "label": "Condition pricing"
        }
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        configuration = {item["name"]: item["value"] for item in self.configuration}

        self.config = SalingoPricingGlobalConfig(
            price_per_kg=configuration["price_per_kg"],
            minimum_price=configuration["minimum_price"],
            type_pricing=configuration["type_pricing"],
            brand_pricing=configuration["brand_pricing"],
            material_pricing=configuration["material_pricing"],
            condition_pricing=configuration["condition_pricing"],
        )
