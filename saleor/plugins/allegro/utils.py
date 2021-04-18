import json
import logging
import re
import uuid

from collections import defaultdict
from datetime import datetime, timedelta

import pytz
import requests
from slugify import slugify

from saleor.plugins.manager import get_plugins_manager
from saleor.product.models import AssignedProductAttribute, \
    AttributeValue, ProductVariant, Product

logger = logging.getLogger(__name__)

class AllegroAPI:
    token = None
    errors = []
    env = None

    def __init__(self, token, env):
        self.token = token
        self.errors = []
        self.env = env

    def refresh_token(self, refresh_token, client_id, client_secret,
                      saleor_redirect_url, url_env):

        logger.info('Refresh token')

        endpoint = 'auth/oauth/token?grant_type=refresh_token&refresh_token=' + \
                   refresh_token + '&redirect_uri=' + str(saleor_redirect_url)

        data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'redirect_uri': str(saleor_redirect_url),
        }

        response = self.auth_request(endpoint=endpoint, data=data, client_id=client_id,
                                     client_secret=client_secret, url_env=url_env)

        if response.status_code == 200:
            return json.loads(response.text)['access_token'], json.loads(response.text)[
                'refresh_token'], json.loads(response.text)['expires_in']
        else:
            logger.error(f"Refresh token error, status_code: {response.status_code}, "
                         f"response: {response.text}")
            return None

    def update_offer(self, saleor_product, starting_at, offer_type, product_images):
        offer_id = saleor_product.private_metadata.get('publish.allegro.id')
        category_id = saleor_product.product_type.metadata.get(
            'allegro.mapping.categoryId')
        require_parameters = self.get_require_parameters(category_id)
        parameters_mapper = ParametersMapperFactory().get_mapper()
        parameters = parameters_mapper.set_product(
            saleor_product).set_require_parameters(require_parameters).run_mapper()
        product_mapper = ProductMapperFactory().get_mapper()
        product = product_mapper.set_saleor_product(saleor_product) \
            .set_saleor_images(self.upload_images(product_images)) \
            .set_saleor_parameters(parameters).set_obj_publication_starting_at(
            starting_at).set_offer_type(offer_type).set_category(
            category_id).run_mapper()
        offer = self.update_allegro_offer(allegro_product=product, allegro_id=offer_id)
        return offer

    @staticmethod
    def get_plugin_configuration():
        manager = get_plugins_manager()
        plugin = manager.get_plugin('allegro')
        configuration = {item["name"]: item["value"] for item in plugin.configuration}
        return configuration

    def publish_to_allegro(self, allegro_product):

        endpoint = 'sale/offers'

        try:
            response = self.post_request(endpoint=endpoint, data=allegro_product)
            return json.loads(response.text)
        except AttributeError as err:
            self.errors.append('Publish to Allegro error: ' + str(err))
            logger.error('Publish to Allegro error: ' + str(err))
            return None

    def update_allegro_offer(self, allegro_product, allegro_id):

        endpoint = 'sale/offers/' + allegro_id

        allegro_product['id'] = allegro_id

        response = self.put_request(endpoint=endpoint, data=allegro_product)
        return json.loads(response.text)

    def post_request(self, endpoint, data):
        try:
            url = self.env + '/' + endpoint

            headers = {'Authorization': 'Bearer ' + self.token,
                       'Accept': 'application/vnd.allegro.public.v1+json',
                       'Content-Type': 'application/vnd.allegro.public.v1+json'}

            logger.info("Post request url: " + str(url))
            logger.info("Post request headers: " + str(headers))

            response = requests.post(url, data=json.dumps(data), headers=headers)

        except TypeError as err:
            self.errors.append('POST request error: ' + str(err))
            logger.error('POST request error: ' + str(err))
            return None

        if response.status_code == 401 and self.is_unauthorized(response):
            return self.post_request(endpoint, data)

        return response

    def get_request(self, endpoint, params=None):

        try:
            url = self.env + '/' + endpoint

            headers = {'Authorization': 'Bearer ' + self.token,
                       'Accept': 'application/vnd.allegro.public.v1+json',
                       'Content-Type': 'application/vnd.allegro.public.v1+json'}

            response = requests.get(url, headers=headers, params=params)

        except TypeError as err:
            self.errors.append('GET request error: ' + str(err))
            logger.error('GET request error: ' + str(err))
            return None
        if response.status_code == 401 and self.is_unauthorized(response):
            return self.get_request(endpoint, params)

        return response

    def put_request(self, endpoint, data):

        try:
            url = self.env + '/' + endpoint

            headers = {'Authorization': 'Bearer ' + self.token,
                       'Accept': 'application/vnd.allegro.public.v1+json',
                       'Content-Type': 'application/vnd.allegro.public.v1+json'}
            response = requests.put(url, data=json.dumps(data), headers=headers)

        except TypeError as err:
            self.errors.append('PUT request error: ' + str(err))
            logger.error('PUT request error: ' + str(err))
            return None
        if response.status_code == 401 and self.is_unauthorized(response):
            return self.put_request(endpoint, data)

        return response

    def is_unauthorized(self, response):

        allegro_plugin_config = self.get_plugin_configuration()

        if response.reason == 'Unauthorized':
            access_token, refresh_token, expires_in = self.refresh_token(
                allegro_plugin_config.get('refresh_token'),
                allegro_plugin_config.get('client_id'),
                allegro_plugin_config.get('client_secret'),
                allegro_plugin_config.get('saleor_redirect_url'),
                allegro_plugin_config.get('auth_env')) or (None, None, None)
            if access_token and refresh_token and expires_in is not None:
                self.token = access_token
                AllegroAuth.save_token_in_plugin_configuration(access_token,
                                                               refresh_token,
                                                               expires_in)
            return True
        else:
            return False

    @staticmethod
    def auth_request(endpoint, data, client_id, client_secret, url_env):

        url = url_env + '/' + endpoint

        response = requests.post(url, auth=requests.auth.HTTPBasicAuth(client_id,
                                                                       client_secret),
                                 data=json.dumps(data))

        return response

    def valid_offer(self, offer_id):
        endpoint = 'sale/offers/' + offer_id

        response = self.get_request(endpoint)

        return json.loads(response.text)

    def get_require_parameters(self, category_id):

        require_params = []

        endpoint = 'sale/categories/' + category_id + '/parameters'
        response = self.get_request(endpoint)
        try:
            require_params = [param for param in json.loads(response.text)['parameters']
                              if
                              param['required'] is True]
        except KeyError as err:
            self.errors.append('Key error ' + str(err))
            logger.error(err)
        except AttributeError as err:
            self.errors.append('Attribute error ' + str(err))
            logger.error(err)

        return require_params

    def upload_images(self, product_images):
        images_url = [pi.replace('/media', '') for pi in product_images]
        return [self.upload_image(image_url) for image_url in images_url]

    def upload_image(self, url):
        endpoint = 'sale/images'

        data = {
            "url": url
        }
        logger.info("Upload images from: " + str(url))

        response = self.post_request(endpoint=endpoint, data=data)

        try:
            logger.info("Upload images response " + str(json.loads(response.text)))
            return json.loads(response.text)['location']
        except KeyError as err:
            logger.error(err)
            self.errors.append('Key error ' + str(err))
        except AttributeError as err:
            logger.error(err)
            self.errors.append('Attribute error ' + str(err))

    def update_status_and_publish_data_in_private_metadata(self, product,
                                                           allegro_offer_id, status,
                                                           is_published, errors):
        product.store_value_in_private_metadata({'publish.allegro.status': status})
        product.store_value_in_private_metadata(
            {'publish.allegro.date': datetime.now(pytz.timezone('Europe/Warsaw'))
                .strftime('%Y-%m-%d %H:%M:%S')})
        product.store_value_in_private_metadata(
            {'publish.status.date': datetime.now(pytz.timezone('Europe/Warsaw'))
                .strftime('%Y-%m-%d %H:%M:%S')})
        product.store_value_in_private_metadata(
            {'publish.allegro.id': str(allegro_offer_id)})
        self.update_errors_in_private_metadata(product, errors)
        product.is_published = is_published
        product.save(update_fields=["private_metadata", "is_published"])

    @staticmethod
    def update_errors_in_private_metadata(product, errors):
        if len(errors) > 0:
            logger.error(str(product.variants.first()) + ' ' + str(errors))
            product.store_value_in_private_metadata({'publish.allegro.errors': errors})
            product.is_published = False
            product.save(update_fields=["private_metadata", "is_published"])

    def get_detailed_offer_publication(self, offer_id):
        endpoint = 'sale/offer-publication-commands/' + str(offer_id) + '/tasks'
        response = self.get_request(endpoint=endpoint)

        return json.loads(response.text)

    def offer_publication(self, offer_id):

        endpoint = 'sale/offer-publication-commands/' + str(uuid.uuid1())
        data = {
            "publication": {
                "action": "ACTIVATE"
            },
            "offerCriteria": [
                {
                    "offers": [
                        {
                            "id": offer_id
                        }
                    ],
                    "type": "CONTAINS_OFFERS"
                }
            ]
        }
        response = self.put_request(endpoint=endpoint, data=data)

        return json.loads(response.text)


