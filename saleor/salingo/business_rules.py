from asyncio import run
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
import logging
import re
from typing import List, Dict, Optional
import yaml
import time

import rule_engine

from django.db import transaction

from saleor.channel.models import Channel
from saleor.product.models import (Category, Product, ProductVariantChannelListing,
                                   ProductChannelListing)
from saleor.plugins.models import PluginConfiguration
from saleor.plugins.base_plugin import ConfigurationTypeField
from measurement.measures import Mass
from saleor.salingo.utils import patch_async
from saleor.plugins.allegro.api import AllegroAPI


PluginConfigurationType = List[dict]

logger = logging.getLogger(__name__)


class BusinessRulesEvaluator:
    def __init__(self, plugin_slug, mode):
        self.plugin_slug = plugin_slug
        self.mode = mode

    def evaluate_rules(self):
        sorted_configs = self.get_sorted_configs()
        context = rule_engine.Context(resolver=rule_engine.resolve_attribute)

        for config in sorted_configs:
            logger.info(f'Przetwarzam ruleset: {config["ruleset"]} w trybie {self.mode}')
            engine_rules = self.get_rules(config['rules'])
            self.validate_rules(engine_rules)
            # Resolve products for given config
            offset = 0
            resolver_function = getattr(Resolvers, config['resolver'])
            products = resolver_function(offset=offset)
            executor = ExecutorsFactory.get_executor(plugin_slug=self.plugin_slug, config=config)
            executor_function = getattr(executor, config['executor'])

            while products:
                already_processed = set()
                for rule in engine_rules:
                    rule_object = rule_engine.Rule(rule['rule'], context=context)
                    matching_products = rule_object.filter(products)
                    output_for_update = {}
                    # Prepare output for matching products
                    for product in matching_products:
                        if product.id not in already_processed:
                            output = executor_function(product, rule['result'])
                            already_processed.add(product.id)
                            if output:
                                output_for_update[output.variant_id] = output
                    # Bulk action on matching products
                    if output_for_update and self.mode == 'commit':
                        executor.bulk_handler(output_for_update)

                offset = self.calculate_offset(offset)
                products = resolver_function(offset=offset)

    def get_sorted_configs(self):
        configs = PluginConfiguration.objects.filter(identifier=self.plugin_slug, active=True)
        configs_dict = []
        for config in configs:
            config = {item["name"]: item["value"] for item in config.configuration}
            configs_dict.append(config)

        return sorted(configs_dict, key=lambda single_config: single_config['execute_order'])

    @staticmethod
    def get_rules(yaml_rules):
        rules = yaml.safe_load(yaml_rules)
        engine_rules = [rule for rule in rules]

        return engine_rules

    @staticmethod
    def validate_rules(rules):
        for rule in rules:
            r = rule['rule']
            if not rule_engine.Rule.is_valid(r):
                raise Exception(f'Invalid engine rule: {r}')

    def calculate_offset(self, current_offset):
        if self.plugin_slug == 'salingo_routing' and self.mode == 'commit':
            return current_offset
        else:
            return current_offset + 10000


class ExecutorsFactory:
    @staticmethod
    def get_executor(plugin_slug, config):
        if plugin_slug == 'salingo_pricing':
            global_pricing_config = get_plugin_config_by_identifier('salingo_pricing_global')
            global_config = PricingConfig(
                condition=lowercase(yaml.safe_load(global_pricing_config['condition_pricing'])),
                material=lowercase(yaml.safe_load(global_pricing_config['material_pricing'])),
                product_type=lowercase(yaml.safe_load(global_pricing_config['type_pricing'])),
                brand=lowercase(yaml.safe_load(global_pricing_config['brand_pricing'])),
                minimum_price=Decimal(global_pricing_config['minimum_price']),
                price_per_kg=Decimal(global_pricing_config['price_per_kg'])
            )
            return PricingExecutors(config=config, global_config=global_config)
        if plugin_slug == 'salingo_routing':
            return RoutingExecutors(config=config)


