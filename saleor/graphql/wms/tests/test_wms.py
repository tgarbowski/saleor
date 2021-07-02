import graphene
import pytest

from saleor.graphql.tests.utils import get_graphql_content
from saleor.plugins.manager import PluginsManager
from saleor.wms.models import WmsDocument, WmsDocPosition

QUERY_WMSDOCUMENT = """
    query ($id: ID, $number: String){
        wmsDocument(id: $id, number: $number){
            id
            createdAt
            updatedAt
            warehouse {
                id
            }
            warehouseSecond {
                id
            }
            documentType
            createdBy {
                id
            }
            recipient {
                id
            }
            deliverer
            number
            status
        }
    }
"""

QUERY_FETCH_ALL_WMSDOCUMENTS = """
    query {
        wmsDocuments(first: 10) {
            totalCount
            edges {
                node {
                    id
                    documentType
                }
            }
        }
    }
"""

QUERY_WMSDOCUMENTS_WITH_FILTER = """
    query ($filter: WmsDocumentFilterInput!, ) {
        wmsDocuments(first:5, filter: $filter) {
            totalCount
            edges{
                node{
                    id
                    number
                }
            }
        }
    }
"""

MUTATION_CREATE_WMSDOCUMENT = """
mutation WmsDocumentCreate($input: WmsDocumentInput!)  {
    wmsDocumentCreate(input: $input) {
        wmsDocument{
            createdBy{
                id
            }
            recipient{
                id
            }
            deliverer
            documentType
            number
            status
            warehouse{
                id
            }
            warehouseSecond{
                id
            }
        }
        errors {
            field
            message
        }
    }
}
"""

MUTATION_UPDATE_WMSDOCUMENT = """
mutation WmsDocumentUpdate($id: ID!, $input: WmsDocumentInput!) {
    wmsDocumentUpdate(id: $id, input: $input){
        wmsDocument {
            documentType
            status
            number
        }
        errors {
            field
            message
        }
    }
}
"""

DELETE_WMSDOCUMENT_MUTATION = """
    mutation WmsDocumentDelete($id: ID!) {
        wmsDocumentDelete(id: $id) {
            wmsDocument {
                id
                number
            }
            errors {
                field
                message
            }
        }
    }
"""

QUERY_WMSDOCPOSITION = """
    query ($id: ID){
        wmsDocPosition(id: $id){
            document {
                id
                number
            }
            quantity
            weight
            productVariant {
                id
            }
            id
        }
    }
"""

QUERY_FETCH_ALL_WMSDOCPOSITIONS = """
    query {
        wmsDocPositions(first: 10) {
            totalCount
            edges {
                node {
                    id
                }
            }
        }
    }
"""

MUTATION_CREATE_WMSDOCPOSITION = """
mutation WmsDocPositionCreate($input: WmsDocPositionInput!) {
    wmsDocPositionCreate(input: $input){
        wmsDocPosition {
            quantity
            weight
            productVariant {
                id
            }
            document {
                id
            }
        }
        errors {
            field
            message
        }
    }
}
"""

MUTATION_UPDATE_WMSDOCPOSITION = """
mutation WmsDocPositionUpdate($id: ID!, $input: WmsDocPositionInput!) {
    wmsDocPositionUpdate(id: $id, input: $input){
        wmsDocPosition {
            quantity
            weight
            productVariant {
                id
            }
            document {
                id
            }
        }
        errors {
            field
            message
        }
    }
}
"""

DELETE_WMSDOCPOSITION_MUTATION = """
    mutation WmsDocumentDelete($id: ID!) {
        wmsDocPositionDelete(id: $id) {
            wmsDocPosition {
                id
            }
            errors {
                field
                message
            }
        }
    }
"""


def test_wmsdocument_query_by_id(
    superuser_api_client, wms_document, permission_manage_wmsdocument
):
    # given
    variables = {"id": graphene.Node.to_global_id("WmsDocument", wms_document.pk)}
    #staff_api_client.user.user_permissions.add(permission_manage_wmsdocument)
    # when
    response = superuser_api_client.post_graphql(QUERY_WMSDOCUMENT, variables=variables)

    # then
    content = get_graphql_content(response)
    wmsdocument_data = content["data"]["wmsDocument"]
    assert wmsdocument_data is not None
    assert wmsdocument_data["number"] == wms_document.number


