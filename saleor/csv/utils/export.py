import codecs
import csv
import uuid
from datetime import date, datetime
from tempfile import NamedTemporaryFile
from typing import IO, TYPE_CHECKING, Any, Dict, List, Set, Union

import petl as etl
import json
from django.db.models.functions import Concat, Cast, TruncSecond, TruncDay
from django.utils import timezone
from django.db.models import Count, F, Value, DateTimeField, CharField, FloatField
from ...giftcard.models import GiftCard
from ...invoice.models import Invoice
from ...product.models import Product
from .. import FileTypes
from ..notifications import send_export_download_link_notification
from .product_headers import get_product_export_fields_and_headers_info
from .products_data import get_products_data

if TYPE_CHECKING:
    # flake8: noqa
    from django.db.models import QuerySet

    from ..models import ExportFile


BATCH_SIZE = 10000


def export_products(
    export_file: "ExportFile",
    scope: Dict[str, Union[str, dict]],
    export_info: Dict[str, list],
    file_type: str,
    delimiter: str = ",",
):
    from ...graphql.product.filters import ProductFilter

    file_name = get_filename("product", file_type)
    queryset = get_queryset(Product, ProductFilter, scope)

    (
        export_fields,
        file_headers,
        data_headers,
    ) = get_product_export_fields_and_headers_info(export_info)

    temporary_file = create_file_with_headers(file_headers, delimiter, file_type)

    export_products_in_batches(
        queryset,
        export_info,
        set(export_fields),
        data_headers,
        delimiter,
        temporary_file,
        file_type,
    )

    save_csv_file_in_export_file(export_file, temporary_file, file_name)
    temporary_file.close()

    send_export_download_link_notification(export_file, "products")


def export_invoices(
    export_file: "ExportFile",
    month: str,
    year: str,
    delimiter: str = ";",
    file_type: str = "csv"
):
    file_name = get_filename("financial_tally", "CSV")
    queryset = Invoice.objects.filter(created__month=month, created__year=year)

    headers = ["reciever_nip","receiver_name", "receiver_address","invoice_number",
               "created_date","sale_date","WDT","Export","net_price_0_percent",
               "transport_price_5_percent","tax_price_5_percent","net_price_7_8_percent",
               "tax_price_7_8_percent","net_price_22_23_percent", "tax_price_22_23_percent"]

    temporary_file = create_file_with_headers(headers, delimiter, file_type)
    export_invoices_in_batches(
        queryset,
        temporary_file,
        headers,
        delimiter,
        file_type
    )
    translate_tally_headers(temporary_file)
    save_csv_file_in_export_file(export_file, temporary_file, file_name)
    temporary_file.close()
    send_export_download_link_notification(export_file, "financial_tally")


def export_gift_cards(
    export_file: "ExportFile",
    scope: Dict[str, Union[str, dict]],
    file_type: str,
    delimiter: str = ",",
):
    from ...graphql.giftcard.filters import GiftCardFilter

    file_name = get_filename("gift_card", file_type)

    queryset = get_queryset(GiftCard, GiftCardFilter, scope)
    # only unused gift cards codes can be exported
    queryset = queryset.filter(used_by_email__isnull=True)

    export_fields = ["code"]
    temporary_file = create_file_with_headers(export_fields, delimiter, file_type)

    export_gift_cards_in_batches(
        queryset,
        export_fields,
        delimiter,
        temporary_file,
        file_type,
    )

    save_csv_file_in_export_file(export_file, temporary_file, file_name)
    temporary_file.close()

    send_export_download_link_notification(export_file, "gift cards")


def get_filename(model_name: str, file_type: str) -> str:
    hash = uuid.uuid4()
    return "{}_data_{}_{}.{}".format(
        model_name, timezone.now().strftime("%d_%m_%Y_%H_%M_%S"), hash, file_type
    )


def get_queryset(model, filter, scope: Dict[str, Union[str, dict]]) -> "QuerySet":
    queryset = model.objects.all()
    if "ids" in scope:
        queryset = model.objects.filter(pk__in=scope["ids"])
    elif "filter" in scope:
        queryset = filter(data=parse_input(scope["filter"]), queryset=queryset).qs

    queryset = queryset.order_by("pk")

    return queryset


def parse_input(data: Any) -> Dict[str, Union[str, dict]]:
    """Parse input to correct data types, since scope coming from celery will be parsed to strings."""
    if "attributes" in data:
        serialized_attributes = []

        for attr in data.get("attributes") or []:
            if "date_time" in attr:
                if gte := attr["date_time"].get("gte"):
                    attr["date_time"]["gte"] = datetime.fromisoformat(gte)
                if lte := attr["date_time"].get("lte"):
                    attr["date_time"]["lte"] = datetime.fromisoformat(lte)

            if "date" in attr:
                if gte := attr["date"].get("gte"):
                    attr["date"]["gte"] = date.fromisoformat(gte)
                if lte := attr["date"].get("lte"):
                    attr["date"]["lte"] = date.fromisoformat(lte)

            serialized_attributes.append(attr)

        if serialized_attributes:
            data["attributes"] = serialized_attributes

    return data


