import logging
from typing import Dict

import zeep

from saleor.plugins.manager import get_plugins_manager


logger = logging.getLogger(__name__)


class GlsApi():
    client = None
    service = None
    factory = None
    config = None

    def __init__(self):
        self._set_config()
        self._init_zeep()
        self.session_id = self._create_session()

    def _set_config(self):
        self.config = get_gls_config()

    def _init_zeep(self):
        self.client = zeep.Client(self.config.api_url)
        self.factory = self.client.type_factory('ns0')
        self.service = self.client.service

    def _create_session(self) -> str:
        """Returns session id"""
        return self.service.adeLogin(
            self.config.username,
            self.config.password
        )

    def generate_package_shipment(self, payload) -> int:
        """Returns package id"""
        return self.service.adePreparingBox_Insert(self.session_id, payload)

    def generate_label(self, number, mode) -> str:
        """Returns label as b64 string"""
        return self.service.adePreparingBox_GetConsignLabels(self.session_id, number, mode)

    def get_packages(self, id_start=0):
        """Returns packages info"""
        return self.service.adePreparingBox_GetConsignIDs(self.session_id, id_start)

    def get_package(self, package_id) -> Dict:
        """Returns package info"""
        return self.service.adePreparingBox_GetConsign(self.session_id, package_id)


def get_gls_config():
    manager = get_plugins_manager()
    config = manager.get_plugin(plugin_id='Gls').config
    return config

