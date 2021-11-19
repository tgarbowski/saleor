from django.core.management.base import BaseCommand, CommandError

from saleor.salingo.business_rules import BusinessRulesEvaluator


class Command(BaseCommand):
    version = "1.0"

    def add_arguments(self, parser):
        parser.add_argument(
            "--mode",
            type=str,
            help=("""Two modes allowed: commit and dry_run. Mode dry_run allows running
                     command without database records mutation.""")
        )

    def handle(self, *args, **options):
        mode = options.get("mode")
        Command.validate_parameters(mode)

        routing = BusinessRulesEvaluator(plugin_slug='salingo_routing', mode=mode)
        routing.evaluate_rules()

        pricing = BusinessRulesEvaluator(plugin_slug='salingo_pricing', mode=mode)
        pricing.evaluate_rules()

    @staticmethod
    def validate_parameters(mode):
        if not mode:
            raise CommandError(
                "Mode not provided. "
                "Use `--mode` flag "
                "eg. --category_slugs=dry_run "
                "or --category_slugs=commit"
            )

        if mode not in ['commit', 'dry_run']:
            raise CommandError("Invalid mode. Only commit or dry_run modes are allowed.")
