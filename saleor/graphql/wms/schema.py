import graphene

from ...core.permissions import WMSPermissions
from ..decorators import permission_required
from .mutations import (WmsDocumentCreate, WmsDocumentUpdate, WmsDocPositionCreate,
                        WmsDocPositionUpdate, WmsDocumentDelete, WmsDocPositionDelete,
                        WmsDelivererCreate, WmsDelivererUpdate, WmsDelivererDelete)

from saleor.graphql.core.fields import FilterConnectionField
from saleor.graphql.wms.resolvers import (resolve_wms_documents, resolve_wms_document,
                                          resolve_wms_doc_positions, resolve_wms_document_pdf,
                                          resolve_wms_actions_report,
                                          resolve_wms_products_report, resolve_wms_doc_position,
                                          resolve_wms_deliverers, resolve_wms_deliverer)
from .types import (WmsDeliverer, WmsDocPosition, WmsDocument, WMSDocumentCountableConnection,
                    WMSDocPositionCountableConnection, WMSDelivererCountableConnection)
from .filters import WmsDocPositionFilterInput, WmsDocumentFilterInput, WmsDelivererFilterInput
from graphene.types.generic import GenericScalar
from ..core.connection import create_connection_slice, filter_connection_queryset


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
