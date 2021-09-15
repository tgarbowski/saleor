import json

from slugify import slugify

from .utils import get_plugin_configuration
from saleor.product.models import AssignedProductAttribute, AttributeValue, ProductVariant


class ParametersMapperFactory:

    @staticmethod
    def get_mapper():
        mapper = ParametersMapper(AllegroParametersMapper).mapper()
        return mapper


class ParametersMapper:

    def __init__(self, mapper):
        self.mapper = mapper

    def mapper(self):
        return self.mapper.map()


class BaseParametersMapper:

    def __init__(self):
        self.mapped_parameters = []
        self.plugin_config = get_plugin_configuration()

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

        assigned_product_attributes = AssignedProductAttribute.objects.filter(
            product=self.product)

        attributes = {}

        for assigned_product_attribute in assigned_product_attributes:
            try:
                attribute_id = assigned_product_attribute.assignment.attribute_id

                attributes[slugify(
                    str(assigned_product_attribute.assignment.attribute.slug))] = \
                    str(AttributeValue.objects.filter(
                        attribute_id=attribute_id))

            except AttributeValue.DoesNotExist:
                pass

        attributes_name = attributes.keys()

        return attributes, attributes_name

    # TODO: rebuild, too much if conditionals, and add case when dictionary is empty
    #  like for bluzki dzieciece
    def create_allegro_parameter(self, mapped_parameter_key, mapped_parameter_value):
        key = self.get_allegro_key(mapped_parameter_key)
        if key.get('dictionary') is None:
            if mapped_parameter_value is not None:
                if mapped_parameter_value.replace('.', '').isnumeric():
                    value = self.set_allegro_typed_value(key, mapped_parameter_value)
                    return value
                elif key.get('restrictions') and key.get('restrictions').get('range'):
                    if '-' in mapped_parameter_value:
                        value = self.set_allegro_typed_range_value(key, mapped_parameter_value)
                        return value
                else:
                    return None
            else:
                return None
        else:
            value = self.set_allegro_value(key, mapped_parameter_value)
            return value

    def get_allegro_key(self, key):
        param = next((param for param in self.require_parameters if
                      slugify(param["name"]) == key), None)
        return param

    @staticmethod
    def set_allegro_value(param, mapped_value):
        if mapped_value is not None:
            value = next((value for value in param['dictionary'] if
                          value["value"].lower() == mapped_value.lower()), None)
            if value is not None:
                return {'id': param['id'], 'valuesIds': [value['id']], "values": [],
                        "rangeValue": None}

    @staticmethod
    def set_allegro_fuzzy_value(param, mapped_value):
        if param.get('dictionary') is not None:
            value = next((value for value in param['dictionary'] if
                          mapped_value.lower()[:-1] in value["value"].lower()), None)
            if value is not None:
                return {'id': param['id'], 'valuesIds': [value['id']], "values": [],
                        "rangeValue": None}

    @staticmethod
    def set_allegro_typed_value(param, value):
        if param.get('dictionary') is None and value is not None:
            return {'id': param['id'], 'valuesIds': [],
                    "values": [value], "rangeValue": None}

    @staticmethod
    def set_allegro_typed_range_value(param, value):
        if param.get('dictionary') is None and value is not None:
            splited = value.split('-')
            return {'id': param['id'], 'valuesIds': [],
                    "values": [], "rangeValue": {'from': splited[0], 'to': splited[1]}}

    def create_allegro_fuzzy_parameter(self, mapped_parameter_key,
                                       mapped_parameter_value):
        key = self.get_allegro_key(mapped_parameter_key)
        if key is not None and key.get('dictionary') is not None:
            value = self.set_allegro_fuzzy_value(key, mapped_parameter_value)
            return value


