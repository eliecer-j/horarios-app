from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schedule", "0009_split_shift_times"),
    ]

    operations = [
        migrations.AddField(
            model_name="assignmentnovelty",
            name="actual_start_time_2",
            field=models.TimeField(blank=True, null=True),
        ),
    ]
