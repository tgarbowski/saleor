import datetime

from django.db import models

from saleor.product.models import ProductVariant

from saleor.account.models import User
from saleor.warehouse.models import Warehouse

from django.utils.translation import gettext_lazy as _


class WMSDocument(models.Model):

    class DocumentTypes(models.TextChoices):
        GOODS_RECEIVED_NOTE = "GRN", _("Goods_received_note")
        GOODS_ISSUED_NOTE = "GIN", _("Goods_issued_note")

    date = models.DateField(verbose_name="data", default=datetime.date.today)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, null=True)
    documentType = models.CharField(max_length=5, choices=DocumentTypes.choices, default=DocumentTypes.GOODS_RECEIVED_NOTE)
    createdBy = models.ForeignKey(User, verbose_name="Stworzone przez", on_delete=models.CASCADE, blank=True, null=True, related_name="creator")
    contractor = models.ForeignKey(User, verbose_name="Kontrahent", on_delete=models.CASCADE, blank=True, null=True, related_name="contractor")
    deliverer = models.JSONField(verbose_name="Dostawca", blank=True, null=True)
    name = models.CharField(max_length=255, blank=False, verbose_name="Nr dokumentu", default=None)

    def __repr__(self):
        class_ = type(self)
        return "%s(pk=%r, name=%r, created_by=%r)" % (
            class_.__name__,
            self.pk,
            self.name,
            self.createdBy,
        )

    def __str__(self):
        return self.name or str(self.pk)


class WMSDocumentPosition(models.Model):
    product_variant = models.ForeignKey(
        ProductVariant, related_name="product_variant", on_delete=models.DO_NOTHING
    )
    amount = models.IntegerField(verbose_name="Liczba", default=0)
    document = models.ForeignKey(
        WMSDocument, related_name="Dokument", on_delete=models.CASCADE
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