def test_wmsdocument_query_by_number(
    superuser_api_client, wms_document,
):
    variables = {"number": wms_document.number}
    response = superuser_api_client.post_graphql(QUERY_WMSDOCUMENT, variables=variables)
    content = get_graphql_content(response)
    wmsdocument_data = content["data"]["wmsDocument"]
    assert wmsdocument_data is not None
    assert wmsdocument_data["number"] == wms_document.number


def test_fetch_all_wmsdocuments(superuser_api_client):
    response = superuser_api_client.post_graphql(QUERY_FETCH_ALL_WMSDOCUMENTS)
    content = get_graphql_content(response)
    num_wmsdocuments = WmsDocument.objects.count()
    assert content["data"]["wmsDocuments"]["totalCount"] == num_wmsdocuments
    assert len(content["data"]["wmsDocuments"]["edges"]) == num_wmsdocuments


def test_wmsdocuments_query_with_filter(superuser_api_client, wms_document):

    variables = {
        "filter": {
            "documentType": ["GRN"]
        }
    }

    response = superuser_api_client.post_graphql(QUERY_WMSDOCUMENTS_WITH_FILTER, variables)
    content = get_graphql_content(response)
    first_wmsdocument_id = graphene.Node.to_global_id("WmsDocument", wms_document.pk)
    wmsdocuments = content["data"]["wmsDocuments"]["edges"]

    assert len(wmsdocuments) == 1
    assert wmsdocuments[0]["node"]["id"] == first_wmsdocument_id
    assert wmsdocuments[0]["node"]["number"] == wms_document.number


def test_create_wmsdocument(
    superuser_api_client,
    staff_user,
    customer_user,
    warehouse,
    setup_wms
):
    query = MUTATION_CREATE_WMSDOCUMENT
    manager = PluginsManager(plugins=setup_wms.PLUGINS)

    import json
    warehouse_id = graphene.Node.to_global_id("Warehouse", warehouse.pk)
    createdby_id = graphene.Node.to_global_id("User", staff_user.pk)
    customer_user_id = graphene.Node.to_global_id("User", customer_user.pk)
    deliverer = {"firma": "Google", "miasto": "Warszawa"}
    deliverer = json.dumps(deliverer)

    variables = {
        "input": {
            "createdBy": createdby_id,
            "recipient": customer_user_id,
            "deliverer": deliverer,
            "documentType": "GRN",
            "warehouse": warehouse_id
        }
    }

    response = superuser_api_client.post_graphql(
        query, variables
    )
    content = get_graphql_content(response)
    data = content["data"]["wmsDocumentCreate"]
    assert data["errors"] == []
    assert data["wmsDocument"]["status"] == "DRAFT"
    assert data["wmsDocument"]["createdBy"]["id"] == createdby_id
    assert data["wmsDocument"]["recipient"]["id"] == customer_user_id
    assert data["wmsDocument"]["documentType"] == "GRN"
    assert data["wmsDocument"]["warehouse"]["id"] == warehouse_id
    assert data["wmsDocument"]["deliverer"] == deliverer


def test_update_wmsdocument(
    superuser_api_client,
    wms_document
):
    query = MUTATION_UPDATE_WMSDOCUMENT

    wms_document_id = graphene.Node.to_global_id("WmsDocument", wms_document.pk)
    wms_document_type = "GIN"

    variables = {
        "id": wms_document_id,
        "input": {
            "documentType": wms_document_type
        }
    }

    response = superuser_api_client.post_graphql(
        query, variables
    )
    content = get_graphql_content(response)
    data = content["data"]["wmsDocumentUpdate"]
    assert data["errors"] == []
    assert data["wmsDocument"]["number"] == wms_document.number
    assert data["wmsDocument"]["documentType"] == wms_document_type


