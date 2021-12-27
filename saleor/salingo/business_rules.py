from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
import logging
import re
from typing import List
import yaml

import pytz
import rule_engine

from django.core.exceptions import ValidationError
from django.db import transaction

from saleor.channel.models import Channel
from saleor.product.models import (Category, Product, ProductVariantChannelListing,
                                   ProductChannelListing)
from saleor.plugins.models import PluginConfiguration
from saleor.plugins.base_plugin import BasePlugin, ConfigurationTypeField
from saleor.plugins.error_codes import PluginErrorCode


PluginConfigurationType = List[dict]

logger = logging.getLogger(__name__)


class BusinessRulesEvaluator:
    def __init__(self, plugin_slug, mode):
        self.plugin_slug = plugin_slug
        self.mode = mode

    def evaluate_rules(self):
        sorted_configs = self.get_sorted_configs()

        for config in sorted_configs:
            ruleset = self.get_value_by_name(config=config, name='ruleset')
            yaml_rules = self.get_value_by_name(config=config, name='rules')
            resolver = self.get_value_by_name(config=config, name='resolver')
            executor = self.get_value_by_name(config=config, name='executor')
            logger.info(f'Przetwarzam ruleset: {ruleset} w trybie {self.mode}')
            engine_rules = self.get_rules(yaml_rules)
            self.validate_rules(engine_rules)
            # Resolve products for given config
            resolver_function = getattr(Resolvers, resolver)
            products = resolver_function()
            # Check rules
            for product in products:
                for rule in engine_rules:
                    rule_object = rule_engine.Rule(rule['rule'])
                    if rule_object.matches(product):
                        executor_function = getattr(Executors, executor)
                        executor_function(self.mode, product, rule['result'])
                        break

    def get_sorted_configs(self):
        configs = PluginConfiguration.objects.filter(identifier=self.plugin_slug, active=True)
        configs_dict = [config.configuration for config in configs]
        return sorted(configs_dict, key=lambda single_config: self.get_value_by_name(single_config, 'execute_order'))

    @staticmethod
    def get_value_by_name(config, name):
        for item in config:
            if item['name'] == name:
                return item['value']

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

    @classmethod
    def move_from_unpublished(cls, mode, product, channel):
        message = f'{datetime.now()} moved from channel ' \
                  f'{product["channel"]["slug"]} to channel {channel}'
        logger.info(f'{product["sku"]} {message}')

        if mode == 'dry_run': return

        cls.change_product_channel(product=product, channel=channel)
        cls.log_to_product_history(product=product, message=message)

    @classmethod
    def calculate_price(cls, payload: "PricingVariables"):
        if payload.price_mode == PriceEnum.KILOGRAM.value:
            price = payload.weight * payload.result_price
        elif payload.price_mode == PriceEnum.ITEM.value:
            price = payload.result_price
        elif payload.price_mode == PriceEnum.DISCOUNT.value:
            price = payload.current_price - (payload.current_price * payload.result_price / 100)
        elif payload.price_mode == PriceEnum.MANUAL.value:
            price = payload.current_price
        else:
            price = payload.current_price

        return round(price, 2)

    @classmethod
    def get_validated_pricing_variables(cls, current_price, weight, result):
        if not isinstance(result, str):
            return None

        price_mode = result[:1]

        if price_mode not in [e.value for e in PriceEnum]:
            return None

        try:
            result_price = Decimal(result[1:])
        except InvalidOperation:
            return None

        if weight is None:
            return None

        return PricingVariables(
            price_mode=price_mode,
            current_price=current_price,
            result_price=result_price,
            weight=Decimal(weight.kg)
        )


    @classmethod
    def change_price(cls, mode, product, result):
        validated_pricing_variables = cls.get_validated_pricing_variables(
            current_price=product['channel']['price_amount'],
            weight=product['weight'],
            result=result
        )

        if validated_pricing_variables is None: return

        price = cls.calculate_price(validated_pricing_variables)

        message = f'{datetime.now()} calculated price for channel ' \
                  f'{product["channel"]["slug"]} {PriceEnum(validated_pricing_variables.price_mode).name} {price}'

        logger.info(f'{product["sku"]}: {message}')

        if mode == 'dry_run': return

        ProductVariantChannelListing.objects.filter(variant_id=product['variant_id']).update(price_amount=price)

        cls.log_to_product_history(product=product, message=message)

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
    def log_to_product_history(cls, product, message):
        product_id = product['id']
        product_instance = Product.objects.get(pk=product_id)
        history = product_instance.private_metadata.get('history')

        if history:
            product_instance.private_metadata['history'].append('message')
        else:
            product_instance.private_metadata['history'] = [message]

        product_instance.save(update_fields=['private_metadata'])


