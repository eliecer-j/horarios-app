from datetime import date, timedelta

from django.db import connection, transaction

from .models import Person


def monday_of(day):
    return day - timedelta(days=day.weekday())


def week_assignments(week_start):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT person_id, day, branch_id, start_time, end_time "
            "FROM assignments WHERE week_start = %s",
            [week_start.isoformat()],
        )
        return {
            (person_id, day): {
                "branch_id": branch_id,
                "start_time": start_time,
                "end_time": end_time,
            }
            for person_id, day, branch_id, start_time, end_time in cursor.fetchall()
        }


def available_weeks():
    with connection.cursor() as cursor:
        cursor.execute("SELECT DISTINCT week_start FROM assignments ORDER BY week_start")
        return [date.fromisoformat(row[0]) for row in cursor.fetchall()]


def is_on_vacation(person, assigned_date):
    return bool(
        person.vacation_start
        and person.vacation_end
        and person.vacation_start <= assigned_date <= person.vacation_end
    )


def save_assignment(week_start, person_id, day, form):
    assigned_date = week_start + timedelta(days=day)
    person = Person.objects.get(pk=person_id)
    if is_on_vacation(person, assigned_date):
        raise ValueError("No se pueden asignar turnos durante las vacaciones.")

    status = form.cleaned_data["status"]
    if status == "unassigned":
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM assignments WHERE week_start = %s AND person_id = %s AND day = %s",
                [week_start.isoformat(), person_id, day],
            )
        return

    if status == "rest":
        branch_id, start_time, end_time = None, None, None
    else:
        branch_id = form.cleaned_data["branch"].pk
        start_time = form.cleaned_data["start_time"]
        end_time = form.cleaned_data["end_time"]
        if start_time == end_time:
            raise ValueError("La hora de inicio y la hora de fin no pueden ser iguales.")

    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            "INSERT OR REPLACE INTO assignments "
            "(week_start, person_id, day, branch_id, start_time, end_time) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            [week_start.isoformat(), person_id, day, branch_id, start_time, end_time],
        )


def assignments_between(start_date, end_date):
    earliest_week = (start_date - timedelta(days=6)).isoformat()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT week_start, person_id, day, branch_id, start_time, end_time "
            "FROM assignments WHERE week_start BETWEEN %s AND %s "
            "ORDER BY week_start, day, person_id",
            [earliest_week, end_date.isoformat()],
        )
        rows = cursor.fetchall()
    assignments = []
    for week_start, person_id, day, branch_id, start_time, end_time in rows:
        assigned_date = date.fromisoformat(week_start) + timedelta(days=day)
        if start_date <= assigned_date <= end_date:
            assignments.append((assigned_date, person_id, branch_id, start_time, end_time))
    return assignments


def clear_week(week_start):
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM assignments WHERE week_start = %s", [week_start.isoformat()])


def remove_vacation_assignments(person, start, end):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT week_start, day FROM assignments WHERE person_id = %s",
            [person.pk],
        )
        rows = cursor.fetchall()
        remove_keys = []
        for week_start, day in rows:
            assigned_date = date.fromisoformat(week_start) + timedelta(days=day)
            if start <= assigned_date <= end:
                remove_keys.append((week_start, person.pk, day))
        cursor.executemany(
            "DELETE FROM assignments WHERE week_start = %s AND person_id = %s AND day = %s",
            remove_keys,
        )
    return len(remove_keys)


def person_display_name(person, duplicate_names=None):
    if duplicate_names is None:
        duplicate_names = name_counts(Person.objects.all())
    if duplicate_names.get(person.name.strip().lower(), 0) > 1:
        return f"{person.name} · DNI {person.dni}" if person.dni else f"{person.name} · sin DNI"
    return person.name


def name_counts(people):
    counts = {}
    for person in people:
        key = person.name.strip().lower()
        counts[key] = counts.get(key, 0) + 1
    return counts


def delete_person(person):
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM assignments WHERE person_id = %s", [person.pk])
        person.delete()


def delete_branch(branch):
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM assignments WHERE branch_id = %s", [branch.pk])
        branch.delete()
