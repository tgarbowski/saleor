from dataclasses import dataclass
from datetime import date
import json
import math
import uuid
from typing import List, Set

from botocore.exceptions import ClientError
from measurement.measures import Mass

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Q, Sum
from django.contrib.postgres.aggregates import ArrayAgg
from django.utils.text import slugify

from saleor.plugins.allegro.utils import skus_to_product_ids, product_ids_to_skus
from saleor.plugins.allegro.tasks import unpublish_from_multiple_channels
from saleor.product.models import (
    Category, ProductVariant, ProductMedia, ProductChannelListing, ProductVariantChannelListing,
    Product, ProductType
)
from saleor.product.search import update_product_search_document
from saleor.channel.models import Channel
from saleor.salingo.sql.raw_sql import delete_medias_by_product_id
from saleor.core.error_codes import MetadataErrorCode
from saleor.salingo.images import create_collage
from saleor.warehouse.models import Stock, Warehouse
from saleor.attribute.models import AssignedProductAttribute, AttributeValue
from .images import create_new_media_from_existing_media
from saleor.product.thumbnails import create_product_thumbnails


class Megapack:
    def __init__(self, megapack: Product, megapack_sku: str):
        self.megapack = megapack
        self.megapack_sku = megapack_sku

    def create(self, skus: List[str]) -> Product:
        removed_skus = self.removed_skus(skus)

        if removed_skus:
            self.change_channel_listings(removed_skus, channel_slug='unpublished')
            self.clear_bundle_ids(removed_skus)

        self.assign_sku_to_metadata_bundle_id(skus)
        self.change_channel_listings(skus, channel_slug='bundled')
        self.assign_bundle_content_to_product()
        self.create_description_json_for_megapack()
        self.save_megapack_with_valid_products(skus)
        self.assign_photos_from_products_to_megapack()
        self.validate_mega_pack(skus)
        return self.megapack

    def clear_bundle_ids(self, skus: List[str]):
        products = Product.objects.filter(variants__sku__in=skus)

        for product in products:
            product.delete_value_from_metadata('bundle.id')

        Product.objects.bulk_update(products, ['metadata'])

    def assign_sku_to_metadata_bundle_id(self, skus: List[str]):
        products = Product.objects.filter(variants__sku__in=skus)

        for product in products:
            product.metadata["bundle.id"] = self.megapack_sku

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

    def removed_skus(self, skus):
        current_skus = self.megapack.private_metadata.get('skus')
        if current_skus:
            return [sku for sku in current_skus if sku not in skus]
        return []

    def variants_by_skus(self, skus):
        return ProductVariant.objects.select_related('product').filter(sku__in=skus)

    def assign_photos_from_products_to_megapack(self) -> None:
        def get_images_step(variants_count):
            return int(variants_count / 12) or 1

        valid_skus = self.megapack.private_metadata.get('skus')
        product_variants = self.variants_by_skus(valid_skus)
        collage_images = []
        self.remove_existing_megapack_images()
        step = get_images_step(len(product_variants))

        for product_variant in product_variants[::step]:
            photo = ProductMedia.objects.filter(product=product_variant.product.pk).first()
            if not photo:
                continue
            try:
                new_image = create_new_media_from_existing_media(self.megapack, photo)
            except (ClientError, FileNotFoundError):
                continue
            create_product_thumbnails(new_image.pk)
            collage_images.append(new_image)

        if collage_images:
            create_collage(collage_images[:12], self.megapack)

    def remove_existing_megapack_images(self):
        with connection.cursor() as cursor:
            cursor.execute(
                delete_medias_by_product_id,
                [self.megapack.pk]
            )

    def is_bundle_id_correct(self, product: Product):
        return product.metadata.get('bundle.id') == self.megapack_sku

    def get_bundle_content(self):
        return self.megapack.get_value_from_private_metadata('bundle.content')

    def assign_bundle_content_to_product(self):
        bundle_content = self.generate_bundle_content(self.megapack_sku)

        if bundle_content:
            self.save_bundle_content_and_weight(bundle_content)
        else:
            if self.get_bundle_content():
                self.delete_bundle_content_and_null_weight()

    def generate_bundle_content(self, sku: str):
        with connection.cursor() as dbCursor:
            dbCursor.execute(f"select generate_bundle_content('{sku}')")
            data = dbCursor.fetchall()
        return data[0][0]

    def calculate_weight(self, bundle_content):
        weight = 0
        try:
            for content in bundle_content:
                weight += content[2] * 1000
        except (TypeError, IndexError):
            weight = None

        return weight

    def save_bundle_content_and_weight(self, bundle_content):
        bundle_content_json = json.loads(bundle_content)
        self.megapack.private_metadata['bundle.content'] = bundle_content_json
        self.megapack.weight = self.calculate_weight(bundle_content_json)
        self.megapack.save()

    def delete_bundle_content_and_null_weight(self):
        self.megapack.delete_value_from_private_metadata('bundle.content')
        self.megapack.weight = None
        self.megapack.save()

    def save_megapack_with_valid_products(self, skus: List[str]):
        verified_skus = []
        product_variants = self.variants_by_skus(skus)

        for product_variant in product_variants:
            if self.is_bundle_id_correct(product_variant.product) is False:
                continue
            verified_skus.append(product_variant.sku)

        self.megapack.private_metadata['skus'] = verified_skus
        self.megapack.save(update_fields=["private_metadata"])

    def create_description_json_for_megapack(self):
        description_json = generate_description_json_for_megapack(
            self.megapack.private_metadata.get("bundle.content"),
            self.megapack.private_metadata.get('bundle.sizes')
        )
        self.megapack.description = description_json

    def validate_mega_pack(self, skus: List[str]):
        product_variants = self.variants_by_skus(skus)
        validation_message = ""
        products_already_assigned = self.products_already_assigned(product_variants)
        products_not_exist = self.skus_not_existing(skus, product_variants)

        if products_not_exist:
            products_not_exist_str = ", ".join(products_not_exist)
            validation_message += f'Produkty nie istnieją:  {products_not_exist_str}.'
        if products_already_assigned:
            products_already_assigned_str = ", ".join(products_already_assigned)
            validation_message += f'Produkty już przypisane do megapaki:  {products_already_assigned_str}.'

        if validation_message:
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

    def skus_not_existing(self, skus, product_variants):
        product_variants_skus = [product_variant.sku for product_variant in product_variants]
        products_not_exist = []

        if len(skus) > len(product_variants):
            products_not_exist = [product for product in skus if product not in product_variants_skus]

        return products_not_exist

    def products_already_assigned(self, product_variants):
        products_already_assigned = []

        for product_variant in product_variants:
            if self.is_bundle_id_correct(product_variant.product) is False:
                products_already_assigned.append(product_variant.sku)

        return products_already_assigned


