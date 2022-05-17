from dataclasses import dataclass

from ..base_plugin import BasePlugin, ConfigurationTypeField


@dataclass
class PrintserversConfiguration:
    label_url: str
    receipt_url: str


class PrintserversPlugin(BasePlugin):
    PLUGIN_ID = "printservers"
    PLUGIN_NAME = "Printservers"
    DEFAULT_ACTIVE = True
    PLUGIN_DESCRIPTION = "Plugin for print servers configuration"
    CONFIGURATION_PER_CHANNEL = False
    DEFAULT_CONFIGURATION = [{"name": "label_url",
                              "value": ""},
                             {"name": "receipt_url",
                              "value": ""}]

    CONFIG_STRUCTURE = {
        "label_url": {
            "type": ConfigurationTypeField.STRING,
            "label": "Label print server url",
        },
        "receipt_url": {
            "type": ConfigurationTypeField.STRING,
            "label": "Receipt print server url",
        }}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        configuration = {item["name"]: item["value"] for item in self.configuration}

        self.config = PrintserversConfiguration(
            label_url=configuration["label_url"],
            receipt_url=configuration["receipt_url"])
