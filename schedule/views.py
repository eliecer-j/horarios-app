import calendar
import hmac
from datetime import date, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from .exports import fortnight_workbook, workbook_response
from .forms import AnalysisPasswordForm, AssignmentForm, BranchForm, PersonForm
from .metrics import DAY_SHIFT_END_HOUR, DAY_SHIFT_START_HOUR, summarize_period
from .models import Branch, Person
from .services import (
    assignments_between,
    available_weeks,
    clear_week,
    delete_branch,
    delete_person,
    is_on_vacation,
    monday_of,
    name_counts,
    person_display_name,
    remove_vacation_assignments,
    save_assignment,
    week_assignments,
)


DAYS = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
CONTENT_TEMPLATE = "content_template"


def render_screen(request, template, context=None, status=200):
    context = context or {}
    context[CONTENT_TEMPLATE] = template
    context.setdefault("current_path", request.path)
    if request.headers.get("HX-Request") == "true":
        from django.shortcuts import render

        return render(request, template, context, status=status)
    from django.shortcuts import render

    return render(request, "base.html", context, status=status)


def home(_request):
    selected_week = _request.GET.get("week")
    week_start = _parse_week(selected_week) if selected_week else monday_of(timezone.localdate())
    return redirect("schedule", week_start=week_start.isoformat())


def _parse_week(value):
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise Http404("La semana solicitada no es válida.") from exc
    return monday_of(parsed)


def _week_label(week_start):
    week_end = week_start + timedelta(days=6)
    start = f"{week_start.day} {MONTHS[week_start.month - 1]}"
    end = f"{week_end.day} {MONTHS[week_end.month - 1]}"
    span = f"{start} – {end}" if week_start.month != week_end.month else f"{week_start.day}–{week_end.day} {MONTHS[week_start.month - 1]}"
    return f"Semana {week_start.isocalendar().week:02d} · {span} {week_end.year}"


def _schedule_context(week_start, edit=None, form=None, message="", filter_key="all"):
    people = list(Person.objects.all())
    branches = list(Branch.objects.all())
    assignments = week_assignments(week_start)
    duplicate_names = name_counts(people)
    today = timezone.localdate()
    days = [
        {
            "index": offset,
            "date": week_start + timedelta(days=offset),
            "label": DAYS[offset],
            "is_today": week_start + timedelta(days=offset) == today,
        }
        for offset in range(7)
    ]
    no_rest_count = pending_cells = pending_people = 0
    rows = []
    for person in people:
        available_days = [day for day in days if not is_on_vacation(person, day["date"])]
        assigned = [assignments.get((person.pk, day["index"])) for day in available_days]
        assigned = [value for value in assigned if value is not None]
        rests = sum(1 for value in assigned if value["branch_id"] is None)
        missing = len(available_days) - len(assigned)
        has_pending = missing > 0
        alert = bool(available_days) and rests == 0
        pending_cells += missing
        pending_people += int(has_pending)
        no_rest_count += int(alert)
        if filter_key == "pending" and not has_pending:
            continue
        if filter_key == "no_rest" and not alert:
            continue
        rows.append({
            "person": person,
            "display_name": person_display_name(person, duplicate_names),
            "rests": rests,
            "alert": alert,
            "cells": [
                {
                    "day": day,
                    "assignment": assignments.get((person.pk, day["index"])),
                    "on_vacation": is_on_vacation(person, day["date"]),
                    "branch": next(
                        (branch for branch in branches
                         if assignments.get((person.pk, day["index"]), {}).get("branch_id") == branch.pk),
                        None,
                    ),
                }
                for day in days
            ],
        })
    all_weeks = {monday_of(value) for value in available_weeks()}
    all_weeks.update(week_start + timedelta(weeks=offset) for offset in range(-12, 27))
    all_weeks.add(monday_of(today))
    all_weeks.add(week_start)
    return {
        "week_start": week_start,
        "week_end": week_start + timedelta(days=6),
        "week_label": _week_label(week_start),
        "previous_week": (week_start - timedelta(days=7)).isoformat(),
        "next_week": (week_start + timedelta(days=7)).isoformat(),
        "today_week": monday_of(today).isoformat(),
        "is_current_week": week_start == monday_of(today),
        "week_options": sorted(all_weeks),
        "days": days,
        "rows": rows,
        "people_count": len(people),
        "pending_cells": pending_cells,
        "pending_people": pending_people,
        "no_rest_count": no_rest_count,
        "filter_key": filter_key,
        "edit": edit,
        "edit_person": next((person for person in people if edit and person.pk == edit[0]), None),
        "edit_day": edit[1] if edit else None,
        "edit_day_name": DAYS[edit[1]] if edit else "",
        "edit_date": week_start + timedelta(days=edit[1]) if edit else None,
        "edit_form": form,
        "branches": branches,
        "message": message,
        "has_people": bool(people),
        "has_branches": bool(branches),
        "today": today,
    }


