from datetime import datetime
import requests

import boto3
from botocore.client import ClientError

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from saleor.product.models import ProductMedia

class Command(BaseCommand):
    version = "1.0"

    def add_arguments(self, parser):
        parser.add_argument('--start_date', type=str, help='product creation start date')
        parser.add_argument('--end_date', type=str, help='product creation end date')
        parser.add_argument('--source', type=str, help='s3 source bucket')
        parser.add_argument('--target', type=str, help='s3 target bucket')
        parser.add_argument('--backup', type=str, help='s3 backup bucket')
        parser.add_argument('--mode', type=str, help='processing mode')

    def handle(self, *args, **options):
        self.start_date = options['start_date']
        self.end_date = options['end_date']
        self.source = options['source']
        self.target = options['target']
        self.backup = options['backup']
        self.mode = options['mode']

        self.validate_dates()

        if self.mode == 'backup':
            self.validate_bucket(self.backup)
            self.process_images_backup_mode()
        elif self.mode == 'migration':
            self.process_images_migration_mode()

    def process_images_migration_mode(self):
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

    def process_images_backup_mode(self):
        images = self.get_images()

        url = f'{settings.REMOVER_API_URL}/process_images/backup'
        headers = {
            "X-API-KEY": settings.REMOVER_API_KEY
        }
        data = {
            "source": self.source,
            "target": self.target,
            "backup": self.backup,
            "images": images
        }

        response = requests.post(
            url=url,
            json=data,
            headers=headers
        )
        print(response.json())

    def get_images(self):
        images = ProductMedia.objects.raw('''
                select
                ppi.id,
                ppi.image,
                ppi.ppoi
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
                and cast(pp.created_at as date) between %s and %s
                and pa."name" = 'Kolor'
                and pav."name" != 'biały'
                and pt."name" not like 'Biustonosz%%'
                order by pv.sku
                ''', [self.start_date, self.end_date])

        images_list = [image.image.name for image in images]

        return images_list

    def validate_bucket(self, bucket):
        s3 = boto3.resource('s3')

        try:
            s3.meta.client.head_bucket(Bucket=bucket)
        except ClientError:
            raise CommandError(
                "Wrong backup bucket name. "
            )

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
