from dataclasses import dataclass
from typing import List

from saleor.payment.interface import AddressData
from saleor.shipping.interface import ShippingMethodData


@dataclass
class InpostAddress:
    street: str
    city: str
    post_code: str
    country_code: str
    building_number: str = None
    id: str = None

@dataclass
class InpostReceiver:
    first_name: str
    last_name: str
    phone: str
    adress: InpostAddress
    name: str = None
    email: str = None

@dataclass
class InpostDimension:
    length: str
    width: str
    height: str
    unit: str

@dataclass
class InpostWeight:
    amount: str
    unit: str

@dataclass
class InpostParcel:
    id: str = None
    template: str = None
    dimensions: InpostDimension = None
    weight: InpostWeight = None
    tracking_number: str = None
    is_non_standard: bool = None

@dataclass
class InpostShipment:
    """for locker service target_point must be provided in custom_attributes"""
    receiver: InpostReceiver
    parcels: List[InpostParcel] = None
    custom_attributes: dict = None
    additional_services: List[str] = None
    cod: dict = None

@dataclass
class UserData:
    email: str
    address: AddressData

# Shipping package interface
@dataclass
class Shipping:
    courier: str
    shipping_method: ShippingMethodData
    receiver: UserData
    sender: AddressData

