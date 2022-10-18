from dataclasses import asdict

import requests

from .interface import InpostPackage
from saleor.plugins.manager import get_plugins_manager


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
        api_url = self.config.get('api_url')
        access_token = self.config.get('access_token')

        url = f'{api_url}shipments/{shipment_id}/label?format=zpl'
        headers = {"Authorization": f'Bearer {access_token}'}
        response = requests.get(url=url, headers=headers)
        if response.status_code == 200:
            return response.content
        else:
            return response.json()

    def create_package(self, package: InpostPackage):
        organization_id = self.config.get('organization_id')
        access_token = self.config.get('access_token')
        api_url = self.config.get('api_url')

        url = f'{api_url}organizations/{organization_id}/shipments'
        headers = {"Authorization": f'Bearer {access_token}'}
        payload = asdict(package)
        response = requests.post(url=url, headers=headers, json=payload)

        return response.json()

    def get_package(self, package_id: str):
        access_token = self.config.get('access_token')
        api_url = self.config.get('api_url')

        url = f'{api_url}shipments/{package_id}'
        headers = {"Authorization": f'Bearer {access_token}'}

        response = requests.get(url=url, headers=headers)
        return response.json()
