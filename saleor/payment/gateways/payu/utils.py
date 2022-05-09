import decimal
import json
import requests
from requests.structures import CaseInsensitiveDict
import uuid

from saleor.payment.interface import PaymentData
from saleor.payment.models import Payment


def get_client_token(**_):
    return str(uuid.uuid4())


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


def calculate_payu_price_to_decimal(price: str):
    price = int(price) / decimal.Decimal(100)
    return price


def set_payment_token(payment_id):
    payment = Payment.objects.get(pk=payment_id)
    token = get_client_token()
    payment.token = token
    payment.save()

    return token


def generate_payu_redirect_url(config, payment_information: "PaymentData") -> str:
    authorization_token = generate_authorization_token(config)
    url = f'{config.connection_params["api_url"]}/api/v2_1/orders'
    headers = {"Authorization": f'Bearer {authorization_token["access_token"]}'}
    # Set unique payment token
    payment_id = payment_information.payment_id
    payment_token = set_payment_token(payment_id)

    data = {
        "notifyUrl": config.connection_params["notify_url"],
        "customerIp": payment_information.customer_ip_address,
        "merchantPosId": config.connection_params["pos_id"],
        "description": payment_information.customer_email,
        "currencyCode": "PLN",
        "totalAmount": calculate_price_to_payu(payment_information.amount),
        "extOrderId": payment_token,
        "continueUrl": config.connection_params["continue_url"],
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
    response = requests.post(url=url, headers=headers, json=data, allow_redirects=False)
    # save payu order id to db
    payment = Payment.objects.get(pk=payment_information.payment_id)
    payment.store_value_in_private_metadata(
        {"payu_order_id": response.json()["orderId"]}
    )
    payment.save()

    redirect_url = response.json()["redirectUri"]
    return redirect_url


def get_payu_order_id(payment_id: int) -> str:
    payment = Payment.objects.get(pk=payment_id)
    payu_order_id = payment.get_value_from_private_metadata("payu_order_id")
    return payu_order_id


def refund_payment_request(config: "GatewayConfig", payment_id: int, amount_to_refund: str):
    authorization_token = generate_authorization_token(config)
    payu_order_id = get_payu_order_id(payment_id=payment_id)

    url = f'{config.connection_params["api_url"]}/api/v2_1/orders/{payu_order_id}/refunds'
    headers = {"Authorization": f'Bearer {authorization_token["access_token"]}'}

    payload = {
        "refund": {
            "description": "Refund",
            "amount": int(amount_to_refund)
        }
    }

    response = requests.post(url=url, json=payload, headers=headers)

    if response.status_code == 200:
        return response.json(), None
    else:
        error = response.json().get('status').get('codeLiteral') or 'unexpected_error'
        return response.json(), error
