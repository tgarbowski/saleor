from django.core.management.base import BaseCommand

from saleor.salingo.megapack import create_megapacks


class Command(BaseCommand):
    version = "1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def add_arguments(self, parser):
        parser.add_argument(
            "--source_channel_slug",
            type=str,
            help=('Source channel slug'),
            required=True
        )
        parser.add_argument(
            "--megapack_channel_slug",
            type=str,
            help=('Megapack channel slug'),
            required=True
        )

    def handle(self, *args, **options):
        source_channel_slug = options.get("source_channel_slug")
        megapack_channel_slug = options.get("megapack_channel_slug")

        create_megapacks(
            source_channel_slug=source_channel_slug,
            megapack_channel_slug=megapack_channel_slug
        )
