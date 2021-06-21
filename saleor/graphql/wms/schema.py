import graphene

from .mutations import (WMSDocumentCreate, WMSDocumentUpdate, WMSDocPositionCreate,
                        WMSDocPositionUpdate, WMSDocumentDelete, WMSDocPositionDelete)

from saleor.wms import models
from saleor.graphql.core.fields import FilterInputConnectionField
from saleor.graphql.wms.filters import WMSDocumentFilterInput
from saleor.graphql.wms.resolvers import (resolve_wms_documents, resolve_wms_document,
                                          resolve_wms_doc_positions, resolve_wms_document_pdf,
                                          resolve_wms_actions_report, resolve_wms_products_report)
from .types import WMSDocPosition, WMSDocument
from .filters import WMSDocPositionFilterInput
from graphene.types.generic import GenericScalar

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

    @staticmethod
    def resolve_wms_documents(self, info, **kwargs):
        return resolve_wms_documents(info, **kwargs)

    @staticmethod
    def resolve_wms_document(self, info, **kwargs):
        return resolve_wms_document(info, **kwargs)

    @staticmethod
    def resolve_wms_document_pdf(self, info, **kwargs):
        return resolve_wms_document_pdf(info, **kwargs)

    @staticmethod
    def resolve_wms_actions_report(self, info, **kwargs):
        return resolve_wms_actions_report(info, **kwargs)

    @staticmethod
    def resolve_wms_products_report(self, info, **kwargs):
        return resolve_wms_products_report(info, **kwargs)


class WMSDocPositionQueries(graphene.ObjectType):
    wms_doc_positions = FilterInputConnectionField(
        WMSDocPosition,
        filter=WMSDocPositionFilterInput(description="Filtering wms document positions"),
        description="List of wms document positions"
    )

    @staticmethod
    def resolve_wms_doc_positions(self, info, **kwargs):
        return resolve_wms_doc_positions(info, **kwargs)