@dataclass
class BundlableProducts:
    weight: Mass
    product_ids: List[int]
    size: Set[str]
    sort_order: int
    name: str = None


class MegapackBulkCreate:
    min_weight = 5
    max_weight_by_size = 10

    def create(self, channel: str):
        '''
        1. Get products by root categories
        2. For each root category group by product size
        3. Calculate weight SUM for each product size
        4. Check if weight is < min_weight
        5. Shuffle products
        '''
        packs_by_categories = {}

        for category in self.get_root_categories():
            sizable_attributes = self.get_attributes_by_root_category(
                channel_slug=channel,
                category_tree_id=category.tree_id
            )
            for sizable_attribute in sizable_attributes:
                products_by_size = self.products_by_size(
                    channel_slug=channel,
                    category_tree_id=category.tree_id,
                    attribute_name=sizable_attribute
                )
                products = self.split_same_sizes(products_by_size)
                products = self.accumulate_min_weight_sizes(products)
                self.name_packs(products, category.name, sizable_attribute)

                if category.name not in packs_by_categories:
                    packs_by_categories[category.name] = []
                packs_by_categories[category.name].extend(products)
        return packs_by_categories

    def divide_chunks(self, a, n):
        k, m = divmod(len(a), n)
        return (a[i * k + min(i, m):(i + 1) * k + min(i + 1, m)] for i in range(n))

    def split_same_sizes(self, products_by_size):
        ids_to_delete = []
        products_to_append = []

        for i, size in enumerate(products_by_size):
            if size.weight.kg > self.max_weight_by_size:
                splitable_products = self.split_same_size(size)
                ids_to_delete.append(i)
                for a in splitable_products:
                    products_to_append.append(a)

        products_without = [i for j, i in enumerate(products_by_size) if j not in ids_to_delete]
        products_with = products_without + products_to_append
        products_with = sorted(products_with, key=lambda x: x.sort_order)
        return products_with

    def split_same_size(self, products_by_size):
        amount = math.ceil(products_by_size.weight.kg / self.max_weight_by_size)
        weight = products_by_size.weight / amount
        splitable_product_ids = list(self.divide_chunks(products_by_size.product_ids, amount))
        splitable_products = []

        for products in splitable_product_ids:
            splitable_products.append(
                BundlableProducts(
                    weight=weight,
                    product_ids=products,
                    size=products_by_size.size.copy(),
                    sort_order=products_by_size.sort_order
                )
            )
        return splitable_products

    def accumulate_min_weight_sizes(self, products_by_size):
        for i, size in reversed(list(enumerate(products_by_size))):
            if size.weight.kg < self.min_weight and i > 0:
                products_by_size[i - 1].weight += size.weight
                products_by_size[i - 1].size.update(size.size)
                products_by_size[i - 1].product_ids.extend(size.product_ids)
                products_by_size[i] = None

        return [product_by_size for product_by_size in products_by_size if product_by_size]

    def name_packs(self, packs, category_name, sizable_attribute):
        attribute_suffix = self.get_attribute_suffix(sizable_attribute)

        for pack in packs:
            sizes = ' '.join(pack.size)
            pack.name = f'{category_name} {attribute_suffix} rozmiar {sizes}'

        return packs

    def get_attribute_suffix(self, attribute_name: str):
        try:
            attribute_category = attribute_name.split("Rozmiar")[1].split()[0]
        except IndexError:
            attribute_category = ''
        if attribute_category == 'dzieci':
            attribute_category = ''
        return attribute_category

    def get_root_categories(self):
        root_category_slugs = ['kobieta', 'mezczyzna', 'dziecko']
        return Category.objects.filter(slug__in=root_category_slugs)

    def get_bundable_products(self, channel_slug, category_tree_id):
        return ProductChannelListing.objects.filter(
            Q(**{'product__metadata__bundle.id__isnull': True}),
            channel__slug=channel_slug,
            product__category__tree_id=category_tree_id
        ).values_list('product_id')

    def get_attributes_by_root_category(self, channel_slug, category_tree_id):
        product_ids = self.get_bundable_products(channel_slug, category_tree_id)

        return list(AssignedProductAttribute.objects.filter(
            assignment__attribute__name__icontains='rozmiar',
            product__pk__in=product_ids
        ).values_list('assignment__attribute__name', flat=True).distinct())

    def products_by_size(self, channel_slug, category_tree_id, attribute_name):
        product_ids = self.get_bundable_products(channel_slug, category_tree_id)

        products_by_size = AttributeValue.objects.filter(
            productassignments__product_id__in=product_ids,
            attribute__name=attribute_name,
        ).values('name', 'sort_order')

        products_by_size = list(products_by_size.annotate(
            product_ids=ArrayAgg(
                'productassignments__product_id',
                filter=Q(productassignments__product_id__in=product_ids)
            ),
            weight=ArrayAgg(
                'productassignments__product__weight',
                filter=Q(productassignments__product_id__in=product_ids)
            )
        ))

        output = []

        for products in products_by_size:
            weight = Mass(g=sum(c.g for c in products['weight']))

            prod = BundlableProducts(
                product_ids=products['product_ids'],
                size={products['name']},
                weight=weight,
                sort_order=products['sort_order']
            )
            output.append(prod)

        return output