class RoutingExecutors:
    def __init__(self, config):
        self.config = config

    @classmethod
    def bulk_handler(cls, products, channel):
        cls.bulk_change_channel_listings(products, channel)

    def move_from_unpublished(self, product: 'ProductRulesVariables', result: str):
        message = f'{datetime.now()} moved from channel ' \
                  f'{product.channel_slug} to channel {result}'
        logger.info(f'{product.sku} {message}')

        return RoutingOutput(
            variant_id=product.variant_id,
            id=product.id,
            channel=result,
            message=message
        )

    @classmethod
    def bulk_change_channel_listings(cls, products: Dict[int, 'RoutingOutput']):
        for x in list(products)[0:1]:
            channel = x['channel']
        channel_id = Channel.objects.get(slug=channel).pk
        variant_ids = dict.keys(products)
        product_ids = []
        product_messages = {}

        for key, value in products.items():
            product_ids.append(value.id)
            product_messages[value.id] = value.message

        with transaction.atomic():
            ProductChannelListing.objects.filter(product_id__in=product_ids).update(
                channel_id=channel_id,
                publication_date=None,
                is_published=False
            )
            ProductVariantChannelListing.objects.filter(variant_id=variant_ids).update(
                channel_id=channel_id)

        bulk_log_to_private_metadata(product_messages=product_messages, key='history')


