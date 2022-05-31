from typing import Any, Optional
from uuid import uuid4
from distutils.util import strtobool

from dataclasses import dataclass

from django.core.files.base import ContentFile
from django.utils.text import slugify

from ...core import JobStatus
from ...invoice.models import Invoice
from ...order.models import Order
from ..base_plugin import BasePlugin, ConfigurationTypeField
from .utils import (generate_invoice_number, generate_invoice_pdf, generate_correction_invoice_pdf,
                    generate_correction_invoice_number, generate_correction_receipt_number)
from saleor.plugins.allegro.utils import get_plugin_configuration


@dataclass
class InvoiceConfiguration:
    begin_number: str
    invoice_prefix: str
    receipt_prefix: str
    correction_invoice_prefix: str
    correction_receipt_prefix: str


class InvoicingPlugin(BasePlugin):
    PLUGIN_ID = "mirumee.invoicing"
    PLUGIN_NAME = "Invoicing"
    DEFAULT_ACTIVE = True
    PLUGIN_DESCRIPTION = "Built-in saleor plugin that handles invoice creation."
    CONFIGURATION_PER_CHANNEL = False
    DEFAULT_CONFIGURATION = [
        {"name": "begin_number",
         "value": "1"
        },
        {"name": "invoice_prefix",
         "value": "FVS-"
        },
        {"name": "receipt_prefix",
         "value": "PSK-"
        },
        {"name": "correction_invoice_prefix",
         "value": "FVSK-"
        },
        {"name": "correction_receipt_prefix",
         "value": "PSK-"
        }
    ]
    CONFIG_STRUCTURE = {
        "begin_number": {
            "type": ConfigurationTypeField.STRING,
            "label": "First invoice number if no invoices in database",
        },
        "invoice_prefix": {
            "type": ConfigurationTypeField.STRING,
            "label": "Invoice prefix",
        },
        "receipt_prefix": {
            "type": ConfigurationTypeField.STRING,
            "label": "Receipt prefix",
        },
        "correction_invoice_prefix": {
            "type": ConfigurationTypeField.STRING,
            "label": "Correction invoice prefix",
        },
        "correction_receipt_prefix": {
            "type": ConfigurationTypeField.STRING,
            "label": "Correction receipt prefix",
        }
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        configuration = {item["name"]: item["value"] for item in self.configuration}

        self.config = InvoiceConfiguration(
            begin_number=configuration["begin_number"],
            invoice_prefix=configuration["invoice_prefix"],
            receipt_prefix=configuration["receipt_prefix"],
            correction_invoice_prefix=configuration["correction_invoice_prefix"],
            correction_receipt_prefix=configuration["correction_receipt_prefix"],
        )

    def invoice_request(
        self,
        order: "Order",
        invoice: "Invoice",
        number: Optional[str],
        previous_value: Any,
    ) -> Any:
        invoice_number = generate_invoice_number(
            begin_number=self.config.begin_number,
            prefix=self.config.invoice_prefix)
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
    last_correction_invoice: "Invoice"
) -> "Invoice":
    config = get_plugin_configuration(plugin_id="mirumee.invoicing")
    is_invoice = bool(strtobool(order.metadata.get("invoice")))

    if is_invoice:
        correction_prefix = config.get("correction_invoice_prefix")
        invoice_number = generate_correction_invoice_number(
            prefix=correction_prefix,
            last_correction_invoice=last_correction_invoice
        )
    else:
        correction_prefix = config.get("correction_receipt_prefix")
        correction_receipt_count = Invoice.objects.filter(
            order__metadata__invoice=False,
            parent__isnull=False
        ).count()
        correction_receipt_count -= 1
        invoice_number = generate_correction_receipt_number(
            prefix=correction_prefix,
            correction_receipt_count=correction_receipt_count
        )

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
    return invoice