def create_megapacks(source_channel_slug: str, megapack_channel_slug: str):
    megapacks_per_categories = MegapackBulkCreate().create(channel=source_channel_slug)

    for megapack_per_category in megapacks_per_categories:
        for megapack in megapacks_per_categories[megapack_per_category]:
            megapack_product = create_bundle_product(
                channel_slug=megapack_channel_slug,
                product_name=megapack.name,
                category_name=megapack_per_category
            )

            save_bundle_sizes_metadata(megapack_product, megapack.size)

            process_megapack(
                skus=product_ids_to_skus(megapack.product_ids),
                megapack=megapack_product
            )


def create_bundle_product(channel_slug, product_name, category_name):
    product_type = ProductType.objects.get(name='Mega Paka')
    channel = Channel.objects.get(slug=channel_slug)
    warehouse = Warehouse.objects.first()
    category = Category.objects.get(name=category_name)

    product_count = daily_products_count_by_user(workstation='00', user_id='50')
    megapack_sku = create_megapack_sku(product_count)
    product = create_product(megapack_sku, product_name, product_type, category, channel, warehouse)
    update_product_search_document(product)
    return product


def save_bundle_sizes_metadata(product: Product, sizes: Set):
    sizes_str = ' '.join(sizes)
    product.store_value_in_private_metadata({'bundle.sizes': sizes_str})
    product.save()


def daily_products_count_by_user(workstation: str, user_id: str) -> int:
    start_string = f'{workstation}{user_id}'

    variant = ProductVariant.objects.filter(
        sku__startswith=start_string,
        created__startswith=date.today()
    ).order_by('-sku').first()

    if variant:
        daily_number = int(variant.sku[-4:])
    else:
        daily_number = 0
    return daily_number


