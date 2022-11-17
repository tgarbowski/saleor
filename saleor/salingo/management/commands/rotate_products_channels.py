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
        parser.add_argument(
            "--plugin",
            type=str,
            help=("""Two plugins allowed: salingo_routing and salingo_pricing.""")
        )

    def handle(self, *args, **options):
        mode = options.get("mode")
        plugin = options.get("plugin")

        Command.validate_parameters(mode, plugin)

        routing = BusinessRulesEvaluator(plugin_slug=plugin, mode=mode)
        routing.evaluate_rules()

    @staticmethod
    def validate_parameters(mode, plugin):
        if not mode:
            raise CommandError(
                "Mode not provided. "
                "Use `--mode` flag "
                "eg. --mode=dry_run "
                "or --mode=commit"
            )

        if mode not in ['commit', 'dry_run']:
            raise CommandError("Invalid mode. Only commit or dry_run modes are allowed.")

        if not plugin:
            raise CommandError(
                "Plugin not provided. "
                "Use `--plugin` flag "
                "eg. --plugin=dry_run "
                "or --plugin=commit"
            )

        if plugin not in ['salingo_routing', 'salingo_pricing']:
            raise CommandError("Invalid plugin. Only salingo_routing or salingo_pricing plugins are allowed.")
