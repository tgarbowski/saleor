import json
import logging
import urllib.parse
import uuid

from datetime import datetime, timedelta
from math import ceil

import requests

from .enums import AllegroErrors
from .products_mapper import ProductMapperFactory
from .parameters_mapper import ParametersMapperFactory
from saleor.plugins.manager import get_plugins_manager
from saleor.plugins.models import PluginConfiguration
from saleor.product.models import ProductVariant
from .utils import AllegroErrorHandler, returned_products
from saleor.plugins.allegro import ProductPublishState

logger = logging.getLogger(__name__)


class AllegroAPI:
    api_public = 'public.v1'

    def __init__(self, channel):
        self.channel = channel
        self.errors = []
        self.product_errors = []
        self.require_parameters = []
        self.set_config()

    def set_config(self):
        config = self.get_plugin_config(self.channel)
        self.plugin_config = config
        self.token = config.get('token_value')
        self.env = config.get('env')

    def get_plugin_config(self, channel):
        manager = get_plugins_manager()
        plugin = manager.get_plugin(
            plugin_id='allegro',
            channel_slug=channel)
        configuration = {item["name"]: item["value"] for item in plugin.configuration if
                         plugin.configuration}
        return configuration

    def refresh_token(self):
        conf = self.plugin_config
        logger.info('Refresh token')

        endpoint = (f'auth/oauth/token?grant_type=refresh_token&refresh_token={conf["refresh_token"]}'
                    f'&redirect_uri={conf["saleor_redirect_url"]}')

        data = {
            'grant_type': 'refresh_token',
            'refresh_token': conf['refresh_token'],
            'redirect_uri': conf['saleor_redirect_url']
        }

        response = self.auth_request(endpoint=endpoint, data=data)

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
        parameters_mapper = ParametersMapperFactory().get_mapper(self.channel)
        parameters = parameters_mapper.set_product(
            saleor_product).set_require_parameters(require_parameters).run_mapper(parameters_type)
        product_mapper = ProductMapperFactory().get_mapper(self.channel)

        try:
            product = product_mapper.set_saleor_product(saleor_product) \
                .set_saleor_images(self.upload_images(product_images)) \
                .set_saleor_parameters(parameters).set_obj_publication_starting_at(
                starting_at).set_offer_type(offer_type).set_category(
                category_id).run_mapper()
        except IndexError as err:
            self.errors.append(str(err))
            AllegroErrorHandler.update_errors_in_private_metadata(
                saleor_product,
                [error for error in self.errors],
                self.channel
            )

        return product

    def prepare_product_parameters(self, saleor_product, parameters_type):
        category_id = saleor_product.product_type.metadata.get(
            'allegro.mapping.categoryId')
        require_parameters = self.get_require_parameters(category_id, parameters_type)
        self.require_parameters = require_parameters
        parameters_mapper = ParametersMapperFactory().get_mapper(self.channel)
        parameters = parameters_mapper.set_product(
            saleor_product).set_require_parameters(require_parameters).run_mapper(parameters_type)

        return parameters

    def prepare_product(self, saleor_product, parameters, product_images):
        product_mapper = ProductMapperFactory().get_mapper(self.channel)

        category_id = saleor_product.product_type.metadata.get(
            'allegro.mapping.categoryId')

        product = product_mapper.set_saleor_product(saleor_product) \
            .set_saleor_images(product_images) \
            .set_saleor_parameters(parameters).set_category(
            category_id).run_product_mapper()

        return product

    def get_available_shipping_carriers(self):
        endpoint = 'order/carriers'
        return self.get_request(endpoint=endpoint)

    def add_parcel_tracking_number(self, order_id, carrier_id, waybill):
        endpoint = f'order/checkout-forms/{order_id}/shipments'
        payload = {
            "carrierId": carrier_id,
            "waybill": waybill
        }
        return self.post_request(endpoint=endpoint, data=payload, api_version=self.api_public)

    def update_order_status(self, order_id, status):
        endpoint = f'order/checkout-forms/{order_id}/fulfillment'
        payload = {
            "status": status
        }
        return self.put_request(endpoint=endpoint, data=payload)

    def get_orders(self, statuses, updated_at_from):
        def get_100_orders(offset=0):
            parameters = {
                "status": statuses,
                "offset": offset,
                "updatedAt.gte": f'{updated_at_from}Z'
            }
            encoded_parameters = urllib.parse.urlencode(parameters, True)
            endpoint = f'order/checkout-forms?{encoded_parameters}'
            response = self.get_request(endpoint=endpoint)
            return response

        orders = []
        first_100_orders = get_100_orders()

        if first_100_orders.status_code != 200:
            logger.info(f'Fetching orders error: {first_100_orders.json()}')
            return orders

        first_100_orders = first_100_orders.json()
        orders.extend(first_100_orders['checkoutForms'])
        total_count = first_100_orders['totalCount']

        if first_100_orders['count'] < total_count:
            for offset in range(100, total_count, 100):
                offset_orders = get_100_orders(offset=offset)
                if offset_orders.status_code == 200:
                    orders.extend(offset_orders.json()['checkoutForms'])

        return orders


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

        data = {
            "productSet": [
                {
                    "product": {
                        "id": allegro_product_id
                    }
                }
            ],
            "description": description
        }

        response = self.patch_request(endpoint=endpoint, data=data, api_version=self.api_public)

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

            response = requests.post(url, data=json.dumps(data), headers=headers)
            logger.info(f'trace-id: {response.headers.get("trace-id")}')

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

            response = requests.patch(url, data=json.dumps(data), headers=headers)
            logger.info(f'trace-id: {response.headers.get("trace-id")}')

        except TypeError as err:
            self.errors.append('PATCH request error: ' + str(err))
            logger.error('PATCH request error: ' + str(err))
            return None

        if response.status_code == 401 and self.is_unauthorized(response):
            headers['Authorization'] = 'Bearer ' + self.token
            response = requests.patch(url, data=json.dumps(data), headers=headers)

        return response

    def get_request(self, endpoint, params=None, api_version='public.v1'):
        try:
            url = self.env + '/' + endpoint

            headers = {'Authorization': 'Bearer ' + self.token,
                       'Accept': f'application/vnd.allegro.{api_version}+json',
                       'Content-Type': f'application/vnd.allegro.{api_version}+json'}

            logger.info(f'GET request url: {url}')

            response = requests.get(url, headers=headers, params=params)
            logger.info(f'trace-id: {response.headers.get("trace-id")}')

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
            logger.info(f'trace-id: {response.headers.get("trace-id")}')

        except TypeError as err:
            self.errors.append('PUT request error: ' + str(err))
            logger.error('PUT request error: ' + str(err))
            return None
        if response.status_code == 401 and self.is_unauthorized(response):
            headers['Authorization'] = 'Bearer ' + self.token
            response = requests.put(url, data=json.dumps(data), headers=headers)


        return response

    def is_unauthorized(self, response):
        if response.reason == 'Unauthorized':
            access_token, refresh_token, expires_in = self.refresh_token() or (None, None, None)
            if access_token and refresh_token and expires_in is not None:
                self.token = access_token
                self.save_token_in_plugin_configuration(access_token, refresh_token, expires_in)
            return True
        else:
            return False

    def save_token_in_plugin_configuration(self, access_token, refresh_token, expires_in):
        cleaned_data = {
            "configuration": [{"name": "token_value", "value": access_token},
                              {"name": "token_access",
                               "value": (datetime.now() + timedelta(
                                   seconds=expires_in)).strftime("%d/%m/%Y %H:%M:%S")},
                              {"name": "refresh_token", "value": refresh_token}]
        }

        manager = get_plugins_manager()
        plugin = manager.get_plugin(plugin_id='allegro', channel_slug=self.channel)

        plugin.save_plugin_configuration(
            plugin_configuration=PluginConfiguration.objects.get(
                identifier=plugin.PLUGIN_ID,
                channel__slug=self.channel), cleaned_data=cleaned_data)

    def auth_request(self, endpoint, data):
        url = f'{self.plugin_config["auth_env"]}/{endpoint}'

        response = requests.post(
            url,
            auth=requests.auth.HTTPBasicAuth(self.plugin_config['client_id'], self.plugin_config['client_secret']),
            data=json.dumps(data))

        return response

    def get_offer(self, offer_id):
        endpoint = 'sale/offers/' + offer_id

        response = self.get_request(endpoint)

        return json.loads(response.text)

    def get_customer_returns(self):
        endpoint = 'order/customer-returns?limit=1000'
        response = self.get_request(endpoint=endpoint, api_version='beta.v1')
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

    def get_detailed_offer_publication(self, offer_id):
        endpoint = 'sale/offer-publication-commands/' + str(offer_id) + '/tasks'
        response = self.get_request(endpoint=endpoint)

        return json.loads(response.text)

    def unpublish_offers(self, offers, unique_id):
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
        return self.put_request(endpoint=endpoint, data=data)

    def bulk_offer_unpublish(self, skus):
        offers = self.get_offers_by_skus(skus, publication_statuses=['ACTIVE', 'ACTIVATING', 'ENDED'])
        if not isinstance(offers, list):
            logger.error('Error with fetching offers')
            return {'status': 'ERROR', 'message': AllegroErrors.ALLEGRO_ERROR, 'errors': 'Error with fetching allegro offers'}
        if not offers:
            logger.info('No offers found')
            return {'status': 'OK', 'message': AllegroErrors.NO_OFFERS_FOUND, 'errors': []}
        # Check if someone doesnt bid or purchased any offer
        offers_bid_or_purchased = self.offers_bid_or_purchased(offers)
        # TODO: move returned products elsewhere
        offers_bid_or_purchased = self.offers_returned(offers_bid_or_purchased)
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
        response = self.unpublish_offers(offers=offers[:1000], unique_id=unique_id)
        logger.info('Offer Ending: ' + str(response.json()))

        if response.status_code != 201:
            error_message = 'Błąd wycofania oferty z allegro: ' + response.json()['errors'][0]['userMessage']
            return {'status': 'ERROR', 'uuid': unique_id, 'message': AllegroErrors.ALLEGRO_ERROR,
                    'errors': error_message}

        if offers_bid_or_purchased:
            logger.info('Some offers were terminated and some offers are purchased or bid')
            return {'status': 'OK', 'uuid': unique_id, 'message': AllegroErrors.BID_OR_PURCHASED,
                    'errors': offers_bid_or_purchased}
        else:
            logger.info('Some offers were terminated and no offers are purchased or bid')
            return {'status': 'OK', 'uuid': unique_id, 'errors': []}

    def offers_bid_or_purchased(self, offers):
        offers_bid_or_purchased = [
            {"sku": offer["external"]["id"], "offer": offer["id"]}
            for offer in offers
            if offer["saleInfo"]["biddersCount"]
               or offer["stock"]["sold"]
               or not offer["stock"]["available"]
        ]

        logger.info(f'OFFERS BID OR PURCHASED BASED ON ALLEGRO RESPONSE{offers_bid_or_purchased}')
        return offers_bid_or_purchased

    def offers_returned(self, offers):
        skus = [offer['sku'] for offer in offers]
        skus_to_pass = returned_products(skus)
        logger.info(f'SKUS TO PASS{skus_to_pass}')
        filtered_offers = [offer for offer in offers if offer['sku'] not in skus_to_pass]
        logger.info(f'OFFERS BID OR PURCHASED{filtered_offers}')
        return filtered_offers

    def get_offers_by_skus(self, skus, publication_statuses):
        def get_offers_by_max_100_skus(sku_params, publication_statuses_params):
            endpoint = f'sale/offers?{publication_statuses_params}&limit=1000&{sku_params}'
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
                endpoint = f'sale/offers?{publication_statuses_params}&limit=1000&offset={offset}&{sku_params}'
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
            publication_statuses_dict = {"publication.status": publication_statuses}
            publication_statuses_params = urllib.parse.urlencode(publication_statuses_dict, True)
            fetched_offers = get_offers_by_max_100_skus(sku_params, publication_statuses_params)
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
            AllegroErrorHandler.update_product_errors_in_private_metadata(saleor_product, self.errors)
        if 'error' in allegro_product:
            self.product_errors.append(allegro_product.get('error_description'))
            self.errors += self.product_errors
            AllegroErrorHandler.update_product_errors_in_private_metadata(saleor_product, self.errors)

    def error_handling(self, offer, saleor_product):
        must_assign_offer_to_product = False
        if 'error' in offer:
            self.errors.append(offer.get('error_description'))
            AllegroErrorHandler.update_errors_in_private_metadata(
                saleor_product,
                [error for error in self.errors],
                self.channel
            )
        elif 'errors' in offer:
            self.errors += offer['errors']
            AllegroErrorHandler.update_errors_in_private_metadata(
                saleor_product,
                [error.get('message') for error in self.errors],
                self.channel)
        elif offer['validation'].get('errors') is not None:
            if len(offer['validation'].get('errors')) > 0:
                for error in offer['validation'].get('errors'):
                    if 'You cannot publish offer without a related product' in error['message']:
                        must_assign_offer_to_product = True
                    logger.error((error['message'] + ' dla ogłoszenia: ' + self.plugin_config['auth_env'] + '/offer/' + offer['id'] + '/restore'))
                    self.errors.append((error['message'] + 'dla ogłoszenia: ' + self.plugin_config['auth_env'] + '/offer/' + offer['id'] + '/restore'))
                AllegroErrorHandler.update_status_and_publish_data_in_private_metadata(
                    saleor_product, offer['id'],
                    ProductPublishState.MODERATED.value,
                    self.errors, self.channel)
            else:
                self.errors = []
                self.offer_publication(offer.get('id'))
                AllegroErrorHandler.update_status_and_publish_data_in_private_metadata(
                    saleor_product, offer['id'],
                    ProductPublishState.PUBLISHED.value,
                    self.errors, self.channel)

        if must_assign_offer_to_product:
            return 'must_assign_offer_to_product'
