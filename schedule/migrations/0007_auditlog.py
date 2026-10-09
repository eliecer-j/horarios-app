from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schedule", "0006_vacation_periods"),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("action", models.CharField(max_length=120)),
                ("details", models.TextField(blank=True)),
            ],
            options={
                "db_table": "audit_logs",
                "ordering": ("-created_at", "-pk"),
            },
        ),
    ]
