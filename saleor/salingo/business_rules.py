from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
import logging
import re
from typing import List
import yaml

import rule_engine

from django.forms.models import model_to_dict
from django.core.exceptions import ValidationError

from saleor.channel.models import Channel
from saleor.product.models import Product, ProductVariantChannelListing, ProductChannelListing
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
        message = f'{datetime.now()} moved from channel' \
                  f'{product["channel"]} to channel {channel}'
        logger.info(f'{product["product_variant"]["sku"]} {message}')

        if mode == 'dry_run': return

        cls.change_product_channel(product=product, channel=channel)
        cls.log_to_product_history(product=product, message=message)

    @classmethod
    def calculate_price(cls, mode, product, result):
        # eg. results: "k23.40", "i123.00"
        current_price = product['product_variant_channellisting']['price_amount']
        result_price = Decimal(result[1:])
        weight = Decimal(product['product']['weight'].value)
        price_mode = result[:1]

        if price_mode == PriceEnum.KILOGRAM.value:
            price = weight * result_price
        elif price_mode == PriceEnum.ITEM.value:
            price = result_price
        elif price_mode == PriceEnum.DISCOUNT.value:
            price = current_price * result_price / 100
        else:
            return

        message = f'{datetime.now()} calculated price for channel ' \
                  f'{product["channel"]} {PriceEnum(price_mode).name} {price}'

        logger.info(f'{product["product_variant"]["sku"]}: {message}')

        if mode == 'dry_run': return

        variant_id = product['product_variant']['id']
        variant_channel_listing = ProductVariantChannelListing.objects.get(variant_id=variant_id)
        variant_channel_listing.price_amount = price
        variant_channel_listing.save(update_fields=['price_amount'])

        cls.log_to_product_history(product=product, message=message)

    @classmethod
    def change_product_channel(cls, product, channel):
        channel = Channel.objects.get(slug=channel)
        product_id = product['product']['id']
        variant_id = product['product_variant']['id']

        product_channel_listing = ProductChannelListing.objects.get(
            product_id=product_id)
        variant_channel_listing = ProductVariantChannelListing.objects.get(
            variant_id=variant_id)

        product_channel_listing.channel = channel
        variant_channel_listing.channel = channel

        product_channel_listing.save(update_fields=['channel'])
        variant_channel_listing.save(update_fields=['channel'])

    @classmethod
    def log_to_product_history(cls, product, message):
        product_id = product['product']['id']
        product_instance = Product.objects.get(pk=product_id)
        history = product_instance.private_metadata.get('history')

        if history:
            product_instance.private_metadata['history'].append('message')
        else:
            product_instance.private_metadata['history'] = [message]

        product_instance.save(update_fields=['private_metadata'])
        # TODO: []history pole i cena tez


class Resolvers:

    @classmethod
    def resolve_unpublished(cls):
        return cls.get_products_custom_dict(channel='unpublished')

    @classmethod
    def get_products_custom_dict(cls, channel):
        product_variant_channel_listing = ProductVariantChannelListing.objects.filter(
            channel__slug=channel).select_related('variant', 'variant__product')

        product_ids = [pvcl.variant.product.id for pvcl in product_variant_channel_listing]
        product_channel_listings = ProductChannelListing.objects.filter(
            product_id__in=product_ids).select_related('channel')

        product_fields_to_exclude = ['private_metadata', 'seo_title', 'seo_description',
                                     'description', 'description_plaintext']

        products = []
        # TODO: validate if pcl is correct
        for pvcl, pcl in zip(product_variant_channel_listing, product_channel_listings):
            products.append(
                {
                    'product': model_to_dict(pvcl.variant.product, exclude=product_fields_to_exclude),
                    'product_variant': model_to_dict(pvcl.variant, exclude=['media']),
                    'product_variant_channellisting': model_to_dict(pvcl),
                    'product_channel_listing': model_to_dict(pcl),
                    'channel': pcl.channel.slug
                }
            )
        # transform location format
        for product in products:
            location = product.get('product_variant').get('private_metadata').get('location')
            product['product_variant']['location'] = cls.parse_location(location)

        return products

    @staticmethod
    def parse_location(location):
        # eg. input: R01K01
        if location is None:
            return {'type': None, 'number': None, 'box': None}

        digits = re.findall('\d+', location)

        parsed_location = {
            'type': location[0],
            'number': int(digits[0]),
            'box': int(digits[1])
        }

        return parsed_location


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


class PriceEnum(Enum):
    DISCOUNT = 'd'
    ITEM = 'i'
    KILOGRAM = 'k'
    MANUAL = 'm'
