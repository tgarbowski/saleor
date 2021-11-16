import logging
import re
from typing import List
import yaml

import rule_engine

from django.core.exceptions import ValidationError
from django.forms.models import model_to_dict

from ..base_plugin import BasePlugin
from saleor.channel.models import Channel
from saleor.product.models import ProductVariantChannelListing, ProductChannelListing
from saleor.plugins.models import PluginConfiguration
from saleor.plugins.error_codes import PluginErrorCode


PluginConfigurationType = List[dict]

logger = logging.getLogger(__name__)


class SalingoRoutingPlugin(BasePlugin):
    PLUGIN_NAME = "Salingo routing"
    PLUGIN_ID = "salingo_routing"
    DEFAULT_ACTIVE = True
    DEFAULT_CONFIGURATION = []
    PLUGIN_DESCRIPTION = ("Salingo routing configuration")
    # CONFIGURATION_PER_CHANNEL = True
    CONFIG_STRUCTURE = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configuration = {item["name"]: item["value"] for item in self.configuration}

    def rotate_products_channels(self):
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
            products = resolver_function()
            # Check rules
            for product in products:
                for rule in engine_rules:
                    rule_object = rule_engine.Rule(rule['rule'])
                    if rule_object.matches(product):
                        executor_function = getattr(Executors, executor)
                        executor_function(product, rule['result'])
                        break

    def get_sorted_configs(self):
        configs = PluginConfiguration.objects.filter(identifier='salingo_routing')
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

    @classmethod
    def validate_plugin_configuration(self, plugin_configuration: "PluginConfiguration"):
        config = plugin_configuration.configuration
        yaml_rules = self.get_value_by_name(config=config, name='rules')
        engine_rules = self.get_rules(yaml_rules)

        try:
            self.validate_rules(engine_rules)
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


class Executors:

    @classmethod
    def move_from_unpublished(cls, product, result):
        cls.change_product_channel(product=product, channel=result)

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


class Resolvers:

    @classmethod
    def resolve_unpublished(cls):
        return cls.get_products_custom_dict(channel='unpublished')

    @classmethod
    def get_products_custom_dict(cls, channel):
        product_variant_channel_listing = ProductVariantChannelListing.objects.filter(
            channel__slug=channel).select_related('variant', 'variant__product')[:5]

        product_ids = [pvcl.variant.product.id for pvcl in product_variant_channel_listing]
        product_channel_listings = ProductChannelListing.objects.filter(product_id__in=product_ids)

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
                    'product_channel_listing': model_to_dict(pcl)
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
