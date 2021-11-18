from decimal import Decimal
import logging
import re
from typing import List
import yaml

import rule_engine

from django.forms.models import model_to_dict
from django.core.exceptions import ValidationError

from saleor.channel.models import Channel
from saleor.product.models import ProductVariantChannelListing, ProductChannelListing
from saleor.plugins.models import PluginConfiguration
from saleor.plugins.base_plugin import BasePlugin
from saleor.plugins.error_codes import PluginErrorCode


PluginConfigurationType = List[dict]

logger = logging.getLogger(__name__)


class BusinessRulesEvaluator:
    def __init__(self, plugin_slug, dry_run):
        self.plugin_slug = plugin_slug
        self.dry_run = dry_run

    def evaluate_rules(self, **kwargs):
        sorted_configs = self.get_sorted_configs()

        for config in sorted_configs:
            logger.info('Przetwarzam ruleset')
            yaml_rules = self.get_value_by_name(config=config, name='rules')
            resolver = self.get_value_by_name(config=config, name='resolver')
            executor = self.get_value_by_name(config=config, name='executor')
            engine_rules = self.get_rules(yaml_rules)
            self.validate_rules(engine_rules)
            # Resolve products for given config
            resolver_function = getattr(Resolvers, resolver)
            products = resolver_function(**kwargs)
            # Check rules
            for product in products:
                for rule in engine_rules:
                    rule_object = rule_engine.Rule(rule['rule'])
                    if rule_object.matches(product):
                        logger.info(f'{product["product_variant"]["sku"]} moved from channel '
                                    f'{product["channel"]} to channel {rule["result"]}')
                        if self.dry_run: return
                        executor_function = getattr(Executors, executor)
                        executor_function(product, rule['result'])
                        break

    def get_sorted_configs(self):
        configs = PluginConfiguration.objects.filter(identifier=self.plugin_slug)
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
    def move_from_unpublished(cls, product, channel):
        pricing = BusinessRulesEvaluator('salingo_pricing')
        product['new_channel'] = channel
        pricing.evaluate_rules(product=product)
        cls.change_product_channel_and_price(product=product, channel=channel)

    @classmethod
    def calculate_price(cls, product, result):
        # eg. results: "k23.40", "i123.00"
        price = 0
        result_price = Decimal(result[1:])
        weight = Decimal(product['product']['weight'].value)

        if result.startswith('k'):
            price = weight * result_price
        elif result.startswith('i'):
            price = result_price

        product['product_variant_channellisting']['price_amount'] = price

    @classmethod
    def change_product_channel_and_price(cls, product, channel):
        channel = Channel.objects.get(slug=channel)
        product_id = product['product']['id']
        variant_id = product['product_variant']['id']
        price = product['product_variant_channellisting']['price_amount']

        product_channel_listing = ProductChannelListing.objects.get(
            product_id=product_id)
        variant_channel_listing = ProductVariantChannelListing.objects.get(
            variant_id=variant_id)

        product_channel_listing.channel = channel
        variant_channel_listing.channel = channel
        variant_channel_listing.price_amount = price

        product_channel_listing.save(update_fields=['channel'])
        variant_channel_listing.save(update_fields=['channel', 'price_amount'])


class Resolvers:

    @classmethod
    def resolve_unpublished(cls, **kwargs):
        return cls.get_products_custom_dict(channel='unpublished')

    @classmethod
    def resolve_product(cls, **kwargs):
        return [kwargs['product']]

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


class BusinessRulesBasePlugin(BasePlugin):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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
