import csv
import uuid
from datetime import date, datetime
from enum import Enum
from tempfile import NamedTemporaryFile
from typing import IO, TYPE_CHECKING, Any, Dict, List, Set, Union

import petl as etl
from django.db.models.functions import Concat, Cast, TruncDay
from django.utils import timezone
from django.db.models import F, Value, DateTimeField, CharField

from ...giftcard.models import GiftCard
from ...invoice.models import Invoice
from ...payment.models import Payment
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

class DocType(Enum):
    INVOICE = "4"
    INVOICE_CORRECTION = "9"


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


def export_tally_csv(
    export_file: "ExportFile",
    month: str,
    year: str,
):
    file_type = "csv"
    delimiter = ";"
    file_name = get_filename("tally_csv", "CSV")
    queryset = Invoice.objects.filter(created__month=month, created__year=year)

    headers = ["reciever_nip","receiver_name", "receiver_address","invoice_number",
               "created_date","sale_date","wdt","export","net_price_0_percent",
               "transport_price_5_percent","tax_price_5_percent","net_price_7_8_percent",
               "tax_price_7_8_percent","net_price_22_23_percent", "tax_price_22_23_percent"]

    temporary_file = create_file_with_headers(headers, delimiter, file_type)
    export_tally_data_in_batches(
        queryset,
        temporary_file,
        headers,
        delimiter,
        file_type
    )
    temporary_file = clean_tally_fields(temporary_file, delimiter)
    translate_tally_headers(temporary_file)
    save_csv_file_in_export_file(export_file, temporary_file, file_name)
    temporary_file.close()
    send_export_download_link_notification(export_file, "tally_csv")


def export_miglo_csv(
    export_file: "ExportFile",
    month: str,
    year: str,
):
    file_type = "csv"
    delimiter = ";"
    file_name = get_filename("miglo_csv", "CSV")
    queryset = Invoice.objects.filter(created__month=month, created__year=year)
    headers = ["DocType","DocId","DocNumber","DocDate","SaleDate","Term","CustomerId",
               "Netto","Brutto","PaymentTypeId","PaymentName","StoreId","StoreName",
               "ExternalNumber","OriginalNumber","OriginalDate","CorrectionType",
               "ParentFile","ParentBrutto"]

    temporary_file = create_file_with_headers(headers, delimiter, file_type)
    export_miglo_data_in_batches(
        queryset,
        temporary_file,
        headers,
        delimiter,
        file_type
    )
    temporary_file = clean_miglo_fields(temporary_file, delimiter)
    save_csv_file_in_export_file(export_file, temporary_file, file_name)
    temporary_file.close()
    send_export_download_link_notification(export_file, "miglo_csv")


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


def export_tally_data_in_batches(
    queryset: "QuerySet",
    temporary_file: Any,
    headers: List[str],
    delimiter: str,
    file_type: str
):
    for batch_pks in queryset_in_batches(queryset):
        invoice_batch = Invoice.objects.filter(pk__in=batch_pks).prefetch_related(
            "order",
            "order__billing_address"
        )
        export_data = list(invoice_batch.values(
            reciever_nip=F("order__billing_address__vat_id"),
            receiver_name=Concat(F("order__billing_address__first_name"),
                                 Value(" "),
                                 F("order__billing_address__last_name")),
            receiver_address=Concat(F("order__billing_address__postal_code"),
                                    Value(" "),
                                    F("order__billing_address__city"),
                                    Value(", "),
                                    F("order__billing_address__street_address_1"),
                                    Value(" "),
                                    F("order__billing_address__street_address_2")),
            invoice_number=F("number"),
            created_date=Cast(TruncDay('created', DateTimeField()), CharField()),
            sale_date=Cast(TruncDay('created', DateTimeField()), CharField()),
            wdt=Value("0"),
            export=Value("0"),
            net_price_0_percent=Value("0"),
            transport_price_5_percent=Value("0"),
            tax_price_5_percent=Value("0"),
            net_price_7_8_percent=Value("0"),
            tax_price_7_8_percent=Value("0"),
            net_price_22_23_percent=F("private_metadata__summary__to"),
            tax_price_22_23_percent=F("private_metadata__summary__to")
        ))
        append_to_file(export_data, headers, temporary_file, file_type, delimiter)


def get_miglo_query_values_list(
        invoice_queryset: "QuerySet",
        payment_queryset: "QuerySet",
        is_correction: bool = False
):
    if is_correction:
        invoice_data = list(invoice_queryset.values(
            DocType=Value(DocType.INVOICE_CORRECTION.value),
            DocId=F("id"),
            DocNumber=F("number"),
            DocDate=Cast(TruncDay('created', DateTimeField()), CharField()),
            SaleDate=Cast(TruncDay('created', DateTimeField()), CharField()),
            Term=Value("0"),
            CustomerId=F("order__user"),
            Netto=F("private_metadata__summary__to"),
            Brutto=F("private_metadata__summary__to"),
            # TODO: change StoreName and StoreId from static value to fetch from DB
            # StoreId=F("order__collection_point"),
            # StoreName=F("order__warehouse__name"),
            StoreId=Value("1"),
            StoreName=Value("Magazyn 1"),
            ExternalNumber=F("order_id"),
            OriginalNumber=F("parent__number"),
            OriginalDate=Cast(TruncDay('parent__created_at', DateTimeField()),
                              CharField()),
            CorrectionType=Value("2"),
            ParentFile=F('parent__invoice_file'),
            ParentBrutto=F("parent__private_metadata__summary__to")
        ))
    else:
        invoice_data = list(invoice_queryset.values(
            DocType=Value(DocType.INVOICE.value),
            DocId=F("id"),
            DocNumber=F("number"),
            DocDate=Cast(TruncDay('created', DateTimeField()), CharField()),
            SaleDate=Cast(TruncDay('created', DateTimeField()), CharField()),
            Term=Value("0"),
            CustomerId=F("order__user"),
            Netto=F("private_metadata__summary__to"),
            Brutto=F("private_metadata__summary__to"),
            # TODO: change StoreName and StoreId from static value to fetch from DB
            # StoreId=F("order__collection_point"),
            # StoreName=F("order__warehouse__name"),
            StoreId=Value("1"),
            StoreName=Value("Magazyn 1"),
            ExternalNumber=F("order_id"),
            OriginalNumber=F("parent__number"),
            OriginalDate=Cast(TruncDay('parent__created', DateTimeField()),
                              CharField()),
        ))

    payment_data = list(payment_queryset.values(
        PaymentTypeId=F("gateway"),
        PaymentName=F("gateway")
    ))
    return invoice_data, payment_data


