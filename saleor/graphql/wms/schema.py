import graphene

from ...core.permissions import ProductPermissions
from ..decorators import permission_required
from .mutations import (WmsDocumentCreate, WmsDocumentUpdate, WmsDocPositionCreate,
                        WmsDocPositionUpdate, WmsDocumentDelete, WmsDocPositionDelete)

from saleor.wms import models
from saleor.graphql.core.fields import FilterInputConnectionField
from saleor.graphql.wms.filters import WmsDocumentFilterInput
from saleor.graphql.wms.resolvers import (resolve_wms_documents, resolve_wms_document,
                                          resolve_wms_doc_positions, resolve_wms_document_pdf,
                                          resolve_wms_actions_report, resolve_wms_products_report,
                                          resolve_wms_doc_position)
from .types import WmsDocPosition, WmsDocument
from .filters import WmsDocPositionFilterInput
from graphene.types.generic import GenericScalar


class WmsDocumentMutations(graphene.ObjectType):
    # Documents
    wms_document_create = WmsDocumentCreate.Field()
    wms_document_update = WmsDocumentUpdate.Field()
    wms_document_delete = WmsDocumentDelete.Field()
    # Document positions
    wms_doc_position_create = WmsDocPositionCreate.Field()
    wms_doc_position_update = WmsDocPositionUpdate.Field()
    wms_doc_position_delete = WmsDocPositionDelete.Field()


class WmsDocumentQueries(graphene.ObjectType):
    wms_documents = FilterInputConnectionField(
        WmsDocument,
        filter=WmsDocumentFilterInput(description="Filtering wms documents"),
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

    @permission_required(ProductPermissions.MANAGE_PRODUCTS)
    def resolve_wms_documents(self, info, **kwargs):
        return resolve_wms_documents(info, **kwargs)

    @permission_required(ProductPermissions.MANAGE_PRODUCTS)
    def resolve_wms_document(self, info, **kwargs):
        return resolve_wms_document(info, **kwargs)

    @permission_required(ProductPermissions.MANAGE_PRODUCTS)
    def resolve_wms_document_pdf(self, info, **kwargs):
        return resolve_wms_document_pdf(info, **kwargs)

    @permission_required(ProductPermissions.MANAGE_PRODUCTS)
    def resolve_wms_actions_report(self, info, **kwargs):
        return resolve_wms_actions_report(info, **kwargs)

    @permission_required(ProductPermissions.MANAGE_PRODUCTS)
    def resolve_wms_products_report(self, info, **kwargs):
        return resolve_wms_products_report(info, **kwargs)


class WmsDocPositionQueries(graphene.ObjectType):
    wms_doc_positions = FilterInputConnectionField(
        WmsDocPosition,
        filter=WmsDocPositionFilterInput(description="Filtering wms document positions"),
        description="List of wms document positions"
    )

    wms_doc_position = graphene.Field(
        WmsDocPosition,
        id=graphene.Argument(graphene.ID, description="ID of the wms document."),
        description="Look up a wms document position by id",
    )

    @permission_required(ProductPermissions.MANAGE_PRODUCTS)
    def resolve_wms_doc_positions(self, info, **kwargs):
        return resolve_wms_doc_positions(info, **kwargs)

    @permission_required(ProductPermissions.MANAGE_PRODUCTS)
    def resolve_wms_doc_position(self, info, **kwargs):
        return resolve_wms_doc_position(info, **kwargs)