def schedule(request, week_start):
    week_start = _parse_week(week_start)
    edit = None
    form = None
    edit_value = request.GET.get("edit", "")
    if edit_value:
        try:
            person_id, day = map(int, edit_value.split("-", 1))
            if day not in range(7) or not Person.objects.filter(pk=person_id).exists():
                raise ValueError
            edit = (person_id, day)
            current = week_assignments(week_start).get(edit)
            initial = {
                "status": "work",
                "branch": Branch.objects.order_by("name").values_list("pk", flat=True).first(),
            }
            if current:
                initial = {
                    "status": "rest" if current["branch_id"] is None else "work",
                    "branch": current["branch_id"],
                    "start_time": current["start_time"] or "",
                    "end_time": current["end_time"] or "",
                }
            form = AssignmentForm(initial=initial)
        except (ValueError, Person.DoesNotExist):
            raise Http404("La asignación solicitada no existe.")
    context = _schedule_context(
        week_start, edit=edit, form=form,
        filter_key=request.GET.get("filter", "all"),
    )
    return render_screen(request, "schedule/content.html", context)


@require_POST
def assignment_save(request, week_start, person_id, day):
    week_start = _parse_week(week_start)
    if day not in range(7):
        raise Http404("El día solicitado no es válido.")
    if not Person.objects.filter(pk=person_id).exists():
        raise Http404("La persona solicitada no existe.")
    form = AssignmentForm(request.POST)
    try:
        if form.is_valid():
            save_assignment(week_start, person_id, day, form)
            return render_screen(
                request, "schedule/content.html",
                _schedule_context(week_start, message="Turno actualizado."),
            )
    except ValueError as exc:
        form.add_error(None, str(exc))
    return render_screen(
        request, "schedule/content.html",
        _schedule_context(week_start, edit=(person_id, day), form=form),
    )


@require_POST
def schedule_clear(request, week_start):
    week_start = _parse_week(week_start)
    clear_week(week_start)
    return render_screen(
        request, "schedule/content.html",
        _schedule_context(week_start, message="Se vaciaron los turnos de la semana."),
    )


def people(request):
    query = request.GET.get("q", "").strip()
    editing = request.GET.get("edit")
    person = None
    if editing:
        try:
            person = Person.objects.get(pk=int(editing))
        except (ValueError, Person.DoesNotExist) as exc:
            raise Http404("La persona solicitada no existe.") from exc
    form = PersonForm(person=person)
    message = request.GET.get("message", "")
    if request.method == "POST":
        person_id = request.POST.get("person_id", "").strip()
        if person_id:
            try:
                person = Person.objects.get(pk=int(person_id))
            except (ValueError, Person.DoesNotExist) as exc:
                raise Http404("La persona solicitada no existe.") from exc
        form = PersonForm(request.POST, person=person)
        if form.is_valid():
            cleaned = form.cleaned_data
            removed = 0
            with transaction.atomic():
                if person is None:
                    person = Person()
                person.name = cleaned["name"]
                person.dni = cleaned["dni"]
                person.vacation_start = cleaned["vacation_start"]
                person.vacation_end = cleaned["vacation_end"]
                person.save()
                if person.vacation_start and person.vacation_end:
                    removed = remove_vacation_assignments(
                        person, person.vacation_start, person.vacation_end
                    )
            editing = None
            person = None
            form = PersonForm()
            message = "Persona guardada."
            if removed:
                message += f" Se quitaron {removed} turnos durante sus vacaciones."

    queryset = Person.objects.all()
    if query:
        queryset = queryset.filter(Q(name__icontains=query) | Q(dni__icontains=query))
    people_list = list(queryset)
    week_start = monday_of(timezone.localdate())
    assignments = week_assignments(week_start)
    duplicate_names = name_counts(people_list)
    for person_item in people_list:
        week_values = [
            assignments.get((person_item.pk, day))
            for day in range(7)
            if not is_on_vacation(person_item, week_start + timedelta(days=day))
        ]
        week_values = [value for value in week_values if value is not None]
        person_item.week_work = sum(1 for value in week_values if value["branch_id"] is not None)
        person_item.week_rest = sum(1 for value in week_values if value["branch_id"] is None)
        person_item.display_name = person_display_name(person_item, duplicate_names)
    return render_screen(request, "people/content.html", {
        "people": people_list,
        "query": query,
        "editing": editing,
        "editing_person": person,
        "form": form,
        "message": message,
        "week_label": _week_label(week_start),
        "total_people": Person.objects.count(),
    })


