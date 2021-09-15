import re
from collections import defaultdict
from datetime import datetime, timedelta

from .utils import get_plugin_configuration
from saleor.product.models import ProductVariant


class ProductMapperFactory:

    @staticmethod
    def get_mapper():
        mapper = ProductMapper(AllegroProductMapper).mapper()
        return mapper


class ProductMapper:

    def __init__(self, mapper):
        self.mapper = mapper

    def mapper(self):
        return self.mapper.map()


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
        return {item['data']['text'].split(":")[0]: item['data']['text'].split(":")[1].strip() for item
                in list_in[1:] if len(item['data']['text'].split(':')) > 1}

    def set_description(self, product):
        product_sections = []
        product_items = [{
            'type': 'IMAGE',
            'url': self.saleor_images[0]
        }]

        product_description = self.parse_list_to_map(product.description['blocks'])

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
            'content': '<p>' + product.description['blocks'][0]['data']['text'].replace(
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
            print('xDDDDD')
            print(self.saleor_product.description['blocks'])
            description_blocks = self.parse_list_to_map(
                self.saleor_product.description['blocks'])
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
            from saleor.product.models import ProductVariantChannelListing
            product_variant_channel_listing = ProductVariantChannelListing.objects.get(
                variant_id=product_variant.id,
                channel_id=3
            )

            self.set_price_amount(
                str(product_variant_channel_listing.price_amount))
            self.set_price_currency(product_variant_channel_listing.currency)
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