class Resolvers:

    @classmethod
    def resolve_unpublished(cls):
        return cls.get_products_custom_dict(channel='unpublished')

    @classmethod
    def resolve_allegro_unpublished(cls):
        filters = {"is_published": False}
        return cls.get_products_custom_dict(channel='allegro', filters=filters)

    @classmethod
    def resolve_allegro(cls):
        return cls.get_products_custom_dict(channel='allegro')

    @classmethod
    def get_products_custom_dict(cls, channel, filters={}):
        LIMIT = 10000

        product_channel_listings = ProductChannelListing.objects.filter(
            channel__slug=channel, **filters
        ).select_related('channel', 'product').order_by('product_id')[:LIMIT]

        product_ids = [pcl.product.id for pcl in product_channel_listings]

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
                    'type': pvcl.variant.product.product_type.slug,
                    'name': pvcl.variant.product.name,
                    'slug': pvcl.variant.product.slug,
                    'category': pvcl.variant.product.category.slug,
                    'root_category': cls.get_root_category(category_tree_ids,
                                                           pvcl.variant.product.category.tree_id),
                    'weight': pvcl.variant.product.weight,
                    'age': cls.parse_datetime(pvcl.variant.product.created_at),
                    'sku': pvcl.variant.sku,
                    'brand': cls.get_attribute_from_description(pcl.product.description, 'Marka'),
                    'material': cls.get_attribute_from_description(pcl.product.description, 'Materiał'),
                    'condition': cls.get_attribute_from_description(pcl.product.description, 'Stan'),
                    'channel': {
                        'id': pcl.channel.id,
                        'publication_date': pcl.publication_date,
                        'age': cls.parse_date(pcl.publication_date),
                        'is_published': pcl.is_published,
                        'product_id': pcl.product_id,
                        'slug': pcl.channel.slug,
                        'visible_in_listings': pcl.visible_in_listings,
                        'available_for_purchase': pcl.available_for_purchase,
                        'currency': pvcl.currency,
                        'price_amount': pvcl.price_amount,
                        'cost_price_amount': pvcl.cost_price_amount
                    },
                    'location': cls.parse_location(pvcl.variant.private_metadata.get('location'))
                }
            )

        return products

    @staticmethod
    def get_attribute_from_description(description, attribute_name):
        for block in description.get('blocks'):
            text = block.get('data').get('text')

            if text and attribute_name in text:
                return text.partition(":")[2].lower()

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
        delta = datetime.now(pytz.timezone('Europe/Warsaw')) - publication_date
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
    current_price: Decimal
    result_price: Decimal
    weight: Decimal


class PriceEnum(Enum):
    DISCOUNT = 'd'
    ITEM = 'i'
    KILOGRAM = 'k'
    MANUAL = 'm'


@dataclass
class BusinessRulesConfiguration:
    ruleset: str
    execute_order: int
    resolver: str
    executor: str


class BusinessRulesBasePlugin(BasePlugin):
    DEFAULT_CONFIGURATION = [
        {"name": "ruleset", "value": ""},
        {"name": "execute_order", "value": ""},
        {"name": "resolver", "value": ""},
        {"name": "executor", "value": ""},
        {"name": "rules", "value": ""}
    ]
    CONFIG_STRUCTURE = {
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configuration = {item["name"]: item["value"] for item in self.configuration}

        self.config = BusinessRulesConfiguration(
            ruleset=configuration["ruleset"],
            execute_order=configuration["execute_order"],
            resolver=configuration["resolver"],
            executor=configuration["executor"]
        )

    @classmethod
    def validate_plugin_configuration(self, plugin_configuration: "PluginConfiguration"):
        config = plugin_configuration.configuration
        yaml_rules = BusinessRulesEvaluator.get_value_by_name(config=config, name='rules')
        engine_rules = BusinessRulesEvaluator.get_rules(yaml_rules)

        try:
            BusinessRulesEvaluator.validate_rules(engine_rules)
        except Exception as e:
            raise ValidationError(
                {
                    "rules": ValidationError(
                        "Invalid engine rule.",
                        code=PluginErrorCode.INVALID.value,
                    )
                }
            )

    @classmethod
    def _append_config_structure(cls, configuration: PluginConfigurationType):
        config_structure = getattr(cls, "CONFIG_STRUCTURE") or {}

        for configuration_field in configuration:

            structure_to_add = config_structure.get(configuration_field.get("name"))
            if structure_to_add:
                configuration_field.update(structure_to_add)
