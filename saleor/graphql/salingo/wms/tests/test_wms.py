import graphene
import pytest

from saleor.graphql.tests.utils import get_graphql_content
from saleor.wms.models import WmsDocument, WmsDocPosition
from saleor.graphql.account.enums import CountryCodeEnum


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
            deliverer {
                id
            }
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
            deliverer {
                id
            }
            documentType
            number
            status
            location
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

QUERY_WMSDELIVERER = """
    query ($id: ID){
        wmsDeliverer(id: $id){
            id
            companyName
            street
            city
            postalCode
            email
            vatId
            phone
            country
            firstName
            lastName
        }
    }
"""

MUTATION_CREATE_WMSDELIVERER = """
mutation WmsDelivererCreate($input: WmsDelivererInput!)  {
    wmsDelivererCreate(input: $input) {
        wmsDeliverer{
          id
          companyName
          street
          city
          postalCode
          email
          vatId
          phone
          country
          firstName
          lastName
        }
        errors {
            field
            message
        }
    }
}
"""

MUTATION_UPDATE_WMSDELIVERER = """
mutation WmsDelivererUpdate($id: ID!, $input: WmsDelivererInput!)  {
    wmsDelivererUpdate(id: $id, input: $input) {
        wmsDeliverer{
          id
          companyName
          street
          city
          postalCode
          email
          vatId
          phone
          country
          firstName
          lastName
        }
        errors {
            field
            message
        }
    }
}
"""

DELETE_WMSDELIVERER_MUTATION = """
    mutation WmsDelivererDelete($id: ID!)  {
        wmsDelivererDelete(id: $id) {
            wmsDeliverer{
                id
                companyName
            }
            errors {
                field
                message
            }
        }
    }
"""


WMS_DOCUMENT_BULK_DELETE_MUTATION = """
    mutation WmsDocumentBulkDelete($ids: [ID]!) {
        wmsDocumentBulkDelete(ids: $ids) {
            count
            errors{
                message
            }
        }
}
"""


def test_wmsdocument_query_by_id(
    staff_api_client, wms_document, permission_manage_wmsdocument
):
    # given
    variables = {"id": graphene.Node.to_global_id("WmsDocument", wms_document.pk)}
    staff_api_client.user.user_permissions.add(permission_manage_wmsdocument)
    # when
    response = staff_api_client.post_graphql(QUERY_WMSDOCUMENT, variables=variables)

    # then
    content = get_graphql_content(response)
    wmsdocument_data = content["data"]["wmsDocument"]
    assert wmsdocument_data is not None
    assert wmsdocument_data["number"] == wms_document.number


def test_wmsdocument_query_by_number(
    staff_api_client, wms_document, permission_manage_wmsdocument
):
    variables = {"number": wms_document.number}
    staff_api_client.user.user_permissions.add(permission_manage_wmsdocument)
    response = staff_api_client.post_graphql(QUERY_WMSDOCUMENT, variables=variables)
    content = get_graphql_content(response)
    wmsdocument_data = content["data"]["wmsDocument"]
    assert wmsdocument_data is not None
    assert wmsdocument_data["number"] == wms_document.number


def test_fetch_all_wmsdocuments(staff_api_client, permission_manage_wmsdocument):
    staff_api_client.user.user_permissions.add(permission_manage_wmsdocument)
    response = staff_api_client.post_graphql(QUERY_FETCH_ALL_WMSDOCUMENTS)
    content = get_graphql_content(response)
    num_wmsdocuments = WmsDocument.objects.count()
    assert content["data"]["wmsDocuments"]["totalCount"] == num_wmsdocuments
    assert len(content["data"]["wmsDocuments"]["edges"]) == num_wmsdocuments


def test_wmsdocuments_query_with_filter(staff_api_client, wms_document, permission_manage_wmsdocument):

    variables = {
        "filter": {
            "documentType": ["GRN"]
        }
    }

    staff_api_client.user.user_permissions.add(permission_manage_wmsdocument)
    response = staff_api_client.post_graphql(QUERY_WMSDOCUMENTS_WITH_FILTER, variables)
    content = get_graphql_content(response)
    first_wmsdocument_id = graphene.Node.to_global_id("WmsDocument", wms_document.pk)
    wmsdocuments = content["data"]["wmsDocuments"]["edges"]

    assert len(wmsdocuments) == 1
    assert wmsdocuments[0]["node"]["id"] == first_wmsdocument_id
    assert wmsdocuments[0]["node"]["number"] == wms_document.number


