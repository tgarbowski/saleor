from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
import logging
import re
from typing import List, Dict, Optional
import yaml

import rule_engine

from django.db import transaction

from saleor.channel.models import Channel
from saleor.product.models import (Category, Product, ProductVariantChannelListing,
                                   ProductChannelListing)
from saleor.plugins.models import PluginConfiguration
from saleor.plugins.base_plugin import ConfigurationTypeField


PluginConfigurationType = List[dict]

logger = logging.getLogger(__name__)


class BusinessRulesEvaluator:
    def __init__(self, plugin_slug, mode):
        self.plugin_slug = plugin_slug
        self.mode = mode

    def evaluate_rules(self):
        sorted_configs = self.get_sorted_configs()
        additional_config = self.get_additional_config()

        for config in sorted_configs:
            logger.info(f'Przetwarzam ruleset: {config["ruleset"]} w trybie {self.mode}')
            engine_rules = self.get_rules(config['rules'])
            self.validate_rules(engine_rules)
            # Resolve products for given config
            offset = 0
            resolver_function = getattr(Resolvers, config['resolver'])
            products = resolver_function(offset=offset)
            executor = Executors(mode=self.mode, config=config, additional_config=additional_config)
            executor_function = getattr(executor, config['executor'])

            while products:
                already_processed = set()
                for rule in engine_rules:
                    rule_object = rule_engine.Rule(rule['rule'])
                    matching_products = rule_object.filter(products)
                    for product in matching_products:
                        if product['id'] not in already_processed:
                            executor_function(product, rule['result'])
                            already_processed.add(product['id'])
                offset += 10000
                products = resolver_function(offset=offset)

    def get_sorted_configs(self):
        configs = PluginConfiguration.objects.filter(identifier=self.plugin_slug, active=True)
        configs_dict = []
        for config in configs:
            config = {item["name"]: item["value"] for item in config.configuration}
            configs_dict.append(config)

        return sorted(configs_dict, key=lambda single_config: single_config['execute_order'])

    def get_additional_config(self):
        if self.plugin_slug == 'salingo_pricing':
            config = PluginConfiguration.objects.get(identifier='salingo_pricing_global')
            configuration = {item["name"]: item["value"] for item in config.configuration}
            return self.get_pricing_config(configuration)

    def get_pricing_config(self, config):
        return PricingConfig(
            condition=lowercase(Executors.load_yaml(config['condition_pricing'])),
            material=lowercase(Executors.load_yaml(config['material_pricing'])),
            product_type=lowercase(Executors.load_yaml(config['type_pricing'])),
            brand=lowercase(Executors.load_yaml(config['brand_pricing'])),
            minimum_price=Decimal(config['minimum_price']),
            price_per_kg=Decimal(config['price_per_kg'])
        )

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