class PricingExecutors:
    def __init__(self, config, global_config):
        self.config = config
        self.global_config = global_config

    def calculate_price(self, payload: 'PricingVariables') -> Decimal:
        if payload.price_mode == PriceEnum.KILOGRAM.value:
            price = payload.weight * payload.result_price
        elif payload.price_mode == PriceEnum.ITEM.value:
            price = payload.result_price
        elif payload.price_mode == PriceEnum.DISCOUNT.value:
            price = payload.current_price - (payload.current_price * payload.result_price / 100)
        elif payload.price_mode == PriceEnum.MANUAL.value:
            price = payload.current_price
        elif payload.price_mode == PriceEnum.ALGORITHM.value:
            price = self.calculate_price_by_algorithm(payload=payload)
        else:
            price = payload.current_price

        return round(price, 2)

    def calculate_price_by_algorithm(self, payload: 'PricingVariables') -> Decimal:
        pricing_config = self.global_config
        percentages = 0

        if payload.product_type in pricing_config.product_type:
            base_price = pricing_config.product_type[payload.product_type]
        else:
            return self.calculate_price_by_cost_price(
                min_price=pricing_config.minimum_price,
                price_per_kg=pricing_config.price_per_kg,
                weight=payload.weight,
                current_cost_price_amount=payload.current_cost_price_amount
            )

        if payload.condition in pricing_config.condition:
            condition_percentage = pricing_config.condition[payload.condition]
            percentages += self.percentage_string_to_int(percentage_string=condition_percentage)

        if payload.material in pricing_config.material:
            material_percentage = pricing_config.material[payload.material]
            percentages += self.percentage_string_to_int(percentage_string=material_percentage)

        if payload.brand in pricing_config.brand:
            brand_percentage = pricing_config.brand[payload.brand]
            percentages += self.percentage_string_to_int(percentage_string=brand_percentage)

        price = Decimal(base_price) + Decimal(base_price) * Decimal(percentages) / 100
        return price

    def calculate_price_by_cost_price(self, min_price, price_per_kg, weight, current_cost_price_amount):
        if current_cost_price_amount:
            cost_price = current_cost_price_amount
        else:
            cost_price = self.calculate_cost_price_amount(
                price_per_kg=price_per_kg,
                weight=weight
            )
        price = cost_price * 2
        if price < min_price:
            price = min_price
        return round(price, 2)

    @staticmethod
    def percentage_string_to_int(percentage_string):
        percentage = int(percentage_string.split('%')[0])
        return percentage

    @staticmethod
    def calculate_cost_price_amount(price_per_kg: Decimal, weight: Decimal):
        cost_price_amount = price_per_kg * weight

        return round(cost_price_amount, 2)

    @classmethod
    def get_validated_pricing_variables(cls, product: 'ProductRulesVariables', result: str):
        if not isinstance(result, str):
            return None

        price_mode = result[:1]

        if price_mode not in [e.value for e in PriceEnum]:
            return None

        try:
            result_price = Decimal(result[1:])
        except InvalidOperation:
            return None

        if product.weight is None:
            message = f'Weight not provided for SKU: {product.sku}, can not calculate price.'
            logger.info(message)
            return None

        if product.channel_price_amount:
            channel_price_amount = Decimal(product.channel_price_amount)
        else:
            channel_price_amount = None

        if product.channel_cost_price_amount:
            channel_cost_price_amount = Decimal(product.channel_cost_price_amount)
        else:
            channel_cost_price_amount = None

        return PricingVariables(
            price_mode=price_mode,
            current_price=channel_price_amount,
            result_price=result_price,
            weight=Decimal(product.weight.kg),
            brand=product.brand,
            product_type=product.type,
            material=product.material,
            condition=product.condition,
            current_cost_price_amount=channel_cost_price_amount
        )

    def change_price(self, product: 'ProductRulesVariables', result):
        validated_pricing_variables = self.get_validated_pricing_variables(
            product=product,
            result=result
        )

        if validated_pricing_variables is None: return

        price = self.calculate_price(validated_pricing_variables)

        if price < self.global_config.minimum_price:
            price = self.global_config.minimum_price

        if validated_pricing_variables.current_cost_price_amount:
            cost_price_amount = validated_pricing_variables.current_cost_price_amount
        else:
            cost_price_amount = self.calculate_cost_price_amount(
                price_per_kg=self.global_config.price_per_kg,
                weight=validated_pricing_variables.weight
            )

        message = f'{datetime.now()} calculated price for channel ' \
                  f'{product.channel_slug} {PriceEnum(validated_pricing_variables.price_mode).name} {price}'

        logger.info(f'{product.sku}: {message}')

        return PricingCalculationOutput(
            variant_id=product.variant_id,
            id=product.id,
            price_amount=price,
            cost_price_amount=cost_price_amount,
            message=message,
            sku=product.sku
        )
    @classmethod
    def bulk_handler(cls, products: Dict[int, 'PricingCalculationOutput']) -> None:
        cls.bulk_update_pricing(products)
        cls.bulk_update_pricing_allegro(products)

    @classmethod
    def bulk_update_pricing_allegro(cls, products: Dict[int, 'PricingCalculationOutput']):
        # key:value > sku:price
        prices = {}

        for key, value in products.items():
            prices[value.sku] = value.price_amount

        skus = list(dict.keys(prices))
        # GET offers by skus
        allegro_api = AllegroAPI(channel='allegro')
        offers = allegro_api.get_offers_by_skus(skus, publication_statuses=['ACTIVE'])
        # transform fetched offer into dict sku:offer_id
        sku_offer_id = {}

        for offer in offers:
            sku_offer_id[offer['external']['id']] = offer['id']

        # OFFER_ID:PRICE dict
        offer_id_price = {}
        for key, value in sku_offer_id.items():
            offer_id_price[value] = prices[key]

        offers_price_update = prepare_allegro_update_price_requests(allegro_api, offer_id_price)
        update_results = run(patch_async(offers_price_update))

        if update_results:
            retries = 1
            # Retry 5 times in case of HTTP 429
            while retries < 5 and update_results:
                # Allegro API blocks for 60s when default limit 9000 req/s is exceeded
                time.sleep(65)
                index_from_start_again = get_backstep_offer_index(
                    offers_price_update=offers_price_update,
                    failed_result=update_results
                )
                offers_price_update = offers_price_update[index_from_start_again:]
                update_results = run(patch_async(offers_price_update))
                retries += 1

    @classmethod
    def bulk_update_pricing(cls, products: Dict[int, 'PricingCalculationOutput']) -> None:
        variant_ids = dict.keys(products)
        product_messages = {}

        for key, value in products.items():
            product_messages[value.id] = value.message

        pvcl = ProductVariantChannelListing.objects.filter(variant_id__in=variant_ids)

        for listing in pvcl:
            product = products[listing.variant_id]
            listing.price_amount = product.price_amount
            listing.cost_price_amount = product.cost_price_amount

        ProductVariantChannelListing.objects.bulk_update(
            objs=pvcl,
            fields=['price_amount', 'cost_price_amount'],
            batch_size=500
        )

        bulk_log_to_private_metadata(product_messages=product_messages, key='history')