@require_POST
def person_delete(request, person_id):
    try:
        person = Person.objects.get(pk=person_id)
    except Person.DoesNotExist as exc:
        raise Http404("La persona solicitada no existe.") from exc
    delete_person(person)
    if request.headers.get("HX-Request") != "true":
        return redirect("people")
    request.method = "GET"
    request.GET = request.GET.copy()
    request.GET["message"] = "Persona eliminada junto con sus turnos."
    return people(request)


def branches(request):
    editing = request.GET.get("edit")
    branch = None
    if editing:
        try:
            branch = Branch.objects.get(pk=int(editing))
        except (ValueError, Branch.DoesNotExist) as exc:
            raise Http404("La sucursal solicitada no existe.") from exc
    form = BranchForm(branch=branch)
    message = ""
    if request.method == "POST":
        branch_id = request.POST.get("branch_id", "").strip()
        if branch_id:
            try:
                branch = Branch.objects.get(pk=int(branch_id))
            except (ValueError, Branch.DoesNotExist) as exc:
                raise Http404("La sucursal solicitada no existe.") from exc
        form = BranchForm(request.POST, branch=branch)
        if form.is_valid():
            branch = branch or Branch()
            branch.name = form.cleaned_data["name"]
            branch.color = form.cleaned_data["color"]
            try:
                branch.save()
            except IntegrityError:
                form.add_error("name", "Ya existe una sucursal con ese nombre.")
            else:
                message = "Sucursal guardada."
                branch = None
                editing = None
                form = BranchForm()

    branches_list = list(Branch.objects.all())
    week_start = monday_of(timezone.localdate())
    assignments = week_assignments(week_start)
    query = request.GET.get("q", "").strip()
    if query:
        branches_list = [item for item in branches_list if query.casefold() in item.name.casefold()]
    for branch_item in branches_list:
        matching = [value for value in assignments.values() if value["branch_id"] == branch_item.pk]
        branch_item.week_shifts = len(matching)
        branch_item.week_people = len({
            person_id for (person_id, _), value in assignments.items()
            if value["branch_id"] == branch_item.pk
        })
    return render_screen(request, "branches/content.html", {
        "branches": branches_list,
        "query": query,
        "editing": editing,
        "editing_branch": branch,
        "form": form,
        "message": request.GET.get("message", message),
        "week_label": _week_label(week_start),
    })


@require_POST
def branch_delete(request, branch_id):
    try:
        branch = Branch.objects.get(pk=branch_id)
    except Branch.DoesNotExist as exc:
        raise Http404("La sucursal solicitada no existe.") from exc
    delete_branch(branch)
    if request.headers.get("HX-Request") == "true":
        request.method = "GET"
        request.GET = request.GET.copy()
        request.GET["message"] = "Sucursal eliminada junto con sus turnos."
        return branches(request)
    return redirect("branches")


