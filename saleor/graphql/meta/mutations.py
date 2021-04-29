import json
from typing import List

import graphene
from django.core.exceptions import ValidationError, ObjectDoesNotExist

from ...core import models
from ...core.error_codes import MetadataErrorCode
from ...core.exceptions import PermissionDenied
from ..core.mutations import BaseMutation
from ..core.types.common import MetadataError
from .extra_methods import MODEL_EXTRA_METHODS
from .permissions import PRIVATE_META_PERMISSION_MAP, PUBLIC_META_PERMISSION_MAP
from .types import ObjectWithMetadata
from ...product.models import ProductVariant, ProductImage


class MetadataPermissionOptions(graphene.types.mutation.MutationOptions):
    permission_map = {}


class BaseMetadataMutation(BaseMutation):
    class Meta:
        abstract = True

    @classmethod
    def __init_subclass_with_meta__(
        cls, arguments=None, permission_map=[], _meta=None, **kwargs,
    ):
        if not _meta:
            _meta = MetadataPermissionOptions(cls)
        if not arguments:
            arguments = {}
        fields = {"item": graphene.Field(ObjectWithMetadata)}

        _meta.permission_map = permission_map

        super().__init_subclass_with_meta__(_meta=_meta, **kwargs)
        cls._update_mutation_arguments_and_fields(arguments=arguments, fields=fields)

    @classmethod
    def get_instance(cls, info, **data):
        object_id = data.get("id")
        return cls.get_node_or_error(info, object_id)

    @classmethod
    def validate_model_is_model_with_metadata(cls, model, object_id):
        if not issubclass(model, models.ModelWithMetadata):
            raise ValidationError(
                {
                    "id": ValidationError(
                        f"Couldn't resolve to a item with meta: {object_id}",
                        code=MetadataErrorCode.NOT_FOUND.value,
                    )
                }
            )

    @classmethod
    def validate_metadata_keys(cls, metadata_list: List[dict]):
        # raise an error when any of the key is empty
        if not all([data["key"].strip() for data in metadata_list]):
            raise ValidationError(
                {
                    "input": ValidationError(
                        "Metadata key cannot be empty.",
                        code=MetadataErrorCode.REQUIRED.value,
                    )
                }
            )

    @classmethod
    def get_model_for_type_name(cls, info, type_name):
        graphene_type = info.schema.get_type(type_name).graphene_type
        return graphene_type._meta.model

    @classmethod
    def get_permissions(cls, info, **data):
        object_id = data.get("id")
        if not object_id:
            return []
        type_name, object_pk = graphene.Node.from_global_id(object_id)
        model = cls.get_model_for_type_name(info, type_name)
        cls.validate_model_is_model_with_metadata(model, object_id)
        permission = cls._meta.permission_map.get(type_name)
        if permission:
            return permission(info, object_pk)
        raise NotImplementedError(
            f"Couldn't resolve permission to item: {object_id}. "
            "Make sure that type exists inside PRIVATE_META_PERMISSION_MAP "
            "and PUBLIC_META_PERMISSION_MAP"
        )

    @classmethod
    def mutate(cls, root, info, **data):
        try:
            permissions = cls.get_permissions(info, **data)
        except ValidationError as e:
            return cls.handle_errors(e)
        if not cls.check_permissions(info.context, permissions):
            raise PermissionDenied()
        result = super().mutate(root, info, **data)
        if not result.errors:
            cls.perform_model_extra_actions(root, info, **data)
        return result

    @classmethod
    def perform_model_extra_actions(cls, root, info, **data):
        """Run extra metadata method based on mutating model."""
        type_name, _ = graphene.Node.from_global_id(data["id"])
        if MODEL_EXTRA_METHODS.get(type_name):
            instance = cls.get_instance(info, **data)
            MODEL_EXTRA_METHODS[type_name](instance, info, **data)

    @classmethod
    def success_response(cls, instance):
        """Return a success response."""
        return cls(**{"item": instance, "errors": []})

    @classmethod
    def clear_bundle_id_for_removed_products(cls, instance, data):
        data_skus = json.loads(data['skus'].replace("'", '"'))
        if "skus" in instance.private_metadata:
            previous_products = json.loads(instance.private_metadata["skus"]
                                           .replace("'", '"'))
            for previous_product in enumerate(previous_products):
                if previous_product[1] not in data_skus:
                    try:
                        product_variant = ProductVariant.objects\
                            .get(sku=previous_product[1])
                        product_variant.product.metadata['bundle.id'] = ""
                        product_variant.product.save()
                    except ObjectDoesNotExist as e:
                        continue

    @classmethod
    def assign_sku_to_metadata_bundle_id(cls, instance, data):
        bundle_id = ProductVariant.objects.get(product=instance.pk).sku
        product_variants = ProductVariant.objects.filter(sku__in=eval(data['skus']))
        for index, product_variant in enumerate(product_variants):
            product = product_variant.product
            if 'bundle.id' not in product.metadata or \
                    product.metadata['bundle.id'] == '':
                product.metadata["bundle.id"] = bundle_id
                product.save()

    @classmethod
    def assign_photos_from_products_to_megapack(cls, instance, items):
        product_variants = ProductVariant.objects.filter(sku__in=eval(items['skus']))
        for product_variant in product_variants:
            if 'bundle.id' not in product_variant.product.metadata or product_variant.\
                    product.metadata['bundle.id'] == '':
                photo = ProductImage.objects.get(product=product_variant.product.pk)
                ProductImage.objects.create(product=instance, ppoi=photo.ppoi,
                                            alt=photo.alt, image=photo.image)

    @classmethod
    def validate_mega_pack(cls, instance,  data):
        data_skus = json.loads(data['skus'].replace("'", '"'))
        bundle_id = ProductVariant.objects.get(product=instance.pk).sku
        product_variants = ProductVariant.objects.filter(sku__in=eval(data['skus']))
        if len(data_skus) > len(product_variants):
            raise ValidationError({
                "input": ValidationError(
                    "Product does not exist",
                    code=MetadataErrorCode.MEGAPACK_ASSIGNED.value,
                )
            })
        for product_variant in product_variants:
            if 'bundle.id' in product_variant.product.metadata:
                if product_variant.product.metadata['bundle.id'] != bundle_id:
                    raise ValidationError(
                        {
                            "input": ValidationError(
                                "Metadata key cannot be empty.",
                                code=MetadataErrorCode.MEGAPACK_ASSIGNED.value,
                                name="dfadfd",
                            )
                        }
                    )
            if 'publish.allegro.status' in product_variant.product.private_metadata:
                if product_variant.product.private_metadata['publish.allegro.status']\
                 == "published":
                    raise ValidationError({
                        "input": ValidationError(
                            "Product published.",
                            code=MetadataErrorCode.MEGAPACK_ASSIGNED.value,
                        )
                    })