class ParametersMapper:

    def __init__(self, mapper):
        self.mapper = mapper

    def mapper(self):
        return self.mapper.map()


class BaseParametersMapper:

    def __init__(self):
        self.mapped_parameters = []

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
                attributes[slugify(
                    str(assigned_product_attribute.assignment.attribute.slug))] = \
                    str(AttributeValue.objects.get(
                        assignedproductattribute=assigned_product_attribute))

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

    def run_mapper(self):

        attributes, attributes_name = self.get_product_attributes()

        self.set_product_attributes(attributes)

        for require_parameter in self.require_parameters:
            self.mapped_parameters.append(
                self.get_allegro_parameter(require_parameter['name']))

        return self.mapped_parameters

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
        config = self.get_plugin_configuration()
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
        config = self.get_plugin_configuration()
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

    @staticmethod
    def get_plugin_configuration():
        manager = get_plugins_manager()
        plugin = manager.get_plugin('allegro')
        configuration = {item["name"]: item["value"] for item in plugin.configuration}
        return configuration

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


class ParametersMapperFactory:

    @staticmethod
    def get_mapper():
        mapper = ParametersMapper(AllegroParametersMapper).mapper()
        return mapper


class ProductMapper:

    def __init__(self, mapper):
        self.mapper = mapper

    def mapper(self):
        return self.mapper.map()


