import enum
import json
import logging
import re
import urllib
import uuid

from collections import defaultdict
from datetime import datetime, timedelta
from math import ceil

import pytz
import requests
from slugify import slugify

from django.core.mail import EmailMultiAlternatives

from saleor.plugins.manager import get_plugins_manager
from saleor.plugins.models import PluginConfiguration
from saleor.product.models import AssignedProductAttribute, \
    AttributeValue, ProductVariant, Product

logger = logging.getLogger(__name__)


class AllegroErrors(enum.Enum):
   ALLEGRO_ERROR = 'allegro_error'
   NO_OFFERS_FOUND = 'no_offers_found'
   BID_OR_PURCHASED = 'bid_or_purchased'
   TASK_FAILED = 'task_failed'


class AllegroAPI:
    api_public = 'public.v1'
    api_beta = 'beta.v2'

    def __init__(self, token, env):
        self.token = token
        self.errors = []
        self.product_errors = []
        self.env = env
        self.require_parameters = []
        self.plugin_config = get_plugin_configuration()

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

    @staticmethod
    def calculate_hours_to_token_expire(token):
        token_expire = datetime.strptime(token, '%d/%m/%Y %H:%M:%S')
        duration = token_expire - datetime.now()
        return divmod(duration.total_seconds(), 3600)[0]

    def prepare_offer(self, saleor_product, starting_at, offer_type, product_images, parameters_type):
        category_id = saleor_product.product_type.metadata.get(
            'allegro.mapping.categoryId')
        require_parameters = self.get_require_parameters(category_id, parameters_type)
        parameters_mapper = ParametersMapperFactory().get_mapper()
        parameters = parameters_mapper.set_product(
            saleor_product).set_require_parameters(require_parameters).run_mapper(parameters_type)
        product_mapper = ProductMapperFactory().get_mapper()

        try:
            product = product_mapper.set_saleor_product(saleor_product) \
                .set_saleor_images(self.upload_images(product_images)) \
                .set_saleor_parameters(parameters).set_obj_publication_starting_at(
                starting_at).set_offer_type(offer_type).set_category(
                category_id).run_mapper()
        except IndexError as err:
            self.errors.append(str(err))
            self.update_errors_in_private_metadata(
                saleor_product,
                [error for error in self.errors])

        return product

    def prepare_product_parameters(self, saleor_product, parameters_type):
        category_id = saleor_product.product_type.metadata.get(
            'allegro.mapping.categoryId')
        require_parameters = self.get_require_parameters(category_id, parameters_type)
        self.require_parameters = require_parameters
        parameters_mapper = ParametersMapperFactory().get_mapper()
        parameters = parameters_mapper.set_product(
            saleor_product).set_require_parameters(require_parameters).run_mapper(parameters_type)

        return parameters

    def prepare_product(self, saleor_product, parameters, product_images):
        product_mapper = ProductMapperFactory().get_mapper()

        category_id = saleor_product.product_type.metadata.get(
            'allegro.mapping.categoryId')

        product = product_mapper.set_saleor_product(saleor_product) \
            .set_saleor_images(product_images) \
            .set_saleor_parameters(parameters).set_category(
            category_id).run_product_mapper()

        return product

    def publish_to_allegro(self, allegro_product):

        endpoint = 'sale/offers'

        try:
            response = self.post_request(
                endpoint=endpoint,
                data=allegro_product,
                api_version=self.api_public)
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

    def add_product_to_offer(self, allegro_product_id, allegro_id, description):
        endpoint = 'sale/product-offers/' + allegro_id

        allegro_product = {
            "product":{
                "id": allegro_product_id
            },
            "description": description
        }
        response = self.patch_request(endpoint=endpoint, data=allegro_product, api_version=self.api_beta)

        return response.json()

    def propose_a_product(self, product):
        endpoint = 'sale/product-proposals'
        response = self.post_request(endpoint=endpoint, data=product,
                                      api_version=self.api_public)

        return json.loads(response.text)

    def post_request(self, endpoint, data, api_version):
        try:
            url = self.env + '/' + endpoint

            headers = {'Authorization': 'Bearer ' + self.token,
                       'Accept': f'application/vnd.allegro.{api_version}+json',
                       'Content-Type': f'application/vnd.allegro.{api_version}+json'}

            logger.info("Post request url: " + str(url))
            logger.info("Post request headers: " + str(headers))

            response = requests.post(url, data=json.dumps(data), headers=headers)

        except TypeError as err:
            self.errors.append('POST request error: ' + str(err))
            logger.error('POST request error: ' + str(err))
            return None

        if response.status_code == 401 and self.is_unauthorized(response):
            headers['Authorization'] = 'Bearer ' + self.token
            response = requests.post(url, data=json.dumps(data), headers=headers)

        return response

    def patch_request(self, endpoint, data, api_version):
        try:
            url = self.env + '/' + endpoint

            headers = {'Authorization': 'Bearer ' + self.token,
                       'Accept': f'application/vnd.allegro.{api_version}+json',
                       'Content-Type': f'application/vnd.allegro.{api_version}+json'}

            logger.info("Patch request url: " + str(url))
            logger.info("Patch request headers: " + str(headers))

            response = requests.patch(url, data=json.dumps(data), headers=headers)

        except TypeError as err:
            self.errors.append('PATCH request error: ' + str(err))
            logger.error('PATCH request error: ' + str(err))
            return None

        if response.status_code == 401 and self.is_unauthorized(response):
            headers['Authorization'] = 'Bearer ' + self.token
            response = requests.patch(url, data=json.dumps(data), headers=headers)

        return response

    def get_request(self, endpoint, params=None):

        try:
            url = self.env + '/' + endpoint

            headers = {'Authorization': 'Bearer ' + self.token,
                       'Accept': 'application/vnd.allegro.public.v1+json',
                       'Content-Type': 'application/vnd.allegro.public.v1+json'}

            logger.info(f'GET request url: {url}')
            #logger.info(self.token)

            response = requests.get(url, headers=headers, params=params)

        except TypeError as err:
            self.errors.append('GET request error: ' + str(err))
            logger.error('GET request error: ' + str(err))
            return None

        if response.status_code == 401 and self.is_unauthorized(response):
            headers['Authorization'] = 'Bearer ' + self.token
            response = requests.get(url, headers=headers, params=params)

        return response

    def put_request(self, endpoint, data):
        try:
            url = self.env + '/' + endpoint

            headers = {'Authorization': 'Bearer ' + self.token,
                       'Accept': 'application/vnd.allegro.public.v1+json',
                       'Content-Type': 'application/vnd.allegro.public.v1+json'}

            logger.info(f'PUT request url: {url}')

            response = requests.put(url, data=json.dumps(data), headers=headers)
        except TypeError as err:
            self.errors.append('PUT request error: ' + str(err))
            logger.error('PUT request error: ' + str(err))
            return None
        if response.status_code == 401 and self.is_unauthorized(response):
            headers['Authorization'] = 'Bearer ' + self.token
            response = requests.put(url, data=json.dumps(data), headers=headers)


        return response

    def is_unauthorized(self, response):
        allegro_plugin_config = self.plugin_config

        if response.reason == 'Unauthorized':
            access_token, refresh_token, expires_in = self.refresh_token(
                allegro_plugin_config.get('refresh_token'),
                allegro_plugin_config.get('client_id'),
                allegro_plugin_config.get('client_secret'),
                allegro_plugin_config.get('saleor_redirect_url'),
                allegro_plugin_config.get('auth_env')) or (None, None, None)
            if access_token and refresh_token and expires_in is not None:
                self.token = access_token
                self.save_token_in_plugin_configuration(access_token,
                                                               refresh_token,
                                                               expires_in)
            return True
        else:
            return False

    @staticmethod
    def save_token_in_plugin_configuration(access_token, refresh_token, expires_in):
        cleaned_data = {
            "configuration": [{"name": "token_value", "value": access_token},
                              {"name": "token_access",
                               "value": (datetime.now() + timedelta(
                                   seconds=expires_in)).strftime("%d/%m/%Y %H:%M:%S")},
                              {"name": "refresh_token", "value": refresh_token}]
        }

        manager = get_plugins_manager()
        plugin = manager.get_plugin('allegro')

        plugin.save_plugin_configuration(
            plugin_configuration=PluginConfiguration.objects.get(
                identifier=plugin.PLUGIN_ID), cleaned_data=cleaned_data)

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

    def get_require_parameters(self, category_id, required_type):

        require_params = []

        endpoint = 'sale/categories/' + category_id + '/parameters'
        response = self.get_request(endpoint)
        try:
            require_params = [param for param in json.loads(response.text)['parameters']
                              if
                              param[required_type] is True]
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

        response = self.post_request(
            endpoint=endpoint,
            data=data,
            api_version=self.api_public)

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
                                                           errors):
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
        product.save()

    @staticmethod
    def update_errors_in_private_metadata(product, errors):
        if errors:
            product.is_published = False
            logger.error(str(product.variants.first()) + ' ' + str(errors))
            product.store_value_in_private_metadata({'publish.allegro.errors': errors})
        else:
            product.is_published = True
            product.store_value_in_private_metadata({'publish.allegro.errors': []})
        product.save(update_fields=["private_metadata", "is_published"])

    def update_product_errors_in_private_metadata(self, product, errors):
            product.store_value_in_private_metadata({'publish.allegro.errors': errors})
            product.save(update_fields=["private_metadata"])

    def get_detailed_offer_publication(self, offer_id):
        endpoint = 'sale/offer-publication-commands/' + str(offer_id) + '/tasks'
        response = self.get_request(endpoint=endpoint)

        return json.loads(response.text)

    def bulk_offer_unpublish(self, skus):
        # Get offers by sku codes
        offers = self.get_offers_by_skus(skus)
        if not isinstance(offers, list):
            return {'status': 'ERROR', 'message': AllegroErrors.ALLEGRO_ERROR, 'errors': ['Error with fetching offers']}
        if not offers:
            return {'status': 'OK', 'message': AllegroErrors.NO_OFFERS_FOUND, 'errors': []}
        # Check if someone doesnt bid or purchased any offer
        offers_bid_or_purchased = self.offers_bid_or_purchased(offers)
        # Append SKU/OFFER error list to errors section if some offer is bid or purchased
        if offers_bid_or_purchased:
            offers_to_remove = [offer['offer'] for offer in offers_bid_or_purchased]
            offers = [offer for offer in offers if not offer['id'] in offers_to_remove]
        # Bulk offers unpublish
        offers = [{'id': offer['id']} for offer in offers if offer['publication']['status'] != 'ENDED']
        if not offers:
            return {'status': 'OK', 'message': AllegroErrors.NO_OFFERS_FOUND, 'errors': []}
        unique_id = str(uuid.uuid1())
        endpoint = f'sale/offer-publication-commands/{unique_id}'
        data = {
            "publication": {
                "action": "END",
                "republish": False
            },
            "offerCriteria": [
                {
                    "offers": offers,
                    "type": "CONTAINS_OFFERS"
                }
            ]
        }
        logger.info('Unique ID: ' + unique_id)
        response = self.put_request(endpoint=endpoint, data=data)
        logger.info('Offer Ending: ' + str(response.json()))

        if response.status_code != 201:
            return {'status': 'ERROR', 'uuid': unique_id, 'message': AllegroErrors.ALLEGRO_ERROR,
                    'errors': response.json()}

        if offers_bid_or_purchased:
            return {'status': 'OK', 'uuid': unique_id, 'message': AllegroErrors.BID_OR_PURCHASED,
                    'errors': offers_bid_or_purchased}
        else:
            return {'status': 'OK', 'uuid': unique_id, 'errors': []}

    def offers_bid_or_purchased(self, offers):
        offers_bid_or_purchased = [
            {'sku': offer['external']['id'], 'offer': offer['id'],
             'available': offer['stock']['available'], 'sold': offer['stock']['sold'],
             'error_message': 'Sold or not available'}
             for offer in offers
             if offer['saleInfo']['biddersCount'] or offer['stock']['sold'] or not offer['stock']['available']]
        # Remove canceled allegro offers
        if offers_bid_or_purchased:
            skus = [offer['sku'] for offer in offers_bid_or_purchased]
            skus_to_pass = []
            product_variants = ProductVariant.objects.select_related('product').filter(sku__in=skus)

            for product_variant in product_variants:
                if 'reserved' not in product_variant.metadata or product_variant.metadata['reserved'] is False:
                    skus_to_pass.append(product_variant.sku)
                elif 'publish.allegro.status' in product_variant.product.private_metadata and \
                        product_variant.product.private_metadata['publish.allegro.status'] == 'moderated':
                    skus_to_pass.append(product_variant.sku)

            offers_bid_or_purchased = [offer for offer in offers_bid_or_purchased
                                       if offer['sku'] not in skus_to_pass]

        return offers_bid_or_purchased

    def get_offers_by_skus(self, skus):
        def get_offers_by_max_100_skus(sku_params):
            endpoint = (f'sale/offers?publication.status=ACTIVE&publication.status=ACTIVATING'
                        f'&publication.status=ENDED&limit=1000&{sku_params}')
            response = self.get_request(endpoint=endpoint)
            if response.status_code != 200:
                logger.error('Error with fetching offers: ' + str(response.json()))
                return False
            response = response.json()
            offers_max_100_skus = []
            offset = 0
            counter = 0
            count = response['count']
            offers_max_100_skus += response['offers']
            # Get max 1000 offers each request for given 100 sku codes
            while count < response['totalCount']:
                counter += 1
                offset += response['count']
                endpoint = (f'sale/offers?publication.status=ACTIVE&publication.status=ACTIVATING'
                            f'&publication.status=ENDED&limit=1000&offset={offset}&{sku_params}')
                response = self.get_request(endpoint=endpoint)
                if response.status_code != 200:
                    logger.error('Error with fetching offers: ' + str(response.json()))
                    return False
                response = response.json()
                offers_max_100_skus += response['offers']
                count += response['count']
                if counter == 20:
                    return False
            return offers_max_100_skus
        # Get offers by max 100 sku codes
        skus_amount = len(skus)
        request_count = ceil(skus_amount / 100)
        offers = []
        start = 0
        end = 100 if skus_amount >= 100 else skus_amount
        for chunk in range(request_count):
            offers_list_of_tuples = [('external.id', sku) for sku in skus[start:end]]
            sku_params = urllib.parse.urlencode(offers_list_of_tuples)
            fetched_offers = get_offers_by_max_100_skus(sku_params)
            if not isinstance(fetched_offers, list):
                return False
            offers += fetched_offers
            start += 100
            if skus_amount - start >= 100:
                end += 100
            else:
                end += skus_amount - start

        return offers

    def check_unpublish_status(self, unique_id):
        endpoint = f'sale/offer-publication-commands/{unique_id}'
        response = self.get_request(endpoint=endpoint).json()

        try:
            total = response['taskCount']['total']
            success = response['taskCount']['success']
            failed = response['taskCount']['failed']
            if total != success + failed:
                return {
                    'status': 'PROCEEDING',
                    'taskCount': response['taskCount'],
                    'errors': []
                }
            if failed:
                return self.check_unpublish_errors(unique_id)
        except KeyError:
            return {
                'status': 'ERROR',
                'message': AllegroErrors.ALLEGRO_ERROR,
                'errors': [response]
            }

        return {
            'status': 'OK',
            'taskCount': response['taskCount'],
            'errors': []
        }

    def check_unpublish_errors(self, unique_id):
        endpoint = f'sale/offer-publication-commands/{unique_id}/tasks'
        response = self.get_request(endpoint=endpoint).json()

        try:
            tasks_failed = [task for task in response['tasks'] if task['status'] != 'SUCCESS']
        except KeyError:
            logger.error('Offers unpublish check errors: ' + str(response))
            return {
                'status': 'ERROR',
                'message': AllegroErrors.ALLEGRO_ERROR,
                'errors': [response]
            }

        return {
            'status': 'ERROR',
            'message': AllegroErrors.TASK_FAILED,
            'errors': tasks_failed
        }

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
        logger.info('Offer Activation: ' + str(response.json()))

        return json.loads(response.text)

    def transform_product_error_response(self, error):
        parameters_ids = [int(s) for s in error.split() if s.isdigit()]
        if parameters_ids:
            parameter_names = ''
            for parameter in self.require_parameters:
                if int(parameter['id']) in parameters_ids:
                    parameter_names += parameter['name'] + ','
            if parameter_names:
                error += f' Nazwy parametrów: {parameter_names}'
                error = error.rstrip(',')
        return error

    def error_handling_product(self, allegro_product, saleor_product):
        if 'errors' in allegro_product:
            product_errors = [error.get('userMessage') for error in allegro_product['errors']]
            for i, error in enumerate(product_errors):
                error = self.transform_product_error_response(error)
                product_errors[i] = error
                logger.error(error)
            self.product_errors += product_errors
            self.errors += self.product_errors
            self.update_product_errors_in_private_metadata(saleor_product, self.errors)
        if 'error' in allegro_product:
            self.product_errors.append(allegro_product.get('error_description'))
            self.errors += self.product_errors
            self.update_product_errors_in_private_metadata(saleor_product, self.errors)

    def error_handling(self, offer, saleor_product, ProductPublishState):
        must_assign_offer_to_product = False
        if 'error' in offer:
            self.errors.append(offer.get('error_description'))
            self.update_errors_in_private_metadata(
                saleor_product,
                [error for error in self.errors])
        elif 'errors' in offer:
            self.errors += offer['errors']
            self.update_errors_in_private_metadata(
                saleor_product,
                [error.get('message') for error in self.errors])
        elif offer['validation'].get('errors') is not None:
            if len(offer['validation'].get('errors')) > 0:
                for error in offer['validation'].get('errors'):
                    if 'too few offers related to a product' in error['message']:
                        must_assign_offer_to_product = True
                    logger.error((error['message'] + ' dla ogłoszenia: ' + self.env + '/offer/' + offer['id'] + '/restore'))
                    self.errors.append((error['message'] + 'dla ogłoszenia: ' + self.env + '/offer/' + offer['id'] + '/restore'))
                self.update_status_and_publish_data_in_private_metadata(
                    saleor_product, offer['id'],
                    ProductPublishState.MODERATED.value,
                    self.errors)
            else:
                self.errors = []
                self.offer_publication(offer.get('id'))
                self.update_status_and_publish_data_in_private_metadata(
                    saleor_product, offer['id'],
                    ProductPublishState.PUBLISHED.value,
                    self.errors)

        if must_assign_offer_to_product:
            return 'must_assign_offer_to_product'


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
        self.plugin_config = get_plugin_configuration()

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

    def set_images_product(self, images):
        self.product['images'] = images
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

    def get_offer_description_footer(self):
        return self.plugin_config.get('offer_description_footer')

    def get_implied_warranty(self):
        return self.plugin_config.get('implied_warranty')

    def get_return_policy(self):
        return self.plugin_config.get('return_policy')

    def get_warranty(self):
        return self.plugin_config.get('warranty')

    def get_delivery_shipping_rates(self):
        return self.plugin_config.get('delivery_shipping_rates')

    def get_delivery_handling_time(self):
        return self.plugin_config.get('delivery_handling_time')

    def get_publication_duration(self):
        return self.plugin_config.get('publication_duration')

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

    def run_product_mapper(self):
        self.set_name(self.prepare_name(self.saleor_product.name))
        self.set_parameters(self.saleor_parameters)
        self.set_images_product(self.saleor_images)
        return self.product

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