@transaction.atomic
def create_product(sku, product_name, product_type, category, channel, warehouse):
    product = Product.objects.create(
        name=product_name,
        slug=create_product_slug(product_name),
        product_type=product_type,
        category=category,
    )
    ProductChannelListing.objects.create(
        product=product,
        channel=channel,
        is_published=False,
        currency=channel.currency_code
    )

    variant = ProductVariant.objects.create(product=product, sku=sku)
    product.default_variant = variant
    product.save(update_fields=['default_variant'])

    ProductVariantChannelListing.objects.create(
        variant=variant,
        channel=channel,
        currency=channel.currency_code,
    )
    Stock.objects.create(warehouse=warehouse, product_variant=variant, quantity=1)
    return product


def create_megapack_sku(product_count: int):
    today = date.today()
    day = str(today.day).zfill(2)
    month = str(today.month).zfill(2)
    year = str(today.year)[2:]

    current_date_str = f'{year}{month}{day}'
    user_id = '50'
    product_code = '1'
    product_number = str(product_count + 1).zfill(4)
    return f'00{user_id}{current_date_str}{product_code}{product_number}'


def create_product_slug(slug: str):
    slug = slugify(slug, allow_unicode=True)
    unique_slug = slug
    extension = 1

    search_field = "slug__iregex"
    pattern = rf"{slug}-\d+$|{slug}$"
    slug_values = (
        Product._default_manager.filter(**{search_field: pattern}).values_list("slug", flat=True)
    )

    while unique_slug in slug_values:
        extension += 1
        unique_slug = f"{slug}-{extension}"

    return unique_slug


def process_megapack(skus, megapack):
    megapack_sku = ProductVariant.objects.get(product_id=megapack.pk).sku
    megapack = Megapack(megapack=megapack, megapack_sku=megapack_sku)
    megapack.create(skus=skus)


def bulk_allegro_offers_unpublish(skus, megapack):
    """Unpublish from allegro and return skus sold or bid"""
    product_ids = skus_to_product_ids(skus)
    skus_purchased = unpublish_from_multiple_channels(product_ids)
    skus_sold_or_bid = [sku_purchased['sku'] for sku_purchased in skus_purchased if skus_purchased['reason'] != 'UNKNOWN']
    skus_unknown = [sku_purchased['sku'] for sku_purchased in skus_purchased if skus_purchased['reason'] == 'UNKNOWN']

    if skus_unknown:
        megapack.private_metadata["publish.allegro.errors"] = ['UNKNOWN']
        megapack.save()
        raise ValidationError({
            "megapack": ValidationError(
                message=['UNKNOWN'],
                code=MetadataErrorCode.MEGAPACK_ASSIGNED.value,
            )
        })

    return skus_sold_or_bid


def get_allegro_sold_validation_message(skus_sold_or_bid):
    allegro_products = []
    allegro_sold_or_bid_product_variants = ProductVariant.objects.select_related('product').filter(sku__in=skus_sold_or_bid)

    for removed_product_variant in allegro_sold_or_bid_product_variants:
        removed_pv_location = removed_product_variant.private_metadata.get("location")
        location = removed_pv_location or "brak lokacji"
        allegro_products.append(f'{removed_product_variant.sku}: {location}')

    products_published_str = ", ".join(allegro_products)
    validation_message = f'Produkty sprzedane lub licytowane:  {products_published_str}.'
    return validation_message


def generate_description_json_for_megapack(bundle_content, sizes=None):
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

    if sizes:
        size_text = f'Rozmiary: {sizes}'
        size_list_fragment = {"data": {"style": "unorder", "items": [size_text]}, "type": "list"}
        blocks.append(size_list_fragment)

    description_json["blocks"] = blocks
    description_json["entityMap"] = {}
    return description_json


def calculate_and_save_megapack_prices():
    megapacks_without_prices = ProductVariantChannelListing.objects.filter(
        variant__product__product_type__name='Mega Paka',
        price_amount=None,
        cost_price_amount=None
    ).select_related("variant", "variant__product")

    for megapack in megapacks_without_prices:
        megapack_skus = megapack.variant.product.private_metadata.get('skus')
        if not megapack_skus:
            continue
        price_amount, cost_price_amount = calculate_megapack_price(megapack_skus)
        megapack.price_amount = price_amount
        megapack.cost_price_amount = cost_price_amount

    ProductVariantChannelListing.objects.bulk_update(megapacks_without_prices, ['price_amount', 'cost_price_amount'])


def calculate_megapack_price(skus: List[str]):
    """Returns calculated megapack price amount and cost_price_amount"""
    prices = ProductVariantChannelListing.objects.filter(
        variant__sku__in=skus
    ).aggregate(
        Sum('price_amount'),
        Sum('cost_price_amount')
    )

    return prices['price_amount__sum'], prices['cost_price_amount__sum']


def bundable_products(channel_slug):
    return ProductChannelListing.objects.filter(
        Q(**{'product__metadata__bundle.id__isnull': True}),
        channel__slug=channel_slug
    ).values_list('product_id')