def test_create_wmsdocument(
    staff_api_client,
    permission_manage_wmsdocument,
    staff_user,
    customer_user,
    warehouse,
    wms_deliverer,
    setup_wms
):
    query = MUTATION_CREATE_WMSDOCUMENT

    warehouse_id = graphene.Node.to_global_id("Warehouse", warehouse.pk)
    createdby_id = graphene.Node.to_global_id("User", staff_user.pk)
    customer_user_id = graphene.Node.to_global_id("User", customer_user.pk)
    deliverer_id = graphene.Node.to_global_id("WmsDeliverer", wms_deliverer.pk)
    location = "location100"

    variables = {
        "input": {
            "createdBy": createdby_id,
            "recipient": customer_user_id,
            "deliverer": deliverer_id,
            "documentType": "GRN",
            "warehouse": warehouse_id,
            "location": location
        }
    }

    staff_api_client.user.user_permissions.add(permission_manage_wmsdocument)
    response = staff_api_client.post_graphql(
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
    assert data["wmsDocument"]["deliverer"]["id"] == deliverer_id
    assert data["wmsDocument"]["location"] == location


def test_update_wmsdocument(
        staff_api_client,
        wms_document,
        permission_manage_wmsdocument,
        setup_wms
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

    staff_api_client.user.user_permissions.add(permission_manage_wmsdocument)
    response = staff_api_client.post_graphql(
        query, variables
    )
    content = get_graphql_content(response)
    data = content["data"]["wmsDocumentUpdate"]
    assert data["errors"] == []
    assert data["wmsDocument"]["number"] == 'GIN1'
    assert data["wmsDocument"]["documentType"] == wms_document_type


def test_delete_wmsdocument(staff_api_client, wms_document, permission_manage_wmsdocument):
    query = DELETE_WMSDOCUMENT_MUTATION
    node_id = graphene.Node.to_global_id("WmsDocument", wms_document.id)
    variables = {"id": node_id}
    staff_api_client.user.user_permissions.add(permission_manage_wmsdocument)
    response = staff_api_client.post_graphql(
        query, variables
    )
    content = get_graphql_content(response)
    data = content["data"]["wmsDocumentDelete"]
    assert data["wmsDocument"]["number"] == wms_document.number
    with pytest.raises(wms_document._meta.model.DoesNotExist):
        wms_document.refresh_from_db()
    assert node_id == data["wmsDocument"]["id"]


def test_wmsdocposition_query_by_id(
    staff_api_client, wms_docposition, permission_manage_wmsdocument
):

    wmsdocposition_id = graphene.Node.to_global_id("WmsDocPosition", wms_docposition.pk)

    # given
    variables = {"id": wmsdocposition_id}

    # when
    staff_api_client.user.user_permissions.add(permission_manage_wmsdocument)
    response = staff_api_client.post_graphql(QUERY_WMSDOCPOSITION, variables=variables)

    # then
    content = get_graphql_content(response)
    wmsdocposition_data = content["data"]["wmsDocPosition"]
    assert wmsdocposition_data is not None
    assert wmsdocposition_data["id"] == wmsdocposition_id


def test_fetch_all_wmsdocpositions(staff_api_client, permission_manage_wmsdocument):
    staff_api_client.user.user_permissions.add(permission_manage_wmsdocument)
    response = staff_api_client.post_graphql(QUERY_FETCH_ALL_WMSDOCPOSITIONS)
    content = get_graphql_content(response)
    num_wmsdocpositions = WmsDocPosition.objects.count()
    assert content["data"]["wmsDocPositions"]["totalCount"] == num_wmsdocpositions
    assert len(content["data"]["wmsDocPositions"]["edges"]) == num_wmsdocpositions


def test_create_wmsdocposition(
    staff_api_client,
    wms_document,
    variant,
    permission_manage_wmsdocument
):
    query = MUTATION_CREATE_WMSDOCPOSITION

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

    staff_api_client.user.user_permissions.add(permission_manage_wmsdocument)
    response = staff_api_client.post_graphql(
        query, variables
    )
    content = get_graphql_content(response)
    data = content["data"]["wmsDocPositionCreate"]
    assert data["errors"] == []
    assert data["wmsDocPosition"]["quantity"] == quantity
    assert data["wmsDocPosition"]["weight"] == weight
    assert data["wmsDocPosition"]["productVariant"]["id"] == variant_id
    assert data["wmsDocPosition"]["document"]["id"] == wmsdocument_id


def test_create_wmsdocposition_negative_quantity(
    staff_api_client,
    wms_document,
    variant,
    permission_manage_wmsdocument
):
    query = MUTATION_CREATE_WMSDOCPOSITION

    wmsdocument_id = graphene.Node.to_global_id("WmsDocument", wms_document.pk)
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.pk)
    quantity = -10
    weight = 50

    variables = {
        "input": {
            "quantity": quantity,
            "weight": weight,
            "productVariant": variant_id,
            "document": wmsdocument_id
        }
    }

    staff_api_client.user.user_permissions.add(permission_manage_wmsdocument)
    response = staff_api_client.post_graphql(
        query, variables
    )
    content = get_graphql_content(response)
    data = content["data"]["wmsDocPositionCreate"]
    assert data["errors"][0]['field'] == "quantity"
    assert data["wmsDocPosition"] is None


def test_create_wmsdocposition_negative_weight(
    staff_api_client,
    wms_document,
    variant,
    permission_manage_wmsdocument
):
    query = MUTATION_CREATE_WMSDOCPOSITION

    wmsdocument_id = graphene.Node.to_global_id("WmsDocument", wms_document.pk)
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.pk)
    quantity = 10
    weight = -50

    variables = {
        "input": {
            "quantity": quantity,
            "weight": weight,
            "productVariant": variant_id,
            "document": wmsdocument_id
        }
    }

    staff_api_client.user.user_permissions.add(permission_manage_wmsdocument)
    response = staff_api_client.post_graphql(
        query, variables
    )
    content = get_graphql_content(response)
    data = content["data"]["wmsDocPositionCreate"]
    assert data["errors"][0]['field'] == "weight"
    assert data["wmsDocPosition"] is None


