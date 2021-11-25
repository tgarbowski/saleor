import boto3

from django.core.management.base import BaseCommand

from saleor.product.models import ProductMedia
from saleor.core.utils import create_thumbnails
from collections import namedtuple


class Command(BaseCommand):
    version = "1.0"

    def add_arguments(self, parser):
        parser.add_argument(
            "--image",
            type=str,
            help=('Image path')
        )
        parser.add_argument(
            "--bucket",
            type=str,
            help=('Bucket name')
        )

    def handle(self, *args, **options):
        image = options.get("image")
        bucket = options.get("bucket")
        media = ProductMedia.objects.get(image=image)
        file = self.get_file_from_s3(key=image, bucket=bucket)
        self.upload_from_memory_to_s3(key=image, bucket=bucket, data=file)
        self.update_thumbnails(image)
        create_thumbnails(pk=media.id, model=ProductMedia, size_set="products")

    def get_file_from_s3(self, key, bucket):
        s3 = boto3.client('s3')
        image = s3.get_object(
            Bucket=bucket,
            Key=key
        )
        data = image['Body'].read()

        return data

    def upload_from_memory_to_s3(self, key, bucket, data):
        s3 = boto3.client('s3')
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=data
        )

    def update_thumbnails(self, image):
        client = boto3.client('s3')
        Size = namedtuple('Size', ['x', 'y'])
        sizes = [Size(*t) for t in
                 [(60, 60), (120, 120), (255, 255), (510, 510), (540, 540),
                  (1080, 1080)]]

        for size in sizes:
            key = f'__sized__/{image}-thumbnail-{size.x}x{size.y}-70.jpg'
