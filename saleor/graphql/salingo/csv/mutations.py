import graphene

from ...core.mutations import ModelMutation
from ....core.permissions import OrderPermissions
from saleor.invoice import models
from saleor.graphql.invoice.types import Invoice
from ...core.types.common import InvoiceError
from ....csv import models as csv_models
from ....csv.events import export_started_event
from ....csv.tasks import export_tally_csv_task, export_miglo_csv_task


class ExtTallyCsv(ModelMutation):
    class Arguments:
        month = graphene.String(required=True, description="Tally month")
        year = graphene.String(required=True, description="Tally year")

    class Meta:
        description = "Export products to csv file."
        permissions = (OrderPermissions.MANAGE_ORDERS,)
        model = models.Invoice
        object_type = Invoice
        error_type_class = InvoiceError
        error_type_field = "export_errors"

    @classmethod
    def perform_mutation(cls, root, info, **data):
        month = data["month"]
        year = data["year"]

        app = info.context.app
        kwargs = {"app": app} if app else {"user": info.context.user}
        export_file = csv_models.ExportFile.objects.create(
            **kwargs, message="Tally-" + month + "-" + year)
        export_started_event(export_file=export_file, **kwargs)
        export_tally_csv_task(export_file.pk, month, year)

        export_file.refresh_from_db()
        return cls()


class ExtMigloCsv(ModelMutation):
    class Arguments:
        month = graphene.String(required=True, description="Tally month")
        year = graphene.String(required=True, description="Tally year")

    class Meta:
        description = "Export products to csv file."
        permissions = (OrderPermissions.MANAGE_ORDERS,)
        model = models.Invoice
        object_type = Invoice
        error_type_class = InvoiceError
        error_type_field = "export_errors"

    @classmethod
    def perform_mutation(cls, root, info, **data):
        month = data["month"]
        year = data["year"]

        app = info.context.app
        kwargs = {"app": app} if app else {"user": info.context.user}

        export_file = csv_models.ExportFile.objects.create(
            **kwargs, message="Miglo-" + month + "-" + year)
        export_started_event(export_file=export_file, **kwargs)
        export_miglo_csv_task(export_file.pk, month, year)

        export_file.refresh_from_db()
        return cls()
