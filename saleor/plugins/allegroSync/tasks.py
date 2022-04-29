import json
import logging

from ...celeryconf import app
from saleor.product.models import ProductVariant, Product
from saleor.plugins.allegro.api import AllegroAPI
from saleor.plugins.manager import get_plugins_manager
from saleor.plugins.models import PluginConfiguration
from .utils import valid_product, send_mail

logger = logging.getLogger(__name__)


@app.task()
def synchronize_allegro_offers_task():
    channels = list(PluginConfiguration.objects.filter(identifier='allegro').values_list(
            'channel__slug', flat=True))

    for channel in channels:
        synchronize_allegro_offers_one_channel(channel)

def synchronize_allegro_offers_one_channel(channel):
    allegro_api = AllegroAPI(channel=channel)
    params = {'publication.status': ['ACTIVE'], 'limit': '1', 'offset': 0}
    response = allegro_api.get_request('sale/offers', params)
    total_count = json.loads(response.text).get('totalCount')

    if total_count in [None, 0]:
        return
    limit = 1000
    errors = []
    updated_amount = 0
    manager = get_plugins_manager()
    plugin = manager.get_plugin(plugin_id='allegro', channel_slug=channel)

    for i in range(int(int(total_count) / limit) + 1):
        offset = i * limit
        params = {'publication.status': ['ACTIVE'], 'limit': limit, 'offset': offset}
        response = allegro_api.get_request('sale/offers', params)
        logger.info(
            f'Fetching 1000 offers status: {response.status_code}, offset: {offset}')
        offers = json.loads(response.text).get('offers')
        if offers:
            skus = [offer.get('external').get('id') for offer in offers]
            product_variants = list(
                ProductVariant.objects.select_related('product').filter(sku__in=skus))
            products_to_update = []
            for offer in offers:
                product_errors = []
                sku = offer.get('external').get('id')
                offer_id = offer.get('id')
                variant = next((x for x in product_variants if x.sku == sku), None)
                if variant:
                    product = variant.product
                    product_errors = valid_product(product)
                    if product.private_metadata.get('publish.allegro.id') != offer_id:
                        product.private_metadata['publish.allegro.id'] = offer_id
                        products_to_update.append(product)
                else:
                    product_errors.append('nie znaleziono produktu o podanym SKU')

                if product_errors:
                    errors.append({'sku': sku, 'errors': product_errors})

            if products_to_update:
                Product.objects.bulk_update(products_to_update, ['private_metadata'])
                updated_amount += len(products_to_update)

    html_errors_list = plugin.create_table(errors)

    send_mail(html_errors_list, updated_amount)