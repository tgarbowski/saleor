import json
from json.decoder import JSONDecodeError

import requests

from django.core.handlers.wsgi import WSGIRequest
from django.http import HttpResponse

def handle_webhook(request: WSGIRequest, gateway_config: "GatewayConfig"):
    try:
        json_data = json.loads(request.body)
    except JSONDecodeError:
        return HttpResponse(status=400)

    shipment_id = json_data.get("shipment_id")
    inpost_api = InpostApi(config=gateway_config)
    return inpost_api.get_label(shipment_id=shipment_id)


class InpostApi:
    def __init__(self, config):
        self.config = config

    def get_label(self, shipment_id):
        url = f'{self.config.api_url}shipments/{shipment_id}/label'
        headers = {"Authorization": f'Bearer {self.config.access_token}'}
        response = requests.get(url=url, headers=headers)
        return response
