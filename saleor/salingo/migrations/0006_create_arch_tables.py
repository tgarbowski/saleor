from django.db import migrations

from ..utils import read_sql_from_file


class Migration(migrations.Migration):

    dependencies = [
        ('salingo', '0005_update_child_age_parameter'),
    ]

    operations = [
        migrations.RunSQL(read_sql_from_file("create_arch_tables.sql"))
    ]
