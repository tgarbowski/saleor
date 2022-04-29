from saleor.plugins.inpost.plugin import Shipping
from .api import  GlsApi


def create_gls_receiver(shipping: Shipping):
    receiver = {
        'rname1': shipping.receiver.address.first_name,
        'rname2': shipping.receiver.address.last_name,
        'rcountry': shipping.receiver.address.country,
        'rzipcode': shipping.receiver.address.postal_code,
        'rcity': shipping.receiver.address.city,
        'rstreet': shipping.receiver.address.street_address_1,
        'rphone': shipping.receiver.address.phone,
        'rcontact': shipping.receiver.email
    }
    return receiver


def create_gls_package(package):
    package_data = {
        'weight': sum(int(parcel['weight']) for parcel in package),
        'quantity': len(package)
    }
    return package_data


def get_cod_payload(cod_amount):
    cod = {
        "srv_bool": {
            "cod": True,
            "cod_amount": cod_amount
        }
    }
    return cod


def save_package_data_to_fulfillment(fulfillment, package_id) -> None:
    package_data = {
        "package": {
            "id": package_id
        }
    }
    fulfillment.store_value_in_private_metadata(package_data)
    fulfillment.tracking_number = package_id
    fulfillment.save()


def create_gls_shipment(shipping: Shipping, package, fulfillment, order):
    gls_api = GlsApi()

    total_gross_amount = order.total_gross_amount
    is_cod = shipping.shipping_method.metadata.get('cod')
    cod = get_cod_payload(cod_amount=total_gross_amount) if is_cod else {}
    receiver = create_gls_receiver(shipping=shipping)
    package_data = create_gls_package(package=package)
    payload = {**receiver, **package_data, **cod}

    package_id = gls_api.generate_package_shipment(
        payload=payload
    )

    save_package_data_to_fulfillment(
        fulfillment=fulfillment,
        package_id=package_id
    )

    return package_id


def generate_gls_label(package_id: str):
    gls_api = GlsApi()

    label = gls_api.generate_label(
        number=int(package_id),
        mode='roll_160x100_zebra'
    )
    return label
