from datetime import datetime
import requests

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from saleor.product.models import ProductImage

class Command(BaseCommand):
    version = "1.0"

    def add_arguments(self, parser):
        parser.add_argument('--start_date', type=str, help='product creation start date')
        parser.add_argument('--end_date', type=str, help='product creation end date')
        parser.add_argument('--source', type=str, help='s3 source bucket')
        parser.add_argument('--target', type=str, help='s3 target bucket')

    def handle(self, *args, **options):
        self.start_date = options['start_date']
        self.end_date = options['end_date']
        self.source = options['source']
        self.target = options['target']

        self.validate_dates()
        self.process_images()

    def process_images(self):
        images = self.get_images()

        url = f'{settings.REMOVER_API_URL}/process_images/migration'
        headers = {
            "X-API-KEY": settings.REMOVER_API_KEY
        }
        data = {
            "source": self.source,
            "target": self.target,
            "images": images
        }

        response = requests.post(
            url=url,
            json=data,
            headers=headers
        )
        print(response.json())

    def get_images(self):
        images = ProductImage.objects.raw('''
                select
                ppi.image id,
                ppi.image image
                from
                product_product pp,
                product_productimage ppi,
                product_producttype pt,
                product_productvariant pv,
                product_assignedproductattribute paa,
                product_assignedproductattribute_values paav,
                product_attributevalue pav,
                product_attribute pa
                where
                pp.id = ppi.product_id
                and pp.product_type_id = pt.id
                and pp.id = pv.product_id
                and pp.id = paa.product_id
                and paa.id = paav.assignedproductattribute_id
                and paav.attributevalue_id = pav.id
                and pav.attribute_id = pa.id
                and pp.created_at between %s and %s
                and pa."name" = 'Kolor'
                and pav."name" != 'biały'
                and pt."name" not like 'Biustonosz%%'
                order by pv.sku
                ''', [self.start_date, self.end_date])

        images_list = [image.id for image in images]

        return images_list

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