class ProductMapperFactory:

    @staticmethod
    def get_mapper():
        mapper = ProductMapper(AllegroProductMapper).mapper()
        return mapper


class AllegroProductMapper:

    def __init__(self):
        nested_dict = lambda: defaultdict(nested_dict)
        nest = nested_dict()
        self.product = nest

    def map(self):
        return self

    def set_saleor_product(self, saleor_product):
        self.saleor_product = saleor_product
        return self

    def set_implied_warranty(self, implied_warranty):
        self.product['afterSalesServices']['impliedWarranty']['id'] = implied_warranty
        return self

    def set_return_policy(self, return_policy):
        self.product['afterSalesServices']['returnPolicy']['id'] = return_policy
        return self

    def set_warranty(self, warranty):
        self.product['afterSalesServices']['warranty']['id'] = warranty
        return self

    def set_category(self, category):
        self.product['category']['id'] = category
        return self

    def set_delivery_additional_info(self, delivery_additional_info):
        self.product['delivery']['additionalInfo'] = delivery_additional_info
        return self

    def set_delivery_handling_time(self, delivery_handling_time):
        self.product['delivery']['handlingTime'] = delivery_handling_time
        return self

    def set_delivery_shipment_date(self, delivery_shipment_date):
        self.product['delivery']['shipmentDate'] = delivery_shipment_date
        return self

    def set_delivery_shipping_rates(self, delivery_shipping_rates):
        self.product['delivery']['shippingRates']['id'] = delivery_shipping_rates
        return self

    def set_location_country_code(self, location_country_code):
        self.product['location']['countryCode'] = location_country_code
        return self

    def set_location_province(self, location_province):
        self.product['location']['province'] = location_province
        return self

    def set_location_city(self, location_city):
        self.product['location']['city'] = 'Poznań'
        return self

    def set_location_post_code(self, location_post_code):
        self.product['location']['postCode'] = location_post_code
        return self

    def set_invoice(self, invoice):
        self.product['payments']['invoice'] = invoice
        return self

    def set_format(self, format):
        self.product['sellingMode']['format'] = format
        return self

    def set_starting_price_amount(self, starting_price_amount):
        self.product['sellingMode']['startingPrice']['amount'] = starting_price_amount
        return self

    def set_price_amount(self, price_amount):
        self.product['sellingMode']['price']['amount'] = price_amount
        return self

    def set_price_currency(self, price_currency):
        self.product['sellingMode']['price']['currency'] = price_currency
        return self

    def set_starting_price_currency(self, starting_price_currency):
        self.product['sellingMode']['startingPrice'][
            'currency'] = starting_price_currency
        return self

    def set_name(self, name):
        self.product['name'] = name
        return self

    def set_saleor_images(self, saleor_images):
        self.saleor_images = saleor_images
        return self

    def set_images(self, images):

        self.product['images'] = [{'url': image} for image in images]
        return self

    @staticmethod
    def parse_list_to_map(list_in):
        return {item['text'].split(":")[0]: item['text'].split(":")[1].strip() for item
                in list_in[1:] if len(item['text'].split(':')) > 1}

    def set_description(self, product):
        product_sections = []
        product_items = [{
            'type': 'IMAGE',
            'url': self.saleor_images[0]
        }]

        product_description = self.parse_list_to_map(product.description_json['blocks'])

        product_items.append({
            'type': 'TEXT',
            'content': '<h1>Charakterystyka produktu</h1><p></p>' + ''.join([
                '<p>' + '<b>' +
                element[
                    0] + ': ' + '</b>' +
                element[
                    1].replace(
                    '&',
                    '&amp;') + '</p>'
                for
                element
                in
                product_description.items()
                if
                element[
                    0] != 'Jakość'])
        })

        product_items[1]['content'] += '<p>' + self.get_offer_description_footer() + '</p>'

        product_sections.append({'items': product_items})

        product_items = [{
            'type': 'TEXT',
            'content': '<h1>Opis produktu</h1>'
        }]

        product_sections.append({'items': product_items})

        product_items = [{
            'type': 'TEXT',
            'content': '<p>' + product.description_json['blocks'][0]['text'].replace(
                '&', '&amp;') + '</p>'
        }]

        product_sections.append({'items': product_items})

        product_items = [{
            'type': 'IMAGE',
            'url': self.saleor_images[0]
        }]

        product_sections.append({'items': product_items})

        self.product['description']['sections'] = product_sections

        return self

    def set_stock_available(self, stock_available):
        self.product['stock']['available'] = stock_available
        return self

    def set_stock_unit(self, stock_unit):
        self.product['stock']['unit'] = stock_unit
        return self

    def set_publication_duration(self, publication_duration):
        self.product['publication']['duration'] = publication_duration
        return self

    def set_publication_ending_at(self, publication_ending_at):
        self.product['publication']['endingAt'] = publication_ending_at
        return self

    def set_publication_starting_at(self, publication_starting_at):
        self.product['publication']['startingAt'] = publication_starting_at
        return self

    def set_publication_status(self, publication_status):
        self.product['publication']['status'] = publication_status
        return self

    def set_publication_ended_by(self, publication_ended_by):
        self.product['publication']['endedBy'] = publication_ended_by
        return self

    def set_publication_republish(self, publication_republish):
        self.product['publication']['republish'] = publication_republish
        return self

    def set_saleor_parameters(self, saleor_parameters):
        self.saleor_parameters = saleor_parameters
        return self

    def set_parameters(self, parameters):
        self.product['parameters'] = parameters
        return self

    def set_external(self, sku):
        self.product['external']['id'] = sku
        return self

    @staticmethod
    def calculate_name_length(name):
        name_length = len(name.strip())
        if '&' in name:
            name_length += 4
        return name_length

    def remove_last_word(self, name):
        name = re.sub("\s\w+$", "", name)
        if self.calculate_name_length(name) > 50:
            return self.remove_last_word(name)
        else:
            return name

    def prepare_name(self, name):
        if self.calculate_name_length(name) > 50:
            name = re.sub(
                "NIEMOWLĘC[AEY]|DZIECIĘC[AEY]|DAMSK[AI]E?|MĘSK[AI]E?|INN[AEY]|POLIESTER",
                "", name)
            name = re.sub("\s{3}", " ", name)
            if self.calculate_name_length(name) > 50:
                name = re.sub("\sROZM.*$", "", name)
            if self.calculate_name_length(name) > 50:
                name = self.remove_last_word(name)
            return name
        else:
            name = re.sub("POLIESTER", "", name)
            description_blocks = self.parse_list_to_map(
                self.saleor_product.description_json['blocks'])
            if description_blocks.get('Kolor') and description_blocks.get('Kolor')\
                    .upper() != 'INNY':
                if self.calculate_name_length(name) + len(' ' + description_blocks.
                        get('Kolor')) <= 50:
                    name = name + ' ' + (description_blocks.get('Kolor')).upper()
            if description_blocks.get('Zapięcie') and description_blocks.\
                    get('Zapięcie').upper() != 'BRAK':
                if self.calculate_name_length(name) + len(' ' + description_blocks.
                        get('Zapięcie')) <= 50:
                    name = name + ' ' + (description_blocks.get('Zapięcie')).upper()
            if description_blocks.get('Stan') and description_blocks.\
                    get('Stan').upper() not in ['UŻYWANY', 'UŻYWANY Z DEFEKTEM']:
                if self.calculate_name_length(name) + len(' ' + description_blocks.
                        get('Stan')) <= 50:
                    name = name + ' ' + (description_blocks.get('Stan')).upper()
            return name

    @staticmethod
    def get_plugin_configuration():
        manager = get_plugins_manager()
        plugin = manager.get_plugin('allegro')
        configuration = {item["name"]: item["value"] for item in plugin.configuration}
        return configuration

    def get_offer_description_footer(self):
        config = self.get_plugin_configuration()
        return config.get('offer_description_footer')

    def get_implied_warranty(self):
        config = self.get_plugin_configuration()
        return config.get('implied_warranty')

    def get_return_policy(self):
        config = self.get_plugin_configuration()
        return config.get('return_policy')

    def get_warranty(self):
        config = self.get_plugin_configuration()
        return config.get('warranty')

    def get_delivery_shipping_rates(self):
        config = self.get_plugin_configuration()
        return config.get('delivery_shipping_rates')

    def get_delivery_handling_time(self):
        config = self.get_plugin_configuration()
        return config.get('delivery_handling_time')

    def get_publication_duration(self):
        config = self.get_plugin_configuration()
        return config.get('publication_duration')

    def set_obj_publication_starting_at(self, publication_starting_at):
        self.publication_starting_at = publication_starting_at
        return self

    def set_offer_type(self, offer_type):
        self.offer_type = offer_type
        return self

    def get_publication_starting_at(self):
        return self.publication_starting_at

    def get_offer_type(self):
        return self.offer_type

    def run_mapper(self):
        self.set_implied_warranty(self.get_implied_warranty())
        self.set_return_policy(self.get_return_policy())
        self.set_warranty(self.get_warranty())

        self.set_delivery_handling_time(self.get_delivery_handling_time())
        self.set_delivery_shipping_rates(self.get_delivery_shipping_rates())

        self.set_location_country_code('PL')
        self.set_location_province('MAZOWIECKIE')
        self.set_location_city('Piaseczno')
        self.set_location_post_code('05-500')

        self.set_invoice('VAT')

        self.set_format(self.get_offer_type())

        if self.get_offer_type() == 'BUY_NOW':
            product_variant = ProductVariant.objects.filter(
                product=self.saleor_product).first()
            self.set_price_amount(
                str(product_variant.price_amount))
            self.set_price_currency(product_variant.currency)
            self.set_publication_republish('False')
        else:
            product_variant = ProductVariant.objects.filter(
                product=self.saleor_product).first()
            self.set_starting_price_amount(
                str(product_variant.price_amount))
            self.set_starting_price_currency(product_variant.currency)
            self.set_publication_republish('True')
            self.set_publication_duration(self.get_publication_duration())

        self.set_name(self.prepare_name(self.saleor_product.name))
        self.set_images(self.saleor_images)

        self.set_description(self.saleor_product)

        # FIXME: po sprzedaniu przedmiotu na tym parametrze update?
        self.set_stock_available('1')

        self.set_stock_unit('SET')
        self.set_publication_ending_at('')

        if self.get_publication_starting_at() is not None:
            if datetime.strptime(self.get_publication_starting_at(),
                                 '%Y-%m-%d %H:%M') > (
                    datetime.now() + timedelta(hours=2)):
                self.set_publication_starting_at(str((datetime.strptime(
                    self.get_publication_starting_at(), '%Y-%m-%d %H:%M') - timedelta(
                    hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")))

        self.set_publication_status('INACTIVE')
        self.set_publication_ended_by('USER')

        self.set_parameters(self.saleor_parameters)
        self.set_external(
            str(ProductVariant.objects.filter(product=self.saleor_product).first()))

        return self.product


def email_errors(products_bulk_ids):
    # Send email on last bulk item
    products = Product.objects.filter(id__in=products_bulk_ids)
    publish_errors = []

    for product in products:
        error = product.get_value_from_private_metadata('publish.allegro.errors')
        if error is not None:
            publish_errors.append(
                {'sku': product.variants.first().sku, 'errors': error})

    if publish_errors:
        manager = get_plugins_manager()
        plugin = manager.get_plugin('allegro')
        plugin.send_mail_with_publish_errors(publish_errors, None)
