from dataclasses import dataclass
from typing import List
import re
import logging
import yaml

import rule_engine

from ..base_plugin import BasePlugin

from saleor.product.models import ProductVariantChannelListing, ProductChannelListing
from django.forms.models import model_to_dict
from saleor.plugins.manager import get_plugins_manager
from saleor.plugins.models import PluginConfiguration


PluginConfigurationType = List[dict]

logger = logging.getLogger(__name__)

@dataclass
class SalingoRoutingConfiguration:
    username: str


class SalingoRoutingPlugin(BasePlugin):
    PLUGIN_NAME = "Salingo routing"
    PLUGIN_ID = "salingo_routing"
    DEFAULT_ACTIVE = True
    DEFAULT_CONFIGURATION = []
    PLUGIN_DESCRIPTION = (
        "Salingo routing configuration"
    )
    #CONFIGURATION_PER_CHANNEL = True
    CONFIG_STRUCTURE = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configuration = {item["name"]: item["value"] for item in self.configuration}
        self.rules_bulk()


    def rules_bulk(self):
        custom_dict = self.get_custom_dict()

        configs = PluginConfiguration.objects.filter(identifier='salingo_routing')

        configs_dict = []

        for config in configs:
            configs_dict.append(config.configuration)

        sorted_configs = sorted(configs_dict, key=lambda single_config: self.sort_by_order(single_config))
        engine_rules = []

        for config in sorted_configs:
            logger.info('Przetwarzam ruleset')
            rules = yaml.safe_load(config[4]['value'])
            for rule in rules:
                r = rule['rule']
                if (rule_engine.Rule.is_valid(r)):
                    engine_rules.append(rule_engine.Rule(r))
                else:
                    print("Invalid rule: " + r)

        for product in custom_dict:
            for rule in engine_rules:
                is_match = rule.matches(product)
                print('is_match', is_match)


    @staticmethod
    def sort_by_order(config):
        for item in config:
            if item['name'] == 'execute_order':
                return item['value']


    @staticmethod
    def plugin_configuration(channel):
        manager = get_plugins_manager()
        plugin = manager.get_plugin(
            plugin_id='salingo_routing',
            channel_slug=channel)
        configuration = {item["name"]: item["value"] for item in plugin.configuration if
                         plugin.configuration}
        return configuration


    def get_custom_dict(self):
        product_skus = ['010320091000121', '010320091000123', '010320092100001', '010320091000124']
        variant_ids = [153623, 153641, 153650, 153661]

        product_variant_channel_listing = ProductVariantChannelListing.objects.filter(
            variant_id__in=variant_ids).select_related(
                'variant', 'variant__product'
        )

        product_ids = [pvcl.variant.product.id for pvcl in product_variant_channel_listing]
        product_channel_listings = ProductChannelListing.objects.filter(product_id__in=product_ids)

        product_fields_to_exclude = ['private_metadata', 'seo_title', 'seo_description',
                                     'description', 'description_plaintext']

        xds = []
        # TODO: zwalidowac, czy pcl się zgadza
        for xd, sd in zip(product_variant_channel_listing, product_channel_listings):
            xds.append(
                {
                    'product': model_to_dict(xd.variant.product, exclude=product_fields_to_exclude),
                    'product_variant': model_to_dict(xd.variant, exclude=['media']),
                    'product_variant_channellisting': model_to_dict(xd),
                    'product_channel_listing': model_to_dict(sd)
                }
            )
        # TODO: niektóre produkty nie mają lokacji
        for record in xds:
            #record['product_variant']['location'] = self.parse_location(record['product_variant']['private_metadata']['location'])
            record['product_variant']['location'] = self.parse_location('R01K100')

        return xds


    @staticmethod
    def parse_location(location):
        # eg. input: R01K01
        digits = re.findall('\d+', location)

        parsed_location = {
            'type': location[0],
            'number': int(digits[0]),
            'box': int(digits[1])
        }

        return parsed_location


    @classmethod
    def _append_config_structure(cls, configuration: PluginConfigurationType):
        config_structure = getattr(cls, "CONFIG_STRUCTURE") or {}

        for configuration_field in configuration:

            structure_to_add = config_structure.get(configuration_field.get("name"))
            if structure_to_add:
                configuration_field.update(structure_to_add)
