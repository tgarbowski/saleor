from dataclasses import dataclass

from ..base_plugin import BasePlugin, ConfigurationTypeField


@dataclass
class DpdConfiguration:
    username: str
    password: str
    master_fid: str
    api_url: str


class DpdPlugin(BasePlugin):
    PLUGIN_NAME = "Dpd"
    PLUGIN_ID = "Dpd"
    DEFAULT_ACTIVE = True
    DEFAULT_CONFIGURATION = [
        {"name": "Username", "value": None},
        {"name": "Password", "value": None},
        {"name": "Master FID", "value": None},
        {"name": "Api url", "value": None},
    ]
    PLUGIN_DESCRIPTION = (
        "DPD service integration"
    )
    CONFIG_STRUCTURE = {
        "Username": {
            "type": ConfigurationTypeField.STRING,
            "label": "Username",
        },
        "Password": {
            "type": ConfigurationTypeField.STRING,
            "label": "Password",
        },
        "Master FID": {
            "type": ConfigurationTypeField.STRING,
            "label": "Master FID",
        },
        "Api url": {
            "type": ConfigurationTypeField.STRING,
            "label": "Api url",
        },
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configuration = {item["name"]: item["value"] for item in self.configuration}
        self.config = DpdConfiguration(
            username=configuration["Username"],
            password=configuration["Password"],
            master_fid=configuration["Master FID"],
            api_url=configuration["Api url"],
        )