class AllegroParametersMapper(BaseParametersMapper):

    def map(self):
        return self

    def run_mapper(self, parameters_type):

        attributes, attributes_name = self.get_product_attributes()

        self.set_product_attributes(attributes)

        for require_parameter in self.require_parameters:
            allegro_parameter = self.get_allegro_parameter(require_parameter['name'])
            if allegro_parameter is not None:
                self.mapped_parameters.append(allegro_parameter)

        producer_code = [element for element in self.require_parameters if element['name'] == 'Kod producenta']

        if parameters_type == 'requiredForProduct':
            for param, mapped in zip(self.require_parameters, self.mapped_parameters):
                try:
                    if param['options']['ambiguousValueId'] == mapped['valuesIds'][0] and param['options']['customValuesEnabled']:
                        mapped['values'] = ['inny']
                except IndexError:
                    pass
                if param.get('restrictions').get('range') is False:
                    del mapped['rangeValue']
                    del mapped['valuesIds']

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

    def get_specific_parameter_key(self, parameter):

        if parameter == 'Materiał dominujący':
            return 'Materiał'

        custom_map = self.product.product_type.metadata.get(
            'allegro.mapping.attributes')
        if custom_map is not None:
            custom_map = [m for m in custom_map if '*' not in m]
            if bool(custom_map):
                return self.parse_attributes_to_map(custom_map).get(parameter)

    def get_global_parameter_key(self, parameter):
        config = self.plugin_config
        custom_map = config.get(
            'allegro.mapping.' + self.parse_parameters_name(parameter))
        if custom_map is not None:
            if bool(custom_map):
                if isinstance(custom_map, str):
                    return self.parse_list_to_map(
                        json.loads(custom_map.replace('\'', '\"'))).get(parameter)
                else:
                    if isinstance(custom_map, list):
                        return self.parse_list_to_map(custom_map).get(parameter)
                    else:
                        return self.parse_list_to_map(json.loads(custom_map)).get(
                            parameter)

    def get_global_parameter_map(self, parameter):
        config = self.plugin_config
        custom_map = config.get('allegro.mapping.' + parameter)
        if custom_map is not None:
            if isinstance(custom_map, str):
                return self.parse_list_to_map(
                    json.loads(custom_map.replace('\'', '\"')))
            else:
                pass
                # return self.parse_list_to_map((custom_map))

    @staticmethod
    def parse_list_to_map(list_in):
        if len(list_in) > 0 and len(list_in[0]) == 2:
            return {item[0]: item[1] for item in list_in}
        elif len(list_in) > 0 and len(list_in[0]) == 3:
            return {item[0]: item[2] for item in list_in}

    @staticmethod
    def parse_attributes_to_map(list_in):
        return {item[0]: item[1:] for item in list_in}

    def get_mapped_parameter_value(self, parameter):
        mapped_parameter_map = self.get_global_parameter_map(parameter)
        if mapped_parameter_map is not None and mapped_parameter_map.get(
                self.product_attributes.get(parameter)) is not None:
            return mapped_parameter_map.get(self.product_attributes.get(parameter))

        return self.product_attributes.get(parameter)

    def get_mapped_parameter_key_and_value(self, parameter):
        mapped_parameter_key_in_saleor_scope = None
        mapped_parameter_key = self.get_specific_parameter_key(
            parameter) or self.get_global_parameter_key(parameter) or parameter

        if type(mapped_parameter_key) == list:
            if len(mapped_parameter_key) < 2:
                mapped_parameter_key, *_ = mapped_parameter_key
            else:
                mapped_parameter_key, mapped_parameter_key_in_saleor_scope = mapped_parameter_key
        mapped_parameter_value = self.get_parameter_out_of_saleor_specyfic(str(
            mapped_parameter_key))
        if mapped_parameter_value is not None:
            return mapped_parameter_key, mapped_parameter_value, mapped_parameter_key_in_saleor_scope
        mapped_parameter_value = self.product_attributes.get(
            slugify(str(mapped_parameter_key)))

        return mapped_parameter_key, mapped_parameter_value, mapped_parameter_key_in_saleor_scope

    def get_parameter_out_of_saleor_specyfic(self, parameter):
        custom_map = self.product.product_type.metadata.get(
            'allegro.mapping.attributes')
        if custom_map is not None:
            if isinstance(custom_map, str):
                custom_map = json.loads(custom_map.replace('\'', '\"'))
            custom_map = [m for m in custom_map if '*' in m]
            if bool(custom_map):
                return self.parse_list_to_map(custom_map).get(parameter)

    def get_parameter_out_of_saleor_global(self, parameter):
        mapped_parameter_map = self.get_global_parameter_map(slugify(parameter))
        if mapped_parameter_map is not None:
            return mapped_parameter_map.get("*")

    def get_value_one_to_one_global(self, parameter, value):
        mapped_parameter_map = self.get_global_parameter_map(slugify(parameter))
        if mapped_parameter_map is not None:
            return mapped_parameter_map.get(value)

    def get_universal_value_parameter(self, parameter):
        mapped_parameter_map = self.get_global_parameter_map(parameter)
        if mapped_parameter_map is not None:
            return mapped_parameter_map.get("!")

    def get_shoe_size(self, parameter, key):
        mapped_parameter_map = self.get_global_parameter_map(slugify(parameter))
        if mapped_parameter_map is not None:
            return mapped_parameter_map.get(key)

    def get_allegro_parameter(self, parameter):
        mapped_parameter_key, mapped_parameter_value, mapped_parameter_key_in_saleor_scope = \
            self.get_mapped_parameter_key_and_value(parameter)
        if mapped_parameter_key_in_saleor_scope:
            mapped_parameter_key = mapped_parameter_key_in_saleor_scope
        allegro_parameter = self.create_allegro_parameter(slugify(parameter),
                                                          mapped_parameter_value)

        if allegro_parameter is None:
            mapped_parameter_value = self.get_value_one_to_one_global(
                mapped_parameter_key, mapped_parameter_value)
            allegro_parameter = self.create_allegro_parameter(slugify(parameter),
                                                              mapped_parameter_value)

        if allegro_parameter is None:
            mapped_parameter_value = self.get_parameter_out_of_saleor_global(
                mapped_parameter_key)
            allegro_parameter = self.create_allegro_parameter(slugify(parameter),
                                                              mapped_parameter_value)

        if allegro_parameter is None:
            mapped_parameter_value = self.get_universal_value_parameter(
                slugify(mapped_parameter_key))
            allegro_parameter = self.create_allegro_parameter(slugify(parameter),
                                                              mapped_parameter_value)

        if allegro_parameter is None:
            if mapped_parameter_value is None:
                mapped_parameter_value = self.get_parameter_out_of_saleor_global(
                    mapped_parameter_key) or self.product_attributes.get(
                    slugify(str(mapped_parameter_key)))
            allegro_parameter = self.create_allegro_fuzzy_parameter(slugify(parameter),
                                                                    str(
                                                                        mapped_parameter_value))

        if allegro_parameter is None:
            if mapped_parameter_value is None:
                if 'rozmiar-buty-damskie' in self.product_attributes:
                    key = 'rozmiar-buty-damskie-' + self.product_attributes.get(
                        'rozmiar-buty-damskie')
                    mapped_parameter_value = self.get_shoe_size(
                        slugify(mapped_parameter_key), key)
                if 'rozmiar-buty-meskie' in self.product_attributes:
                    key = 'rozmiar-buty-meskie-' + self.product_attributes.get(
                        'rozmiar-buty-meskie')
                    mapped_parameter_value = self.get_shoe_size(
                        slugify(mapped_parameter_key), key)
                allegro_parameter = self.create_allegro_parameter(slugify(parameter),
                                                        mapped_parameter_value)
        return allegro_parameter
