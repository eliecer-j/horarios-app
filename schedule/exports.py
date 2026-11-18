from io import BytesIO

from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .details import assignment_detail_rows
from .metrics import assignment_period_metrics, summarize_period
from .models import Branch
from .services import assignments_between


def fortnight_workbook(start_date, end_date, people):
    assignments = assignments_between(start_date, end_date)
    daily_metrics = assignment_period_metrics(people, assignments)
    summaries, totals = summarize_period(people, assignments, daily_metrics)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Quincena"
    header_fill = PatternFill("solid", fgColor="0F766E")
    total_fill = PatternFill("solid", fgColor="D9EAE7")
    rest_fill = PatternFill("solid", fgColor="EEF1F4")
    sheet.append([f"Análisis de turnos · {start_date:%d/%m/%Y} al {end_date:%d/%m/%Y}"])
    sheet.merge_cells("A1:F1")
    sheet["A1"].font = Font(bold=True, size=14)
    sheet.append(["Nombre", "Días trabajados", "Horas trabajadas", "Horas diurnas", "Horas nocturnas", "Horas extra"])
    for cell in sheet[2]:
        cell.fill = header_fill
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(horizontal="center")
    for person in people:
        metric = summaries[person.pk]
        sheet.append([
            person.name, metric["days"], metric["worked"],
            metric["daytime"], metric["nighttime"], metric["overtime"],
        ])
    sheet.append([
        "TOTAL", totals["days"], totals["worked"],
        totals["daytime"], totals["nighttime"], totals["overtime"],
    ])
    for cell in sheet[sheet.max_row]:
        cell.fill = total_fill
        cell.font = Font(bold=True)
    sheet.append([])
    sheet.append(["Detalle de turnos"])
    sheet[sheet.max_row][0].font = Font(bold=True, size=12)
    sheet.append([
        "Nombre", "Día", "Sucursal", "Horario inicio", "Horario fin", "Trabajadas",
        "Horas extra", "HD", "HN", "Observación",
    ])
    detail_header = sheet.max_row
    for cell in sheet[detail_header]:
        cell.fill = header_fill
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(horizontal="center")

    branches = {branch.pk: branch.name for branch in Branch.objects.all()}
    for row in assignment_detail_rows(people, assignments, daily_metrics, branches):
        sheet.append([
            row["name"], row["day"], row["branch"], row["start"], row["end"],
            row["worked"], row["overtime"], row["daytime"], row["nighttime"],
            row["observation"],
        ])
        if row["is_non_work"]:
            for cell in sheet[sheet.max_row]:
                cell.fill = rest_fill
    for column in range(1, 11):
        sheet.cell(row=detail_header, column=column).alignment = Alignment(horizontal="center")
    for column, width in zip("ABCDEFGHIJ", (30, 18, 30, 16, 16, 14, 14, 10, 10, 36)):
        sheet.column_dimensions[column].width = width
    sheet.freeze_panes = "A3"
    sheet.auto_filter.ref = f"A{detail_header}:J{sheet.max_row}"
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def workbook_response(payload, filename):
    response = HttpResponse(
        payload,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
