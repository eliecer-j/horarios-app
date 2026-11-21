from django.db import migrations, models


def add_is_active(apps, schema_editor):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        columns = {
            column.name
            for column in connection.introspection.get_table_description(
                cursor, "branches"
            )
        }
    if "is_active" not in columns:
        schema_editor.execute(
            "ALTER TABLE branches ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("schedule", "0012_auditlog_user"),
    ]

    operations = [
        migrations.AddField(
            model_name="branch",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(add_is_active, migrations.RunPython.noop),
    ]
