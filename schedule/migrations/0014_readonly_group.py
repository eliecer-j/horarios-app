from django.db import migrations

READONLY_GROUP = "Solo lectura"


def create_readonly_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name=READONLY_GROUP)


class Migration(migrations.Migration):

    dependencies = [
        ("schedule", "0013_branch_is_active"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_readonly_group, migrations.RunPython.noop),
    ]
