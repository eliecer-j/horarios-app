from django.db import migrations, models
import django.db.models


def copy_existing_vacations(apps, schema_editor):
    Person = apps.get_model("schedule", "Person")
    VacationPeriod = apps.get_model("schedule", "VacationPeriod")
    database = schema_editor.connection.alias
    for person in Person.objects.using(database).all().iterator():
        if person.vacation_start and person.vacation_end:
            VacationPeriod.objects.using(database).get_or_create(
                person_id=person.pk,
                start_date=person.vacation_start,
                end_date=person.vacation_end,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("schedule", "0005_create_legacy_schedule_tables"),
    ]

    operations = [
        migrations.CreateModel(
            name="VacationPeriod",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("person_id", models.IntegerField()),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
            ],
            options={
                "db_table": "vacation_periods",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("person_id", "start_date", "end_date"),
                        name="unique_person_vacation_period",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("end_date__gte", django.db.models.F("start_date"))),
                        name="vacation_period_date_order",
                    ),
                ],
            },
        ),
        migrations.RunPython(copy_existing_vacations, migrations.RunPython.noop),
    ]
