from django.db import migrations


def add_assignment_type(apps, schema_editor):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        columns = {
            column.name
            for column in connection.introspection.get_table_description(
                cursor, "assignments"
            )
        }
    if "assignment_type" not in columns:
        schema_editor.execute(
            "ALTER TABLE assignments ADD COLUMN assignment_type "
            "VARCHAR(16) NOT NULL DEFAULT 'rest'"
        )
    schema_editor.execute(
        "UPDATE assignments SET assignment_type = 'work' "
        "WHERE branch_id IS NOT NULL"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("schedule", "0007_auditlog"),
    ]

    operations = [
        migrations.RunPython(add_assignment_type, migrations.RunPython.noop),
    ]
