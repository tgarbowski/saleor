from django.db import migrations
from ..utils import read_sql_from_file


class Migration(migrations.Migration):
    dependencies = [
        ("salingo", "0003_update_description_json")
    ]

    operations = [
        migrations.RunSQL(read_sql_from_file("top_parent.sql")),
        migrations.RunSQL(read_sql_from_file("generate_bundle_content.sql"))
    ]
