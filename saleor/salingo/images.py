from collections import namedtuple
from io import BytesIO
import math
import os
import secrets
import random
from typing import List, Tuple

import boto3
from PIL import Image

from django.conf import settings
from django.core.files.images import ImageFile

from saleor.product import ProductMediaTypes
from saleor.product.models import Product, ProductMedia
from saleor.product.thumbnails import create_product_thumbnails


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


class AwsBucketUtils:
    def get_s3_bucket(self):
        s3 = boto3.resource('s3')
        bucket_name = os.environ.get("AWS_MEDIA_BUCKET_NAME")
        return s3.Bucket(bucket_name)

    def get_s3_images(self, images) -> List[bytes]:
        images_data = []
        bucket = self.get_s3_bucket()

        for image in images:
            img_component = bucket.Object(image.image.name)
            img_data = img_component.get().get('Body').read()
            images_data.append(img_data)
        return images_data


class CollageCreator:
    def __init__(self, images):
        self.images = images
        self.aws_bucket = AwsBucketUtils()

    def calculate_grid(self, initial_images_amount: int) -> Tuple[int, int]:
        cols = int(math.sqrt(initial_images_amount))
        rows = math.floor(initial_images_amount / cols)
        return cols, rows

    def width(self, cols: int) -> int:
        col_px = 318
        return col_px * cols

    def height(self, rows: int) -> int:
        row_px = 336
        return row_px * rows

    def create_empty_image(self, width: int, height: int) -> Image:
        return Image.new("RGBA", (width, height), color=(255, 255, 255, 255))

    def _create_collage(self, cols: int, rows: int, images_data):
        i = 0
        width = self.width(cols)
        height = self.height(rows)
        collage = self.create_empty_image(width=width, height=height)

        for x in range(0, width, int(width / cols)):
            for y in range(0, height, int(height / rows)):
                image = Image.open(BytesIO(images_data[i]))

                resized_image = image.resize(
                    (width, int(image.size[1] * (width / image.size[0])))
                )
                required_loss = (resized_image.size[1] - width)
                resized_image = resized_image.crop(
                    box=(0, required_loss / 2, width,
                         resized_image.size[1] - required_loss / 2))

                resized_image = resized_image.resize(
                    (int(width / cols), int(height / rows)))
                collage.paste(resized_image, (x, y))
                i += 1

        return collage

    def create(self, image_format='PNG') -> Image:
        cols, rows = self.calculate_grid(len(self.images))
        images_amount = cols * rows
        images = self.images[:images_amount]
        images_data = self.aws_bucket.get_s3_images(images)

        collage = self._create_collage(
            cols=cols,
            rows=rows,
            images_data=images_data
        )
        collage_io = BytesIO()
        collage.save(collage_io, format=image_format)
        return collage_io


def get_first_product_media(product):
    return ProductMedia.objects.filter(
        product=product
    ).order_by('sort_order').first()


def swap_sort_order(new_image, product):
    last_photo_sort_order = new_image.sort_order
    first_photo = get_first_product_media(product)
    first_photo.sort_order = last_photo_sort_order
    first_photo.save()
    new_image.sort_order = 0
    new_image.save()


def create_collage(images: List[ProductMedia], product: Product):
    collage_creator = CollageCreator(images=images)
    collage = collage_creator.create()
    # Save new collage image to db
    photo_name = collage_photo_name(product.name)
    media = create_new_media_from_bytes(product=product, image=collage, name=photo_name)
    swap_sort_order(media, product)
    # Create thumbnails
    create_product_thumbnails.delay(media.pk)


def create_new_media_from_existing_media(product: Product, product_media: ProductMedia) -> ProductMedia:
    name = create_new_product_media_name(product_media.image.name)
    image_bytes = product_media_to_bytes_io(product_media)
    media = create_new_media_from_bytes(product, image_bytes, name)
    return media


def product_media_to_bytes_io(media: ProductMedia) -> BytesIO:
    media_bytes = media.image.file.read()
    return BytesIO(media_bytes)


def create_new_media_from_bytes(product: Product, image: BytesIO, name: str) -> ProductMedia:
    image = ImageFile(image, name=name)

    new_media = product.media.create(
        image=image, alt=product.name.upper(), type=ProductMediaTypes.IMAGE
    )
    return new_media


def create_new_product_media_name(media_name: str) -> str:
    media_name = media_name.replace('products/', '')

    file_name, format = os.path.splitext(media_name)
    hash = secrets.token_hex(nbytes=4)
    new_name = f"{file_name}_{hash}{format}"
    return new_name


def collage_photo_name(product_name) -> str:
    rand_int = random.randint(1000000, 9999999)
    return f'{product_name}x{rand_int}.png'
