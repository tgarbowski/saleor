import base64
from dataclasses import dataclass

from phonenumber_field.modelfields import PhoneNumber

from ..base_plugin import BasePlugin, ConfigurationTypeField
from .interface import (
    InpostAddress, InpostParcel, InpostDimension, InpostReceiver, InpostWeight,
    InpostPackage
)
from .api import InpostApi
from saleor.salingo.shipping import CarrierError, ShipmentStrategy, Shipping
from saleor.plugins.allegro.utils import get_allegro_channels_slugs


WEBHOOK_PATH = "/webhooks"


@dataclass
class InpostConfiguration:
    organization_id: str
    access_token: str
    api_url: str


class InpostPlugin(BasePlugin):
    PLUGIN_NAME = "Inpost"
    PLUGIN_ID = "Inpost"
    DEFAULT_ACTIVE = False
    CONFIGURATION_PER_CHANNEL = False
    DEFAULT_CONFIGURATION = [
        {"name": "organization_id", "value": None},
        {"name": "access_token", "value": None},
        {"name": "api_url", "value": None}
    ]
    PLUGIN_DESCRIPTION = (
        "Inpost service integration"
    )
    CONFIG_STRUCTURE = {
        "organization_id": {
            "type": ConfigurationTypeField.STRING,
            "label": "Organization ID",
        },
        "access_token": {
            "type": ConfigurationTypeField.SECRET,
            "label": "Access token",
        },
        "api_url": {
            "type": ConfigurationTypeField.STRING,
            "label": "Api url",
        },
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configuration = {item["name"]: item["value"] for item in self.configuration}
        self.config = InpostConfiguration(
            organization_id=configuration["organization_id"],
            access_token=configuration["access_token"],
            api_url=configuration["api_url"]
        )

    def _get_gateway_config(self):
        return self.config


class InpostShipment(ShipmentStrategy):
    def create_package(self, shipping, package, fulfillment) -> str:
        return create_inpost_shipment(shipping, package, fulfillment)

    def generate_label(self, package_id) -> str:
        return generate_inpost_label(package_id)

    def get_tracking_number(self, package_id) -> str:
        return get_inpost_tracking_number(package_id)


def create_inpost_address(shipping: Shipping) -> InpostAddress:
    address = shipping.receiver.address.street_address_1
    if shipping.receiver.address.street_address_2:
        address += " " + shipping.receiver.address.street_address_2
    inpost_address = InpostAddress(
        city=shipping.receiver.address.city,
        post_code=shipping.receiver.address.postal_code,
        country_code=shipping.receiver.address.country,
        street=address,
        line1=shipping.receiver.address.street_address_2
    )
    return inpost_address


def create_inpost_receiver(shipping: Shipping) -> InpostReceiver:
    receiver_address = create_inpost_address(shipping=shipping)

    receiver = InpostReceiver(
        first_name=shipping.receiver.address.first_name,
        last_name=shipping.receiver.address.last_name,
        email=shipping.receiver.email,
        phone=PhoneNumber.from_string(shipping.receiver.address.phone).national_number,
        adress=receiver_address
    )

    return receiver


def create_inpost_package(package):
    parcels = []

    for parcel in package:
        dimensions = InpostDimension(
            length=parcel.sizeX,
            width=parcel.sizeY,
            height=parcel.sizeZ
        )
        p = InpostParcel(
            weight=InpostWeight(amount=parcel.weight, unit="kg"),
            dimensions=dimensions
        )
        parcels.append(p)

    return parcels


def save_package_data_to_fulfillment(fulfillment, parcels, package_id, tracking_number):
    # length dimensions come in cm, inpost api requires mm
    new_parcels = []

    for parcel in parcels:
        new_parcels.append(
            {
                "id": parcel['id'],
                "weight": parcel['weight']['amount'],
                "sizeX": parcel['dimensions']['length'] * 10,
                "sizeY": parcel['dimensions']['width'] * 10,
                "sizeZ": parcel['dimensions']['height'] * 10
            }
        )

    package_data = {
        "package": {
            "id": package_id,
            "parcels": new_parcels
        }
    }

    fulfillment.store_value_in_private_metadata(package_data)
    fulfillment.tracking_number = tracking_number or package_id
    fulfillment.save()


def create_custom_attributes(shipping: Shipping):
    locker_id = shipping.order_metadata.get("locker_id")

    custom_attributes = {
        "sending_method": "dispatch_order"
    }
    if locker_id:
        custom_attributes['target_point'] = locker_id

    return custom_attributes


def create_inpost_shipment_payload(shipping: Shipping, package) -> InpostPackage:
    receiver = create_inpost_receiver(shipping=shipping)
    parcels = create_inpost_package(package=package)
    custom_attributes = create_custom_attributes(shipping=shipping)
    service = shipping.courier_service

    return InpostPackage(
        receiver=receiver,
        parcels=parcels,
        service=service,
        custom_attributes=custom_attributes
    )


def create_inpost_shipment(shipping: Shipping, package, fulfillment):
    if fulfillment.order.channel.slug not in get_allegro_channels_slugs():
        shipping.courier_service = 'inpost_locker_standard'

    inpost_shipment = create_inpost_shipment_payload(shipping=shipping, package=package)
    inpost_api = InpostApi()
    response = inpost_api.create_package(package=inpost_shipment)
    package_id = response.get('id')

    if not package_id:
        raise CarrierError(get_inpost_errors(response))

    tracking_number = response.get('tracking_number')

    if not tracking_number:
        try:
            package_info = inpost_api.get_package(package_id=package_id)
            tracking_number = package_info.get('tracking_number')
        except:
            pass

    save_package_data_to_fulfillment(
        fulfillment=fulfillment,
        parcels=response.get('parcels'),
        package_id=package_id,
        tracking_number=tracking_number
    )

    return package_id


def generate_inpost_label(package_id: str):
    inpost_api = InpostApi()
    label = inpost_api.get_label(shipment_id=package_id)

    if isinstance(label, dict):
        raise CarrierError(get_inpost_errors(label))
    label_b64 = base64.b64encode(label).decode('ascii')
    return label_b64


def get_inpost_tracking_number(package_id):
    api = InpostApi()
    package_info = api.get_package(package_id=package_id)
    return package_info.get('tracking_number')


def get_inpost_errors(response):
    return response.get('details') or response.get('description') or response.get('message') or ''
