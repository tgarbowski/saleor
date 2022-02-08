from typing import List

from saleor.plugins.base_plugin import BasePlugin


PluginConfigurationType = List[dict]

class AllegroGlobalPlugin(BasePlugin):
    PLUGIN_NAME = "Allegro global"
    PLUGIN_ID = "allegro_global"
    DEFAULT_ACTIVE = False
    PLUGIN_DESCRIPTION = ("Allegro global configuration")
    CONFIGURATION_PER_CHANNEL = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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
