import graphene

from .mutations import ExtReceiptRequest, ExtReceiptUpdate, ExtInvoiceCorrectionRequest


class InvoiceMutations(graphene.ObjectType):
    ext_receipt_request = ExtReceiptRequest.Field()
    ext_receipt_update = ExtReceiptUpdate.Field()
    ext_invoice_correction_request = ExtInvoiceCorrectionRequest.Field()
