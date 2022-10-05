from decimal import Decimal

from saleor.discount.models import OrderDiscount
from saleor.order.models import Order, OrderLine
from saleor.plugins.allegro.orders import insert_allegro_order, cancel_allegro_order
from saleor.plugins.allegro import ProductPublishState


TWO_PLACES = Decimal("0.01")

CHECKOUT_FORM = {
    "id": "29738e61-7f6a-11e8-ac45-09db60ede9d6",
    "messageToSeller": "Please send me an item in red color",
    "buyer": {
        "id": "23123123",
        "email": "user-email@allegro.pl",
        "login": "User_Login",
        "firstName": "Jan",
        "lastName": "Kowalski",
        "companyName": None,
        "guest": False,
        "personalIdentity": "67062589524",
        "phoneNumber": None,
        "preferences": {"language": "pl-PL"},
        "address": {
            "street": "Solna",
            "city": "Poznań",
            "postCode": "60-166",
            "countryCode": "PL",
        },
    },
    "payment": {
        "id": "0f8f1d13-7e9e-11e8-9b00-c5b0dfb78ea6",
        "type": "CASH_ON_DELIVERY",
        "provider": "P24",
        "finishedAt": "2018-10-12T10:12:32.321Z",
        "paidAmount": {"amount": "123.45", "currency": "PLN"},
        "reconciliation": {"amount": "123.45", "currency": "PLN"},
    },
    "status": "READY_FOR_PROCESSING",
    "fulfillment": {"status": "SENT", "shipmentSummary": {"lineItemsSent": "SOME"}},
    "delivery": {
        "address": {
            "firstName": "Jan",
            "lastName": "Kowalski",
            "street": "Grunwaldzka 182",
            "city": "Poznań",
            "zipCode": "60-166",
            "countryCode": "PL",
            "companyName": None,
            "phoneNumber": None,
            "modifiedAt": None,
        },
        "method": {
            "id": "1fa56f79-4b6a-4821-a6f2-ca9c16d5c925",
            "name": "DHL",
        },
        "pickupPoint": {
            "id": "POZ08A",
            "name": "Paczkomat POZ08A",
            "description": "Stacja paliw BP",
            "address": {
                "street": "Grunwaldzka 108",
                "zipCode": "60-166",
                "city": "Poznań",
            },
        },
        "cost": {"amount": "123.45", "currency": "PLN"},
        "time": {
            "guaranteed": {"from": "2018-01-01T16:00:00Z", "to": "2018-01-01T18:00:00Z"}
        },
        "smart": False,
        "calculatedNumberOfPackages": 1,
    },
    "invoice": {
        "required": True,
        "address": {
            "street": "Grunwaldzka 182",
            "city": "Poznań",
            "zipCode": "60-166",
            "countryCode": "PL",
            "company": {"name": "Udix Sp. z o.o.", "taxId": None},
            "naturalPerson": {"firstName": "Jan", "lastName": "Kowalski"},
        },
        "dueDate": "2021-12-01",
    },
    "lineItems": [
        {
            "id": "62ae358b-8f65-4fc4-9c77-bedf604a2e2b",
            "offer": {
                "id": "3213213",
                "name": "Name of purchased offer",
                "external": {"id": "SKU_A"},
            },
            "quantity": 1,
            "originalPrice": {"amount": "123.45", "currency": "PLN"},
            "price": {"amount": "123.45", "currency": "PLN"},
            "reconciliation": {
                "value": {"amount": "123.45", "currency": "PLN"},
                "type": "BILLING",
                "quantity": 1,
            },
            "selectedAdditionalServices": [
                {
                    "definitionId": "CARRY_IN",
                    "name": "Wniesienie",
                    "price": {"amount": "123.45", "currency": "PLN"},
                    "quantity": 1,
                }
            ],
            "boughtAt": "2018-01-01T10:23:43Z",
        }
    ],
    "surcharges": [
        {
            "id": "0f8f1d13-7e9e-11e8-9b00-c5b0dfb78ea6",
            "type": "CASH_ON_DELIVERY",
            "provider": "P24",
            "finishedAt": "2018-10-12T10:12:32.321Z",
            "paidAmount": {"amount": "123.45", "currency": "PLN"},
            "reconciliation": {"amount": "123.45", "currency": "PLN"},
        }
    ],
    "discounts": [{"type": "COUPON"}],
    "summary": {"totalToPay": {"amount": "123.45", "currency": "PLN"}},
    "updatedAt": "2011-12-03T10:15:30.133Z",
    "revision": "819b5836",
}

