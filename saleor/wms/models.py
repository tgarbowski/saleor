from django_countries.fields import CountryField

from django.db import models
from django.utils.translation import gettext_lazy as _

from saleor.account.models import PossiblePhoneNumberField
from saleor.product.models import ProductVariant
from saleor.account.models import User
from saleor.warehouse.models import Warehouse
from saleor.core.permissions import WMSPermissions
from saleor.order.models import Order


class WmsDeliverer(models.Model):
    company_name = models.CharField(max_length=256)
    street = models.CharField(max_length=256)
    city = models.CharField(max_length=256)
    postal_code = models.CharField(max_length=20)
    email = models.CharField(max_length=256, blank=True)
    vat_id = models.CharField(max_length=256, blank=True)
    phone = PossiblePhoneNumberField(blank=True, default="")
    country = CountryField()
    first_name = models.CharField(max_length=256, blank=True)
    last_name = models.CharField(max_length=256, blank=True)


class WmsDocument(models.Model):

    class DocumentTypes(models.TextChoices):
        GOODS_RECEIVED_NOTE = "GRN", _("Goods_received_note")
        GOODS_ISSUED_NOTE = "GIN", _("Goods_issued_note")
        INTERNAL_WAREHOUSE_MOVEMENT = "IWM", _("Internal warehouse movement")
        FINISHED_GOODS_TRANSFER_NOTE = "FGTN", _("Finished goods transfer note")
        INTERNAL_OUTGOINGS = "IO", _("Internal outgoings")


    class DocumentStatuses(models.TextChoices):
        APPROVED = "APPROVED", _("APPROVED")
        DRAFT = "DRAFT", _("DRAFT")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    warehouse = models.ForeignKey(Warehouse, related_name='+', on_delete=models.CASCADE)
    warehouse_second = models.ForeignKey(
        Warehouse,
        related_name='+',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    document_type = models.CharField(max_length=10, choices=DocumentTypes.choices)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="wms_created_by",
        null=True
    )
    recipient = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="wms_recipient",
        null=True
    )
    recipient_email = models.EmailField(blank=True, default="")
    deliverer = models.ForeignKey(
        WmsDeliverer,
        blank=True,
        null=True,
        related_name="wms_deliverer",
        on_delete=models.SET_NULL
    )
    order = models.ForeignKey(
        Order,
        blank=True,
        null=True,
        on_delete=models.SET_NULL
    )
    number = models.CharField(max_length=255, unique=True, blank=True)
    status = models.CharField(max_length=20, choices=DocumentStatuses.choices, default='DRAFT')
    location = models.CharField(max_length=50, blank=True)

    class Meta:
        permissions = (
            (WMSPermissions.MANAGE_WMS.codename, "Manage wms."),
        )

    def __repr__(self):
        class_ = type(self)
        return "%s(pk=%r, document_number=%r, created_by=%r)" % (
            class_.__name__,
            self.pk,
            self.number,
            self.created_by,
        )

    def __str__(self):
        return self.number or str(self.pk)


class WmsDocPosition(models.Model):
    product_variant = models.ForeignKey(
        ProductVariant, related_name="wms_doc_position", on_delete=models.DO_NOTHING
    )
    quantity = models.IntegerField(default=0)
    weight = models.FloatField(default=0)
    document = models.ForeignKey(
        WmsDocument, related_name="wms_doc_position", on_delete=models.CASCADE
    )

    def __repr__(self):
        class_ = type(self)
        return "%s(pk=%r, name=%r, variant_pk=%r)" % (
            class_.__name__,
            self.pk,
            self.product_variant.product.name,
            self.product_variant,
        )

    def __str__(self):
        return self.product_variant.product.name or str(self.product_variant)
