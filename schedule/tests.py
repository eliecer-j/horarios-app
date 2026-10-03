from datetime import date

from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import AssignmentForm
from .metrics import shift_metrics
from .models import Branch, Person
from .services import monday_of


class LegacyDatabaseViewsTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with connection.cursor() as cursor:
            cursor.execute(
                "CREATE TABLE people ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, dni TEXT, "
                "vacation_start TEXT, vacation_end TEXT)"
            )
            cursor.execute(
                "CREATE TABLE branches ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, color TEXT NOT NULL)"
            )
            cursor.execute(
                "CREATE TABLE assignments ("
                "week_start TEXT NOT NULL, person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE, "
                "day INTEGER NOT NULL CHECK (day BETWEEN 0 AND 6), "
                "branch_id INTEGER REFERENCES branches(id) ON DELETE CASCADE, "
                "start_time TEXT, end_time TEXT, PRIMARY KEY (week_start, person_id, day), "
                "CHECK ((start_time IS NULL AND end_time IS NULL AND branch_id IS NULL) "
                "OR (start_time IS NOT NULL AND end_time IS NOT NULL AND branch_id IS NOT NULL)))"
            )

    @classmethod
    def tearDownClass(cls):
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE assignments")
            cursor.execute("DROP TABLE branches")
            cursor.execute("DROP TABLE people")
        super().tearDownClass()

    def setUp(self):
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM assignments")
            cursor.execute("DELETE FROM branches")
            cursor.execute("DELETE FROM people")
        self.person = Person.objects.create(name="Ana Torres")
        self.branch = Branch.objects.create(name="Centro", color="#2F6FED")
        self.week_start = monday_of(date.today())

    def test_schedule_page_renders_legacy_data(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO assignments VALUES (%s, %s, 0, %s, '08:00', '16:00')",
                [self.week_start.isoformat(), self.person.pk, self.branch.pk],
            )
        response = self.client.get(reverse("schedule", args=[self.week_start.isoformat()]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ana Torres")
        self.assertContains(response, "Centro")
        self.assertLess(
            response.content.index(b">Dom<span>"),
            response.content.index(b'class="rest-count-column">Descansos</th>'),
        )

    def test_rest_assignment_is_saved(self):
        response = self.client.post(
            reverse("assignment_save", args=[self.week_start.isoformat(), self.person.pk, 0]),
            {"status": "rest"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT branch_id, start_time, end_time FROM assignments "
                "WHERE week_start = %s AND person_id = %s AND day = 0",
                [self.week_start.isoformat(), self.person.pk],
            )
            self.assertEqual(cursor.fetchone(), (None, None, None))

    def test_people_page_uses_legacy_table(self):
        response = self.client.get(reverse("people"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ana Torres")

    def test_edit_person_form_loads_saved_vacation_dates(self):
        self.person.vacation_start = date(2026, 10, 12)
        self.person.vacation_end = date(2026, 10, 19)
        self.person.save()

        response = self.client.get(reverse("people"), {"edit": self.person.pk})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="person-form-card"', html=False)
        self.assertContains(response, 'name="vacation_start" value="2026-10-12"', html=False)
        self.assertContains(response, 'name="vacation_end" value="2026-10-19"', html=False)

    def test_branches_page_uses_legacy_table(self):
        response = self.client.get(reverse("branches"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Centro")

    def test_assignment_editor_renders(self):
        response = self.client.get(
            reverse("schedule", args=[self.week_start.isoformat()]),
            {"edit": f"{self.person.pk}-0"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Guardar turno")
        self.assertEqual(response.context["edit_form"]["status"].value(), "work")
        self.assertEqual(response.context["edit_form"]["branch"].value(), self.branch.pk)
        self.assertContains(response, '<dialog id="assignment-dialog"', html=False)
        self.assertContains(response, 'placeholder="12:00"', html=False)
        self.assertContains(response, 'placeholder="17:00"', html=False)

    def test_assignment_form_accepts_only_24_hour_hhmm(self):
        valid_form = AssignmentForm(data={
            "status": "work",
            "branch": self.branch.pk,
            "start_time": "12:00",
            "end_time": "17:00",
        })
        self.assertTrue(valid_form.is_valid())

        invalid_form = AssignmentForm(data={
            "status": "work",
            "branch": self.branch.pk,
            "start_time": "1:00",
            "end_time": "17:00",
        })
        self.assertFalse(invalid_form.is_valid())
        self.assertIn("Usa formato HH:MM.", invalid_form.errors["start_time"])

    @override_settings(ANALYSIS_PASSWORD="test-password")
    def test_analysis_page_renders_after_unlock(self):
        session = self.client.session
        session["analysis_authenticated"] = True
        session.save()
        response = self.client.get(
            reverse("analysis"),
            {"month": self.week_start.strftime("%Y-%m"), "fortnight": "1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Horas trabajadas")

    def test_schedule_export_downloads_excel(self):
        response = self.client.get(
            reverse("schedule_export"),
            {"start": self.week_start.isoformat(), "end": self.week_start.isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_overnight_shift_metrics(self):
        self.assertEqual(shift_metrics("22:00", "06:00"), (8.0, 0.0, 0.0, 0.0))


class WeekDateTests(TestCase):
    def test_monday_of_week(self):
        self.assertEqual(monday_of(date(2026, 10, 3)), date(2026, 9, 28))
