import graphene

from .mutations import (WMSDocumentCreate, WMSDocumentUpdate, WMSDocPositionCreate,
                        WMSDocPositionUpdate, WMSDocumentDelete, WMSDocPositionDelete)

from saleor.wms.models import WMSDocument
from saleor.graphql.core.fields import FilterInputConnectionField
from saleor.graphql.wms.filters import WMSDocumentFilterInput
from saleor.graphql.wms.resolvers import (resolve_wms_documents, resolve_wms_document,
                                          resolve_wms_doc_positions)
from .types import WMSDocPosition, WMSDocument
from .filters import WMSDocPositionFilterInput


class WMSDocumentMutations(graphene.ObjectType):
    # Documents
    wmsdocument_create = WMSDocumentCreate.Field()
    wmsdocument_update = WMSDocumentUpdate.Field()
    wms_document_delete = WMSDocumentDelete.Field()
    # Document positions
    wmsdocposition_create = WMSDocPositionCreate.Field()
    wmsdocposition_update = WMSDocPositionUpdate.Field()
    wms_doc_position_delete = WMSDocPositionDelete.Field()


class WMSDocumentQueries(graphene.ObjectType):
    wms_documents = FilterInputConnectionField(
        WMSDocument,
        filter=WMSDocumentFilterInput(description="Filtering wms documents"),
        description="List of wms documents"
    )
    wms_document = graphene.Field(
        WMSDocument,
        id=graphene.Argument(graphene.ID, description="ID of the wms document.",),
        number=graphene.Argument(graphene.String, description="Number of the wms document"),
        description="Look up a wms document by id or number.",
    )

    @staticmethod
    def resolve_wms_documents(self, info, **kwargs):
        return resolve_wms_documents(info, **kwargs)

    @staticmethod
    def resolve_wms_document(self, info, **kwargs):
        return resolve_wms_document(info, **kwargs)


class WMSDocPositionQueries(graphene.ObjectType):
    wms_doc_positions = FilterInputConnectionField(
        WMSDocPosition,
        filter=WMSDocPositionFilterInput(description="Filtering wms document positions"),
        description="List of wms document positions"
    )

    @staticmethod
    def resolve_wms_doc_positions(self, info, **kwargs):
        return resolve_wms_doc_positions(info, **kwargs)
