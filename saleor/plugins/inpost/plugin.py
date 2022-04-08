from dataclasses import dataclass

from phonenumber_field.modelfields import PhoneNumber

from ..base_plugin import BasePlugin, ConfigurationTypeField

from saleor.site.models import SiteSettings

from saleor.payment.interface import AddressData
from saleor.shipping.interface import ShippingMethodData

from .interface import (
    InpostAddress, InpostParcel, InpostDimension, InpostReceiver, InpostWeight,
    InpostShipment, Shipping, UserData
)
from .api import InpostApi
from dataclasses import asdict


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


def create_shipping_information(order: "Order"):
    site_settings = SiteSettings.objects.first()
    sender = AddressData(**site_settings.company_address.as_data())
    receiver_address = AddressData(**order.shipping_address.as_data())
    #shipping_method = ShippingMethodData(**order.shipping_method.as_data())
    courier = order.shipping_method.metadata["courier"]

    receiver = UserData(
        address=receiver_address,
        email=order.user_email
    )

    return Shipping(
        receiver=receiver,
        sender=sender,
        shipping_method=None,
        courier=courier,
    )


def create_inpost_shipment(shipping: Shipping, package):
    receiver_address = InpostAddress(
        city=shipping.receiver.address.city,
        post_code=shipping.receiver.address.postal_code,
        country_code=shipping.receiver.address.country,
        street=shipping.receiver.address.street_address_1,
        # TODO: parse building number
        building_number='30',
        id='30'
    )

    receiver = InpostReceiver(
        first_name=shipping.receiver.address.first_name,
        last_name=shipping.receiver.address.last_name,
        email=shipping.receiver.email,
        phone=PhoneNumber.from_string(shipping.receiver.address.phone).national_number,
        adress=receiver_address
    )

    parcels = []

    for parcel in package:
        dimensions = InpostDimension(
            length=parcel.length,
            width=parcel.width,
            height=parcel.height,
            unit='mm'
        )
        p = InpostParcel(
            weight=InpostWeight(amount="10.0", unit="kg"),
            dimensions=dimensions
        )
        parcels.append(p)

    inpost_shipment = InpostShipment(
        receiver=receiver,
        parcels=parcels
    )

    inpost_api = InpostApi()
    response = inpost_api.create_package(package=inpost_shipment)
    return response