def get_plugin_configuration():
    manager = get_plugins_manager()
    plugin = manager.get_plugin('allegro')
    configuration = {item["name"]: item["value"] for item in plugin.configuration}
    return configuration

def email_bulk_unpublish_message(status, **kwargs):
    if status == 'OK':
        message = 'Wszystkie oferty dla danych SKU zostały pomyślnie wycofane'
    elif status == 'ERROR':
        if kwargs.get('message') == AllegroErrors.TASK_FAILED:
            message = prepare_failed_tasks_email(kwargs.get('errors'))
        else:
            message = str(kwargs.get('errors'))

    send_mail(message)

def send_mail(message):
    subject = 'Logi z wycofywania ofert'
    from_email = 'noreply.salingo@gmail.com'
    to = 'noreply.salingo@gmail.com'
    text_content = 'Logi z wycofywania ofert:'
    html_content = message
    message = EmailMultiAlternatives(subject, text_content, from_email, [to])
    message.attach_alternative(html_content, "text/html")
    return message.send()

def prepare_failed_tasks_email(errors):
    html = '<table style="width:100%; margin-bottom: 1rem;">'
    html += '<tr>'
    html += '<th></th>'
    html += '</tr>'
    for error in errors:
        html += '<tr>'
        html += '<td style="width: 9rem;">' + str(error.get('offer').get('id')) + '</td>'
        html += '<td>' + 'errors: ' + str(error.get('errors')) + '</td>'
        html += '</tr>'
    html += '<tr>'
    html += '<td>' + '</td>'
    html += '</tr>'
    html += '</table>'
    html += '<br>'
    html += '<table style="width:100%; margin-bottom: 1rem;">'
    html += '<tr>'
    html += '</tr>'
    html += '<tr>'
    html += '</tr>'
    html += '</table>'

    return html

