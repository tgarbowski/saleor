import graphene

from .sorters import WmsDocumentSortingInput
from saleor.core.permissions import WMSPermissions
from saleor.graphql.decorators import permission_required
from .mutations import (
    WmsDocumentCreate, WmsDocumentUpdate, WmsDocPositionCreate, WmsDocPositionUpdate,
    WmsDocumentDelete, WmsDocPositionDelete, WmsDelivererCreate, WmsDelivererUpdate, WmsDelivererDelete
)

from saleor.graphql.core.fields import FilterConnectionField
from saleor.graphql.salingo.wms.resolvers import (
    resolve_wms_documents, resolve_wms_document, resolve_wms_doc_positions, resolve_wms_document_pdf,
    resolve_wms_actions_report, resolve_wms_products_report, resolve_wms_doc_position,
    resolve_wms_deliverers, resolve_wms_deliverer
)
from .types import (
    WarehousePdfFiles, WmsDeliverer, WmsDocPosition, WmsDocument, WMSDocumentCountableConnection,
    WMSDocPositionCountableConnection, WMSDelivererCountableConnection
)
from .filters import WmsDocPositionFilterInput, WmsDocumentFilterInput, WmsDelivererFilterInput
from graphene.types.generic import GenericScalar
from saleor.graphql.core.connection import create_connection_slice, filter_connection_queryset
from saleor.graphql.order.schema import OrderFilterInput
from saleor.graphql.utils import resolve_global_ids_to_primary_keys
from saleor.order.models import Order
from saleor.graphql.order.filters import OrderFilter
from saleor.graphql.salingo.wms.utils import generate_wms_documents
from saleor.graphql.salingo.wms.utils import generate_encoded_pdf_documents, generate_warehouse_list


class WmsDocumentMutations(graphene.ObjectType):
    # Documents
    wms_document_create = WmsDocumentCreate.Field()
    wms_document_update = WmsDocumentUpdate.Field()
    wms_document_delete = WmsDocumentDelete.Field()
    # Document positions
    wms_doc_position_create = WmsDocPositionCreate.Field()
    wms_doc_position_update = WmsDocPositionUpdate.Field()
    wms_doc_position_delete = WmsDocPositionDelete.Field()
    # Deliverers
    wms_deliverer_create = WmsDelivererCreate.Field()
    wms_deliverer_update = WmsDelivererUpdate.Field()
    wms_deliverer_delete = WmsDelivererDelete.Field()


class WmsDocumentQueries(graphene.ObjectType):
    wms_documents = FilterConnectionField(
        WMSDocumentCountableConnection,
        sort_by=WmsDocumentSortingInput(description="Sort wms documents."),
        filter=WmsDocumentFilterInput(),
        description="List of wms documents"
    )

    wms_document = graphene.Field(
        WmsDocument,
        id=graphene.Argument(graphene.ID, description="ID of the wms document.",),
        number=graphene.Argument(graphene.String, description="Number of the wms document"),
        description="Look up a wms document by id or number.",
    )

    wms_document_pdf = graphene.String(
        id=graphene.ID(required=True)
    )

    wms_actions_report = GenericScalar(
        startDate=graphene.Argument(graphene.Date, required=True),
        endDate=graphene.Argument(graphene.Date, required=True)
    )
    wms_products_report = GenericScalar(
        startDate=graphene.Argument(graphene.Date, required=True),
        endDate=graphene.Argument(graphene.Date, required=True)
    )

    warehouse_lists_generate = graphene.Field(
        WarehousePdfFiles,
        order_ids=graphene.List(graphene.NonNull(graphene.ID)),
        filters=OrderFilterInput(),
        description='B64 encoded Warehouse pdf files'
    )

    @permission_required(WMSPermissions.MANAGE_WMS)
    def resolve_wms_documents(self, info, **kwargs):
        qs = resolve_wms_documents(info, **kwargs)
        qs = filter_connection_queryset(qs, kwargs)
        return create_connection_slice(qs, info, kwargs, WMSDocumentCountableConnection)

    @permission_required(WMSPermissions.MANAGE_WMS)
    def resolve_wms_document(self, info, **kwargs):
        return resolve_wms_document(info, **kwargs)

    @permission_required(WMSPermissions.MANAGE_WMS)
    def resolve_wms_document_pdf(self, info, **kwargs):
        return resolve_wms_document_pdf(info, **kwargs)

    @permission_required(WMSPermissions.MANAGE_WMS)
    def resolve_wms_actions_report(self, info, **kwargs):
        return resolve_wms_actions_report(info, **kwargs)

    @permission_required(WMSPermissions.MANAGE_WMS)
    def resolve_wms_products_report(self, info, **kwargs):
        return resolve_wms_products_report(info, **kwargs)

    def resolve_warehouse_lists_generate(self, info, **kwargs):
        def get_orders(kwargs):
            global_order_ids = kwargs.get('order_ids')
            filters = kwargs.get('filters')

            if global_order_ids:
                return resolve_global_ids_to_primary_keys(ids=global_order_ids)[1]
            if filters:
                all_orders = Order.objects.all()
                filtered_orders = OrderFilter(
                    data=filters, queryset=all_orders
                ).qs
                return list(
                    filtered_orders.values_list('id', flat=True)), list(filtered_orders.reverse())
            return []

        order_ids, orders = get_orders(kwargs)

        generate_wms_documents(orders)
        wms_list = generate_encoded_pdf_documents(orders)
        warehouse_list = generate_warehouse_list(order_ids=order_ids)

        return WarehousePdfFiles(warehouse_list=warehouse_list, wms_list=wms_list)


class WmsDocPositionQueries(graphene.ObjectType):
    wms_doc_positions = FilterConnectionField(
        WMSDocPositionCountableConnection,
        filter=WmsDocPositionFilterInput(description="Filtering wms document positions"),
        description="List of wms document positions"
    )

    wms_doc_position = graphene.Field(
        WmsDocPosition,
        id=graphene.Argument(graphene.ID, description="ID of the wms document."),
        description="Look up a wms document position by id",
    )

    @permission_required(WMSPermissions.MANAGE_WMS)
    def resolve_wms_doc_positions(self, info, **kwargs):
        qs = resolve_wms_doc_positions(info, **kwargs)
        qs = filter_connection_queryset(qs, kwargs)
        return create_connection_slice(qs, info, kwargs, WMSDocPositionCountableConnection)

    @permission_required(WMSPermissions.MANAGE_WMS)
    def resolve_wms_doc_position(self, info, **kwargs):
        return resolve_wms_doc_position(info, **kwargs)


class WmsDelivererQueries(graphene.ObjectType):
    wms_deliverers = FilterConnectionField(
        WMSDelivererCountableConnection,
        filter=WmsDelivererFilterInput(description="Filtering wms deliverers"),
        description="List of wms deliverers"
    )
    wms_deliverer = graphene.Field(
        WmsDeliverer,
        id=graphene.Argument(graphene.ID, description="ID of the wms deliverer.", ),
        description="Look up a wms deliverer by id.",
    )

    @permission_required(WMSPermissions.MANAGE_WMS)
    def resolve_wms_deliverers(self, info, **kwargs):
        qs = resolve_wms_deliverers(info, **kwargs)
        qs = filter_connection_queryset(qs, kwargs)
        return create_connection_slice(qs, info, kwargs, WMSDelivererCountableConnection)

    @permission_required(WMSPermissions.MANAGE_WMS)
    def resolve_wms_deliverer(self, info, **kwargs):
        return resolve_wms_deliverer(info, **kwargs)