class Resolvers:

    @classmethod
    def resolve_unpublished(cls, offset):
        return cls.get_products_custom_dict(channel='unpublished', offset=offset)

    @classmethod
    def resolve_allegro_unpublished(cls, offset):
        filters = {"is_published": False}
        return cls.get_products_custom_dict(channel='allegro', filters=filters, offset=offset)

    @classmethod
    def resolve_allegro(cls, offset):
        return cls.get_products_custom_dict(channel='allegro', offset=offset)

    @classmethod
    def get_products_custom_dict(cls, channel, offset, filters={}):
        LIMIT = 10000

        product_channel_listings = ProductChannelListing.objects.filter(
            channel__slug=channel, **filters
        ).select_related('channel', 'product').order_by('product_id')[offset:offset + LIMIT]

        product_ids = list(product_channel_listings.values_list('product_id', flat=True))
        if not product_ids: return

        product_variant_channel_listing = ProductVariantChannelListing.objects.filter(
            channel__slug=channel, variant__product__id__in=product_ids
        ).select_related(
            'variant', 'variant__product', 'variant__product__product_type',
            'variant__product__category'
        ).order_by('variant__product_id')[:LIMIT]

        category_tree_ids = cls.get_main_category_tree_ids()
        products = []

        for pcl, pvcl in zip(product_channel_listings, product_variant_channel_listing):
            if pvcl.variant.product_id != pcl.product_id:
                raise Exception(f'Wrong channel listings merge for SKU = {pvcl.variant.sku}. '
                                f'PVCL product_id = {pvcl.variant.product_id} != '
                                f'PCL product_id = {pcl.product_id}')

            products.append(ProductRulesVariables(
                id=pvcl.variant.product.id,
                variant_id=pvcl.variant.id,
                bundle_id=pvcl.variant.product.metadata.get('bundle.id'),
                created_at=pvcl.variant.product.created_at,
                type=pvcl.variant.product.product_type.name.lower(),
                name=pvcl.variant.product.name,
                slug=pvcl.variant.product.slug,
                category=pvcl.variant.product.category.slug,
                root_category=cls.get_root_category(category_tree_ids, pvcl.variant.product.category.tree_id),
                weight=pvcl.variant.product.weight,
                age=cls.parse_datetime(pvcl.variant.product.created_at),
                sku=pvcl.variant.sku,
                brand=cls.get_attribute_from_description(pcl.product.description, 'Marka').lower(),
                material=cls.get_attribute_from_description(pcl.product.description, 'Materiał').lower(),
                condition=cls.get_attribute_from_description(pcl.product.description, 'Stan').lower(),
                channel_id=pcl.channel.id,
                channel_publication_date=pcl.publication_date,
                channel_age=cls.parse_date(pcl.publication_date),
                channel_is_published=pcl.is_published,
                channel_product_id=pcl.product_id,
                channel_slug=pcl.channel.slug,
                channel_visible_in_listings=pcl.visible_in_listings,
                channel_available_for_purchase=pcl.available_for_purchase,
                channel_currency=pvcl.currency,
                channel_price_amount=pvcl.price_amount,
                channel_cost_price_amount=pvcl.cost_price_amount,
                location=cls.parse_location(pvcl.variant.private_metadata.get('location'))
            ))

        return products

    @staticmethod
    def get_attribute_from_description(description, attribute_name):
        for block in description.get('blocks'):
            text = block.get('data').get('text')

            if text and attribute_name in text:
                return text.partition(":")[2].lower().strip()

        return ''

    @staticmethod
    def get_main_category_tree_ids():
        return {
            'kobieta': Category.objects.get(slug='kobieta').tree_id,
            'mezczyzna': Category.objects.get(slug='mezczyzna').tree_id,
            'dziecko': Category.objects.get(slug='dziecko').tree_id
        }

    @staticmethod
    def get_root_category(category_tree_ids, category_tree_id):
        for k, v in category_tree_ids.items():
            if v == category_tree_id:
                return k

    @staticmethod
    def parse_date(publication_date):
        try:
            delta = date.today() - publication_date
        except TypeError:
            return 0
        return delta.days

    @staticmethod
    def parse_datetime(publication_date):
        delta = date.today() - publication_date.date()
        return delta.days

    @staticmethod
    def parse_location(location):
        # eg. input: R01K01
        if not location:
            return Location()

        digits = re.findall('\d+', location)

        try:
            parsed_location = Location(
                type=location[1],
                number=int(digits[0]),
                box=int(digits[1])
            )
        except IndexError:
            return Location()

        return parsed_location


