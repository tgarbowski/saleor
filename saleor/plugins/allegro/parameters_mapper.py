import json
from typing import Dict

from slugify import slugify

from .utils import get_plugin_configuration
from saleor.attribute.models.product import AssignedProductAttribute
from saleor.product.models import ProductVariant
from saleor.attribute.models import AssignedProductAttributeValue


class ParametersMapperFactory:

    @staticmethod
    def get_mapper(channel):
        mapper = ParametersMapper(mapper=AllegroParametersMapper, channel=channel).mapper()
        return mapper


class ParametersMapper:

    def __init__(self, mapper, channel):
        self.mapper = mapper
        self.mapper.channel = channel

    def mapper(self):
        return self.mapper.map()


class BaseParametersMapper:
    def map(self):
        return self

    @staticmethod
    def parse_parameters_name(parameters):
        return parameters.lower().replace(' ', '-')

    def set_product(self, product):
        self.product = product
        return self

    def set_product_attributes(self, product_attributes):
        self.product_attributes = product_attributes
        return self

    def set_require_parameters(self, require_parameters):
        self.require_parameters = require_parameters
        return self

    def get_product_attributes(self):
        attributes = {}
        attributes_metadata = {}
        assigned_product_attributes = AssignedProductAttribute.objects.filter(product=self.product)
        attributes_values = AssignedProductAttributeValue.objects.select_related(
            'assignment__assignment__attribute', 'value'
        ).filter(assignment__in=assigned_product_attributes)

        for attribute in attributes_values:
            attributes_metadata[attribute.assignment.attribute.slug] = attribute.assignment.attribute.metadata
            attributes[attribute.assignment.attribute.slug] = attribute.value.name
        # Transform "joinTo" attributes
        return self.transform_join_to_attributes(attributes, attributes_metadata)

    @staticmethod
    def transform_join_to_attributes(attributes, attributes_metadata):
        for attribute in attributes.keys():
            join_to = attributes_metadata[attribute].get('joinTo')
            if join_to:
                separator = attributes_metadata[attribute].get('separator')
                join_to_slugs = join_to.split(',')
                for join_to_slug in join_to_slugs:
                    if attributes.get(join_to_slug):
                        produced_string = separator if separator else ''
                        attributes[join_to_slug] += produced_string + attributes[attribute]

        return attributes

    def create_allegro_parameter(self, mapped_parameter_key, mapped_parameter_value):
        key = self.get_allegro_key(mapped_parameter_key)

        if not mapped_parameter_value or not key or self.is_parameter_ambigous_and_custom(key):
            return

        if key.get('dictionary') is None:
            if mapped_parameter_value.replace('.', '').isnumeric():
                return self.set_allegro_typed_value(key, mapped_parameter_value)
            elif key.get('restrictions') and key.get('restrictions').get('range') and '-' in mapped_parameter_value:
                return self.set_allegro_typed_range_value(key, mapped_parameter_value)
        else:
            return self.set_allegro_value(key, mapped_parameter_value)

    def is_parameter_ambigous_and_custom(self, key):
        ambigous_value_id = key.get('options', {}).get('ambiguousValueId')
        required_for_product = key.get('requiredForProduct')
        custom_options_enabled = key.get('options', {}).get('customValuesEnabled')
        return all([ambigous_value_id, required_for_product, custom_options_enabled])

    def get_allegro_key(self, key):
        return next((param for param in self.require_parameters if slugify(param["name"]) == key), None)

    @staticmethod
    def set_allegro_value(param, mapped_value):
        value = next((value for value in param['dictionary'] if
                      value["value"].lower() == mapped_value.lower()), None)
        if value:
            return {'id': param['id'], 'valuesIds': [value['id']], "values": None, "rangeValue": None}

    @staticmethod
    def set_allegro_fuzzy_value(param, mapped_value):
        if param.get('dictionary'):
            value = next((value for value in param['dictionary'] if
                          mapped_value.lower()[:-1] in value["value"].lower()), None)
            if value:
                return {'id': param['id'], 'valuesIds': [value['id']], "values": None, "rangeValue": None}

    @staticmethod
    def set_allegro_typed_value(param, value):
        if param.get('dictionary') is None and value:
            return {'id': param['id'], 'valuesIds': None, "values": [value], "rangeValue": None}

    @staticmethod
    def set_allegro_typed_range_value(param, value):
        if param.get('dictionary') is None and value:
            splited = value.split('-')
            return {'id': param['id'], 'valuesIds': None,
                    "values": None, "rangeValue": {'from': splited[0], 'to': splited[1]}}

    def create_allegro_fuzzy_parameter(self, mapped_parameter_key, mapped_parameter_value):
        key = self.get_allegro_key(mapped_parameter_key)
        if key and key.get('dictionary'):
            return self.set_allegro_fuzzy_value(key, mapped_parameter_value)