def export_miglo_data_in_batches(
    queryset: "QuerySet",
    temporary_file: Any,
    headers: List[str],
    delimiter: str,
    file_type: str
):
    for batch_pks in queryset_in_batches(queryset):
        invoice_batch = Invoice.objects.filter(pk__in=batch_pks, parent__isnull=True).prefetch_related(
            "order",
        ).order_by("order_id")
        order_ids = invoice_batch.values_list("order_id", flat=True)
        payment_batch = Payment.objects.filter(order_id__in=order_ids).order_by("order_id")

        invoice_correction_batch = Invoice.objects.filter(pk__in=batch_pks, parent__isnull=False).prefetch_related(
            "order",
        ).order_by("order_id")
        order_ids = invoice_correction_batch.values_list("order_id", flat=True)
        invoice_ids = invoice_correction_batch.values_list("id", flat=True)
        payment_correction_batch = Payment.objects.filter(
                order_id__in=order_ids,
                order__invoices__in=invoice_ids,
                order__invoices__isnull=False,
                is_active=True
            )

        export_invoice_data, export_payment_data = get_miglo_query_values_list(invoice_batch, payment_batch)

        export_invoice_correction_data, export_payment_correction_data = \
            get_miglo_query_values_list(invoice_correction_batch, payment_correction_batch, True)

        export_data = []
        for i in range(len(export_invoice_data)):
                export_data.append(export_invoice_data[i] | export_payment_data[i])
        for i in range(len(export_invoice_correction_data)):
                export_data.append(export_invoice_correction_data[i] | export_payment_correction_data[i])
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


def clean_tally_fields(temp_file, delimiter):

    table = etl.fromcsv(temp_file.name, delimiter=delimiter)
    table = etl.convert(table, {'net_price_22_23_percent': float,
                                'tax_price_22_23_percent': float})
    table = etl.convert(table, {
        'net_price_22_23_percent': lambda v: str(round(v * 100 / 12300, 2)),
        'tax_price_22_23_percent': lambda v: str(round(v * 23 / 12300, 2))})
    table = etl.convert(table, "net_price_22_23_percent", "replace", ".", ",")
    table = etl.convert(table, "tax_price_22_23_percent", "replace", ".", ",")
    table = etl.convert(table, "created_date", "replace", " 00:00:00", "")
    table = etl.convert(table, "sale_date", "replace", " 00:00:00", "")

    temp_file = NamedTemporaryFile("ab+", suffix=".csv")
    etl.tocsv(table, temp_file.name, delimiter=delimiter)
    return temp_file


def clean_miglo_fields(temp_file, delimiter):
    table = etl.fromcsv(temp_file.name, delimiter=delimiter)
    table = etl.convert(table, {'Netto': float,
                                'Brutto': float,
                                'ParentBrutto': float})
    table = etl.convert(table, {
        'Netto': lambda v: str(round(v * 100 / 12300, 2)),
        'Brutto': lambda v: str(round(v * 23 / 12300, 2))},
                        where = lambda r: r.DocType == '4')

    table = etl.convert(table, "DocDate", "replace", " 00:00:00", "")
    table = etl.convert(table, "SaleDate", "replace", " 00:00:00", "")
    table = etl.convert(table, "OriginalDate", "replace", " 00:00:00", "")

    table = etl.convert(table, "PaymentTypeId", "replace", "salingo.payments.payu", "2")
    table = etl.convert(table, "PaymentTypeId", "replace", "salingo.payments.cod", "3")
    table = etl.convert(table, "PaymentName", "replace", "salingo.payments.payu", "Przelew")
    table = etl.convert(table, "PaymentName", "replace", "salingo.payments.cod", "Pobranie")

    table = etl.convert(table, 'CorrectionType', "replace", "2", "1", where = lambda r: r.ParentFile == ' ')
    table = etl.transform.basics.cutout(table, "ParentFile")

    table = etl.convert(table, 'Netto',
                        lambda v, row: str(round((v - row.ParentBrutto) * 100 / 12300, 2)),
                        pass_row=True, where = lambda r: r.DocType == '9')
    table = etl.convert(table, 'Brutto',
                        lambda v, row: str(round((v - row.ParentBrutto) * 23 / 12300, 2)),
                        pass_row=True, where = lambda r: r.DocType == '9')
    table = etl.transform.basics.cutout(table, "ParentBrutto")

    table = etl.convert(table, "Netto", "replace", ".", ",")
    table = etl.convert(table, "Brutto", "replace", ".", ",")

    temp_file = NamedTemporaryFile("ab+", suffix=".csv")
    etl.tocsv(table, temp_file.name, delimiter=delimiter)
    return temp_file


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
