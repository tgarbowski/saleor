from dataclasses import dataclass
from typing import List

from saleor.plugins.base_plugin import BasePlugin, ConfigurationTypeField


PluginConfigurationType = List[dict]

@dataclass
class AllegroGlobalConfiguration:
    publication_starting_at: str
    auction_format: str
    interval_for_offer_publication: str
    offer_publication_chunks: str
    offer_description_footer: str


class AllegroGlobalPlugin(BasePlugin):
    PLUGIN_NAME = "Allegro global"
    PLUGIN_ID = "allegro_global"
    DEFAULT_ACTIVE = False
    PLUGIN_DESCRIPTION = ("Allegro global configuration")
    CONFIGURATION_PER_CHANNEL = False
    DEFAULT_CONFIGURATION = [
        {"name": "publication_starting_at", "value": ''},
        {"name": "auction_format", "value": 'AUCTION'},
        {"name": "interval_for_offer_publication", "value": '5'},
        {"name": "offer_publication_chunks", "value": '13'},
        {"name": "offer_description_footer", "value": ''}
    ]
    CONFIG_STRUCTURE = {
        "publication_starting_at": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "publication_starting_at w formacie %Y-%m-%d %H:%M (2020-09-02 20:00)",
            "label": "publication_starting_at",
        },
        "auction_format": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "AUCTION lub BUY_NOW",
            "label": "auction_format",
        },
        "interval_for_offer_publication": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Podaj liczbe minut co ile mają być publikowane oferty.",
            "label": "interval_for_offer_publication",
        },
        "offer_publication_chunks": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Podaj liczbe przedziałow w ktorych mają być publikowane oferty.",
            "label": "offer_publication_chunks",
        },
        "offer_description_footer": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Podaj tekst który będzie widoczny na dole opisu oferty.",
            "label": "offer_description_footer"
        }
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configuration = {item["name"]: item["value"] for item in self.configuration}
        self.config = AllegroGlobalConfiguration(
            publication_starting_at=configuration[
                "publication_starting_at"],
            auction_format=configuration[
                "auction_format"],
            interval_for_offer_publication=configuration[
                "interval_for_offer_publication"],
            offer_publication_chunks=configuration[
                "offer_publication_chunks"],
            offer_description_footer=configuration[
                "offer_description_footer"]
        )

    @classmethod
    def _append_config_structure(cls, configuration: PluginConfigurationType):
        """Append configuration structure to config from the database.

        Database stores "key: value" pairs, the definition of fields should be declared
        inside of the plugin. Based on this, the plugin will generate a structure of
        configuration with current values and provide access to it via API.
        """
        config_structure = getattr(cls, "CONFIG_STRUCTURE") or {}

        for configuration_field in configuration:

            structure_to_add = config_structure.get(configuration_field.get("name"))
            if structure_to_add:
                configuration_field.update(structure_to_add)
