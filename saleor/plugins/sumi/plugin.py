import json
import logging
from datetime import datetime
from json import JSONDecodeError

import pytz
from django.db import transaction
from django.http import HttpResponse, HttpResponseNotFound
from django.http.response import JsonResponse

from saleor.plugins.allegro.plugin import AllegroPlugin
from saleor.plugins.base_plugin import BasePlugin, ConfigurationTypeField
from saleor.plugins.manager import get_plugins_manager
from saleor.product.models import ProductVariant, ProductVariantChannelListing
from saleor.warehouse.models import Stock

logger = logging.getLogger(__name__)


class SumiConfiguration:
    token: str


class SumiPlugin(BasePlugin):
    PLUGIN_ID = "sumi"
    PLUGIN_NAME = "Sumi"
    PLUGIN_NAME_2 = "Sumi"
    META_CODE_KEY = "SumiPlugin.code"
    META_DESCRIPTION_KEY = "SumiPlugin.description"
    DEFAULT_CONFIGURATION = [{"name": "token", "value": "666"}]
    CONFIG_STRUCTURE = {
        "token": {
            "type": ConfigurationTypeField.STRING,
            "label": "Token do autoryzacji.",
        }
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @staticmethod
    def get_configuration():
        manager = get_plugins_manager()
        plugin = manager.get_plugin(SumiPlugin.PLUGIN_ID)
        configuration = {item["name"]: item["value"] for item in plugin.configuration}
        return configuration

    @staticmethod
    def is_auth(token):
        configuration = SumiPlugin.get_configuration()
        return configuration.get('token') == token

    @staticmethod
    def create_reservation(request):
        try:
            products = json.loads(request.body.decode('utf-8'))['skus']
        except:
            http_response = HttpResponse()
            http_response.status_code = 400
            logger.debug('create_reservation response: ' + str(http_response))
            return http_response
        logger.info('create_reservation request: ' + str(products))
        results = {"status": "ok", "data": [], "errors": []}
        # TODO: wynieś to do dekoratora
        if SumiPlugin.is_auth(request.headers.get('X-API-KEY')) and \
                request.method == 'POST':
            for product in products:
                product_variant = ProductVariant.objects.filter(sku=product)
                if product_variant.exists():
                    if not SumiPlugin.is_product_reserved(product_variant.first()):
                        product_variant_stock = Stock.objects.\
                            filter(product_variant=product_variant.first())
                        if product_variant_stock.exists():
                            result = SumiPlugin.reserve_product(product_variant_stock.
                                                                first())
                            if isinstance(result, Stock):
                                results.get('data').append(str(result.product_variant))
                            else:
                                if result.get('error') is not None:
                                    results.get('errors').append(result.get('error'))
                                    results['status'] = 'error'
                        else:
                            results.get('errors').append('001: nie znaleziono produktu '
                                                         'o kodzie ' + str(product))
                            results['status'] = 'error'
                    else:
                        pass
                else:
                    results.get('errors').append('001: nie znaleziono produktu o ' +
                                                 'kodzie ' + str(product))
                    results['status'] = 'error'

            logger.debug('create_reservation response: ' + str(results))
            return JsonResponse(results)
        else:
            http_response = HttpResponse()
            http_response.status_code = 403
            logger.debug('create_reservation response: ' + str(http_response))
            return http_response

    @staticmethod
    def get_allegro_token(request):
        if not SumiPlugin.is_auth(request.headers.get('X-API-KEY')) and \
                request.method == 'GET':
            channel = request.GET.get('channel')

            if not channel:
                errors = ['001: Nie podano wartości parametru channel.']
                return JsonResponse({'errors': errors}, status=404)

            manager = get_plugins_manager()
            plugin = manager.get_plugin(AllegroPlugin.PLUGIN_ID, channel_slug=channel)

            if plugin is None:
                errors = ['001: Podany channel nie istnieje.']
                return JsonResponse({'errors': errors}, status=404)

            token_data = SumiPlugin.get_token_and_validate(plugin.configuration)

            if not token_data['token']:
                return JsonResponse({'errors': ['002: Problem z pobraniem tokena.']}, status=404)
            else:
                return JsonResponse(
                    {"token": token_data['token'], "validTill": token_data['valid_till']})
        else:
            return JsonResponse({'errors': ['002: Access forbidden.']}, status=403)

    @staticmethod
    def get_token_and_validate(plugin_config):
        configuration = {item["name"]: item["value"] for item in plugin_config}
        token = configuration.get('token_value')
        token_expiration = configuration.get('token_access')

        try:
            valid_till = datetime.strptime(token_expiration, '%d/%m/%Y %H:%M:%S')\
                .strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            valid_till = None

        return {'token': token, 'valid_till': valid_till}

    @staticmethod
    def reserve_product(product_variant_stock):
        try:
            SumiPlugin.update_reservation_status_in_metadata(product_variant_stock.
                                                             product_variant, True)
            return product_variant_stock
        except Exception as ex:
            return {'error': '003: wystąpił błąd podczas przetwarzania sprzedanego '
                             'produktu ' + str(product_variant_stock.product_variant) +
                             ', komunikat błędu: ' + str(ex)}

    @staticmethod
    @transaction.atomic
    def sell_product(
        product_variant_stock,
        product_variant_channel_listing,
        product_data=None
    ):
        try:
            SumiPlugin.update_allegro_status_in_private_metadata(
                product_variant_stock.product_variant.product, 'sold', product_data)
        except Exception as ex:
            return {
                'error': '003: wystąpił błąd podczas przetwarzania sprzedanego '
                'produktu ' + str(product_variant_stock.product_variant) +
                         ', komunikat błędu: ' + str(ex)}

        try:
            return_object = {
                "sku": str(product_variant_stock.product_variant),
                "name": str(product_variant_stock.product_variant.product),
                "netPrice": str(round(float(product_variant_channel_listing
                                            .cost_price_amount) / 1.23, 2)),
                "grossPrice": str(product_variant_channel_listing
                                  .cost_price_amount),
                "vatRate": '23'
            }
        except Exception as ex:
            transaction.set_rollback(True)
            return {
                'error': '003: wystąpił błąd podczas przetwarzania sprzedanego ' +
                         'produktu ' + str(
                    product_variant_stock.product_variant) + ', komunikat błędu: ' +
                         str(ex)}
        try:
            product_variant_stock.decrease_stock(1)
        except:
            return {'error': '002: stan magazynowy produktu ' + str(
                product_variant_stock.product_variant) + ' wynosi 0'}

        return return_object

    @staticmethod
    def update_reservation_status_in_metadata(product_variant, status):
        product_variant.store_value_in_metadata({'reserved': status})
        product_variant.save(update_fields=["metadata"])

    @staticmethod
    def update_allegro_status_in_private_metadata(product, status, product_data=None):
        product.store_value_in_private_metadata({'publish.allegro.status': status})
        date = None
        price = None
        if product_data is not None:
            date = product_data.get('date')
            price = product_data.get('price')

        if date is not None:
            product.store_value_in_private_metadata(
                {'publish.status.date': datetime.strptime(date,
                                  '%Y-%m-%dT%H:%M:%SZ').strftime("%Y-%m-%d %H:%M:%S")})
        else:
            product.store_value_in_private_metadata(
                {'publish.status.date': datetime.now(pytz.timezone('Europe/Warsaw')).
                    strftime('%Y-%m-%d %H:%M:%S')})

        if price is not None:
            product.store_value_in_private_metadata({'publish.allegro.price': price})

        product.save(update_fields=["private_metadata"])

    @staticmethod
    def is_product_reserved(product_variant):
        if product_variant.metadata.get('reserved') is not None:
            if product_variant.metadata.get('reserved'):
                return True
            else:
                return False
        else:
            return False

    @staticmethod
    def is_product_sold(product):
        if product.private_metadata.get('publish.allegro.status') is not None:
            if product.private_metadata.get('publish.allegro.status') == 'sold':
                return True
            else:
                return False
        else:
            return False

    @staticmethod
    def cancel_product_reservation(product_variant_stock):
        try:
            SumiPlugin.update_reservation_status_in_metadata(product_variant_stock.
                                                             product_variant, False)
            return product_variant_stock
        except Exception as ex:
            return {'error': '003: wystąpił błąd podczas przetwarzania produktu ' + str(
                product_variant_stock.product_variant) + ', komunikat błędu: ' +
                             str(ex)}

    @staticmethod
    @transaction.atomic
    def cancel_sold_product_reservation(product_variant_stock):
        try:
            SumiPlugin.update_allegro_status_in_private_metadata(
                product_variant_stock.product_variant.product, 'moderated')
            product_variant_stock.increase_stock(1)
            return product_variant_stock
        except Exception as ex:
            transaction.set_rollback(True)
            return {'error': '003: wystąpił błąd podczas przetwarzania sprzedanego '
                             'produktu ' + str(product_variant_stock.product_variant) +
                             ', komunikat błędu: ' +
                             str(ex)}

    @staticmethod
    def cancel_reservation(request):
        try:
            products = json.loads(request.body.decode('utf-8'))['skus']
        except:
            http_response = HttpResponse()
            http_response.status_code = 400
            logger.debug('cancel_reservation response: ' + str(http_response))
            return http_response
        logger.info('cancel_reservation request: ' + str(products))
        results = {"status": "ok", "data": [], "errors": []}
        # TODO: wynieś to do dekoratora i wywołuj PRZED parsowaniem requesta
        if SumiPlugin.is_auth(
                request.headers.get('X-API-KEY')) and request.method == 'POST':
            for product in products:
                product_variant = ProductVariant.objects.filter(sku=product)
                if product_variant.exists():
                    product_variant_stock = Stock.objects.\
                        filter(product_variant=product_variant.first())
                    if SumiPlugin.is_product_reserved(product_variant.first()):
                        if product_variant_stock.exists():
                            result = SumiPlugin.cancel_product_reservation(
                                product_variant_stock.first())
                            if isinstance(result, Stock):
                                results.get('data').append(str(result.product_variant))
                            else:
                                if result.get('error') is not None:
                                    results.get('errors').append(result.get('error'))
                                    results['status'] = 'error'
                    if SumiPlugin.is_product_sold(product_variant.first().product):
                        if product_variant_stock.exists():
                            result = SumiPlugin.cancel_sold_product_reservation(
                                product_variant_stock.first())
                            if isinstance(result, Stock):
                                results.get('data').append(str(result.product_variant))
                                results['data'] = list(set(results.get('data')))
                            else:
                                if result.get('error') is not None:
                                    results.get('errors').append(result.get('error'))
                                    results['status'] = 'error'
                    else:
                        pass

                else:
                    results.get('errors').append(
                        '001: nie znaleziono produktu o kodzie ' + str(product))
                    results['status'] = 'error'

            logger.debug('cancel_reservation response: ' + str(results))
            return JsonResponse(results)
        else:
            http_response = HttpResponse()
            http_response.status_code = 403
            logger.debug('cancel_reservation response: ' + str(http_response))
            return http_response

    @staticmethod
    def sell_products(request):
        try:
            products = json.loads(request.body.decode('utf-8'))['skus']
        except:
            http_response = HttpResponse()
            http_response.status_code = 400
            logger.debug('sell_products response: ' + str(http_response))
            return http_response
        logger.info('sell_products request: ' + str(products))
        results = {"status": "ok", "data": [], "errors": []}
        # TODO: wynieś to do dekoratora
        if SumiPlugin.is_auth(
                request.headers.get('X-API-KEY')) and request.method == 'POST':
            for product in products:
                product_variant = ProductVariant.objects.filter(sku=product)
                if product_variant.exists():
                    product_variant_stock = Stock.objects.filter(
                        product_variant=product_variant.first())
                    if Stock.objects.exists():
                        if product_variant_stock.first().quantity > 0:
                            result = SumiPlugin.sell_product(product_variant_stock.first())
                            if result.get('error'):
                                results['status'] = 'error'
                                results.get('errors').append(result.get('error'))
                            else:
                                results.get('data').append(result)
                        else:
                            results.get('errors').append('002: stan magazynowy ' +
                                                         'produktu ' + str(
                product_variant_stock.first().product_variant) + ' wynosi 0')
                            results['status'] = 'error'
                    else:
                        results.get('errors').append(
                            '001: nie znaleziono produktu o kodzie ' + str(
                                product))
                        results['status'] = 'error'

                else:
                    results.get('errors').append(
                        '001: nie znaleziono produktu o kodzie ' + str(product))
                    results['status'] = 'error'

            logger.debug('sell_products response: ' + str(results))
            return JsonResponse(results)
        else:
            http_response = HttpResponse()
            http_response.status_code = 403
            logger.debug('sell_products response: ' + str(http_response))
            return http_response

    @classmethod
    def save_plugin_configuration(cls, plugin_configuration: "PluginConfiguration",
                                  cleaned_data):
        current_config = plugin_configuration.configuration
        configuration_to_update = cleaned_data.get("configuration")
        if configuration_to_update:
            cls._update_config_items(configuration_to_update, current_config)
        if "active" in cleaned_data:
            plugin_configuration.active = cleaned_data["active"]
        cls.validate_plugin_configuration(plugin_configuration)
        plugin_configuration.save()
        if plugin_configuration.configuration:
            cls._append_config_structure(plugin_configuration.configuration)
        return plugin_configuration

    @staticmethod
    def locate_products(request):
        try:
            products = json.loads(request.body.decode('utf-8')).get('locations')
        except JSONDecodeError:
            http_response = HttpResponse()
            http_response.status_code = 400
            logger.debug('locate_products response: ' + str(http_response))
            return http_response
        logger.info('locate_products request: ' + str(products))
        results = {"status": "ok", "data": [], "errors": []}
        if SumiPlugin.is_auth(
                request.headers.get('X-API-KEY')) and request.method == 'POST':
            if products is not None:
                for product in products:
                    if type(product) is list:
                        try:
                            sku = product[0]
                            location = product[1]
                            product_variant = ProductVariant.objects.filter(sku=sku)
                            if product_variant.exists():
                                result = SumiPlugin.save_location_in_private_metadata(
                                                    product_variant.first(), location)
                                if isinstance(result, ProductVariant):
                                    results.get('data').append(str(result))
                                else:
                                    results.get('errors').append(result.get('error'))
                                    results['status'] = 'error'
                            else:
                                results.get('errors').append(
                                    '001: nie znaleziono produktu o kodzie ' + str(
                                        sku))
                                results['status'] = 'error'
                        except IndexError as ex:
                            results['status'] = 'error'
                            results.get('errors').append('003: wystąpił błąd podczas ' +
                                                         'przetwarzania sprzedanego ' +
                                                         'produktu ' + str(product) +
                                                         ', komunikat błędu: ' + str(ex))
            else:
                results.get('errors').append(
                    '003: inny błąd')
                results['status'] = 'error'

            logger.debug('locate_products response: ' + str(results))
            return JsonResponse(results)
        else:
            http_response = HttpResponse()
            http_response.status_code = 403
            logger.debug('locate_products response: ' + str(http_response))
            return http_response

    @staticmethod
    def save_location_in_private_metadata(product_variant, location):
        try:
            product_variant.store_value_in_private_metadata({'location': location})
            product_variant.save(update_fields=["private_metadata"])
            return product_variant
        except:
            return {'error': '003: wystąpił błąd podczas przetwarzania produktu ' + str(
                product_variant)}

    @staticmethod
    def sell_products_v2(request):
        http_response = HttpResponse()
        if not SumiPlugin.is_auth(
                request.headers.get('X-API-KEY')) or request.method != 'POST':
            http_response.status_code = 403
            logger.debug('sell_products_v2 response: ' + str(http_response))
            return http_response

        try:
            products = json.loads(request.body.decode('utf-8')).get('products')
        except JSONDecodeError:
            http_response.status_code = 400
            logger.debug('sell_products_v2 response: ' + str(http_response))
            return http_response
        if products is None:
            http_response.status_code = 400
            logger.debug('sell_products_v2 response: ' + str(http_response))
            return http_response

        logger.info('sell_products_v2 request: ' + str(products))
        results = {"status": "ok", "data": [], "errors": []}
        for product in products:
            if product.get('sku') is not None and product.get('date') is not None \
                    and product.get('price') is not None:
                product_variant = ProductVariant.objects.filter(
                    sku=product.get('sku'))
                if product_variant.exists():
                    product_variant_stock = Stock.objects.filter(
                        product_variant=product_variant.first())
                    product_variant_channel_listing = ProductVariantChannelListing.objects.get(
                        variant=product_variant.first()
                    )
                    if Stock.objects.exists():
                        if product_variant_stock.first().quantity > 0:
                            result = SumiPlugin.sell_product(
                                product_variant_stock=product_variant_stock.first(),
                                product_variant_channel_listing=product_variant_channel_listing,
                                product_data=product)
                            if result.get('error'):
                                results['status'] = 'error'
                                results.get('errors').append(result.get('error'))
                            else:
                                results.get('data').append(result)
                        else:
                            results.get('errors').append(
                                '002: stan magazynowy produktu ' + str(
                                    product_variant_stock.first().product_variant) +
                                ' wynosi 0')
                            results['status'] = 'error'
                    else:
                        results.get('errors').append(
                            '001: nie znaleziono produktu o kodzie ' + str(
                                product.get('sku')))
                        results['status'] = 'error'

                else:
                    results.get('errors').append(
                        '001: nie znaleziono produktu o kodzie ' + str(
                            product.get('sku')))
                    results['status'] = 'error'
            else:
                results.get('errors').append(
                    '003: wystąpił błąd podczas przetwarzania danych ' + str(
                        product))
                results['status'] = 'error'

        logger.debug('sell_products_v2 response: ' + str(results))
        return JsonResponse(results)