class Executors:
    def __init__(self, mode, config, additional_config):
        self.mode = mode
        self.config = config
        self.additional_config = additional_config

    def move_from_unpublished(self, product, channel):
        message = f'{datetime.now()} moved from channel ' \
                  f'{product["channel_slug"]} to channel {channel}'
        logger.info(f'{product["sku"]} {message}')

        if self.mode == 'dry_run': return

        self.change_product_channel(product=product, channel=channel)
        self.log_to_product_private_metadata(product_id=product['id'], key='history', value=message)

    def calculate_price(self, payload: "PricingVariables"):
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

    def calculate_price_by_algorithm(self, payload: "PricingVariables"):
        pricing_config = self.additional_config
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

    @staticmethod
    def load_yaml(rule):
        return yaml.safe_load(rule)

    @classmethod
    def get_validated_pricing_variables(cls, product, result):
        if not isinstance(result, str):
            return None

        price_mode = result[:1]

        if price_mode not in [e.value for e in PriceEnum]:
            return None

        try:
            result_price = Decimal(result[1:])
        except InvalidOperation:
            return None

        if product['weight'] is None:
            message = 'Weight not provided, can not calculate price.'
            cls.log_to_product_private_metadata(product_id=product['id'], key='publish.allegro.errors', value=message)
            return None

        if product['channel_price_amount']:
            channel_price_amount = Decimal(product['channel_price_amount'])
        else:
            channel_price_amount = None

        if product['channel_cost_price_amount']:
            channel_cost_price_amount = Decimal(product['channel_cost_price_amount'])
        else:
            channel_cost_price_amount = None

        return PricingVariables(
            price_mode=price_mode,
            current_price=channel_price_amount,
            result_price=result_price,
            weight=Decimal(product['weight'].kg),
            brand=product['brand'],
            product_type=product['type'],
            material=product['material'],
            condition=product['condition'],
            current_cost_price_amount=channel_cost_price_amount
        )

    def change_price(self, product, result):
        validated_pricing_variables = self.get_validated_pricing_variables(
            product=product,
            result=result
        )

        if validated_pricing_variables is None: return

        price = self.calculate_price(validated_pricing_variables)

        if price < self.additional_config.minimum_price:
            price = self.additional_config.minimum_price

        if validated_pricing_variables.current_cost_price_amount:
            cost_price_amount = validated_pricing_variables.current_cost_price_amount
        else:
            cost_price_amount = self.calculate_cost_price_amount(
                price_per_kg=self.additional_config.price_per_kg,
                weight=validated_pricing_variables.weight
            )

        message = f'{datetime.now()} calculated price for channel ' \
                  f'{product["channel_slug"]} {PriceEnum(validated_pricing_variables.price_mode).name} {price}'

        logger.info(f'{product["sku"]}: {message}')

        if self.mode == 'dry_run': return

        ProductVariantChannelListing.objects.filter(variant_id=product['variant_id']).update(
            price_amount=price, cost_price_amount=cost_price_amount)

        self.log_to_product_private_metadata(product_id=product['id'], key='history', value=message)

    @classmethod
    def change_product_channel(cls, product, channel):
        channel_id = Channel.objects.get(slug=channel).pk
        product_id = product['id']
        variant_id = product['variant_id']

        with transaction.atomic():
            ProductChannelListing.objects.filter(product_id=product_id).update(
                channel_id=channel_id,
                publication_date=None,
                is_published=False
            )
            ProductVariantChannelListing.objects.filter(variant_id=variant_id).update(channel_id=channel_id)

    @classmethod
    def log_to_product_private_metadata(cls, product_id, key, value):
        product = Product.objects.get(pk=product_id)
        field = product.private_metadata.get(key)

        if field:
            field.append(value)
        else:
            product.private_metadata[key] = [value]

        product.save(update_fields=['private_metadata'])


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

            products.append(
                {
                    'id': pvcl.variant.product.id,
                    'variant_id': pvcl.variant.id,
                    'bundle_id': pvcl.variant.product.metadata.get('bundle.id'),
                    'created_at': pvcl.variant.product.created_at,
                    'type': pvcl.variant.product.product_type.name.lower(),
                    'name': pvcl.variant.product.name,
                    'slug': pvcl.variant.product.slug,
                    'category': pvcl.variant.product.category.slug,
                    'root_category': cls.get_root_category(category_tree_ids,
                                                           pvcl.variant.product.category.tree_id),
                    'weight': pvcl.variant.product.weight,
                    'age': cls.parse_datetime(pvcl.variant.product.created_at),
                    'sku': pvcl.variant.sku,
                    'brand': cls.get_attribute_from_description(pcl.product.description, 'Marka').lower(),
                    'material': cls.get_attribute_from_description(pcl.product.description, 'Materiał').lower(),
                    'condition': cls.get_attribute_from_description(pcl.product.description, 'Stan').lower(),
                    'channel_id': pcl.channel.id,
                    'channel_publication_date': pcl.publication_date,
                    'channel_age': cls.parse_date(pcl.publication_date),
                    'channel_is_published': pcl.is_published,
                    'channel_product_id': pcl.product_id,
                    'channel_slug': pcl.channel.slug,
                    'channel_visible_in_listings': pcl.visible_in_listings,
                    'channel_available_for_purchase': pcl.available_for_purchase,
                    'channel_currency': pvcl.currency,
                    'channel_price_amount': pvcl.price_amount,
                    'channel_cost_price_amount': pvcl.cost_price_amount,
                    'location': cls.parse_location(pvcl.variant.private_metadata.get('location'))
                }
            )

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
            return {'type': None, 'number': None, 'box': None}

        digits = re.findall('\d+', location)

        try:
            parsed_location = {
                'type': location[1],
                'number': int(digits[0]),
                'box': int(digits[1])
            }
        except IndexError:
            return {'type': None, 'number': None, 'box': None}

        return parsed_location


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