class AllegroParametersMapper(BaseParametersMapper):
    def __init__(self):
        self.mapped_parameters = []
        self.plugin_config = get_plugin_configuration(plugin_id='allegro_global')

    def run_mapper(self, parameters_type):

        attributes = self.get_product_attributes()

        self.set_product_attributes(attributes)

        for require_parameter in self.require_parameters:
            allegro_parameter = self.get_allegro_parameter(require_parameter['name'])
            if allegro_parameter is not None:
                self.mapped_parameters.append(allegro_parameter)

        producer_code = [element for element in self.require_parameters if element['name'] == 'Kod producenta']

        if producer_code:
            product_id = self.product.id
            self.mapped_parameters.append(
                self.producer_code_parameter(product_id, producer_code[0]))

        return self.mapped_parameters

    def producer_code_parameter(self, product_id, element):
        product_variant = ProductVariant.objects.filter(product_id=product_id).first()
        sku = product_variant.sku

        producer_code = {
            "id": element['id'],
            "values": [
                sku
            ]
        }
        return producer_code

    def get_parameter_key_from_product_type_metadata(self, parameter):
        if parameter == 'Materiał dominujący':
            return 'Materiał'

        custom_map = self.product.product_type.metadata.get('allegro.mapping.attributes')
        if custom_map is not None:
            if isinstance(custom_map, str):
                custom_map = json.loads(custom_map.replace('\'', '\"'))
            custom_map = [m for m in custom_map if '*' not in m]
            if custom_map:
                return self.parse_attributes_to_map(custom_map).get(parameter)

    def get_global_parameter_key(self, parameter):
        custom_map = self.plugin_config.get('allegro.mapping.' + self.parse_parameters_name(parameter))

        if custom_map:
            if isinstance(custom_map, str):
                return self.parse_list_to_map(
                    json.loads(custom_map.replace('\'', '\"'))).get(parameter)
            elif isinstance(custom_map, list):
                return self.parse_list_to_map(custom_map).get(parameter)
            else:
                return self.parse_list_to_map(json.loads(custom_map)).get(parameter)

    @staticmethod
    def parse_list_to_map(list_in):
        if len(list_in) > 0 and len(list_in[0]) == 2:
            return {item[0]: item[1] for item in list_in}
        elif len(list_in) > 0 and len(list_in[0]) == 3:
            return {item[0]: item[2] for item in list_in}

    @staticmethod
    def parse_attributes_to_map(list_in):
        return {item[0]: item[1:] for item in list_in}

    def get_mapped_parameter_key(self, parameter):
        mapped_parameter_key = (
            self.get_parameter_key_from_product_type_metadata(parameter)
            or self.get_global_parameter_key(parameter)
            or parameter
        )

        if type(mapped_parameter_key) == list:
            if len(mapped_parameter_key) == 1:
                return mapped_parameter_key[0]
            elif len(mapped_parameter_key) == 2:
                return mapped_parameter_key[1]

        return mapped_parameter_key

    def get_value_from_product_attributes(self, mapped_parameter_key):
        return self.product_attributes.get(slugify(str(mapped_parameter_key)))

    def get_value_from_product_type_metadata(self, parameter):
        custom_map = self.product.product_type.metadata.get('allegro.mapping.attributes')
        if custom_map is not None:
            if isinstance(custom_map, str):
                custom_map = json.loads(custom_map.replace('\'', '\"'))
            custom_map = [m for m in custom_map if len(m) == 3]
            if custom_map:
                return self.parse_list_to_map(custom_map).get(parameter)

    def get_parameter_out_of_saleor_global(self, parameter):
        return self.get_global_parameter_map(parameter).get("*")

    def get_value_one_to_one_global(self, parameter, value):
        return self.get_global_parameter_map(parameter).get(value)

    def get_universal_value_parameter(self, parameter):
        return self.get_global_parameter_map(parameter).get("!")

    def get_global_parameter_map(self, parameter) -> Dict:
        custom_map = self.plugin_config.get('allegro.mapping.' + parameter)
        if isinstance(custom_map, str):
            return self.parse_list_to_map(json.loads(custom_map.replace('\'', '\"')))
        return {}

    def get_allegro_parameter(self, parameter):
        mapped_parameter_key = self.get_mapped_parameter_key(parameter)
        mapped_parameter_value = self.get_value_from_product_type_metadata(str(mapped_parameter_key))

        slugified_parameter = slugify(parameter)
        slugified_mapped_parameter_key = slugify(mapped_parameter_key)

        allegro_parameter = self.create_allegro_parameter(slugified_parameter, mapped_parameter_value)

        if allegro_parameter is None:
            mapped_parameter_value = self.get_value_from_product_attributes(mapped_parameter_key)
            self.create_allegro_parameter(slugified_parameter, mapped_parameter_value)

        if allegro_parameter is None:
            mapped_parameter_value = self.get_value_one_to_one_global(
                slugified_mapped_parameter_key,
                mapped_parameter_value
            )
            allegro_parameter = self.create_allegro_parameter(slugified_parameter, mapped_parameter_value)

        if allegro_parameter is None:
            mapped_parameter_value = self.get_parameter_out_of_saleor_global(slugified_mapped_parameter_key)
            allegro_parameter = self.create_allegro_parameter(slugified_parameter, mapped_parameter_value)

        if allegro_parameter is None:
            mapped_parameter_value = self.get_universal_value_parameter(slugified_parameter)
            allegro_parameter = self.create_allegro_parameter(slugified_parameter, mapped_parameter_value)

        if allegro_parameter is None:
            if mapped_parameter_value is None:
                mapped_parameter_value = self.get_parameter_out_of_saleor_global(
                    slugified_mapped_parameter_key) or self.product_attributes.get(slugify(str(mapped_parameter_key)))
            allegro_parameter = self.create_allegro_fuzzy_parameter(slugified_parameter, str(mapped_parameter_value))

        if allegro_parameter is None:
            if mapped_parameter_value is None:
                if 'rozmiar-buty-damskie' in self.product_attributes:
                    key = 'rozmiar-buty-damskie-' + self.product_attributes.get('rozmiar-buty-damskie')
                    mapped_parameter_value = self.get_value_one_to_one_global(slugified_mapped_parameter_key, key)
                if 'rozmiar-buty-meskie' in self.product_attributes:
                    key = 'rozmiar-buty-meskie-' + self.product_attributes.get('rozmiar-buty-meskie')
                    mapped_parameter_value = self.get_value_one_to_one_global(slugified_mapped_parameter_key, key)
                allegro_parameter = self.create_allegro_parameter(slugified_parameter, mapped_parameter_value)

        return allegro_parameter
