from .tasks import synchronize_allegro_offers_task
from saleor.plugins.base_plugin import BasePlugin
from saleor.plugins.models import PluginConfiguration


class AllegroSyncPlugin(BasePlugin):
    PLUGIN_ID = "allegroSync"
    PLUGIN_NAME = "AllegroSync"
    PLUGIN_NAME_2 = "AllegroSync"
    META_CODE_KEY = "AllegroSyncPlugin.code"
    META_DESCRIPTION_KEY = "AllegroSyncPlugin.description"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def save_plugin_configuration(cls, plugin_configuration: "PluginConfiguration",
                                  cleaned_data):

        current_config = plugin_configuration.configuration

        configuration_to_update = cleaned_data.get("configuration")

        if configuration_to_update:
            cls._update_config_items(configuration_to_update, current_config)
        if "active" in cleaned_data:
            plugin_configuration.active = cleaned_data["active"]
        cls.validate_plugin_configuration(plugin_configuration)
        plugin_configuration.save()
        if plugin_configuration.configuration:
            # Let's add a translated descriptions and labels
            cls._append_config_structure(plugin_configuration.configuration)

        return plugin_configuration

    def synchronize_allegro_offers(self):
        synchronize_allegro_offers_task.delay()