def analysis(request):
    if request.session.get("analysis_authenticated") is not True:
        return redirect("analysis_unlock")
    today = timezone.localdate()
    month_value = request.GET.get("month", today.strftime("%Y-%m"))
    try:
        year, month = map(int, month_value.split("-"))
        if not 1 <= month <= 12:
            raise ValueError
    except ValueError as exc:
        raise Http404("El mes solicitado no es válido.") from exc
    fortnight = request.GET.get("fortnight", "1" if today.day <= 15 else "2")
    if fortnight not in ("1", "2"):
        raise Http404("La quincena solicitada no es válida.")
    start_date = date(year, month, 1 if fortnight == "1" else 16)
    end_date = date(year, month, 15 if fortnight == "1" else calendar.monthrange(year, month)[1])
    people_list = list(Person.objects.all())
    assignments = assignments_between(start_date, end_date)
    summaries, totals = summarize_period(people_list, assignments)
    duplicate_names = name_counts(people_list)
    for person in people_list:
        person.display_name = person_display_name(person, duplicate_names)
    return render_screen(request, "analysis/content.html", {
        "people": people_list,
        "summaries": summaries,
        "people_metrics": [
            (person, summaries[person.pk]) for person in people_list
        ],
        "totals": totals,
        "start_date": start_date,
        "end_date": end_date,
        "month_value": month_value,
        "fortnight": fortnight,
        "month_name": MONTHS[month - 1].title(),
        "day_shift_start": DAY_SHIFT_START_HOUR,
        "day_shift_end": DAY_SHIFT_END_HOUR,
    })


def analysis_unlock(request):
    if request.session.get("analysis_authenticated") is True:
        return redirect("analysis")
    form = AnalysisPasswordForm()
    configuration_error = not settings.ANALYSIS_PASSWORD
    if request.method == "POST":
        form = AnalysisPasswordForm(request.POST)
        if not settings.ANALYSIS_PASSWORD:
            configuration_error = True
        elif form.is_valid() and hmac.compare_digest(
            form.cleaned_data["password"], settings.ANALYSIS_PASSWORD
        ):
            request.session["analysis_authenticated"] = True
            return redirect("analysis")
        else:
            form.add_error("password", "Contraseña incorrecta.")
    return render_screen(request, "analysis/unlock.html", {
        "form": form,
        "configuration_error": configuration_error,
    })


def _parse_export_dates(request):
    try:
        start_date = date.fromisoformat(request.GET.get("start", ""))
        end_date = date.fromisoformat(request.GET.get("end", ""))
    except ValueError as exc:
        raise Http404("Selecciona un rango de fechas válido.") from exc
    if end_date < start_date:
        raise Http404("La fecha final debe ser igual o posterior a la inicial.")
    return start_date, end_date


def schedule_export(request):
    from schedule_export import build_schedule_workbook

    start_date, end_date = _parse_export_dates(request)
    people_list = list(Person.objects.all())
    duplicate_names = {}
    for person in people_list:
        key = person.name.strip().lower()
        duplicate_names[key] = duplicate_names.get(key, 0) + 1
    people_for_export = [
        (person.pk, person_display_name(person, duplicate_names))
        for person in people_list
    ]
    branch_map = {branch.pk: (branch.name, branch.color) for branch in Branch.objects.all()}
    vacations = {
        person.pk: (person.vacation_start.isoformat(), person.vacation_end.isoformat())
        for person in people_list if person.vacation_start and person.vacation_end
    }
    payload = build_schedule_workbook(
        start_date, end_date, people_for_export,
        assignments_between(start_date, end_date), branch_map, vacations,
    )
    return workbook_response(
        payload, f"grilla_turnos_{start_date:%Y%m%d}_{end_date:%Y%m%d}.xlsx"
    )


def analysis_export(request):
    if request.session.get("analysis_authenticated") is not True:
        return redirect("analysis_unlock")
    today = timezone.localdate()
    month_value = request.GET.get("month", today.strftime("%Y-%m"))
    try:
        year, month = map(int, month_value.split("-"))
        fortnight = int(request.GET.get("fortnight", "1"))
        if month not in range(1, 13) or fortnight not in (1, 2):
            raise ValueError
    except ValueError as exc:
        raise Http404("Selecciona un período válido.") from exc
    start_date = date(year, month, 1 if fortnight == 1 else 16)
    end_date = date(year, month, 15 if fortnight == 1 else calendar.monthrange(year, month)[1])
    payload = fortnight_workbook(start_date, end_date, list(Person.objects.all()))
    return workbook_response(payload, f"turnos_{start_date:%Y-%m}_{start_date.day:02d}-{end_date.day:02d}.xlsx")
