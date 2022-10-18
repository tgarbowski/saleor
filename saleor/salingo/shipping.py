from abc import ABC, abstractmethod
from dataclasses import dataclass

from saleor.order.models import Fulfillment
from saleor.site.models import SiteSettings
from saleor.payment.interface import AddressData
from saleor.shipping.interface import ShippingMethodData
from saleor.plugins.allegro.orders import unmangle_email


class ShipmentStrategy(ABC):
    @abstractmethod
    def create_package(self, shipping, package, fulfillment) -> str:
        """Creates a package and saves data to fulfillment metadata"""
        pass

    @abstractmethod
    def generate_label(self, package_id) -> str:
        """Returns b64 encoded shipping label"""
        pass

    @abstractmethod
    def get_tracking_number(self, package_id) -> str:
        """Returns a tracking number"""
        pass


@dataclass
class UserData:
    email: str
    address: AddressData


@dataclass
class Shipping:
    courier: str
    courier_service: str
    shipping_method: ShippingMethodData
    receiver: UserData
    sender: AddressData
    order_metadata: dict
    shipping_method_metadata: dict


class UnknownCarrierError(Exception):
    pass


class CarrierError(Exception):
    def __init__(self, message='Something went wrong with shipment'):
        self.message = message

    def __str__(self):
        return str(self.message)


def shipment_strategy(courier: str):
    from saleor.plugins.inpost.plugin import InpostShipment
    from saleor.plugins.gls.utils import GlsShipment
    from saleor.plugins.dpd.utils import DpdShipment

    strategies = {
        "INPOST": InpostShipment(),
        "GLS": GlsShipment(),
        "DPD": DpdShipment()
    }
    if courier in ['INPOST', 'GLS', 'DPD']:
        return strategies[courier]
    else:
        raise UnknownCarrierError()


def create_shipping_information(order: "Order"):
    site_settings = SiteSettings.objects.first()
    sender = AddressData(**site_settings.company_address.as_data())
    receiver_address = AddressData(**order.shipping_address.as_data())
    shipping_method = ShippingMethodData(
        id='',
        name=order.shipping_method_name,
        price=order.shipping_price_gross,
        metadata=order.shipping_method.metadata
    )
    courier = order.shipping_method.metadata["courier"]
    courier_service = order.shipping_method.metadata.get("courier_service")
    shipping_method_metadata = order.shipping_method.metadata
    order_metadata = order.metadata

    receiver = UserData(
        address=receiver_address,
        email=unmangle_email(order.user_email)
    )

    return Shipping(
        receiver=receiver,
        sender=sender,
        shipping_method=shipping_method,
        courier=courier,
        courier_service=courier_service,
        order_metadata=order_metadata,
        shipping_method_metadata=shipping_method_metadata
    )


def update_tracking_number(order, package_id):
    courier = order.shipping_method.metadata.get("courier")
    tracking_number = shipment_strategy(courier=courier).get_tracking_number(package_id=package_id)

    if tracking_number:
        fulfillment = get_fulfillment_by_package_id(order=order, package_id=package_id)
        fulfillment.tracking_number = tracking_number
        fulfillment.save()


def get_fulfillment_by_package_id(order, package_id):
    return Fulfillment.objects.get(order=order, private_metadata__package__id=int(package_id))
