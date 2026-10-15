from django.db import migrations


def add_split_shift_times(apps, schema_editor):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        columns = {
            column.name
            for column in connection.introspection.get_table_description(
                cursor, "assignments"
            )
        }
    for column in ("start_time_2", "end_time_2"):
        if column not in columns:
            schema_editor.execute(
                f"ALTER TABLE assignments ADD COLUMN {column} TEXT NULL"
            )


class Migration(migrations.Migration):

    dependencies = [
        ("schedule", "0008_assignment_type"),
    ]

    operations = [
        migrations.RunPython(add_split_shift_times, migrations.RunPython.noop),
    ]
