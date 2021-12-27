from collections import namedtuple
from io import BytesIO

import boto3
from PIL import Image

from django.conf import settings


class BackupImageRetrieval:
    def __init__(self, image):
        self.s3 = boto3.client('s3')
        self.bucket = settings.AWS_MEDIA_BUCKET_NAME
        self.backup_bucket = settings.AWS_BACKUP_BUCKET_NAME
        self.image = image

    def handle(self):
        file = self.get_file_from_s3(key=self.image, bucket=self.backup_bucket)
        self.upload_from_memory_to_s3(key=self.image, bucket=self.bucket, data=file)
        self.update_thumbnails(image=file, image_name=self.image)

    def get_file_from_s3(self, key, bucket):
        image = self.s3.get_object(Bucket=bucket, Key=key)
        data = image['Body'].read()

        return data

    def upload_from_memory_to_s3(self, key, bucket, data):
        self.s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=data
        )

    @staticmethod
    def create_thumbnail(buffered_image, size):
        thumbnail = BytesIO()
        main_image = Image.open(buffered_image)
        main_image.thumbnail(size)
        main_image.save(thumbnail, format=main_image.format)
        thumbnail.seek(0)

        return thumbnail

    @staticmethod
    def get_thumbnail_sizes():
        Size = namedtuple('Size', ['x', 'y'])
        thumbnail_sizes = [(60, 60), (120, 120), (255, 255), (510, 510), (540, 540), (1080, 1080)]
        sizes = [Size(*t) for t in thumbnail_sizes]

        return sizes

    def update_thumbnails(self, image, image_name):
        sizes = self.get_thumbnail_sizes()

        for size in sizes:
            buffered_image = BytesIO(image)
            thumbnail = self.create_thumbnail(buffered_image, size)
            name = self.create_thumbnail_name(image_name)
            key = f'__sized__/{name}-thumbnail-{size.x}x{size.y}-70.jpg'
            self.upload_from_memory_to_s3(key=key, bucket=self.bucket, data=thumbnail)

    @staticmethod
    def create_thumbnail_name(image):
        if '.' in image:
            return image.split('.', 1)[0]
        else:
            return image
