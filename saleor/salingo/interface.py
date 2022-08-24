from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, Optional

from measurement.measures import Mass


@dataclass
class ProductRulesVariables:
    id: int
    variant_id: int
    bundle_id: int
    created: datetime
    type: str
    name: str
    slug: str
    category: str
    root_category: str
    weight: Mass
    age: int
    sku: str
    brand: str
    material: str
    condition: str
    channel_id: int
    channel_publication_date: datetime.date
    channel_age: int
    channel_is_published: bool
    channel_product_id: int
    channel_slug: str
    channel_visible_in_listings: bool
    channel_available_for_purchase: bool
    channel_currency: str
    channel_price_amount: Decimal
    channel_cost_price_amount: Decimal
    location: Dict
    initial_price_amount: Decimal
    workstation: str
    user: str
    is_bundled: bool
    discount: str


@dataclass
class PricingCalculationOutput:
    variant_id: int
    id: int
    price_amount: Decimal
    cost_price_amount: Decimal
    message: str
    sku: str
    source_channel: str
    initial_price_amount: Decimal
    is_published: bool
    current_price_amount: Decimal
    current_cost_price_amount: Decimal


@dataclass
class RoutingOutput:
    variant_id: int
    id: int
    message: str
    channel: str
    source_channel: str
    discount_name: str


@dataclass
class Location:
    type: str = None
    number: int = None
    box: int = None


@dataclass
class PricingVariables:
    price_mode: str
    current_price: Optional[Decimal]
    current_cost_price_amount: Optional[Decimal]
    result_price: Decimal
    weight: Decimal
    brand: str
    product_type: str
    material: str
    condition: str


@dataclass
class PricingConfig:
    condition: dict
    product_type: dict
    brand: dict
    material: dict
    minimum_price: Decimal
    price_per_kg: Decimal


@dataclass
class BusinessRulesConfiguration:
    ruleset: str
    execute_order: int
    resolver: str
    executor: str


class PriceEnum(Enum):
    DISCOUNT = 'd'
    ITEM = 'i'
    KILOGRAM = 'k'
    MANUAL = 'm'
    ALGORITHM_OLD = 'aold'
    ALGORITHM_NEW = 'anew'


