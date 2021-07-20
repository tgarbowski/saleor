from django.core.management.base import BaseCommand

from saleor.plugins.allegro.tasks import bulk_allegro_publish_unpublished_to_auction


class Command(BaseCommand):
    version = "1.0"

    def add_arguments(self, parser):
        parser.add_argument('--limit', help='products amount', default=20000)

    def handle(self, *args, **options):
        limit = options['limit']
        bulk_allegro_publish_unpublished_to_auction.delay(limit)
