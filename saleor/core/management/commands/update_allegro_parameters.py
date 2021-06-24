from django.core.management.base import BaseCommand

from saleor.plugins.allegro.tasks import update_published_offers_parameters


class Command(BaseCommand):
    version = "1.0"

    def add_arguments(self, parser):
        parser.add_argument('--limit', help='products amount')
        parser.add_argument('--offset', help='products offset')

    def handle(self, *args, **options):
        limit = options['limit']
        offset = options['offset']
        update_published_offers_parameters.delay(limit, offset)

