from django.core.management.base import BaseCommand

from saleor.plugins.allegro.tasks import bulk_allegro_unpublish_buy_now


class Command(BaseCommand):
    version = "1.0"

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        bulk_allegro_unpublish_buy_now.delay()
