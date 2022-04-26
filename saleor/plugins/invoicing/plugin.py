from typing import Any, Optional
from uuid import uuid4

from dataclasses import dataclass

from django.core.files.base import ContentFile
from django.utils.text import slugify

from ...core import JobStatus
from ...invoice.models import Invoice
from ...order.models import Order
from ..base_plugin import BasePlugin, ConfigurationTypeField
from .utils import generate_invoice_number, generate_invoice_pdf


@dataclass
class InvoiceConfiguration:
    begin_number: str


class InvoicingPlugin(BasePlugin):
    PLUGIN_ID = "mirumee.invoicing"
    PLUGIN_NAME = "Invoicing"
    DEFAULT_ACTIVE = True
    PLUGIN_DESCRIPTION = "Built-in saleor plugin that handles invoice creation."
    CONFIGURATION_PER_CHANNEL = False
    DEFAULT_CONFIGURATION = [{"name": "begin_number",
                              "value": "1"}]
    CONFIG_STRUCTURE = {
        "begin_number": {
            "type": ConfigurationTypeField.STRING,
            "label": "Redirect URL np: https://allegro.pl.allegrosandbox.pl/auth/oauth",
        }}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        configuration = {item["name"]: item["value"] for item in self.configuration}

        self.config = InvoiceConfiguration(
            begin_number=configuration["begin_number"])

    def invoice_request(
        self,
        order: "Order",
        invoice: "Invoice",
        number: Optional[str],
        previous_value: Any,
    ) -> Any:
        invoice_number = generate_invoice_number(begin_number=self.config.begin_number)
        if number is None or number is "":
            invoice.update_invoice(number=invoice_number)
        else:
            invoice.update_invoice(number=number)
        file_content, creation_date = generate_invoice_pdf(invoice)
        invoice.created = creation_date
        slugified_invoice_number = slugify(invoice_number)
        invoice.invoice_file.save(
            f"invoice-{slugified_invoice_number}-order-{order.id}-{uuid4()}.pdf",
            ContentFile(file_content),
        )
        invoice.status = JobStatus.SUCCESS
        invoice.save(
            update_fields=["created", "number", "invoice_file", "status", "updated_at"]
        )
        return invoice
