import json
import locale
import decimal

import requests
from requests.structures import CaseInsensitiveDict


def generate_authorization_token(config):

    credentials_url = f'{config.connection_params["api_url"]}/pl/standard/user/oauth/authorize'

    headers = CaseInsensitiveDict()
    headers["Content-Type"] = "application/x-www-form-urlencoded"

    credentials = f'grant_type=client_credentials&client_id={config.connection_params["pos_id"]}' \
                  f'&client_secret={config.connection_params["md5"]}'

    credentials_response = requests.post(credentials_url, headers=headers,
                                         data=credentials)

    authorization_token = json.loads(credentials_response.content.decode("utf-8"))
    return authorization_token


def calculate_price_to_payu(price: decimal.Decimal):
    payu_price = str(price * decimal.Decimal(100))
    price, separator, tailed_amount = payu_price.partition('.')
    return price
