from django.db import models
from django.utils.translation import gettext_lazy as _

from saleor.product.models import ProductVariant
from saleor.account.models import User
from saleor.warehouse.models import Warehouse


class WMSDocument(models.Model):

    class DocumentTypes(models.TextChoices):
        GOODS_RECEIVED_NOTE = "GRN", _("Goods_received_note")
        GOODS_ISSUED_NOTE = "GIN", _("Goods_issued_note")

    class DocumentStatuses(models.TextChoices):
        APPROVED = "APPROVED", _("APPROVED")
        DRAFT = "DRAFT", _("DRAFT")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, null=True)
    document_type = models.CharField(max_length=10, choices=DocumentTypes.choices)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="wms_created_by"
    )
    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="wms_recipient"
    )
    deliverer = models.JSONField(blank=True, null=True)
    number = models.CharField(max_length=255, blank=False, default=None)
    status = models.CharField(max_length=20, choices=DocumentStatuses.choices)

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


class WMSDocPosition(models.Model):
    product_variant = models.ForeignKey(
        ProductVariant, related_name="wms_doc_position", on_delete=models.DO_NOTHING
    )
    quantity = models.IntegerField(default=0)
    weight = models.FloatField(default=0)
    document = models.ForeignKey(
        WMSDocument, related_name="wms_doc_position", on_delete=models.CASCADE
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
