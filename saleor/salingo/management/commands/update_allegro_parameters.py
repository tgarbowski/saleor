from django.core.management.base import BaseCommand, CommandError

from saleor.plugins.allegro.tasks import update_published_offers_parameters


class Command(BaseCommand):
    version = "1.0"

    def add_arguments(self, parser):
        parser.add_argument('--category_slugs', type=str, help='allegro category slugs')
        parser.add_argument('--limit', help='products amount', default=10)
        parser.add_argument('--offset', help='products offset', default=0,)

    def handle(self, *args, **options):
        limit = options['limit']
        offset = options['offset']
        category_slugs = options['category_slugs']

        Command.validate_parameters(category_slugs, limit)
        update_published_offers_parameters.delay(category_slugs, limit, offset)

    @staticmethod
    def validate_parameters(category_slugs, limit):
        if not category_slugs:
            raise CommandError(
                "Unknown category slugs. "
                "Use `--category_slugs` flag "
                "eg. --category_slugs=slug1,slug2,slug3"
            )

        if int(limit) > 15000:
            raise CommandError("Please lower a limit, maximum allowed is 15000.")