CHECKOUT_FORM_SMART = {
    "id": "29738e61-7f6a-11e8-ac45-09db60ede9d6",
    "messageToSeller": "Please send me an item in red color",
    "buyer": {
        "id": "23123123",
        "email": "user-email@allegro.pl",
        "login": "User_Login",
        "firstName": "Jan",
        "lastName": "Kowalski",
        "companyName": None,
        "guest": False,
        "personalIdentity": "67062589524",
        "phoneNumber": None,
        "preferences": {"language": "pl-PL"},
        "address": {
            "street": "Solna",
            "city": "Poznań",
            "postCode": "60-166",
            "countryCode": "PL",
        },
    },
    "payment": {
        "id": "0f8f1d13-7e9e-11e8-9b00-c5b0dfb78ea6",
        "type": "CASH_ON_DELIVERY",
        "provider": "P24",
        "finishedAt": "2018-10-12T10:12:32.321Z",
        "paidAmount": {"amount": "123.45", "currency": "PLN"},
        "reconciliation": {"amount": "123.45", "currency": "PLN"},
    },
    "status": "READY_FOR_PROCESSING",
    "fulfillment": {"status": "SENT", "shipmentSummary": {"lineItemsSent": "SOME"}},
    "delivery": {
        "address": {
            "firstName": "Jan",
            "lastName": "Kowalski",
            "street": "Grunwaldzka 182",
            "city": "Poznań",
            "zipCode": "60-166",
            "countryCode": "PL",
            "companyName": None,
            "phoneNumber": None,
            "modifiedAt": None,
        },
        "method": {
            "id": "1fa56f79-4b6a-4821-a6f2-ca9c16d5c925",
            "name": "DHL",
        },
        "pickupPoint": {
            "id": "POZ08A",
            "name": "Paczkomat POZ08A",
            "description": "Stacja paliw BP",
            "address": {
                "street": "Grunwaldzka 108",
                "zipCode": "60-166",
                "city": "Poznań",
            },
        },
        "cost": {"amount": "123.45", "currency": "PLN"},
        "time": {
            "guaranteed": {"from": "2018-01-01T16:00:00Z", "to": "2018-01-01T18:00:00Z"}
        },
        "smart": True,
        "calculatedNumberOfPackages": 1,
    },
    "invoice": {
        "required": False,
        "address": {
            "street": "Grunwaldzka 182",
            "city": "Poznań",
            "zipCode": "60-166",
            "countryCode": "PL",
            "company": {"name": "Udix Sp. z o.o.", "taxId": None},
            "naturalPerson": {"firstName": "Jan", "lastName": "Kowalski"},
        },
        "dueDate": "2021-12-01",
    },
    "lineItems": [
        {
            "id": "62ae358b-8f65-4fc4-9c77-bedf604a2e2b",
            "offer": {
                "id": "3213213",
                "name": "Name of purchased offer",
                "external": {"id": "SKU_A"},
            },
            "quantity": 1,
            "originalPrice": {"amount": "123.45", "currency": "PLN"},
            "price": {"amount": "123.45", "currency": "PLN"},
            "reconciliation": {
                "value": {"amount": "123.45", "currency": "PLN"},
                "type": "BILLING",
                "quantity": 1,
            },
            "selectedAdditionalServices": [
                {
                    "definitionId": "CARRY_IN",
                    "name": "Wniesienie",
                    "price": {"amount": "123.45", "currency": "PLN"},
                    "quantity": 1,
                }
            ],
            "boughtAt": "2018-01-01T10:23:43Z",
        }
    ],
    "surcharges": [
        {
            "id": "0f8f1d13-7e9e-11e8-9b00-c5b0dfb78ea6",
            "type": "CASH_ON_DELIVERY",
            "provider": "P24",
            "finishedAt": "2018-10-12T10:12:32.321Z",
            "paidAmount": {"amount": "123.45", "currency": "PLN"},
            "reconciliation": {"amount": "123.45", "currency": "PLN"},
        }
    ],
    "discounts": [{"type": "COUPON"}],
    "summary": {"totalToPay": {"amount": "123.45", "currency": "PLN"}},
    "updatedAt": "2011-12-03T10:15:30.133Z",
    "revision": "819b5836",
}


