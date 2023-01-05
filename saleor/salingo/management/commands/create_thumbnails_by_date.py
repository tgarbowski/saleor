from datetime import datetime, time

from django.core.management.base import BaseCommand
from versatileimagefield.image_warmer import VersatileImageFieldWarmer

from ....product.models import Product, ProductMedia


class Command(BaseCommand):
    help = "Generate thumbnails for date range images"

    def add_arguments(self, parser):
        parser.add_argument('--start_date', type=str, help='product creation start date')
        parser.add_argument('--end_date', type=str, help='product creation end date')

    def handle(self, *args, **options):
        start_date = datetime.strptime(options['start_date'], '%Y-%m-%d').date()
        start_date = datetime.combine(start_date, time.min)

        end_date = datetime.strptime(options['end_date'], '%Y-%m-%d').date()
        end_date = datetime.combine(end_date, time.max)

        self.warm_products(start_date, end_date)

    def warm_products(self, start_date, end_date):
        products = Product.objects.filter(created__range=(start_date, end_date))
        images = ProductMedia.objects.filter(product__in=products)

        warmer = VersatileImageFieldWarmer(
            instance_or_queryset=images,
            rendition_key_set="products",
            image_attr="image",
            verbose=True,
        )
        warmer.warm()
