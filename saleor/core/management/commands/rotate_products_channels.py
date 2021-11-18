from django.core.management.base import BaseCommand

from saleor.salingo.business_rules import BusinessRulesEvaluator


class Command(BaseCommand):
    version = "1.0"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry_run",
            action="store_true",
            help="Allows running command without database records mutation.",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        routing = BusinessRulesEvaluator(plugin_slug='salingo_routing', dry_run=dry_run)
        routing.evaluate_rules()
