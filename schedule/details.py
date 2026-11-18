from .services import name_counts, person_display_name


DAY_NAMES = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")


def assignment_detail_rows(people, assignments, daily_metrics, branches):
    """Construye el detalle diario que comparten el Excel y el modal de Análisis."""
    people = list(people)
    people_by_id = {person.pk: person for person in people}
    duplicate_names = name_counts(people)
    rows = []
    for assignment_index, assignment in enumerate(assignments):
        assigned_date, person_id, branch_id, start_time, end_time = assignment[:5]
        actual_start_time = assignment[5] if len(assignment) > 5 else None
        novelty_kind = assignment[6] if len(assignment) > 6 else None
        observation = assignment[7] if len(assignment) > 7 else ""
        assignment_type = assignment[8] if len(assignment) > 8 else "work"
        start_time_2 = assignment[9] if len(assignment) > 9 else None
        end_time_2 = assignment[10] if len(assignment) > 10 else None
        actual_start_time_2 = assignment[11] if len(assignment) > 11 else None
        person = people_by_id.get(person_id)
        if person is None:
            continue
        metrics = daily_metrics.get(assignment_index, {
            "worked": 0, "overtime": 0, "daytime": 0, "nighttime": 0,
        })
        row = {
            "name": person_display_name(person, duplicate_names),
            "day": f"{DAY_NAMES[assigned_date.weekday()]} {assigned_date:%d/%m/%Y}",
            "is_non_work": branch_id is None,
        }
        if branch_id is None:
            if assignment_type == "incapacity":
                label = "Incapacidad"
            elif assignment_type == "absent":
                label = "No se presentó"
            else:
                label = "Descanso"
            row.update({
                "branch": label,
                "start": "",
                "end": "",
                "worked": 0,
                "overtime": 0,
                "daytime": 0,
                "nighttime": 0,
                "observation": "",
            })
        else:
            display_start = actual_start_time or start_time
            display_end = end_time
            if assignment_type == "split_shift" and start_time_2 and end_time_2:
                display_start += f" / {actual_start_time_2 or start_time_2}"
                display_end += f" / {end_time_2}"
            if novelty_kind in ("did_not_attend", "calamity"):
                worked_hours = 0
                if novelty_kind == "did_not_attend":
                    novelty_label = "No se presentó"
                else:
                    novelty_label = "Calamidad"
                branch_label = (
                    f"{branches.get(branch_id, 'Sucursal eliminada')} · {novelty_label}"
                )
            else:
                worked_hours = metrics["worked"] / 60
                branch_label = branches.get(branch_id, "Sucursal eliminada")
            row.update({
                "branch": branch_label,
                "start": display_start,
                "end": display_end,
                "worked": worked_hours,
                "overtime": metrics["overtime"] / 60,
                "daytime": metrics["daytime"] / 60,
                "nighttime": metrics["nighttime"] / 60,
                "observation": observation,
            })
        rows.append(row)
    return rows