def create_file_with_headers(file_headers: List[str], delimiter: str, file_type: str):
    table = etl.wrap([file_headers])
    if file_type == FileTypes.CSV:
        temp_file = NamedTemporaryFile("ab+", suffix=".csv")
        etl.tocsv(table, temp_file.name, delimiter=delimiter)
    else:
        temp_file = NamedTemporaryFile("ab+", suffix=".xlsx")
        etl.io.xlsx.toxlsx(table, temp_file.name)
    return temp_file


def export_products_in_batches(
    queryset: "QuerySet",
    export_info: Dict[str, list],
    export_fields: Set[str],
    headers: List[str],
    delimiter: str,
    temporary_file: Any,
    file_type: str,
):
    warehouses = export_info.get("warehouses")
    attributes = export_info.get("attributes")
    channels = export_info.get("channels")

    for batch_pks in queryset_in_batches(queryset):
        product_batch = Product.objects.filter(pk__in=batch_pks).prefetch_related(
            "attributes",
            "variants",
            "collections",
            "media",
            "product_type",
            "category",
        )

        export_data = get_products_data(
            product_batch, export_fields, attributes, warehouses, channels
        )

        append_to_file(export_data, headers, temporary_file, file_type, delimiter)


def export_invoices_in_batches(
    queryset: "QuerySet",
    temporary_file: Any,
    headers: List[str],
    delimiter: str,
    file_type: str
):
    for batch_pks in queryset_in_batches(queryset):
        invoice_batch = Invoice.objects.filter(pk__in=batch_pks).prefetch_related(
            "order",
            "order__shipping_address"
        )
        export_data = list(invoice_batch.values(
            reciever_nip=F("order__shipping_address__vat_id"),
            receiver_name=Concat(F("order__shipping_address__first_name"),
                                 Value(" "),
                                 F("order__shipping_address__last_name")),
            receiver_address=Concat(F("order__shipping_address__postal_code"),
                                    Value(" "),
                                    F("order__shipping_address__city"),
                                    Value(", "),
                                    F("order__shipping_address__street_address_1"),
                                    Value(" "),
                                    F("order__shipping_address__street_address_2")),
            invoice_number=F("number"),
            created_date=Cast(TruncDay('created', DateTimeField()), CharField()),
            sale_date=Cast(TruncDay('created', DateTimeField()), CharField()),
            WDT=Value("0"),
            Export=Value("0"),
            net_price_0_percent=Value("0"),
            transport_price_5_percent=Value("0"),
            tax_price_5_percent=Value("0"),
            net_price_7_8_percent=Value("0"),
            tax_price_7_8_percent=Value("0"),
            net_price_22_23_percent=F("private_metadata__summary__to"),
            tax_price_22_23_percent=F("private_metadata__summary__to")
        ))
        append_to_file(export_data, headers, temporary_file, file_type, delimiter)


def export_gift_cards_in_batches(
    queryset: "QuerySet",
    export_fields: List[str],
    delimiter: str,
    temporary_file: Any,
    file_type: str,
):
    for batch_pks in queryset_in_batches(queryset):
        gift_card_batch = GiftCard.objects.filter(pk__in=batch_pks)

        export_data = list(gift_card_batch.values(*export_fields))

        append_to_file(export_data, export_fields, temporary_file, file_type, delimiter)


def translate_tally_headers(file, delimiter: str = ";"):
    file_name = file.name
    headers2 = ["Numer NIP Kontrahenta","Nazwa Kontrahenta","Adres Kontrahenta","Nr faktury",
                "Data wystawienia","Data sprzedaży","WDT","Export",
                "Sprzedaż netto, opodatkowana stawką 0%",
                "Dostawa towarów oraz świadczenie usług na terytorium kraju, opodatkowane stawką 5%",
                "Podatek należny 5%","Sprzedaż netto, opodatkowana stawką 7% albo 8%",
                "Podatek należny 7% albo 8%","Sprzedaż netto, opodatkowana stawką 22% albo 23%",
                "Podatek należny 22% albo 23%"]
    with open(file_name, 'rt') as inFile:
        r = csv.reader(inFile, delimiter=delimiter)
        next(r, None)
        with open(file_name, 'w') as outfile:
            w = csv.writer(outfile, delimiter=delimiter)
            w.writerow(headers2)
            for row in r:
                w.writerow(row)


def queryset_in_batches(queryset):
    """Slice a queryset into batches.

    Input queryset should be sorted be pk.
    """
    start_pk = 0

    while True:
        qs = queryset.filter(pk__gt=start_pk)[:BATCH_SIZE]
        pks = list(qs.values_list("pk", flat=True))

        if not pks:
            break

        yield pks

        start_pk = pks[-1]


def append_to_file(
    export_data: List[Dict[str, Union[str, bool]]],
    headers: List[str],
    temporary_file: Any,
    file_type: str,
    delimiter: str,
):
    table = etl.fromdicts(export_data, header=headers, missing=" ")

    if file_type == FileTypes.CSV:
        etl.io.csv.appendcsv(table, temporary_file.name, delimiter=delimiter)
    else:
        etl.io.xlsx.appendxlsx(table, temporary_file.name)


def save_csv_file_in_export_file(
    export_file: "ExportFile", temporary_file: IO[bytes], file_name: str
):
    export_file.content_file.save(file_name, temporary_file)