def test_delete_wmsdocument(superuser_api_client, wms_document):
    query = DELETE_WMSDOCUMENT_MUTATION
    node_id = graphene.Node.to_global_id("WmsDocument", wms_document.id)
    variables = {"id": node_id}
    response = superuser_api_client.post_graphql(
        query, variables
    )
    content = get_graphql_content(response)
    data = content["data"]["wmsDocumentDelete"]
    assert data["wmsDocument"]["number"] == wms_document.number
    with pytest.raises(wms_document._meta.model.DoesNotExist):
        wms_document.refresh_from_db()
    assert node_id == data["wmsDocument"]["id"]


def test_wmsdocposition_query_by_id(
    superuser_api_client, wms_docposition,
):

    wmsdocposition_id = graphene.Node.to_global_id("WmsDocPosition", wms_docposition.pk)

    # given
    variables = {"id": wmsdocposition_id}

    # when
    response = superuser_api_client.post_graphql(QUERY_WMSDOCPOSITION, variables=variables)

    # then
    content = get_graphql_content(response)
    wmsdocposition_data = content["data"]["wmsDocPosition"]
    assert wmsdocposition_data is not None
    assert wmsdocposition_data["id"] == wmsdocposition_id


def test_fetch_all_wmsdocpositions(superuser_api_client):
    response = superuser_api_client.post_graphql(QUERY_FETCH_ALL_WMSDOCPOSITIONS)
    content = get_graphql_content(response)
    num_wmsdocpositions = WmsDocPosition.objects.count()
    assert content["data"]["wmsDocPositions"]["totalCount"] == num_wmsdocpositions
    assert len(content["data"]["wmsDocPositions"]["edges"]) == num_wmsdocpositions


def test_create_wmsdocposition(
    superuser_api_client,
    wms_document,
    variant
):
    query = MUTATION_CREATE_WMSDOCPOSITION
    #manager = PluginsManager(plugins=setup_wms.PLUGINS)

    wmsdocument_id = graphene.Node.to_global_id("WmsDocument", wms_document.pk)
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.pk)
    quantity = 10
    weight = 50

    variables = {
        "input": {
            "quantity": quantity,
            "weight": weight,
            "productVariant": variant_id,
            "document": wmsdocument_id
        }
    }

    response = superuser_api_client.post_graphql(
        query, variables
    )
    content = get_graphql_content(response)
    data = content["data"]["wmsDocPositionCreate"]
    assert data["errors"] == []
    assert data["wmsDocPosition"]["quantity"] == quantity
    assert data["wmsDocPosition"]["weight"] == weight
    assert data["wmsDocPosition"]["productVariant"]["id"] == variant_id
    assert data["wmsDocPosition"]["document"]["id"] == wmsdocument_id


def test_update_wmsdocposition(
    superuser_api_client,
    wms_docposition
):
    query = MUTATION_UPDATE_WMSDOCPOSITION

    wms_docposition_id = graphene.Node.to_global_id("WmsDocPosition", wms_docposition.pk)
    quantity = 3456
    weight = 45

    variables = {
        "id": wms_docposition_id,
        "input": {
            "quantity": quantity,
            "weight": weight
        }
    }

    response = superuser_api_client.post_graphql(
        query, variables
    )
    content = get_graphql_content(response)
    data = content["data"]["wmsDocPositionUpdate"]
    assert data["errors"] == []
    assert data["wmsDocPosition"]["quantity"] == quantity
    assert data["wmsDocPosition"]["weight"] == weight


def test_delete_wmsdocposition(superuser_api_client, wms_docposition):
    query = DELETE_WMSDOCPOSITION_MUTATION
    node_id = graphene.Node.to_global_id("WmsDocPosition", wms_docposition.id)
    variables = {"id": node_id}
    response = superuser_api_client.post_graphql(
        query, variables
    )
    content = get_graphql_content(response)
    data = content["data"]["wmsDocPositionDelete"]
    assert data["wmsDocPosition"]["id"] == node_id
    with pytest.raises(wms_docposition._meta.model.DoesNotExist):
        wms_docposition.refresh_from_db()
    assert data["wmsDocPosition"]["id"] == node_id
