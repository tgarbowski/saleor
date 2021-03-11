# Generated by Django 3.1.2 on 2021-03-11 13:06

from django.db import migrations
from saleor.salingo.utils import get_sql_function_by_file_name

class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.RunSQL(get_sql_function_by_file_name('sku_to_date.sql', 'sku_to_date(text)'))
    ]
