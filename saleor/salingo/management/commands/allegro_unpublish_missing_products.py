import logging

from django.core.management.base import BaseCommand

from saleor.plugins.allegro.api import AllegroAPI, AllegroClientError
from saleor.product.models import ProductVariant
from saleor.plugins.allegro.tasks import bulk_allegro_unpublish


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Unpublish missing Allegro products'

    def add_arguments(self, parser):
        parser.add_argument('--channel', type=str, help='channel slug')

    def handle(self, **kwargs):
        channel_slug = kwargs['channel']
        # Get SKUS from allegro offers
        api = AllegroAPI(channel=channel_slug)
        offers = api.get_offers(publication_statuses=['ACTIVE', 'ACTIVATING'])
        skus = []
        try:
            for batch_offers in offers:
                for offer in batch_offers:
                    skus.append(offer['external']['id'])
        except AllegroClientError as e:
            logger.error(e)
            return
        # Get missing skus
        variants = list(ProductVariant.objects.filter(sku__in=skus).values_list('sku', flat=True))
        missing_skus = list(set(skus).difference(variants))
        logger.info(f'Missing SKUS: {missing_skus}')
        if not missing_skus:
            return
        # Unpublish missing skus
        bulk_allegro_unpublish(channel=channel_slug, skus=missing_skus)
