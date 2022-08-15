from datetime import datetime
import logging

from django.db import connection
from django.core.management.base import BaseCommand, CommandError

from saleor.product.models import Category, Product
from saleor.plugins.allegro.api import AllegroAPI
from saleor.plugins.allegro.utils import product_ids_to_skus


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Archive sold products'

    def add_arguments(self, parser):
        parser.add_argument('--start_date', type=str, help='start date')
        parser.add_argument('--end_date', type=str, help='end date')

    def handle(self, **kwargs):
        self.set_dates(**kwargs)
        self.validate_dates()

        initial_amount = self.get_products_count()
        logger.info(f'Initial amount: {initial_amount}')

        product_ids = self.get_products_ids()
        self.check_active_allegro_offers(product_ids)
        archived_amount = self.archive_products()
        logger.info(f'Archived amount: {archived_amount}')

        if self.verify_archivisation(initial_amount, archived_amount):
            if archived_amount:
                self.delete_products(product_ids)
                message = f'Pomyślnie zarchiwizowano {archived_amount} produktów.'
            else:
                message = f'Brak produktów do archiwizacji za podany okres.'
        else:
            message = f'Początkowa ilość produktów {initial_amount} różna od' \
                      f'zarchwizowanej ilości produktow: {archived_amount}'

        logger.info(f'Archived amount: {message}')

    def set_dates(self, **kwargs):
        self.start_date = kwargs.get('start_date')
        self.end_date = kwargs.get('end_date')

    @staticmethod
    def check_active_allegro_offers(product_ids):
        allegro_api = AllegroAPI(channel='allegro')
        skus = product_ids_to_skus(product_ids)
        offers = allegro_api.get_offers_by_skus(skus, publication_statuses=['ACTIVE', 'ACTIVATING'])

        if isinstance(offers, list) and offers:
            offers_active = [offer['external']['id'] for offer in offers]
            raise Exception(f'Active offers: {offers_active}')
        elif offers is False:
            raise Exception(f'Errors with fetching offers')

    @staticmethod
    def delete_products(ids):
        total_count = len(ids)
        limit = 100

        for offset in range(0, total_count, limit):
            Product.objects.filter(id__in=ids[offset:offset + limit]).delete()

    @staticmethod
    def verify_archivisation(initial_amount, archived_amount):
        return initial_amount == archived_amount

    def archive_products(self):
        with connection.cursor() as cursor:
            cursor.callproc('archive_products', [self.start_date, self.end_date])
            row = cursor.fetchone()
            amount = row[0]

        return amount

    def get_products_count(self):
        with connection.cursor() as cursor:
            cursor.execute('''
                select COUNT(id)
                from product_product
                where Cast(private_metadata->>'publish.status.date' as DATE)::timestamp between %s and %s
                and (
                    private_metadata->>'publish.allegro.status' = 'sold'
                    or (private_metadata->>'publish.allegro.status' = 'moderated'
                        and private_metadata->>'publish.allegro.price' is not null
                        )
                    )
                and length(coalesce(metadata->>'bundle.id','')) = 0
            ''', [self.start_date, self.end_date])
            row = cursor.fetchone()
            amount = row[0]
        return amount

    def get_products_ids(self):
        products = Category.objects.raw('''
            select id from product_product
            where Cast(private_metadata->>'publish.status.date' as DATE)::timestamp between %s and %s
            and (
                private_metadata->>'publish.allegro.status' = 'sold'
                or (private_metadata->>'publish.allegro.status' = 'moderated'
                    and private_metadata->>'publish.allegro.price' is not null
                    )
                )
            and length(coalesce(metadata->>'bundle.id','')) = 0
        ''', [self.start_date, self.end_date])

        product_ids = [product.id for product in products]
        return product_ids

    def validate_dates(self):
        if not self.start_date:
            raise CommandError(
                "Unknown start date. "
                "Use `--start_date` flag "
                "eg. --start_date '2021-08-17'"
            )
        if not self.end_date:
            raise CommandError(
                "Unknown end_date date. "
                "Use `--end_date` flag "
                "eg. --end_date '2021-08-17'"
            )

        try:
            start_date = datetime.strptime(self.start_date, "%Y-%m-%d")
        except ValueError:
            raise CommandError(
                "Wrong end date. "
                "`--end_date` flag should be in format eg. `2021-08-17`"
            )

        try:
            end_date = datetime.strptime(self.end_date, "%Y-%m-%d")
        except ValueError:
            raise CommandError(
                "Wrong end date. "
                "`--end_date` flag should be in format eg. `2021-08-17`"
            )

        if start_date > end_date:
            raise CommandError(
                "Provided start date is greater than end date."
            )