from collections import defaultdict
import json
import os
import random
import re
import string
from typing import TYPE_CHECKING, Dict, List, Tuple

import boto3
import graphene
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.utils import IntegrityError
from io import BytesIO
from PIL import Image

from ...product import AttributeInputType
from ...product.error_codes import ProductErrorCode
from ...product.models import ProductImage
from ...product.thumbnails import create_product_thumbnails
from ...warehouse.models import Stock
from ...product.models import Attribute, ProductVariant
if TYPE_CHECKING:
    from django.db.models import QuerySet


def parse_draftjs_content_to_string(definitions: dict):
    string = ""
    blocks = definitions.get("blocks")
    if not blocks or not isinstance(blocks, list):
        return ""
    for block in blocks:
        text = block.get("text")
        if not text:
            continue
        string += f"{text} "

    return string


def validate_attributes_input_for_product(
    input_data: List[Tuple["Attribute", List[str]]],
):
    error_no_value_given = ValidationError(
        "Attribute expects a value but none were given",
        code=ProductErrorCode.REQUIRED.value,
    )
    error_dropdown_get_more_than_one_value = ValidationError(
        "Attribute attribute must take only one value",
        code=ProductErrorCode.INVALID.value,
    )
    error_blank_value = ValidationError(
        "Attribute values cannot be blank", code=ProductErrorCode.REQUIRED.value,
    )

    attribute_errors: Dict[ValidationError, List[str]] = defaultdict(list)
    for attribute, values in input_data:
        attribute_id = graphene.Node.to_global_id("Attribute", attribute.pk)
        if not values:
            if attribute.value_required:
                attribute_errors[error_no_value_given].append(attribute_id)
            continue

        if attribute.input_type != AttributeInputType.MULTISELECT and len(values) != 1:
            attribute_errors[error_dropdown_get_more_than_one_value].append(
                attribute_id
            )
            continue

        for value in values:
            if value is None or not value.strip():
                attribute_errors[error_blank_value].append(attribute_id)
                continue

    return prepare_error_list_from_error_attribute_mapping(attribute_errors)


def validate_attributes_input_for_variant(
    input_data: List[Tuple["Attribute", List[str]]]
):
    error_no_value_given = ValidationError(
        "Attribute expects a value but none were given",
        code=ProductErrorCode.REQUIRED.value,
    )
    error_more_than_one_value_given = ValidationError(
        "A variant attribute cannot take more than one value",
        code=ProductErrorCode.INVALID.value,
    )
    error_blank_value = ValidationError(
        "Attribute values cannot be blank", code=ProductErrorCode.REQUIRED.value,
    )

    attribute_errors: Dict[ValidationError, List[str]] = defaultdict(list)
    for attribute, values in input_data:
        attribute_id = graphene.Node.to_global_id("Attribute", attribute.pk)
        if not values:
            attribute_errors[error_no_value_given].append(attribute_id)
            continue

        if len(values) != 1:
            attribute_errors[error_more_than_one_value_given].append(attribute_id)
            continue

        if values[0] is None or not values[0].strip():
            attribute_errors[error_blank_value].append(attribute_id)

    return prepare_error_list_from_error_attribute_mapping(attribute_errors)


def prepare_error_list_from_error_attribute_mapping(
    attribute_errors: Dict[ValidationError, List[str]]
):
    errors = []
    for error, attributes in attribute_errors.items():
        error.params = {"attributes": attributes}
        errors.append(error)

    return errors


def get_used_attribute_values_for_variant(variant):
    """Create a dict of attributes values for variant.

    Sample result is:
    {
        "attribute_1_global_id": ["ValueAttr1_1"],
        "attribute_2_global_id": ["ValueAttr2_1"]
    }
    """
    attribute_values = defaultdict(list)
    for assigned_variant_attribute in variant.attributes.all():
        attribute = assigned_variant_attribute.attribute
        attribute_id = graphene.Node.to_global_id("Attribute", attribute.id)
        for variant in assigned_variant_attribute.values.all():
            attribute_values[attribute_id].append(variant.slug)
    return attribute_values


def get_used_variants_attribute_values(product):
    """Create list of attributes values for all existing `ProductVariants` for product.

    Sample result is:
    [
        {
            "attribute_1_global_id": ["ValueAttr1_1"],
            "attribute_2_global_id": ["ValueAttr2_1"]
        },
        ...
        {
            "attribute_1_global_id": ["ValueAttr1_2"],
            "attribute_2_global_id": ["ValueAttr2_2"]
        }
    ]
    """
    variants = (
        product.variants.prefetch_related("attributes__values")
        .prefetch_related("attributes__assignment")
        .all()
    )
    used_attribute_values = []
    for variant in variants:
        attribute_values = get_used_attribute_values_for_variant(variant)
        used_attribute_values.append(attribute_values)
    return used_attribute_values


@transaction.atomic
def create_stocks(
    variant: "ProductVariant", stocks_data: List[Dict[str, str]], warehouses: "QuerySet"
):
    try:
        Stock.objects.bulk_create(
            [
                Stock(
                    product_variant=variant,
                    warehouse=warehouse,
                    quantity=stock_data["quantity"],
                )
                for stock_data, warehouse in zip(stocks_data, warehouses)
            ]
        )
    except IntegrityError:
        msg = "Stock for one of warehouses already exists for this product variant."
        raise ValidationError(msg)


def can_exclude_distinct(parameters):
    join_filters = ['collections', 'attributes', 'stock_availability', 'allegro_status',
                    'price', 'stock_availability']
    join_sort_by = 'min_variants_price_amount'

    for filter in join_filters:
        if parameters.get('filter').get(filter):
            return False

    try:
        sort_by_fields = parameters['sort_by']['field']
        if join_sort_by in sort_by_fields:
            return False
    except (KeyError, TypeError):
        return True

    return True


