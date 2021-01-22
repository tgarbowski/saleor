from django.core.management.base import BaseCommand
from django.db import transaction

from saleor.product.models import Product
import logging


class Command(BaseCommand):
    version = "1.0"

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        self.change_meta_in_products()

    @transaction.atomic
    def change_meta_in_products(self):
        json_dict = {}
        products = Product.objects.exclude(private_metadata=json_dict)
        for product in products:
            private_metadata = product.private_metadata
            try:
                if private_metadata.get('publish.allegro.status'):
                    product.store_value_in_private_metadata({'publish.status':
                             product.private_metadata.get('publish.allegro.status')})
                    logging.info(str(product) + ' aktualizacja klucza publish.allegro.status -> publish.status')
                    product.delete_value_from_private_metadata('publish.allegro.status')
                    logging.info(str(product) + ' usunięcie klucza publish.allegro.status')
                if private_metadata.get('publish.allegro.id'):
                    product.store_value_in_private_metadata({'publish.id':
                                 product.private_metadata.get('publish.allegro.id')})
                    logging.info(str(product) + ' aktualizacja klucza publish.allegro.id -> publish.id')
                    product.store_value_in_private_metadata({'publish.target': 'allegro'})
                    logging.info(str(product) + ' dodanie klucza publish.target')
                    product.delete_value_from_private_metadata('publish.allegro.id')
                    logging.info(str(product) + ' usunięcie klucza publish.allegro.id')
                if private_metadata.get('publish.allegro.date'):
                    product.store_value_in_private_metadata({'publish.date':
                             product.private_metadata.get('publish.allegro.date')})
                    logging.info(str(product) + ' aktualizacja klucza publish.allegro.date -> publish.date')
                    product.delete_value_from_private_metadata('publish.allegro.date')
                    logging.info(str(product) + ' usunięcie klucza publish.allegro.date')
                if private_metadata.get('publish.allegro.errors') is not None:
                    product.store_value_in_private_metadata({'publish.errors':
                             product.private_metadata.get('publish.allegro.errors')})
                    logging.info(str(product) + ' aktualizacja klucza publish.allegro.errors -> publish.errors')
                    product.delete_value_from_private_metadata('publish.allegro.errors')
                    logging.info(str(product) + ' usunięcie klucza publish.allegro.errors')

                product.save(update_fields=["private_metadata"])
                logging.info(str(product) + ' zmiany zostały poprawnie zapisane')

            except Exception as ex:
                transaction.set_rollback(True)
                logging.info(str(product) + ' wystąpił błąd podczas przetwarzania produktu' +
                                 ', komunikat błędu: ' +
                                 str(ex))