def test_update_wmsdocposition(
    staff_api_client,
    wms_docposition,
    permission_manage_wmsdocument
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

    staff_api_client.user.user_permissions.add(permission_manage_wmsdocument)
    response = staff_api_client.post_graphql(
        query, variables
    )
    content = get_graphql_content(response)
    data = content["data"]["wmsDocPositionUpdate"]
    assert data["errors"] == []
    assert data["wmsDocPosition"]["quantity"] == quantity
    assert data["wmsDocPosition"]["weight"] == weight


def test_delete_wmsdocposition(staff_api_client, wms_docposition, permission_manage_wmsdocument):
    query = DELETE_WMSDOCPOSITION_MUTATION
    node_id = graphene.Node.to_global_id("WmsDocPosition", wms_docposition.id)
    variables = {"id": node_id}
    staff_api_client.user.user_permissions.add(permission_manage_wmsdocument)
    response = staff_api_client.post_graphql(
        query, variables
    )
    content = get_graphql_content(response)
    data = content["data"]["wmsDocPositionDelete"]
    assert data["wmsDocPosition"]["id"] == node_id
    with pytest.raises(wms_docposition._meta.model.DoesNotExist):
        wms_docposition.refresh_from_db()
    assert data["wmsDocPosition"]["id"] == node_id


def test_wmsdeliverer_query_by_id(
    staff_api_client, wms_deliverer, permission_manage_wmsdocument
):
    query = QUERY_WMSDELIVERER
    wmsdeliverer_id = graphene.Node.to_global_id("WmsDeliverer", wms_deliverer.pk)
    variables = {"id": wmsdeliverer_id}
    staff_api_client.user.user_permissions.add(permission_manage_wmsdocument)

    response = staff_api_client.post_graphql(query, variables=variables)
    content = get_graphql_content(response)
    wmsdeliverer_data = content["data"]["wmsDeliverer"]
    assert wmsdeliverer_data is not None
    assert wmsdeliverer_data["id"] == wmsdeliverer_id


def test_update_wmsdeliverer(staff_api_client, wms_deliverer, permission_manage_wmsdocument):
    query = MUTATION_UPDATE_WMSDELIVERER
    wmsdeliverer_id = graphene.Node.to_global_id("WmsDeliverer", wms_deliverer.pk)
    company_name = 'new_company_name'
    email = 'newemail@yandex.com'

    variables = {
        "id": wmsdeliverer_id,
        "input": {
            "companyName": company_name,
            "email": email
        }
    }

    staff_api_client.user.user_permissions.add(permission_manage_wmsdocument)
    response = staff_api_client.post_graphql(
        query, variables
    )
    content = get_graphql_content(response)
    data = content["data"]["wmsDelivererUpdate"]
    assert data["errors"] == []
    assert data["wmsDeliverer"]["companyName"] == company_name
    assert data["wmsDeliverer"]["email"] == email


def test_create_wmsdeliverer(staff_api_client, permission_manage_wmsdocument):
    query = MUTATION_CREATE_WMSDELIVERER

    company_name = "Company name"
    street = "Długa 1"
    city = "Warszawa"
    postal_code = "111-11"
    email = "asd@gmail.com"
    vat_id = "365375734645656"
    phone = "+48911231223"
    country = CountryCodeEnum.US.name
    first_name = "Adam"
    last_name = "Mickiewicz"

    variables = {
        "input": {
            "companyName": company_name,
            "street": street,
            "city": city,
            "postalCode": postal_code,
            "email": email,
            "vatId": vat_id,
            "phone": phone,
            "country": country,
            "firstName": first_name,
            "lastName": last_name
        }
    }

    staff_api_client.user.user_permissions.add(permission_manage_wmsdocument)
    response = staff_api_client.post_graphql(
        query, variables
    )
    content = get_graphql_content(response)
    data = content["data"]["wmsDelivererCreate"]
    assert data["errors"] == []
    assert data["wmsDeliverer"]["companyName"] == company_name
    assert data["wmsDeliverer"]["street"] == street
    assert data["wmsDeliverer"]["postalCode"] == postal_code
    assert data["wmsDeliverer"]["email"] == email
    assert data["wmsDeliverer"]["vatId"] == vat_id
    assert data["wmsDeliverer"]["phone"] == phone
    assert data["wmsDeliverer"]["country"] == country
    assert data["wmsDeliverer"]["firstName"] == first_name
    assert data["wmsDeliverer"]["lastName"] == last_name


def test_delete_wmsdeliverer(staff_api_client, wms_deliverer, permission_manage_wmsdocument):
    query = DELETE_WMSDELIVERER_MUTATION
    node_id = graphene.Node.to_global_id("WmsDeliverer", wms_deliverer.id)
    variables = {"id": node_id}
    staff_api_client.user.user_permissions.add(permission_manage_wmsdocument)
    response = staff_api_client.post_graphql(
        query, variables
    )
    content = get_graphql_content(response)
    data = content["data"]["wmsDelivererDelete"]
    assert data["wmsDeliverer"]["id"] == node_id
    with pytest.raises(wms_deliverer._meta.model.DoesNotExist):
        wms_deliverer.refresh_from_db()
    assert node_id == data["wmsDeliverer"]["id"]


def test_bulk_wms_document_delete(staff_api_client, wms_document_list, permission_manage_wmsdocument):
    query = WMS_DOCUMENT_BULK_DELETE_MUTATION
    wms_document_ids = [wms_document.id for wms_document in wms_document_list]
    variables = {
        "ids": [
            graphene.Node.to_global_id("WmsDocument", wms_document.id)
            for wms_document in wms_document_list
        ]
    }

    staff_api_client.user.user_permissions.add(permission_manage_wmsdocument)
    response = staff_api_client.post_graphql(
        query, variables
    )
    content = get_graphql_content(response)

    assert content["data"]["wmsDocumentBulkDelete"]["count"] == 2
    assert not WmsDocument.objects.filter(id__in=wms_document_ids).exists()
    assert not WmsDocPosition.objects.filter(document__in=wms_document_ids).exists()
