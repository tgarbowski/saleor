from django.core.management.base import BaseCommand

from saleor.plugins.allegro.orders import insert_allegro_orders


class Command(BaseCommand):
    help = 'Save allegro orders in database.'

    def add_arguments(self, parser):
        parser.add_argument('--channel', type=str, help='channel slug')
        parser.add_argument('--days', type=int, help='past days')

    def handle(self, **kwargs):
        insert_allegro_orders(
            channel_slug=kwargs['channel'],
            past_days=kwargs['days']
        )
