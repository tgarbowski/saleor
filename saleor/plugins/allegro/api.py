import json
import logging
import urllib
import uuid

from datetime import datetime, timedelta
from math import ceil

import pytz
import requests

from .enums import AllegroErrors
from .products_mapper import ProductMapperFactory
from .parameters_mapper import ParametersMapperFactory
from saleor.plugins.manager import get_plugins_manager
from saleor.plugins.models import PluginConfiguration
from saleor.product.models import ProductVariant
from .utils import get_plugin_configuration

logger = logging.getLogger(__name__)


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

    def get_offer(self, offer_id):
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
            logger.error('Error with fetching offers')
            return {'status': 'ERROR', 'message': AllegroErrors.ALLEGRO_ERROR, 'errors': ['Error with fetching offers']}
        if not offers:
            logger.info('No offers found')
            return {'status': 'OK', 'message': AllegroErrors.NO_OFFERS_FOUND, 'errors': []}
        # Check if someone doesnt bid or purchased any offer
        offers_bid_or_purchased = self.offers_bid_or_purchased(offers)
        # Append SKU/OFFER error list to errors section if some offer is bid or purchased
        if offers_bid_or_purchased:
            offers_to_remove = [offer['offer'] for offer in offers_bid_or_purchased]
            offers = [offer for offer in offers if not offer['id'] in offers_to_remove]
        # Bulk offers unpublish
        offers = [{'id': offer['id']} for offer in offers if offer['publication']['status'] != 'ENDED']

        if not offers and not offers_bid_or_purchased:
            logger.info('No active/activating offers to terminate and nothing is purchased or bid')
            return {'status': 'OK', 'message': AllegroErrors.NO_OFFER_NEEDS_ENDING, 'errors': []}
        elif not offers and offers_bid_or_purchased:
            logger.info('No active/activating offers to terminate but some offers are purchased or bid')
            return {'status': 'OK', 'message': AllegroErrors.NO_OFFER_NEEDS_ENDING, 'errors': offers_bid_or_purchased}

        unique_id = str(uuid.uuid1())
        endpoint = f'sale/offer-publication-commands/{unique_id}'
        data = {
            "publication": {
                "action": "END",
                "republish": False
            },
            "offerCriteria": [
                {
                    "offers": offers[:1000],
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
            logger.info('Some offers were terminated and some offers are purchased or bid')
            return {'status': 'OK', 'uuid': unique_id, 'message': AllegroErrors.BID_OR_PURCHASED,
                    'errors': offers_bid_or_purchased}
        else:
            logger.info('Some offers were terminated and no offers are purchased or bid')
            return {'status': 'OK', 'uuid': unique_id, 'errors': []}

    def offers_bid_or_purchased(self, offers):
        offers_bid_or_purchased = [
            {'sku': offer['external']['id'], 'offer': offer['id'],
             'available': offer['stock']['available'], 'sold': offer['stock']['sold'],
             'bidders_count': offer['saleInfo']['biddersCount'],'error_message': 'Sold or not available'}
             for offer in offers
             if offer['saleInfo']['biddersCount'] or offer['stock']['sold'] or not offer['stock']['available']]

        logger.info(f'OFFERS BID OR PURCHASED BASED ON ALLEGRO RESPONSE{offers_bid_or_purchased}')
        # Remove canceled allegro offers
        if offers_bid_or_purchased:
            skus = [offer['sku'] for offer in offers_bid_or_purchased]
            skus_to_pass = []
            product_variants = ProductVariant.objects.select_related('product').filter(sku__in=skus)

            for product_variant in product_variants:
                # Products returned from customer
                if 'publish.allegro.status' in product_variant.product.private_metadata and \
                        product_variant.product.private_metadata['publish.allegro.status'] == 'moderated' and \
                        ('reserved' not in product_variant.metadata or product_variant.metadata['reserved'] is False):
                    skus_to_pass.append(product_variant.sku)

            logger.info(f'SKUS TO PASS{skus_to_pass}')

            offers_bid_or_purchased = [offer for offer in offers_bid_or_purchased
                                       if offer['sku'] not in skus_to_pass]

        logger.info(f'OFFERS BID OR PURCHASED{offers_bid_or_purchased}')

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
                    logger.error((error['message'] + ' dla ogłoszenia: ' + self.plugin_config['auth_env'] + '/offer/' + offer['id'] + '/restore'))
                    self.errors.append((error['message'] + 'dla ogłoszenia: ' + self.plugin_config['auth_env'] + '/offer/' + offer['id'] + '/restore'))
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
