import json
import locale
import decimal

import requests
from requests.structures import CaseInsensitiveDict

from saleor.payment.interface import PaymentData


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


def generate_payu_redirect_url(config, payment_information: "PaymentData"):
    authorization_token = generate_authorization_token(config)
    url = f'{config.connection_params["api_url"]}/api/v2_1/orders'

    headers = CaseInsensitiveDict()
    headers["Content-Type"] = "application/json"
    headers["Accept"] = "application/json"
    headers["Authorization"] = f'Bearer {authorization_token["access_token"]}'
    data = {
        "notifyUrl": "https://your.eshop.com/notify",
        "customerIp": payment_information.customer_ip_address,
        "merchantPosId": config.connection_params["pos_id"],
        "description": "RTV market",
        "currencyCode": "PLN",
        "totalAmount": calculate_price_to_payu(payment_information.amount),
        "buyer": {
            "email": payment_information.customer_email,
            "phone": payment_information.billing.phone,
            "firstName": payment_information.billing.first_name,
            "lastName": payment_information.billing.last_name,
            "language": "pl"
        },
        "products": [
            {
                "name": "dummy",
                "unitPrice": "15000",
                "quantity": "1"
            }  # TO DO DOSTAC PRODUKTY
        ]
    }
    resp = requests.post(url, headers=headers,
                         data=str(data).replace("'", '"').encode("utf-8"),
                         allow_redirects=False)
    redirect_url = json.loads(resp.content.decode("utf-8"))["redirectUri"]
    return redirect_url
