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
                ppm.id,
                ppm.image,
                ppm.ppoi
                from
                product_product pp,
                product_productmedia ppm,
                product_producttype ppt,
                product_productvariant ppv,
                attribute_assignedproductattribute aapa,
                attribute_assignedproductattributevalue aapav,
                attribute_attributevalue aav,
                attribute_attribute aa
                where
                pp.id = ppm.product_id
                and pp.product_type_id = ppt.id
                and pp.id = ppv.product_id
                and pp.id = aapa.product_id
                and aapa.id = aapav.assignment_id
                and aapav.value_id = aav.id
                and aav.attribute_id = aa.id
                and cast(pp.created as date) between %s and %s
                and aa."name" = 'Kolor'
                and aav."name" != 'biały'
                and ppt."name" not like 'Biustonosz%%'
                order by ppv.sku
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
