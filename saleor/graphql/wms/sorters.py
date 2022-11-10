import graphene

from ..core.descriptions import DEPRECATED_IN_3X_INPUT
from ..core.types import SortInputObjectType


class WmsDocumentSortField(graphene.Enum):
    NAME = ["pk"]
    STATUS = ["status", "pk"]
    CREATED_AT = ["created_at", "status", "pk"]
    DOCUMENT_TYPE = ["document_type", "status", "pk"]
    WAREHOUSE = ["warehouse", "status", "pk"]

    @property
    def description(self):
        # pylint: disable=no-member
        descriptions = {
            WmsDocumentSortField.CREATION_DATE.name: (
                f"creation date. {DEPRECATED_IN_3X_INPUT}"
            ),
        }

        if self.name in WmsDocumentSortField.__enum__._member_names_:
            if self.name in descriptions:
                return f"Sort orders by {descriptions[self.name]}"

            sort_name = self.name.lower().replace("_", " ")
            return f"Sort orders by {sort_name}."

        raise ValueError("Unsupported enum value: %s" % self.value)


class WmsDocumentSortingInput(SortInputObjectType):
    class Meta:
        sort_enum = WmsDocumentSortField
        type_name = "wmsDocuments"
