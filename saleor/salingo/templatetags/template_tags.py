from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def comma_separator(value: Decimal) -> str:
    """Represents decimal value as string with comma separator"""
    return str(value).replace(".", ",")
