from dataclasses import dataclass
from datetime import datetime

from django.db import transaction
import re

from ..base_plugin import BasePlugin, ConfigurationTypeField
from ...graphql.wms.mutations import WmsDocumentCreate
from ...order.models import Order, OrderLine
from ...wms.models import WmsDocument, WmsDocPosition
from saleor.warehouse.models import Warehouse


@dataclass
class WMSConfiguration:
    GRN: str
    GIN: str
    IWM: str
    FGTN: str
    IO: str


class WMSPlugin(BasePlugin):
    PLUGIN_NAME = "WMS"
    PLUGIN_ID = "WMS"
    DEFAULT_ACTIVE = True
    DEFAULT_CONFIGURATION = [
        {"name": "GRN", "value": "GRN"},
        {"name": "GIN", "value": "GIN"},
        {"name": "IWM", "value": "IWM"},
        {"name": "FGTN", "value": "FGTN"},
        {"name": "IO", "value": "IO"}
    ]
    PLUGIN_DESCRIPTION = (
        "Warehouse management system plugin"
    )
    CONFIG_STRUCTURE = {
        "GRN": {
            "type": ConfigurationTypeField.STRING,
            "label": "Goods received note (GRN) eg. PZ",
        },
        "GIN": {
            "type": ConfigurationTypeField.STRING,
            "label": "Goods issued note (GIN) eg: WZ",
        },
        "IWM": {
            "type": ConfigurationTypeField.STRING,
            "label": "Internal warehouse movement (IWM) eg: MM",
        },
        "FGTN": {
            "type": ConfigurationTypeField.STRING,
            "label": "Finished goods transfer note (FGTN) eg: PW",
        },
        "IO": {
            "type": ConfigurationTypeField.STRING,
            "label": "Internal outgoings (IO) eg: RW",
        }
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configuration = {item["name"]: item["value"] for item in self.configuration}


    def order_fulfilled(
            self,
            order,
            previous_value,
    ):
        with transaction.atomic():
            wms_document = wms_document_create(order)
            wms_positions_bulk_create(order, wms_document_id=wms_document.id)


def wms_document_generate_number():
    now = datetime.now()
    current_year = int(now.strftime("%Y"))

    last_wms_document = WmsDocument.objects.filter().last()
    match = re.search("(\d+)/(\d+)", last_wms_document.number)
    if match:
        number, year = int(match.group(1)), int(match.group(2))
        if current_year == year and number:
            new_number = number + 1
            return f"WZ-{new_number}/{current_year}"
    return f"WZ-1/{current_year}"


def wms_document_create(order: "Order"):
    staff_user = 78
    customer_user = 82
    warehouse = Warehouse.objects.filter().first()
    location = ""
    number = wms_document_generate_number()
    return WmsDocument.objects.create(
        document_type='GRN',
        number=number,
        status='DRAFT',
        created_by_id=staff_user,
        recipient_id=customer_user,
        warehouse=warehouse,
        location=location
    )


def wms_create_position(order_line: "OrderLine", wms_document):
    quantity = order_line.quantity
    product_variant = order_line.variant
    weight = 10
    return WmsDocPosition(
        quantity=quantity,
        product_variant=product_variant,
        weight=weight,
        document=wms_document
    )


def wms_positions_bulk_create(order: "Order", wms_document_id: str):
    order_lines = OrderLine.objects.filter(order=order)
    wms_positions = []
    for order_line in order_lines:
        wms_position = wms_create_position(
            order_line=order_line,
            wms_document=wms_document_id
        )
        wms_positions.append(wms_position)
    return WmsDocPosition.objects.bulk_create(
        wms_positions
    )
