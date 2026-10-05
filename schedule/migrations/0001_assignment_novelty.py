from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="AssignmentNovelty",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("week_start", models.DateField()),
                ("person_id", models.IntegerField()),
                ("day", models.PositiveSmallIntegerField()),
                (
                    "kind",
                    models.CharField(
                        choices=[("late_arrival", "Llegada tarde")],
                        default="late_arrival",
                        max_length=24,
                    ),
                ),
                ("actual_start_time", models.TimeField()),
            ],
            options={
                "db_table": "assignment_novelties",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("week_start", "person_id", "day"),
                        name="unique_assignment_novelty",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("day__gte", 0), ("day__lte", 6)),
                        name="assignment_novelty_day_range",
                    ),
                ],
            },
        ),
    ]
