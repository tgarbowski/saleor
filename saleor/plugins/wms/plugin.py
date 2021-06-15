from ..base_plugin import BasePlugin


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