def create_collage(images, product):
    s3 = boto3.resource('s3')
    bucket_name = os.environ.get("AWS_MEDIA_BUCKET_NAME")
    bucket = s3.Bucket(bucket_name)

    if len(images) == 12:
        images_amount = 12
        cols = 3
        rows = 4
    elif len(images) > 8 and len(images) < 12:
        images_amount = 9
        cols = 3
        rows = 3
    elif len(images) % 2 != 0:
        images_amount = len(images) - 1
    else:
        images_amount = len(images)

    images = images[:images_amount]

    if images_amount < 9:
        cols = 2
        rows = int(images_amount / 2)

    i = 0

    width = 318 * cols
    height = 336 * rows
    collage = Image.new("RGBA", (width, height), color=(255, 255, 255, 255))

    for x in range(0, width, int(width / cols)):
        for y in range(0, height, int(height / rows)):
            img_component = bucket.Object(images[i].image.name)
            img_data = img_component.get().get('Body').read()
            image = Image.open(BytesIO(img_data))

            resized_image = image.resize((width, int(image.size[1] * (width / image.size[0]))))
            required_loss = (resized_image.size[1] - width)
            resized_image = resized_image.crop(
                box=(0, required_loss / 2, width,
                     resized_image.size[1] - required_loss / 2))

            resized_image = resized_image.resize((int(width/cols), int(height/rows)))
            collage.paste(resized_image, (x, y))
            i += 1

    collage_io = BytesIO()
    collage.save(collage_io, format='PNG')
    # Save new collage image to db
    rand_int = random.randint(1000000, 9999999)
    photo_name = f'{product.name}x{rand_int}.png'
    photo_alt = product.name.upper()
    ppoi = images[0].ppoi
    new_image = ProductImage.objects.create(product=product, ppoi=ppoi, alt=photo_alt, image='')
    new_image.image.save(photo_name, collage_io)
    # Swap sort order
    last_photo_sort_order = new_image.sort_order
    first_photo = ProductImage.objects.filter(product=product.pk).order_by('sort_order').first()
    first_photo.sort_order = last_photo_sort_order
    first_photo.save()
    new_image.sort_order = 0
    new_image.save()
    # Create thumbnails
    create_product_thumbnails.delay(new_image.pk)


def create_warehouse_locations_matrix(warehouse_from, warehouse_to):
    warehouse_to = warehouse_to.strip()
    warehouse_from = warehouse_from.strip()
    warehouse_from_location = re.findall(r'\d+', warehouse_from)
    warehouse_to_location = re.findall(r'\d+', warehouse_to)
    warehouse_locations = [[]]
    if len(warehouse_from_location) == 2 and len(warehouse_to_location) == 2 and (warehouse_from[0].upper() == warehouse_to[0].upper()):
        rows_numbers = range(int(warehouse_from_location[0]), int(warehouse_to_location[0]) + 1)
        columns_numbers = range(int(warehouse_from_location[1]), int(warehouse_to_location[1]) + 1)
        row_leading_zeros = count_leading_zeros(warehouse_from_location[0]) * '0'
        column_leading_zeros = count_leading_zeros(warehouse_from_location[1]) * '0'
        row_numbers_list = []
        column_numbers_list = []
        first_letter = warehouse_from[1].upper()
        for row_number in rows_numbers:
            number_str = str(row_number)
            row_numbers_list.append(f'{row_leading_zeros}{number_str}')
        for column_number in columns_numbers:
            number_str = str(column_number)
            column_numbers_list.append(f'{column_leading_zeros}{number_str}')
        warehouse_locations = [[f'#{first_letter}{x}K{y}' for y in column_numbers_list] for x in row_numbers_list]
    flatten_locations = [value for row in warehouse_locations for value in row]

    return flatten_locations

def count_leading_zeros(input):
    for i, char in enumerate(input):
        if char != '0':
            return i
    return len(input)

def generate_key_id():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))


def generate_description_json_for_megapack(bundle_content):
    description_json = {}
    blocks = []
    description_values = {"key": generate_key_id(), "data": {},
                          "text": "Zawartość megapaki: ", "type": "header-two",
                          'depth': 0, 'entityRanges': [], 'inlineStyleRanges': []}
    blocks.append(description_values)
    products_amount = 0
    products_weight = 0
    if bundle_content:
        for section in bundle_content:
            list_fragment = {"key": generate_key_id(), "data": {},
                            "type": "unordered-list-item",
                            'depth': 0, 'entityRanges': [], 'inlineStyleRanges': []}
            if section[0] == "Mężczyzna":
                list_fragment["text"] = f'  ubrania męskie: {section[1]} szt., {section[2]} kg'
            elif section[0] == "Dziecko":
                list_fragment["text"] = f'  ubrania dziecięce: {section[1]} szt., {section[2]} kg'
            else:
                list_fragment["text"] = f'  ubrania damskie: {section[1]} szt., {section[2]} kg'

            products_amount += section[1]
            products_weight += section[2]
            blocks.append(list_fragment)

    list_fragment = {"key": generate_key_id(), "data": {}, "type": "unordered-list-item",
                     'depth': 0, 'entityRanges': [], 'inlineStyleRanges': []}
    list_fragment["text"] = f'  razem: {products_amount} szt., {round(products_weight, 2)} kg'
    blocks.append(list_fragment)

    description_json["blocks"] = blocks
    description_json["entityMap"] = {}
    return description_json
