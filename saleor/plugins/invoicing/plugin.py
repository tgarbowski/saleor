from typing import Any, Optional
from uuid import uuid4

from dataclasses import dataclass

from django.core.files.base import ContentFile
from django.utils.text import slugify

from ...core import JobStatus
from ...invoice.models import Invoice
from ...order.models import Order
from ..base_plugin import BasePlugin, ConfigurationTypeField
from .utils import generate_invoice_number, generate_invoice_pdf, generate_correction_invoice_pdf


@dataclass
class InvoiceConfiguration:
    begin_number: str
    prefix: str


class InvoicingPlugin(BasePlugin):
    PLUGIN_ID = "mirumee.invoicing"
    PLUGIN_NAME = "Invoicing"
    DEFAULT_ACTIVE = True
    PLUGIN_DESCRIPTION = "Built-in saleor plugin that handles invoice creation."
    CONFIGURATION_PER_CHANNEL = False
    DEFAULT_CONFIGURATION = [{"name": "begin_number",
                              "value": "1"},
                             {"name": "prefix",
                              "value": "FVAT-"}]
    CONFIG_STRUCTURE = {
        "begin_number": {
            "type": ConfigurationTypeField.STRING,
            "label": "First invoice number if no invoices in database",
        },
        "prefix": {
            "type": ConfigurationTypeField.STRING,
            "label": "Invoice prefix",
        }}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        configuration = {item["name"]: item["value"] for item in self.configuration}

        self.config = InvoiceConfiguration(
            begin_number=configuration["begin_number"],
            prefix=configuration["prefix"])

    def invoice_request(
        self,
        order: "Order",
        invoice: "Invoice",
        number: Optional[str],
        previous_value: Any,
    ) -> Any:
        invoice_number = generate_invoice_number(
            begin_number=self.config.begin_number,
            prefix=self.config.prefix)
        if not number:
            invoice.update_invoice(number=invoice_number)
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

def invoice_correction_request(
    order: "Order",
    invoice: "Invoice",
    number: Optional[str]
    ) -> Any:
        invoice_number = "88888"
        if not number:
            invoice.update_invoice(number=invoice_number)

        file_content, creation_date = generate_correction_invoice_pdf(invoice, order)

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
