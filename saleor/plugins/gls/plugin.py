from dataclasses import dataclass

from ..base_plugin import BasePlugin, ConfigurationTypeField


@dataclass
class GlsConfiguration:
    username: str
    password: str
    api_url: str


class GlsPlugin(BasePlugin):
    PLUGIN_NAME = "Gls"
    PLUGIN_ID = "Gls"
    DEFAULT_ACTIVE = False
    CONFIGURATION_PER_CHANNEL = False
    DEFAULT_CONFIGURATION = [
        {"name": "Username", "value": None},
        {"name": "Password", "value": None},
        {"name": "Api url", "value": None},
    ]
    PLUGIN_DESCRIPTION = (
        "Gls service integration"
    )
    CONFIG_STRUCTURE = {
        "Username": {
            "type": ConfigurationTypeField.STRING,
            "label": "Username",
        },
        "Password": {
            "type": ConfigurationTypeField.SECRET,
            "label": "Password",
        },
        "Api url": {
            "type": ConfigurationTypeField.STRING,
            "label": "Api url",
        },
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configuration = {item["name"]: item["value"] for item in self.configuration}
        self.config = GlsConfiguration(
            username=configuration["Username"],
            password=configuration["Password"],
            api_url=configuration["Api url"],
        )
