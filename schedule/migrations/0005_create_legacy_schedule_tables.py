from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("schedule", "0004_archive_assignment_novelties"),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "CREATE TABLE IF NOT EXISTS people ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "name VARCHAR(200) NOT NULL, "
                "dni VARCHAR(100) NULL, "
                "vacation_start TEXT NULL, "
                "vacation_end TEXT NULL"
                ")",
                "CREATE TABLE IF NOT EXISTS branches ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "name VARCHAR(200) NOT NULL UNIQUE, "
                "color VARCHAR(7) NOT NULL"
                ")",
                "CREATE TABLE IF NOT EXISTS assignments ("
                "week_start TEXT NOT NULL, "
                "person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE, "
                "day INTEGER NOT NULL CHECK (day BETWEEN 0 AND 6), "
                "branch_id INTEGER REFERENCES branches(id) ON DELETE CASCADE, "
                "start_time TEXT NULL, "
                "end_time TEXT NULL, "
                "PRIMARY KEY (week_start, person_id, day), "
                "CHECK ((start_time IS NULL AND end_time IS NULL AND branch_id IS NULL) "
                "OR (start_time IS NOT NULL AND end_time IS NOT NULL AND branch_id IS NOT NULL))"
                ")",
            ],
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
