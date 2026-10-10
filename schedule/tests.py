from datetime import date, timedelta
from io import BytesIO

from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone
from django.urls import reverse
from openpyxl import load_workbook

from .exports import fortnight_workbook
from .forms import AssignmentForm, LateArrivalForm
from .metrics import assignment_period_metrics, shift_metrics, summarize_period
from .models import AssignmentNovelty, AuditLog, Branch, Person, VacationPeriod
from .services import assignments_between, clear_week, delete_branch, monday_of, week_assignments
from .templatetags.schedule_tags import capitalize


class LegacyDatabaseViewsTests(TestCase):
    def setUp(self):
        VacationPeriod.objects.all().delete()
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
                "INSERT INTO assignments (week_start, person_id, day, branch_id, start_time, end_time, assignment_type) "
                "VALUES (%s, %s, 0, %s, '08:00', '16:00', 'work')",
                [self.week_start.isoformat(), self.person.pk, self.branch.pk],
            )
        response = self.client.get(reverse("schedule", args=[self.week_start.isoformat()]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ana Torres")
        self.assertContains(response, "Centro")
        self.assertContains(response, "schedule-grid-scroll")
        self.assertContains(response, 'title="Ana Torres"', html=False)
        self.assertLess(
            response.content.index(b">Dom<span>"),
            response.content.index(b'class="rest-count-column">Descansos</th>'),
        )

    def test_completed_vacation_days_remain_marked_in_past_week(self):
        week_start = monday_of(date(2020, 1, 6))
        self.person.vacation_start = date(2020, 1, 7)
        self.person.vacation_end = date(2020, 1, 8)
        self.person.save()

        response = self.client.get(
            reverse("schedule", args=[week_start.isoformat()])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.content.count(b'class="shift-cell vacation-cell">Vacaciones</span>'),
            2,
        )

    def test_new_vacation_period_preserves_previous_vacation_cells(self):
        first_start = date(2020, 1, 7)
        first_end = date(2020, 1, 8)
        second_start = date(2020, 2, 4)
        second_end = date(2020, 2, 5)
        self.person.vacation_start = first_start
        self.person.vacation_end = first_end
        self.person.save()

        response = self.client.post(
            reverse("people"),
            {
                "person_id": self.person.pk,
                "name": self.person.name,
                "dni": "",
                "vacation_start": second_start.isoformat(),
                "vacation_end": second_end.isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(
                VacationPeriod.objects.filter(person_id=self.person.pk).values_list(
                    "start_date", "end_date"
                )
            ),
            {(first_start, first_end), (second_start, second_end)},
        )
        for vacation_start in (first_start, second_start):
            week_start = monday_of(vacation_start)
            schedule_response = self.client.get(
                reverse("schedule", args=[week_start.isoformat()])
            )
            self.assertEqual(schedule_response.status_code, 200)
            self.assertEqual(
                schedule_response.content.count(
                    b'class="shift-cell vacation-cell">Vacaciones</span>'
                ),
                2,
            )

    def test_vacation_period_can_be_deleted_without_removing_other_periods(self):
        first_start = date(2020, 1, 7)
        first_end = date(2020, 1, 8)
        second_start = date(2020, 2, 4)
        second_end = date(2020, 2, 5)
        first_period = VacationPeriod.objects.create(
            person_id=self.person.pk,
            start_date=first_start,
            end_date=first_end,
        )
        second_period = VacationPeriod.objects.create(
            person_id=self.person.pk,
            start_date=second_start,
            end_date=second_end,
        )
        self.person.vacation_start = second_start
        self.person.vacation_end = second_end
        self.person.save()

        response = self.client.post(
            reverse(
                "vacation_period_delete",
                args=[self.person.pk, second_period.pk],
            ),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(VacationPeriod.objects.filter(pk=first_period.pk).exists())
        self.assertFalse(VacationPeriod.objects.filter(pk=second_period.pk).exists())
        self.person.refresh_from_db()
        self.assertIsNone(self.person.vacation_start)
        self.assertIsNone(self.person.vacation_end)

        first_week = monday_of(first_start)
        response = self.client.get(
            reverse("schedule", args=[first_week.isoformat()])
        )
        self.assertEqual(
            response.content.count(
                b'class="shift-cell vacation-cell">Vacaciones</span>'
            ),
            2,
        )
        second_week = monday_of(second_start)
        response = self.client.get(
            reverse("schedule", args=[second_week.isoformat()])
        )
        self.assertEqual(
            response.content.count(
                b'class="shift-cell vacation-cell">Vacaciones</span>'
            ),
            0,
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

    def test_incapacity_is_saved_displayed_and_counts_zero_worked_hours(self):
        response = self.client.post(
            reverse("assignment_save", args=[self.week_start.isoformat(), self.person.pk, 0]),
            {"status": "incapacity"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Incapacidad")
        assignment = week_assignments(self.week_start)[(self.person.pk, 0)]
        self.assertEqual(assignment["assignment_type"], "incapacity")
        self.assertIsNone(assignment["branch_id"])
        self.assertIsNone(assignment["start_time"])
        self.assertIsNone(assignment["end_time"])
        assignments = assignments_between(self.week_start, self.week_start)
        self.assertEqual(assignments[0][8], "incapacity")
        daily_metrics = assignment_period_metrics([self.person], assignments)
        summaries, _ = summarize_period([self.person], assignments, daily_metrics)
        self.assertEqual(daily_metrics, {})
        self.assertEqual(summaries[self.person.pk]["worked"], 0)
        workbook = load_workbook(
            BytesIO(fortnight_workbook(self.week_start, self.week_start, [self.person])),
            read_only=True,
        )
        self.assertEqual(workbook.active["C8"].value, "Incapacidad")
        self.assertEqual(workbook.active["F8"].value, 0)

        edit_response = self.client.get(
            reverse("schedule", args=[self.week_start.isoformat()]),
            {"edit": f"{self.person.pk}-0"},
        )
        self.assertEqual(edit_response.context["edit_form"]["status"].value(), "incapacity")

    def test_assignment_change_is_logged_with_ip_and_visible_in_logs(self):
        response = self.client.post(
            reverse("assignment_save", args=[self.week_start.isoformat(), self.person.pk, 0]),
            {
                "status": "work",
                "branch": self.branch.pk,
                "start_time": "08:00",
                "end_time": "16:00",
            },
            REMOTE_ADDR="203.0.113.7",
        )

        self.assertEqual(response.status_code, 200)
        entry = AuditLog.objects.get()
        self.assertEqual(entry.ip_address, "203.0.113.7")
        self.assertEqual(entry.action, "Turno guardado")
        self.assertIn("Ana Torres", entry.details)
        self.assertIn("Centro", entry.details)

        session = self.client.session
        session["analysis_authenticated"] = True
        session.save()
        logs_response = self.client.get(reverse("logs"))
        self.assertEqual(logs_response.status_code, 200)
        self.assertContains(logs_response, "203.0.113.7")
        self.assertContains(logs_response, "Turno guardado")

    def test_assignment_update_logs_previous_and_new_shift(self):
        assignment_url = reverse(
            "assignment_save",
            args=[self.week_start.isoformat(), self.person.pk, 0],
        )
        initial_response = self.client.post(
            assignment_url,
            {
                "status": "work",
                "branch": self.branch.pk,
                "start_time": "08:00",
                "end_time": "16:00",
            },
        )
        self.assertEqual(initial_response.status_code, 200)

        updated_response = self.client.post(
            assignment_url,
            {
                "status": "work",
                "branch": self.branch.pk,
                "start_time": "09:00",
                "end_time": "17:00",
            },
            REMOTE_ADDR="203.0.113.8",
        )

        self.assertEqual(updated_response.status_code, 200)
        entry = AuditLog.objects.latest("pk")
        self.assertEqual(entry.ip_address, "203.0.113.8")
        self.assertEqual(entry.action, "Turno actualizado")
        self.assertIn("Antes: Centro · 08:00–16:00", entry.details)
        self.assertIn("Ahora: Centro · 09:00–17:00", entry.details)

    def test_unchanged_assignment_does_not_create_change_log(self):
        assignment_url = reverse(
            "assignment_save",
            args=[self.week_start.isoformat(), self.person.pk, 0],
        )
        payload = {
            "status": "work",
            "branch": self.branch.pk,
            "start_time": "08:00",
            "end_time": "16:00",
        }
        self.client.post(assignment_url, payload)
        self.client.post(assignment_url, payload)

        self.assertEqual(AuditLog.objects.count(), 1)

    def test_logs_require_analysis_session(self):
        response = self.client.get(reverse("logs"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("analysis_unlock"), response["Location"])

    def test_invalid_assignment_is_not_logged(self):
        response = self.client.post(
            reverse("assignment_save", args=[self.week_start.isoformat(), self.person.pk, 0]),
            {"status": "work", "branch": self.branch.pk, "start_time": "", "end_time": ""},
            REMOTE_ADDR="203.0.113.7",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(AuditLog.objects.exists())

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
        self.assertContains(response, "MODO NOVEDADES")
        self.assertContains(response, "Ir a Turnos")
        self.assertContains(response, "Novedades activas")
        self.assertContains(response, 'title="Ana Torres"', html=False)
        self.assertNotContains(response, "Sin asignar")
        self.assertContains(response, "schedule-main-shell")

    def test_late_arrival_is_included_in_analysis_hours(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO assignments (week_start, person_id, day, branch_id, start_time, end_time, assignment_type) "
                "VALUES (%s, %s, 0, %s, '08:00', '16:00', 'work')",
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
        self.assertContains(response, "Llegada tarde")
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
                "INSERT INTO assignments (week_start, person_id, day, branch_id, start_time, end_time, assignment_type) "
                "VALUES (%s, %s, %s, %s, '08:00', '16:00', 'work')",
                [
                    (self.week_start.isoformat(), self.person.pk, day, self.branch.pk)
                    for day in (0, 1)
                ],
            )
        session = self.client.session
        session["analysis_authenticated"] = True
        session.save()

        for day, kind, observation, badge in (
            (0, AssignmentNovelty.DID_NOT_ATTEND, "No avisó", "No se presentó"),
            (1, AssignmentNovelty.CALAMITY, "Emergencia familiar", "Calamidad"),
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
        self.assertEqual(workbook.active["J8"].value, "No avisó")
        self.assertEqual(workbook.active["J9"].value, "Emergencia familiar")

    def test_changing_shift_times_preserves_existing_novelty(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO assignments (week_start, person_id, day, branch_id, start_time, end_time, assignment_type) "
                "VALUES (%s, %s, 0, %s, '08:00', '16:00', 'work')",
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
        novelty = AssignmentNovelty.objects.get()
        self.assertIsNone(novelty.archived_at)
        self.assertEqual(novelty.actual_start_time.strftime("%H:%M"), "09:30")
        assignments = assignments_between(self.week_start, self.week_start)
        self.assertEqual(assignments[0][5], "09:30")
        session = self.client.session
        session["analysis_authenticated"] = True
        session.save()

        novelties_page = self.client.get(
            reverse("novelties_week", args=[self.week_start.isoformat()])
        )

        self.assertEqual(novelties_page.status_code, 200)
        self.assertContains(novelties_page, "Llegada tarde")
        self.assertNotContains(novelties_page, "Histórico ·")

    def test_changing_shift_branch_archives_outdated_novelty(self):
        other_branch = Branch.objects.create(name="Norte", color="#2F6FED")
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO assignments (week_start, person_id, day, branch_id, start_time, end_time, assignment_type) "
                "VALUES (%s, %s, 0, %s, '08:00', '16:00', 'work')",
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
                "branch": other_branch.pk,
                "start_time": "08:00",
                "end_time": "16:00",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        novelty = AssignmentNovelty.objects.get()
        self.assertIsNotNone(novelty.archived_at)
        self.assertEqual(novelty.actual_start_time.strftime("%H:%M"), "09:30")

    def test_removing_shift_archives_associated_novelty(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO assignments (week_start, person_id, day, branch_id, start_time, end_time, assignment_type) "
                "VALUES (%s, %s, 0, %s, '08:00', '16:00', 'work')",
                [self.week_start.isoformat(), self.person.pk, self.branch.pk],
            )
        AssignmentNovelty.objects.create(
            week_start=self.week_start,
            person_id=self.person.pk,
            day=0,
            actual_start_time="09:30",
        )
        session = self.client.session
        session["analysis_authenticated"] = True
        session.save()

        response = self.client.post(
            reverse(
                "assignment_save",
                args=[self.week_start.isoformat(), self.person.pk, 0],
            ),
            {"status": "unassigned"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        novelty = AssignmentNovelty.objects.get()
        self.assertIsNotNone(novelty.archived_at)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM assignments "
                "WHERE week_start = %s AND person_id = %s AND day = 0",
                [self.week_start.isoformat(), self.person.pk],
            )
            self.assertEqual(cursor.fetchone()[0], 0)

        history_response = self.client.get(
            reverse("novelties_week", args=[self.week_start.isoformat()])
        )
        self.assertEqual(history_response.status_code, 200)
        self.assertContains(history_response, "Histórico · Llegada tarde")
        self.assertContains(history_response, "09:30")

    def test_selecting_no_novelty_archives_record_without_changing_shift(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO assignments (week_start, person_id, day, branch_id, start_time, end_time, assignment_type) "
                "VALUES (%s, %s, 0, %s, '08:00', '16:00', 'work')",
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
        self.assertContains(response, "Novedad conservada en el historial.")
        self.assertNotContains(response, "+ Calamidad")
        novelty = AssignmentNovelty.objects.get()
        self.assertIsNotNone(novelty.archived_at)
        self.assertEqual(novelty.observation, "Registro equivocado")
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT branch_id, start_time, end_time FROM assignments "
                "WHERE week_start = %s AND person_id = %s AND day = 0",
                [self.week_start.isoformat(), self.person.pk],
            )
            self.assertEqual(cursor.fetchone(), (self.branch.pk, "08:00", "16:00"))

    def test_clearing_week_archives_novelties(self):
        AssignmentNovelty.objects.create(
            week_start=self.week_start,
            person_id=self.person.pk,
            day=0,
            actual_start_time="09:30",
        )

        clear_week(self.week_start)

        novelty = AssignmentNovelty.objects.get()
        self.assertIsNotNone(novelty.archived_at)

    def test_deleting_branch_archives_associated_novelties(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO assignments (week_start, person_id, day, branch_id, start_time, end_time, assignment_type) "
                "VALUES (%s, %s, 0, %s, '08:00', '16:00', 'work')",
                [self.week_start.isoformat(), self.person.pk, self.branch.pk],
            )
        AssignmentNovelty.objects.create(
            week_start=self.week_start,
            person_id=self.person.pk,
            day=0,
            actual_start_time="09:30",
        )

        delete_branch(self.branch)

        novelty = AssignmentNovelty.objects.get()
        self.assertIsNotNone(novelty.archived_at)

    def test_history_can_be_deleted_for_one_cell_without_removing_current_novelty(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO assignments (week_start, person_id, day, branch_id, start_time, end_time, assignment_type) "
                "VALUES (%s, %s, 0, %s, '08:00', '16:00', 'work')",
                [self.week_start.isoformat(), self.person.pk, self.branch.pk],
            )
        AssignmentNovelty.objects.create(
            week_start=self.week_start,
            person_id=self.person.pk,
            day=0,
            actual_start_time="09:30",
            archived_at=timezone.now(),
        )
        current_novelty = AssignmentNovelty.objects.create(
            week_start=self.week_start,
            person_id=self.person.pk,
            day=0,
            actual_start_time="10:00",
        )
        session = self.client.session
        session["analysis_authenticated"] = True
        session.save()

        page = self.client.get(
            reverse("novelties_week", args=[self.week_start.isoformat()])
        )
        self.assertContains(page, "Borrar historial")

        response = self.client.post(
            reverse(
                "novelty_history_delete",
                args=[self.week_start.isoformat(), self.person.pk, 0],
            ),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Historial de la celda eliminado.")
        self.assertFalse(
            AssignmentNovelty.objects.filter(archived_at__isnull=False).exists()
        )
        self.assertEqual(
            AssignmentNovelty.objects.get(archived_at__isnull=True).pk,
            current_novelty.pk,
        )
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

    def test_incapacity_appears_in_both_excel_exports(self):
        assignment_response = self.client.post(
            reverse("assignment_save", args=[self.week_start.isoformat(), self.person.pk, 0]),
            {"status": "incapacity"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(assignment_response.status_code, 200)

        schedule_response = self.client.get(
            reverse("schedule_export"),
            {"start": self.week_start.isoformat(), "end": self.week_start.isoformat()},
        )
        self.assertEqual(schedule_response.status_code, 200)
        schedule_sheet = load_workbook(
            BytesIO(schedule_response.content), read_only=True
        ).active
        self.assertEqual(schedule_sheet["B3"].value, "Incapacidad")
        self.assertEqual(schedule_sheet["C3"].value, 0)

        session = self.client.session
        session["analysis_authenticated"] = True
        session.save()
        month = self.week_start.strftime("%Y-%m")
        fortnight = "1" if self.week_start.day <= 15 else "2"
        analysis_response = self.client.get(
            reverse("analysis_export"),
            {"month": month, "fortnight": fortnight},
        )
        self.assertEqual(analysis_response.status_code, 200)
        analysis_sheet = load_workbook(
            BytesIO(analysis_response.content), read_only=True
        ).active
        self.assertEqual(analysis_sheet["C8"].value, "Incapacidad")
        self.assertEqual(analysis_sheet["F8"].value, 0)

    def test_schedule_export_marks_all_vacation_periods(self):
        VacationPeriod.objects.create(
            person_id=self.person.pk,
            start_date=date(2020, 1, 7),
            end_date=date(2020, 1, 8),
        )
        VacationPeriod.objects.create(
            person_id=self.person.pk,
            start_date=date(2020, 2, 4),
            end_date=date(2020, 2, 5),
        )

        response = self.client.get(
            reverse("schedule_export"),
            {"start": "2020-01-06", "end": "2020-02-06"},
        )

        self.assertEqual(response.status_code, 200)
        sheet = load_workbook(BytesIO(response.content), read_only=True).active
        self.assertEqual(sheet["C3"].value, "Vacaciones")
        self.assertEqual(sheet["D3"].value, "Vacaciones")
        self.assertEqual(sheet["AE3"].value, "Vacaciones")
        self.assertEqual(sheet["AF3"].value, "Vacaciones")

    def test_overnight_shift_metrics(self):
        self.assertEqual(shift_metrics("22:00", "06:00"), (8.0, 0.0, 0.0, 0.0))

    def test_analysis_preserves_negative_daytime_balance_and_nighttime_overtime(self):
        week_start = date(2026, 10, 5)
        shift_data = (
            ("09:30", "18:30", None, None),
            ("09:30", "14:00", None, None),
            ("09:30", "18:00", None, None),
            ("09:30", "20:00", "09:37", AssignmentNovelty.LATE_ARRIVAL),
            ("09:30", "15:00", None, None),
            ("09:30", "18:30", None, None),
        )
        assignments = [
            (
                week_start + timedelta(days=day),
                self.person.pk,
                self.branch.pk,
                start_time,
                end_time,
                actual_start_time,
                novelty_kind,
                "",
            )
            for day, (start_time, end_time, actual_start_time, novelty_kind) in zip(
                (0, 1, 2, 3, 4, 6), shift_data
            )
        ]

        daily_metrics = assignment_period_metrics([self.person], assignments)
        summaries, _ = summarize_period([self.person], assignments, daily_metrics)
        metric = summaries[self.person.pk]

        self.assertAlmostEqual(metric["worked"], 46 + 53 / 60)
        self.assertAlmostEqual(metric["overtime"], -1 - 7 / 60)
        self.assertAlmostEqual(metric["daytime"], -2 - 7 / 60)
        self.assertEqual(metric["nighttime"], 1)
        self.assertEqual(daily_metrics[3]["nighttime"], 60)
        self.assertEqual(daily_metrics[1]["daytime"], -210)
        self.assertEqual(daily_metrics[4]["daytime"], -150)
        self.assertEqual(
            sum(item["overtime"] for item in daily_metrics.values()),
            -67,
        )

    def test_analysis_nets_overtime_against_shorter_workdays(self):
        shift_end_times = ("17:16", "17:16", "17:16", "17:16", "13:00", "15:15", "15:00")
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO assignments (week_start, person_id, day, branch_id, start_time, end_time, assignment_type) "
                "VALUES (%s, %s, %s, %s, '08:00', %s, 'work')",
                [
                    (self.week_start.isoformat(), self.person.pk, day, self.branch.pk, end_time)
                    for day, end_time in enumerate(shift_end_times)
                ],
            )

        assignments = assignments_between(
            self.week_start, self.week_start + timedelta(days=6)
        )
        summaries, totals = summarize_period([self.person], assignments)
        metric = summaries[self.person.pk]

        self.assertEqual(metric["days"], 7)
        self.assertAlmostEqual(metric["worked"], 3379 / 60)
        self.assertAlmostEqual(metric["overtime"], 19 / 60)
        self.assertAlmostEqual(metric["daytime"], 19 / 60)
        self.assertEqual(metric["nighttime"], 0)
        self.assertAlmostEqual(totals["overtime"], 19 / 60)

        session = self.client.session
        session["analysis_authenticated"] = True
        session.save()
        month = self.week_start.strftime("%Y-%m")
        fortnight = "1" if self.week_start.day <= 15 else "2"
        response = self.client.get(
            reverse("analysis"),
            {"month": month, "fortnight": fortnight},
        )
        self.assertEqual(response.status_code, 200)
        self.assertAlmostEqual(
            response.context["summaries"][self.person.pk]["overtime"],
            19 / 60,
        )

        workbook_response = self.client.get(
            reverse("analysis_export"),
            {"month": month, "fortnight": fortnight},
        )
        workbook = load_workbook(BytesIO(workbook_response.content), read_only=True)
        self.assertAlmostEqual(workbook.active["C3"].value, 3379 / 60)
        self.assertAlmostEqual(workbook.active["D3"].value, 19 / 60)
        self.assertAlmostEqual(workbook.active["E3"].value, 19 / 60)
        self.assertEqual(workbook.active["F3"].value, 0)
        self.assertEqual(workbook.active["G7"].value, "Horas extra")
        self.assertEqual(workbook.active["H7"].value, "HD")
        self.assertEqual(workbook.active["I7"].value, "HN")
        self.assertAlmostEqual(
            sum(workbook.active.cell(row=row, column=7).value for row in range(8, 15)),
            workbook.active["D3"].value,
        )
        self.assertAlmostEqual(
            sum(workbook.active.cell(row=row, column=8).value for row in range(8, 15)),
            workbook.active["E3"].value,
        )
        self.assertAlmostEqual(
            sum(workbook.active.cell(row=row, column=9).value for row in range(8, 15)),
            workbook.active["F3"].value,
        )

    def test_analysis_export_shows_daily_daytime_and_nighttime_overtime(self):
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO assignments (week_start, person_id, day, branch_id, start_time, end_time, assignment_type) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'work')",
                [
                    (
                        self.week_start.isoformat(), self.person.pk, 0,
                        self.branch.pk, "22:00", "08:00",
                    ),
                    (
                        self.week_start.isoformat(), self.person.pk, 1,
                        self.branch.pk, "15:00", "01:00",
                    ),
                ],
            )
        session = self.client.session
        session["analysis_authenticated"] = True
        session.save()

        workbook_response = self.client.get(
            reverse("analysis_export"),
            {
                "month": self.week_start.strftime("%Y-%m"),
                "fortnight": "1" if self.week_start.day <= 15 else "2",
            },
        )

        self.assertEqual(workbook_response.status_code, 200)
        workbook = load_workbook(BytesIO(workbook_response.content), read_only=True)
        sheet = workbook.active
        self.assertEqual((sheet["G8"].value, sheet["H8"].value, sheet["I8"].value), (2, 2, 0))
        self.assertEqual((sheet["G9"].value, sheet["H9"].value, sheet["I9"].value), (2, 0, 2))
        self.assertEqual(sheet["D3"].value, sheet["G8"].value + sheet["G9"].value)
        self.assertEqual(sheet["E3"].value, sheet["H8"].value + sheet["H9"].value)
        self.assertEqual(sheet["F3"].value, sheet["I8"].value + sheet["I9"].value)

    def test_absence_and_calamity_reduce_overtime_and_daily_quota(self):
        shift_end_times = ("17:16", "17:16", "17:16", "17:16", "13:00", "15:15", "15:00")
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO assignments (week_start, person_id, day, branch_id, start_time, end_time, assignment_type) "
                "VALUES (%s, %s, %s, %s, '08:00', %s, 'work')",
                [
                    (self.week_start.isoformat(), self.person.pk, day, self.branch.pk, end_time)
                    for day, end_time in enumerate(shift_end_times)
                ],
            )
        AssignmentNovelty.objects.create(
            week_start=self.week_start,
            person_id=self.person.pk,
            day=0,
            kind=AssignmentNovelty.DID_NOT_ATTEND,
        )
        AssignmentNovelty.objects.create(
            week_start=self.week_start,
            person_id=self.person.pk,
            day=4,
            kind=AssignmentNovelty.CALAMITY,
        )

        assignments = assignments_between(
            self.week_start, self.week_start + timedelta(days=6)
        )
        summaries, _ = summarize_period([self.person], assignments)
        metric = summaries[self.person.pk]

        self.assertEqual(metric["days"], 5)
        self.assertAlmostEqual(metric["worked"], 2523 / 60)
        self.assertAlmostEqual(metric["overtime"], 123 / 60)
        self.assertAlmostEqual(metric["daytime"], 123 / 60)
        self.assertEqual(metric["nighttime"], 0)


class WeekDateTests(TestCase):
    def test_monday_of_week(self):
        self.assertEqual(monday_of(date(2026, 10, 3)), date(2026, 9, 28))

    def test_capitalize_person_name_and_keep_dni_acronym(self):
        self.assertEqual(capitalize("ANA TORRES"), "Ana Torres")
        self.assertEqual(capitalize("ANA TORRES · DNI 123"), "Ana Torres · DNI 123")