def test_save_allegro_order_discounted_product(
    sale,
    order_app_api_client,
    variant_with_many_stocks_different_shipping_zones,
    channel_USD,
    allegro_shipping_method,
    permission_manage_orders
):
    order_id = insert_allegro_order(
        api_client=order_app_api_client,
        checkout_form=CHECKOUT_FORM,
        channel_id=channel_USD.id
    )

    order = Order.objects.get(pk=order_id)

    assert order_id is not None
    assert order.shipping_method.name == allegro_shipping_method.name
    assert order.status == 'unfulfilled'
    assert order.undiscounted_total_gross_amount == Decimal(133.45).quantize(TWO_PLACES)
    assert order.shipping_price_gross_amount == Decimal(10.00)
    assert order.total_gross_amount == Decimal(133.45).quantize(TWO_PLACES)


def test_save_allegro_order_smart(
    order_app_api_client,
    variant_with_many_stocks_different_shipping_zones,
    channel_USD,
    allegro_shipping_method,
    smart_voucher
):
    order_id = insert_allegro_order(
        api_client=order_app_api_client,
        checkout_form=CHECKOUT_FORM_SMART,
        channel_id=channel_USD.id
    )

    order = Order.objects.get(pk=order_id)
    order_lines = OrderLine.objects.filter(order=order)
    discount = OrderDiscount.objects.get(order=order)

    assert order_id is not None
    assert order.shipping_method.name == allegro_shipping_method.name
    assert order.status == 'unfulfilled'
    assert order.undiscounted_total_gross_amount == Decimal(133.45).quantize(TWO_PLACES)
    assert order.shipping_price_gross_amount == Decimal(10.00)
    assert order.total_gross_amount == Decimal(123.45).quantize(TWO_PLACES)
    assert discount.value == Decimal(10.00)

    for order_line in order_lines:
        product = order_line.variant.product
        assert product.get_value_from_private_metadata(
            'publish.allegro.status'
        ) == ProductPublishState.SOLD.value
        assert product.get_value_from_private_metadata(
            'publish.status.date'
        ) == '2018-01-01 10:23:43'
        assert product.get_value_from_private_metadata(
            'publish.allegro.price'
        ) == '123.45'


def test_save_allegro_order(
    order_app_api_client,
    variant_with_many_stocks_different_shipping_zones,
    channel_USD,
    allegro_shipping_method
):
    order_id = insert_allegro_order(
        api_client=order_app_api_client,
        checkout_form=CHECKOUT_FORM,
        channel_id=channel_USD.id
    )

    order = Order.objects.get(pk=order_id)
    order_lines = OrderLine.objects.filter(order=order)

    assert order_id is not None
    assert order.shipping_method.name == allegro_shipping_method.name
    assert order.status == 'unfulfilled'

    assert order.shipping_price_gross_amount == Decimal(10.00)
    assert order.total_gross_amount == Decimal(133.45).quantize(TWO_PLACES)

    for order_line in order_lines:
        product = order_line.variant.product
        assert product.get_value_from_private_metadata(
            'publish.allegro.status'
        ) == ProductPublishState.SOLD.value
        assert product.get_value_from_private_metadata(
            'publish.status.date'
        ) == '2018-01-01 10:23:43'
        assert product.get_value_from_private_metadata(
            'publish.allegro.price'
        ) == '123.45'


def test_cancel_allegro_order(
    allegro_order,
    order_app_api_client
):
    cancel_allegro_order(
        api_client=order_app_api_client,
        checkout_form=CHECKOUT_FORM
    )

    order = Order.objects.get(pk=allegro_order.pk)
    assert order.status == 'canceled'
