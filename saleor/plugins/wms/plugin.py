from ..base_plugin import BasePlugin, ConfigurationTypeField


class WMSPlugin(BasePlugin):
    PLUGIN_NAME = "WMS"
    PLUGIN_ID = "WMS"
    DEFAULT_ACTIVE = True
    DEFAULT_CONFIGURATION = [
        {"name": "Goods received note (GRN)", "value": None, "label": "Goods received note (GRN)"}
    ]
    PLUGIN_DESCRIPTION = (
        "Warehouse management system plugin"
    )
    CONFIG_STRUCTURE = {
        "asd": {
            "type": ConfigurationTypeField.STRING,
            "label": "asd.",
        }
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    '''
    @staticmethod
    def get_configuration():
        manager = get_plugins_manager()
        plugin = manager.get_plugin(WMSPlugin.PLUGIN_ID)
        configuration = {item["name"]: item["value"] for item in plugin.configuration}
        return configuration
    '''
