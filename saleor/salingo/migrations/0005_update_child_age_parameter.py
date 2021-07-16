# Generated by Django 3.1.2 on 2021-06-24 15:42

from django.db import migrations

from ..utils import read_sql_from_file


class Migration(migrations.Migration):

    dependencies = [
        ('salingo', '0004_generate_bundle_content'),
    ]

    operations = [
        migrations.RunSQL(read_sql_from_file("update_child_age_parameter.sql"))
    ]
