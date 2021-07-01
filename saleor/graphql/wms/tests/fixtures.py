import pytest

from django.contrib.auth.models import Permission

from saleor.plugins.models import PluginConfiguration
from saleor.plugins.wms.plugin import WMSPlugin
from saleor.wms.models import WMSDocument, WMSDocPosition


@pytest.fixture
def wms_document(staff_user, customer_user, warehouse):
    return WMSDocument.objects.create(
        document_type='GRN',
        deliverer={"firma": "Google", "miasto": "Warszawa"},
        number='GRN1',
        status='DRAFT',
        created_by=staff_user,
        recipient=customer_user,
        warehouse=warehouse
    )


@pytest.fixture
def wms_docposition(wms_document, variant):
    return WMSDocPosition.objects.create(
        quantity=10,
        product_variant=variant,
        weight=50,
        document=wms_document
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
