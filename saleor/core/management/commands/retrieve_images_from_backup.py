from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError

from saleor.product.models import ProductMedia
from saleor.salingo.images import BackupImageRetrieval


class Command(BaseCommand):
    version = "1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def add_arguments(self, parser):
        parser.add_argument(
            "--image",
            type=str,
            help=('Image path'),
            required=True
        )

    def handle(self, *args, **options):
        image = options.get("image")
        self.validate_image(image)
        backup_image_retrieval = BackupImageRetrieval(image=image)
        backup_image_retrieval.handle()

    @staticmethod
    def validate_image(image):
        if not image:
            raise CommandError("Please provide image path.")

        try:
            media = ProductMedia.objects.get(image=image)
        except ObjectDoesNotExist:
            raise CommandError("Provided image doesnt match any product.")
