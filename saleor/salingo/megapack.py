import json
from typing import List

from django.core.exceptions import ValidationError
from django.db import connection, transaction

from saleor.plugins.allegro.utils import (
    skus_to_product_ids,
    get_products_by_channels,
    product_ids_to_skus,
    get_allegro_channels_slugs
)
from saleor.product.models import (
    ProductVariant, ProductMedia, ProductChannelListing, ProductVariantChannelListing, Product
)
from saleor.channel.models import Channel
from saleor.salingo.sql.raw_sql import delete_medias_by_product_id
from saleor.core.error_codes import MetadataErrorCode
from saleor.plugins.allegro.api import AllegroAPI
from saleor.salingo.images import create_collage


class Megapack:
    def __init__(self, megapack: Product):
        self.megapack = megapack

    def create(self, skus: List[str]) -> Product:
        #products_sold_in_allegro = self.bulk_allegro_offers_unpublish(skus)
        #skus = self.delete_products_sold_from_data(skus, products_sold_in_allegro)
        self.clear_bundle_id_for_removed_products(skus)
        self.assign_sku_to_metadata_bundle_id(skus)
        self.change_channel_listings(skus, channel_slug='bundled')
        self.assign_bundle_content_to_product()
        self.create_description_json_for_megapack()
        self.save_megapack_with_valid_products(skus)
        #self.assign_photos_from_products_to_megapack()
        #self.validate_mega_pack(skus, products_sold_in_allegro)
        return self.megapack

    def clear_bundle_id_for_removed_products(self, skus: List[str]):
        # TODO: validate removed_skus type is list of strings
        current_skus = self.megapack.private_metadata.get('skus')

        if current_skus:
            removed_skus = [sku for sku in current_skus if sku not in skus]
            product_ids = skus_to_product_ids(removed_skus)
            products = Product.objects.filter(id__in=product_ids)

            for product in products:
                product.delete_value_from_metadata('bundle.id')

            Product.objects.bulk_update(products, ['metadata'])
            # TODO: move change channel listing somewhere else
            if removed_skus:
                self.change_channel_listings(removed_skus, channel_slug='unpublished')

    def assign_sku_to_metadata_bundle_id(self, skus: List[str]):
        bundle_id = ProductVariant.objects.get(product=self.megapack.pk).sku
        products = Product.objects.filter(variants__sku__in=skus)

        for product in products:
            if not product.metadata.get('bundle.id'):
                #product.metadata["bundle.id"] = bundle_id
                product.store_value_in_metadata({"bundle.id": bundle_id})

        Product.objects.bulk_update(products, ['metadata'])

    def change_channel_listings(self, skus: List[str], channel_slug: str):
        channel_id = Channel.objects.get(slug=channel_slug).pk
        product_ids = list(
            ProductVariant.objects.filter(sku__in=skus).values_list('product_id', flat=True)
        )
        variant_ids = list(
            ProductVariant.objects.filter(sku__in=skus).values_list('pk', flat=True)
        )

        with transaction.atomic():
            ProductChannelListing.objects.filter(product_id__in=product_ids).update(
                channel_id=channel_id)
            ProductVariantChannelListing.objects.filter(
                variant_id__in=variant_ids).update(channel_id=channel_id)

    def assign_photos_from_products_to_megapack(self):
        valid_skus = self.megapack.private_metadata.get('skus')
        product_variants = ProductVariant.objects.select_related('product').filter(
            sku__in=valid_skus)
        collage_images = []
        # Remove existing megapack images
        with connection.cursor() as cursor:
            cursor.execute(
                delete_medias_by_product_id,
                [self.megapack.pk]
            )
        # Create images
        step = int(len(product_variants) / 12)
        if step == 0:
            step = 1

        for product_variant in product_variants[::step]:
            photo = ProductMedia.objects.filter(
                product=product_variant.product.pk
            ).first()
            ppoi = photo.ppoi or "0.5x0.5"
            new_image = ProductMedia.objects.create(
                product=self.megapack,
                ppoi=ppoi,
                alt=product_variant.product.name,
                image=photo.image
            )
            collage_images.append(new_image)
        # Create collage image from images
        if len(collage_images) >= 4:
            create_collage(collage_images[:12], self.megapack)

    def validate_mega_pack(self, skus: List[str], products_published):
        bundle_id = ProductVariant.objects.get(product=self.megapack.pk).sku
        product_variants = ProductVariant.objects.select_related('product').filter(sku__in=skus)
        validation_message = ""
        products_already_assigned = []
        products_not_exist = []
        product_variants_skus = [product_variant.sku for product_variant in
                                 product_variants]

        if len(skus) > len(product_variants):
            products_not_exist = [product for product in skus if
                                  product not in product_variants_skus]

        for product_variant in product_variants:
            if product_variant.product.metadata.get('bundle.id') != bundle_id:
                products_already_assigned.append(product_variant.sku)

        if products_published:
            allegro_products = []
            allegro_sold_or_bid_product_variants = ProductVariant.objects.select_related(
                'product').filter(
                sku__in=products_published)
            for removed_product_variant in allegro_sold_or_bid_product_variants:
                removed_pv_location = removed_product_variant.private_metadata.get(
                    "location")
                location = removed_pv_location if removed_pv_location else "brak lokacji"
                allegro_products.append(f'{removed_product_variant.sku}: {location}')
        # TODO: investigate products_not_exist != [""]
        if (products_not_exist and products_not_exist != [
            ""]) or products_already_assigned or products_published:
            if products_not_exist:
                products_not_exist_str = ", ".join(products_not_exist)
                validation_message += f'Produkty nie istnieją:  {products_not_exist_str}.'
            if products_published:
                products_published_str = ", ".join(allegro_products)
                validation_message += f'Produkty sprzedane lub licytowane:  {products_published_str}.'
            if products_already_assigned:
                products_already_assigned_str = ", ".join(products_already_assigned)
                validation_message += f'Produkty już przypisane do megapaki:  {products_already_assigned_str}.'
            self.megapack.private_metadata["publish.allegro.errors"] = [validation_message]
            self.megapack.save()
            raise ValidationError({
                "megapack": ValidationError(
                    message=validation_message,
                    code=MetadataErrorCode.MEGAPACK_ASSIGNED.value,
                )
            })
        self.megapack.delete_value_from_private_metadata('publish.allegro.errors')
        self.megapack.save()

    def bulk_allegro_offers_unpublish(self, skus: List[str]):
        allegro_channel_slugs = get_allegro_channels_slugs()
        product_ids = skus_to_product_ids(skus)
        products_per_channels = get_products_by_channels(product_ids, allegro_channel_slugs)
        products_allegro_sold_or_auctioned = []

        for channel in products_per_channels:
            if not channel['product_ids']:
                continue
            skus = product_ids_to_skus(channel['product_ids'])
            allegro_api = AllegroAPI(channel=channel['channel__slug'])
            allegro_data = allegro_api.bulk_offer_unpublish(skus=skus)
            if allegro_data['errors'] and allegro_data['status'] == "OK":
                for product in enumerate(allegro_data['errors']):
                    if 'sku' in product[1]:
                        products_allegro_sold_or_auctioned.append(product[1]['sku'])

            if allegro_data['status'] == "ERROR":
                self.megapack.private_metadata["publish.allegro.errors"] = allegro_data['errors']
                self.megapack.save()
                raise ValidationError({
                    "megapack": ValidationError(
                        message=allegro_data['errors'],
                        code=MetadataErrorCode.MEGAPACK_ASSIGNED.value,
                    )
                })

        return products_allegro_sold_or_auctioned

    def delete_products_sold_from_data(self, skus: List[str], allegro_sold_products) -> List[str]:
        if isinstance(allegro_sold_products, list):
            return [product for product in skus if product not in allegro_sold_products]

        return [product for product in skus]

    def generate_bundle_content(self, slug: str):
        with connection.cursor() as dbCursor:
            dbCursor.execute(f"select generate_bundle_content('{slug}')")
            data = dbCursor.fetchall()
        return data

    def calculate_weight(self, bundle_content):
        weight = 0
        try:
            for content in bundle_content:
                weight += content[2] * 1000
        except (TypeError, IndexError):
            weight = None

        return weight

    def assign_bundle_content_to_product(self):
        sku = ProductVariant.objects.get(product=self.megapack.pk).sku
        bundle_content = self.generate_bundle_content(sku)
        print('bundle_content', bundle_content)
        if bundle_content[0][0] is not None:
            self.megapack.private_metadata['bundle.content'] = json.loads(bundle_content[0][0])
            self.megapack.weight = self.calculate_weight(json.loads(bundle_content[0][0]))
        else:
            if 'bundle.content' in self.megapack.private_metadata:
                self.megapack.delete_value_from_private_metadata('bundle.content')
                self.megapack.weight = None
            self.megapack.save()

    def save_megapack_with_valid_products(self, skus: List[str]):
        verified_skus = []
        product_variants = ProductVariant.objects.select_related('product').filter(sku__in=skus)
        bundle_id = ProductVariant.objects.get(product=self.megapack.pk).sku

        for product_variant in product_variants:
            if product_variant.product.metadata.get('bundle.id') != bundle_id:
                continue
            verified_skus.append(product_variant.sku)

        self.megapack.private_metadata['skus'] = verified_skus
        self.megapack.save(update_fields=["private_metadata"])

    def create_description_json_for_megapack(self):
        description_json = generate_description_json_for_megapack(
            self.megapack.private_metadata.get("bundle.content")
        )
        self.megapack.description = description_json


def generate_description_json_for_megapack(bundle_content):
    description_json = {}
    blocks = []
    description_values = {"data": {"text": "Zawartość megapaki: ", "level": 2},
                          "type": "header"}
    blocks.append(description_values)
    products_amount = 0
    products_weight = 0
    if bundle_content:
        for section in bundle_content:
            list_fragment = {"data": {"style": "unorder", "items": []}, "type": "list"}
            if section[0] == "Mężczyzna":
                clothes_type = 'męskie'
            elif section[0] == "Dziecko":
                clothes_type = 'dziecięce'
            else:
                clothes_type = 'damskie'

            txt = f'  ubrania {clothes_type}: {section[1]} szt., {section[2]} kg'
            list_fragment["data"]["items"].append(txt)

            products_amount += section[1]
            try:
                products_weight += section[2]
            except TypeError:
                pass
            blocks.append(list_fragment)

    list_fragment = {"data": {"style": "unorder", "items": []}, "type": "list"}
    summary_txt = f'  razem: {products_amount} szt., {round(products_weight, 2)} kg'
    list_fragment["data"]["items"].append(summary_txt)
    blocks.append(list_fragment)

    description_json["blocks"] = blocks
    description_json["entityMap"] = {}
    return description_json
