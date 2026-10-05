from datetime import date, timedelta
from io import BytesIO

from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse
from openpyxl import load_workbook

from .forms import AssignmentForm, LateArrivalForm
from .metrics import shift_metrics
from .models import AssignmentNovelty, Branch, Person
from .services import assignments_between, monday_of
from .templatetags.schedule_tags import capitalize


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
        self.assertContains(response, "schedule-grid-scroll")
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

    def test_novelties_requires_the_analysis_session(self):
        response = self.client.get(
            reverse("novelties_week", args=[self.week_start.isoformat()])
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            f"{reverse('analysis_unlock')}?next=%2Fnovedades%2F{self.week_start.isoformat()}%2F",
        )

    @override_settings(ANALYSIS_PASSWORD="test-password")
    def test_unlock_returns_to_requested_novelties_grid(self):
        target = reverse("novelties_week", args=[self.week_start.isoformat()])
        response = self.client.get(target)
        unlock_url = response["Location"]

        unlock_page = self.client.get(unlock_url)
        self.assertEqual(unlock_page.status_code, 200)
        self.assertContains(unlock_page, f'name="next" value="{target}"', html=False)

        response = self.client.post(
            unlock_url,
            {"password": "test-password", "next": target},
        )
        self.assertRedirects(response, target, fetch_redirect_response=False)
        grid = self.client.get(target)
        self.assertEqual(grid.status_code, 200)
        self.assertContains(grid, "schedule-grid-scroll")

    @override_settings(ANALYSIS_PASSWORD="test-password")
    def test_htmx_login_requests_full_page_reload_to_novelties(self):
        target = reverse("novelties_week", args=[self.week_start.isoformat()])
        unlock_url = f"{reverse('analysis_unlock')}?next=%2Fnovedades%2F{self.week_start.isoformat()}%2F"

        response = self.client.post(
            unlock_url,
            {"password": "test-password", "next": target},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Redirect"], target)

    def test_novelties_menu_renders_grid_without_redirect(self):
        session = self.client.session
        session["analysis_authenticated"] = True
        session.save()

        response = self.client.get(reverse("novelties"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "schedule-grid-scroll")
        self.assertContains(response, "Novedades")
        self.assertContains(response, "schedule-main-shell")

    def test_late_arrival_is_included_in_analysis_hours(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO assignments VALUES (%s, %s, 0, %s, '08:00', '16:00')",
                [self.week_start.isoformat(), self.person.pk, self.branch.pk],
            )
        session = self.client.session
        session["analysis_authenticated"] = True
        session.save()

        page = self.client.get(
            reverse("novelties_week", args=[self.week_start.isoformat()]),
            {"edit": f"{self.person.pk}-0"},
        )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Novedades")
        self.assertContains(page, "Llegada tarde")
        self.assertContains(page, "No se presentó")
        self.assertContains(page, "Calamidad")
        self.assertContains(page, 'data-novelty-kind-select', html=False)
        self.assertContains(page, 'type="text"', html=False)
        self.assertContains(page, 'placeholder="00:00"', html=False)
        self.assertContains(page, 'pattern="(?:[01]\\d|2[0-3]):[0-5]\\d"', html=False)
        self.assertContains(page, "Observación (opcional)")

        response = self.client.post(
            reverse(
                "novelty_save",
                args=[self.week_start.isoformat(), self.person.pk, 0],
            ),
            {"kind": AssignmentNovelty.LATE_ARRIVAL, "actual_start_time": "09:30"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "+ Llegada tarde")
        novelty = AssignmentNovelty.objects.get(
            week_start=self.week_start, person_id=self.person.pk, day=0
        )
        self.assertEqual(novelty.actual_start_time.strftime("%H:%M"), "09:30")
        assignments = assignments_between(self.week_start, self.week_start)
        self.assertEqual(assignments[0][5], "09:30")

        month = self.week_start.strftime("%Y-%m")
        fortnight = "1" if self.week_start.day <= 15 else "2"
        analysis = self.client.get(
            reverse("analysis"),
            {"month": month, "fortnight": fortnight},
        )
        self.assertEqual(analysis.status_code, 200)
        self.assertEqual(analysis.context["totals"]["worked"], 6.5)

        workbook_response = self.client.get(
            reverse("analysis_export"),
            {"month": month, "fortnight": fortnight},
        )
        workbook = load_workbook(BytesIO(workbook_response.content), read_only=True)
        self.assertEqual(workbook.active["C4"].value, 6.5)
        self.assertEqual(workbook.active["D8"].value, "09:30")

    def test_absence_and_calamity_do_not_add_worked_hours(self):
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO assignments VALUES (%s, %s, %s, %s, '08:00', '16:00')",
                [
                    (self.week_start.isoformat(), self.person.pk, day, self.branch.pk)
                    for day in (0, 1)
                ],
            )
        session = self.client.session
        session["analysis_authenticated"] = True
        session.save()

        for day, kind, observation, badge in (
            (0, AssignmentNovelty.DID_NOT_ATTEND, "No avisó", "+ No se presentó"),
            (1, AssignmentNovelty.CALAMITY, "Emergencia familiar", "+ Calamidad"),
        ):
            with self.subTest(kind=kind):
                response = self.client.post(
                    reverse(
                        "novelty_save",
                        args=[self.week_start.isoformat(), self.person.pk, day],
                    ),
                    {"kind": kind, "observation": observation},
                    HTTP_HX_REQUEST="true",
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, badge)
                self.assertContains(response, observation)

                novelty = AssignmentNovelty.objects.get(
                    week_start=self.week_start, person_id=self.person.pk, day=day
                )
                self.assertIsNone(novelty.actual_start_time)
                self.assertEqual(novelty.observation, observation)

        assignments = assignments_between(self.week_start, self.week_start + timedelta(days=1))
        self.assertEqual(assignments[0][5:7], (None, AssignmentNovelty.DID_NOT_ATTEND))
        self.assertEqual(assignments[1][5:7], (None, AssignmentNovelty.CALAMITY))

        month = self.week_start.strftime("%Y-%m")
        fortnight = "1" if self.week_start.day <= 15 else "2"
        analysis = self.client.get(
            reverse("analysis"),
            {"month": month, "fortnight": fortnight},
        )
        metric = analysis.context["summaries"][self.person.pk]
        self.assertEqual(metric["days"], 0)
        self.assertEqual(metric["worked"], 0)

        workbook_response = self.client.get(
            reverse("analysis_export"),
            {"month": month, "fortnight": fortnight},
        )
        workbook = load_workbook(BytesIO(workbook_response.content), read_only=True)
        self.assertEqual(workbook.active["C3"].value, 0)
        self.assertEqual(workbook.active["F8"].value, 0)
        self.assertEqual(workbook.active["F9"].value, 0)
        self.assertIn("No se presentó", workbook.active["C8"].value)
        self.assertIn("Calamidad", workbook.active["C9"].value)
        self.assertEqual(workbook.active["G8"].value, "No avisó")
        self.assertEqual(workbook.active["G9"].value, "Emergencia familiar")

    def test_changing_shift_times_removes_outdated_novelty(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO assignments VALUES (%s, %s, 0, %s, '08:00', '16:00')",
                [self.week_start.isoformat(), self.person.pk, self.branch.pk],
            )
        AssignmentNovelty.objects.create(
            week_start=self.week_start,
            person_id=self.person.pk,
            day=0,
            actual_start_time="09:30",
        )

        response = self.client.post(
            reverse(
                "assignment_save",
                args=[self.week_start.isoformat(), self.person.pk, 0],
            ),
            {
                "status": "work",
                "branch": self.branch.pk,
                "start_time": "09:00",
                "end_time": "17:00",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(AssignmentNovelty.objects.exists())

    def test_selecting_no_novelty_removes_existing_record_only(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO assignments VALUES (%s, %s, 0, %s, '08:00', '16:00')",
                [self.week_start.isoformat(), self.person.pk, self.branch.pk],
            )
        AssignmentNovelty.objects.create(
            week_start=self.week_start,
            person_id=self.person.pk,
            day=0,
            kind=AssignmentNovelty.CALAMITY,
            observation="Registro equivocado",
        )
        session = self.client.session
        session["analysis_authenticated"] = True
        session.save()

        response = self.client.post(
            reverse(
                "novelty_save",
                args=[self.week_start.isoformat(), self.person.pk, 0],
            ),
            {"kind": "", "actual_start_time": "", "observation": ""},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Novedad eliminada.")
        self.assertNotContains(response, "+ Calamidad")
        self.assertFalse(AssignmentNovelty.objects.exists())
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT branch_id, start_time, end_time FROM assignments "
                "WHERE week_start = %s AND person_id = %s AND day = 0",
                [self.week_start.isoformat(), self.person.pk],
            )
            self.assertEqual(cursor.fetchone(), (self.branch.pk, "08:00", "16:00"))

    def test_novelty_time_must_fall_after_shift_start(self):
        no_attendance_form = LateArrivalForm(
            data={
                "kind": AssignmentNovelty.DID_NOT_ATTEND,
                "actual_start_time": "",
                "observation": "No avisó",
            },
            start_time="08:00",
            end_time="16:00",
        )
        self.assertTrue(no_attendance_form.is_valid(), no_attendance_form.errors)

        invalid_format_form = LateArrivalForm(
            data={"kind": AssignmentNovelty.LATE_ARRIVAL, "actual_start_time": "9:30"},
            start_time="08:00",
            end_time="16:00",
        )
        self.assertFalse(invalid_format_form.is_valid())
        self.assertEqual(
            invalid_format_form.errors["actual_start_time"],
            ["Usa formato HH:MM, por ejemplo 09:30."],
        )

        form = LateArrivalForm(
            data={"kind": AssignmentNovelty.LATE_ARRIVAL, "actual_start_time": "07:30"},
            start_time="08:00",
            end_time="16:00",
        )
        self.assertFalse(form.is_valid())
        self.assertIn("posterior al inicio del turno", form.errors["actual_start_time"][0])

        overnight_form = LateArrivalForm(
            data={"kind": AssignmentNovelty.LATE_ARRIVAL, "actual_start_time": "00:30"},
            start_time="22:00",
            end_time="06:00",
        )
        self.assertTrue(overnight_form.is_valid())

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

    def test_capitalize_person_name_and_keep_dni_acronym(self):
        self.assertEqual(capitalize("ANA TORRES"), "Ana Torres")
        self.assertEqual(capitalize("ANA TORRES · DNI 123"), "Ana Torres · DNI 123")