DEFAULT_BUSINESS_RULES_CONFIGURATION = [
        {"name": "ruleset", "value": ""},
        {"name": "execute_order", "value": ""},
        {"name": "resolver", "value": ""},
        {"name": "executor", "value": ""},
        {"name": "rules", "value": ""}
    ]


DEFAULT_BUSINESS_RULES_CONFIG_STRUCTURE = {
        "ruleset": {
            "type": ConfigurationTypeField.STRING,
            "label": "Ruleset"
        },
        "execute_order": {
            "type": ConfigurationTypeField.STRING,
            "label": "Execute order"
        },
        "resolver": {
            "type": ConfigurationTypeField.STRING,
            "label": "Resolver"
        },
        "executor": {
            "type": ConfigurationTypeField.STRING,
            "label": "Executor"
        },
        "rules": {
            "type": ConfigurationTypeField.MULTILINE,
            "label": "Rules"
        }
    }


def lowercase(obj: Dict):
    return dict((k.lower(), v) for k, v in obj.items())


def get_plugin_config_by_identifier(identifier):
    config = PluginConfiguration.objects.get(identifier=identifier)
    configuration = {item["name"]: item["value"] for item in config.configuration}
    return configuration


def bulk_log_to_private_metadata(product_messages: Dict[int, str], key: str):
    product_ids = []

    for product_id, message in product_messages.items():
        product_ids.append(product_id)

    db_products = Product.objects.filter(id__in=product_ids)

    for x in db_products:
        message = product_messages[x.id]
        field = x.private_metadata.get(key)

        if field:
            field.append(message)
        else:
            x.private_metadata[key] = [message]

    Product.objects.bulk_update(
        objs=db_products,
        fields=['private_metadata'],
        batch_size=500
    )


def prepare_allegro_update_price_requests(allegro_api, offer_id_price):
    offers_price_update = []

    for offer_id, price in offer_id_price.items():
        url = f'{allegro_api.env}/sale/product-offers/{offer_id}'
        headers = {'Authorization': 'Bearer ' + allegro_api.token,
                   'Accept': f'application/vnd.allegro.public.v1+json',
                   'Content-Type': f'application/vnd.allegro.public.v1+json'}
        # TODO: ustaw starting price
        payload = {
            "sellingMode": {
                "startingPrice": {
                    "amount": price,
                    "currency": "PLN"
                }
            }
        }

        offers_price_update.append(
            {'url': url,
             'headers': headers,
             'payload': payload,
             'offer_id': offer_id
             }
        )
    return offers_price_update


def get_backstep_offer_index(offers_price_update, failed_result):
    failed_offer_index = None

    for i, offer in enumerate(offers_price_update):
        if offer['offer_id'] == failed_result.rsplit('/', 1)[1]:
            failed_offer_index = i
            break

    if failed_offer_index > 20:
        index_from_start_again = failed_offer_index - 20
    else:
        index_from_start_again = 0

    return index_from_start_again


@dataclass
class ProductRulesVariables:
    id: int
    variant_id: int
    bundle_id: int
    created_at: datetime
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


@dataclass
class PricingCalculationOutput:
    variant_id: int
    id: int
    price_amount: Decimal
    cost_price_amount: Decimal
    message: str
    sku: str


@dataclass
class RoutingOutput:
    variant_id: int
    id: int
    message: str
    channel: str


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


class PriceEnum(Enum):
    DISCOUNT = 'd'
    ITEM = 'i'
    KILOGRAM = 'k'
    MANUAL = 'm'
    ALGORITHM = 'a'


@dataclass
class BusinessRulesConfiguration:
    ruleset: str
    execute_order: int
    resolver: str
    executor: str
