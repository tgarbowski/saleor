import graphene

from saleor.graphql.order.schema import OrderFilterInput
from saleor.graphql.utils import resolve_global_ids_to_primary_keys
from saleor.order.models import Order
from saleor.graphql.order.filters import OrderFilter
from saleor.graphql.wms.utils import generate_warehouse_list
from .mutations import ExtReceiptRequest, ExtReceiptUpdate, ExtInvoiceCorrectionRequest, \
    ExtFinancialTally


class ExternalQueries(graphene.ObjectType):
    warehouse_list_pdf = graphene.Field(
        graphene.String,
        order_ids=graphene.List(graphene.NonNull(graphene.ID)),
        filters=OrderFilterInput(),
        description='B64 encoded warehouse list pdf'
    )

    def resolve_warehouse_list_pdf(self, info, **kwargs):
        def get_order_ids(kwargs):
            global_order_ids = kwargs.get('order_ids')
            filters = kwargs.get('filters')

            if global_order_ids:
                return resolve_global_ids_to_primary_keys(ids=global_order_ids)[1]
            if filters:
                all_orders = Order.objects.all()
                filtered_orders = OrderFilter(
                    data=filters, queryset=all_orders
                ).qs
                return filtered_orders.values_list('id', flat=True)
            return []

        warehouse_list = generate_warehouse_list(order_ids=get_order_ids(kwargs))
        return warehouse_list


class ExternalMutations(graphene.ObjectType):
    ext_receipt_request = ExtReceiptRequest.Field()
    ext_receipt_update = ExtReceiptUpdate.Field()
    ext_invoice_correction_request = ExtInvoiceCorrectionRequest.Field()
    ext_finantial_tally = ExtFinancialTally.Field()
