import zeep
from zeep.exceptions import Fault

from saleor.plugins.manager import get_plugins_manager


class GlsApi():
    client = None
    service = None
    factory = None
    config = None

    def __init__(self):
        self.set_config()
        self.init_zeep()
        self.session_id = self.create_session()

    def set_config(self):
        self.config = get_gls_config()

    def init_zeep(self):
        self.client = zeep.Client(self.config.api_url)
        self.factory = self.client.type_factory('ns0')
        self.service = self.client.service

    def create_session(self) -> str:
        """Returns session id"""
        try:
            session_id = self.service.adeLogin(
                self.config.username,
                self.config.password
            )
            return session_id
        except Exception as e:
            print(e.code)

    def generate_package_shipment(self, payload) -> int:
        """Returns package id"""
        try:
            package = self.service.adePreparingBox_Insert(self.session_id, payload)
            return package
        except Fault as e:
            print(e.code)

    def generate_label(self, number, mode) -> str:
        """Returns label as b64 string"""
        try:
            label = self.service.adePreparingBox_GetConsignLabels(self.session_id, number, mode)
            return label
        except Fault as e:
            print(e.code)


def get_gls_config():
    manager = get_plugins_manager()
    config = manager.get_plugin(plugin_id='Gls').config
    return config