class MetadataInput(graphene.InputObjectType):
    key = graphene.String(required=True, description="Key of a metadata item.")
    value = graphene.String(required=True, description="Value of a metadata item.")


class UpdateMetadata(BaseMetadataMutation):
    class Meta:
        description = "Updates metadata of an object."
        permission_map = PUBLIC_META_PERMISSION_MAP
        error_type_class = MetadataError
        error_type_field = "metadata_errors"

    class Arguments:
        id = graphene.ID(description="ID of an object to update.", required=True)
        input = graphene.List(
            graphene.NonNull(MetadataInput),
            description="Fields required to update the object's metadata.",
            required=True,
        )

    @classmethod
    def perform_mutation(cls, root, info, **data):
        instance = cls.get_instance(info, **data)
        if instance:
            metadata_list = data.pop("input")
            cls.validate_metadata_keys(metadata_list)
            items = {data.key: data.value for data in metadata_list}
            instance.store_value_in_metadata(items=items)
            instance.save(update_fields=["metadata"])
        return cls.success_response(instance)


class DeleteMetadata(BaseMetadataMutation):
    class Meta:
        description = "Delete metadata of an object."
        permission_map = PUBLIC_META_PERMISSION_MAP
        error_type_class = MetadataError
        error_type_field = "metadata_errors"

    class Arguments:
        id = graphene.ID(description="ID of an object to update.", required=True)
        keys = graphene.List(
            graphene.NonNull(graphene.String),
            description="Metadata keys to delete.",
            required=True,
        )

    @classmethod
    def perform_mutation(cls, root, info, **data):
        instance = cls.get_instance(info, **data)
        if instance:
            metadata_keys = data.pop("keys")
            for key in metadata_keys:
                instance.delete_value_from_metadata(key)
            instance.save(update_fields=["metadata"])
        return cls.success_response(instance)


class UpdatePrivateMetadata(BaseMetadataMutation):
    class Meta:
        description = "Updates private metadata of an object."
        permission_map = PRIVATE_META_PERMISSION_MAP
        error_type_class = MetadataError
        error_type_field = "metadata_errors"

    class Arguments:
        id = graphene.ID(description="ID of an object to update.", required=True)
        input = graphene.List(
            graphene.NonNull(MetadataInput),
            description=("Fields required to update the object's metadata."),
            required=True,
        )

    @classmethod
    def perform_mutation(cls, root, info, **data):
        instance = cls.get_instance(info, **data)
        if instance:
            metadata_list = data.pop("input")
            cls.validate_metadata_keys(metadata_list)
            items = {data.key: data.value for data in metadata_list}
            if 'skus' in items:
                cls.validate_mega_pack(instance, items)
                cls.clear_bundle_id_for_removed_products(instance, items)
                cls.assign_photos_from_products_to_megapack(instance, items)
                cls.assign_sku_to_metadata_bundle_id(instance, items)
            instance.store_value_in_private_metadata(items=items)
            instance.save(update_fields=["private_metadata"])
        return cls.success_response(instance)


class DeletePrivateMetadata(BaseMetadataMutation):
    class Meta:
        description = "Delete object's private metadata."
        permission_map = PRIVATE_META_PERMISSION_MAP
        error_type_class = MetadataError
        error_type_field = "metadata_errors"

    class Arguments:
        id = graphene.ID(description="ID of an object to update.", required=True)
        keys = graphene.List(
            graphene.NonNull(graphene.String),
            description="Metadata keys to delete.",
            required=True,
        )

    @classmethod
    def perform_mutation(cls, root, info, **data):
        instance = cls.get_instance(info, **data)
        if instance:
            metadata_keys = data.pop("keys")
            for key in metadata_keys:
                instance.delete_value_from_private_metadata(key)
            instance.save(update_fields=["private_metadata"])
        return cls.success_response(instance)
