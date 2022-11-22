import pytest

from django.contrib.auth.models import Permission

from saleor.plugins.models import PluginConfiguration
from saleor.plugins.wms.plugin import WMSPlugin
from saleor.wms.models import WmsDeliverer, WmsDocument, WmsDocPosition


@pytest.fixture
def wms_document(staff_user, customer_user, warehouse, wms_deliverer):
    return WmsDocument.objects.create(
        document_type='GRN',
        deliverer=wms_deliverer,
        number='GRN1',
        status='DRAFT',
        created_by=staff_user,
        recipient=customer_user,
        warehouse=warehouse,
        location='location1'
    )

@pytest.fixture
def wms_document_2(staff_user, customer_user, warehouse, wms_deliverer):
    return WmsDocument.objects.create(
        document_type='GRN',
        deliverer=wms_deliverer,
        number='GRN2',
        status='DRAFT',
        created_by=staff_user,
        recipient=customer_user,
        warehouse=warehouse,
        location='location2'
    )


@pytest.fixture
def wms_docposition(wms_document, variant):
    return WmsDocPosition.objects.create(
        quantity=10,
        product_variant=variant,
        weight=50,
        document=wms_document
    )


@pytest.fixture
def wms_deliverer():
    return WmsDeliverer.objects.create(
        company_name="firma1",
        street="Długa 1",
        city="Warszawa",
        postal_code="111-11",
        email="asd@gmail.com",
        vat_id="365375734645656",
        phone="+48911231223",
        country="PL",
        first_name="Adam",
        last_name="Mickiewicz"
    )


@pytest.fixture
def permission_manage_wmsdocument():
    return Permission.objects.get(codename="manage_wms")


@pytest.fixture
def setup_wms(settings):
    settings.PLUGINS = ["saleor.plugins.wms.plugin.WMSPlugin"]
    data = {
        "active": True,
        "configuration": [
            {"name": "IWM", "value": "IWM"},
            {"name": "GRN", "value": "PZ"},
            {"name": "FGTN", "value": "FGTN"},
            {"name": "GIN", "value": "GIN"}
        ]
    }
    PluginConfiguration.objects.create(identifier=WMSPlugin.PLUGIN_ID, **data)
    return settings


@pytest.fixture
def wms_document_list(wms_document, wms_document_2):
    return [wms_document, wms_document_2]
