from django.core.management.base import BaseCommand

from saleor.product.models import Product
from saleor.graphql.product.utils import generate_description_json_for_megapack


class Command(BaseCommand):

    def handle(self, *args, **options):
        megapack_products = Product.objects.filter(product_type__slug='mega-paka')

        for megapack_product in megapack_products:
            bundle_content = megapack_product.private_metadata.get("bundle.content")
            megapack_product.description = generate_description_json_for_megapack(bundle_content)
            megapack_product.save(update_fields=["description"])
