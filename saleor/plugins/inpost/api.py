import requests

from .interface import InpostShipment
from saleor.plugins.manager import get_plugins_manager
from dataclasses import asdict


class InpostApi:
    def __init__(self):
        self.config = self.__get_plugin_config()

    def __get_plugin_config(self):
        manager = get_plugins_manager()
        plugin = manager.get_plugin(plugin_id='Inpost')
        configuration = {item["name"]: item["value"] for item in plugin.configuration if
                         plugin.configuration}
        return configuration

    def get_label(self, shipment_id):
        url = f'{self.config.api_url}shipments/{shipment_id}/label'
        headers = {"Authorization": f'Bearer {self.config.access_token}'}
        response = requests.get(url=url, headers=headers)
        return response

    def create_package(self, package: InpostShipment):
        organization_id = self.config.get('organization_id')
        access_token = self.config.get('access_token')
        api_url = self.config.get('api_url')

        url = f'{api_url}organizations/{organization_id}/shipments'
        headers = {"Authorization": f'Bearer {access_token}'}
        payload = asdict(package)
        response = requests.post(url=url, headers=headers, json=payload)

        return response.json()
