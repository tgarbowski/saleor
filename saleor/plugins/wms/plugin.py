from dataclasses import dataclass

from ..base_plugin import BasePlugin, ConfigurationTypeField


@dataclass
class WMSConfiguration:
    GRN: str
    GIN: str
    IWM: str
    FGTN: str
    IO: str


class WMSPlugin(BasePlugin):
    PLUGIN_NAME = "WMS"
    PLUGIN_ID = "WMS"
    DEFAULT_ACTIVE = True
    DEFAULT_CONFIGURATION = [
        {"name": "GRN", "value": "GRN"},
        {"name": "GIN", "value": "GIN"},
        {"name": "IWM", "value": "IWM"},
        {"name": "FGTN", "value": "FGTN"},
        {"name": "IO", "value": "IO"}
    ]
    PLUGIN_DESCRIPTION = (
        "Warehouse management system plugin"
    )
    CONFIG_STRUCTURE = {
        "GRN": {
            "type": ConfigurationTypeField.STRING,
            "label": "Goods received note (GRN) eg. PZ",
        },
        "GIN": {
            "type": ConfigurationTypeField.STRING,
            "label": "Goods issued note (GIN) eg: WZ",
        },
        "IWM": {
            "type": ConfigurationTypeField.STRING,
            "label": "Internal warehouse movement (IWM) eg: MM",
        },
        "FGTN": {
            "type": ConfigurationTypeField.STRING,
            "label": "Finished goods transfer note (FGTN) eg: PW",
        },
        "IO": {
            "type": ConfigurationTypeField.STRING,
            "label": "Internal outgoings (IO) eg: RW",
        }
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configuration = {item["name"]: item["value"] for item in self.configuration}
