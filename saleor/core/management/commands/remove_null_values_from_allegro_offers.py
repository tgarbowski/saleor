import csv
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from django.core.management.base import BaseCommand
from saleor.product.models import ProductVariant
from saleor.plugins.allegro.api import AllegroAPI
from saleor.plugins.allegro.parameters_mapper import ParametersMapperFactory
from saleor.plugins.allegro.plugin import AllegroPlugin
from saleor.plugins.allegro.products_mapper import ProductMapperFactory
from saleor.plugins.manager import PluginsManager


class Command(BaseCommand):
    version = "1.0"

    def add_arguments(self, parser):
        parser.add_argument('--pass', type=str, help='password for email sender')
        parser.add_argument('--path', type=str, help='offset for offers list')

    def handle(self, *args, **options):
        self.remove_null_values_from_allegro_offers(options)

    def valid_product(self, product):
        errors = []

        if not product.is_published:
            errors.append('flaga is_published jest ustawiona na false')
        if product.private_metadata.get('publish.allegro.status') != 'published':
            errors.append('publish.allegro.status != published')

        return errors

    def update_allegro_offer(self, allegro_product, allegro_id):

        endpoint = 'sale/offers/' + allegro_id

        allegro_product['id'] = allegro_id

        response = self.allegro_api.put_request(endpoint=endpoint, data=allegro_product)
        return json.loads(response.text)


    def remove_null_values_from_allegro_offers(self, options):

        manage = PluginsManager(plugins=["saleor.plugins.allegro.plugin.AllegroPlugin"])
        plugin_configs = manage.get_plugin(AllegroPlugin.PLUGIN_ID)
        conf = {item["name"]: item["value"] for item in plugin_configs.configuration}
        token = conf.get('token_value')
        self.allegro_api = AllegroAPI(token)

        data = self.read_csv(options['path'])

        skus = data['sku']
        product_variants = list(ProductVariant.objects.filter(sku__in=skus))

        sku_errors = []

        for product_variant in product_variants:

            self.product = {}
            errors = []

            if product_variant:
                saleor_product = product_variant.product
                allegro_id = saleor_product.private_metadata.get('publish.allegro.id')

                if allegro_id is not None:
                    category_id = saleor_product.product_type.metadata.get(
                        'allegro.mapping.categoryId')

                    require_parameters = self.allegro_api.get_require_parameters(category_id)

                    parameters_mapper = ParametersMapperFactory().get_mapper()

                    parameters = parameters_mapper.set_product(
                        saleor_product).set_require_parameters(require_parameters).run_mapper()

                    product_mapper = ProductMapperFactory().get_mapper()

                    try:
                        product = product_mapper.set_saleor_product(saleor_product) \
                        .set_saleor_images(self.allegro_api.upload_images(saleor_product)) \
                        .set_saleor_parameters(parameters).set_category(
                        category_id).set_obj_publication_starting_at('2020-10-10 10:10').\
                            set_offer_type('AUCTION').run_mapper()
                    except:
                        pass

                    offer = self.allegro_api.update_allegro_offer(allegro_product=product,
                                                      allegro_id=allegro_id)

                    if 'error' in offer:
                        errors.append(offer.get('error_description'))

                    elif 'errors' in offer:
                        errors += offer['errors']

                    elif offer['validation'].get('errors') is not None:
                        if len(offer['validation'].get('errors')) > 0:
                            for error in offer['validation'].get('errors'):
                                errors.append(error['message'])
                else:
                    errors.append('produkt nie ma allegro id')

                sku_errors.append({'sku': product_variant.sku, 'errors': errors})

        html_errors_list = plugin_configs.create_table(sku_errors)
        return self.send_mail(html_errors_list, options)


    def read_csv(self, path):
        with open(path, 'rU') as infile:
            reader = csv.DictReader(infile)
            data = {}
            for row in reader:
                for header, value in row.items():
                    try:
                        data[header].append(value)
                    except KeyError:
                        data[header] = [value]
        return data

    def send_mail(self, html_errors_list, options):
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login('noreply.salingo@gmail.com', options['pass'])

        msg = MIMEMultipart('alternative')

        html = MIMEText(html_errors_list, 'html')

        msg.attach(html)
        msg['Subject'] = 'Logi z zadania aktualizacji ofert'
        msg['From'] = 'sync+noreply.salingo@gmail.com'
        msg['To'] = 'sync+noreply.salingo@gmail.com'

        server.sendmail('noreply.salingo@gmail.com', 'noreply.salingo@gmail.com', msg.as_string())
