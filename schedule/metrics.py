DAY_SHIFT_START_HOUR = 6
DAY_SHIFT_END_HOUR = 19


def shift_metrics(start_time, end_time):
    start_hour, start_minute = map(int, start_time.split(":"))
    end_hour, end_minute = map(int, end_time.split(":"))
    start = start_hour * 60 + start_minute
    duration = end_hour * 60 + end_minute - start
    if duration <= 0:
        duration += 24 * 60

    overtime_start = min(8 * 60, duration)
    overtime_minutes = max(0, duration - overtime_start)
    daytime_overtime = nighttime_overtime = 0
    for offset in range(overtime_start, duration):
        clock_minute = (start + offset) % (24 * 60)
        if DAY_SHIFT_START_HOUR * 60 <= clock_minute < DAY_SHIFT_END_HOUR * 60:
            daytime_overtime += 1
        else:
            nighttime_overtime += 1

    return duration / 60, overtime_minutes / 60, daytime_overtime / 60, nighttime_overtime / 60


def assignment_period_metrics(people, assignments):
    person_rows = {}
    for index, assignment in enumerate(assignments):
        _, person_id, branch_id, start_time, end_time = assignment[:5]
        actual_start_time = assignment[5] if len(assignment) > 5 else None
        novelty_kind = assignment[6] if len(assignment) > 6 else None
        if branch_id is None or not start_time or not end_time:
            continue
        if novelty_kind in ("did_not_attend", "calamity"):
            continue
        metrics = shift_metrics(actual_start_time or start_time, end_time)
        person_rows.setdefault(person_id, []).append({
            "index": index,
            "worked": round(metrics[0] * 60),
            "daytime_gross": round(metrics[2] * 60),
            "nighttime_gross": round(metrics[3] * 60),
            "daytime_shortfall": max(0, 8 * 60 - round(metrics[0] * 60)),
        })

    daily_metrics = {}
    people_by_id = {person.pk: person for person in people}
    for person_id, rows in person_rows.items():
        if person_id not in people_by_id:
            continue
        for row in rows:
            daytime = row["daytime_gross"] - row["daytime_shortfall"]
            nighttime = row["nighttime_gross"]
            daily_metrics[row["index"]] = {
                "worked": row["worked"],
                "overtime": daytime + nighttime,
                "daytime": daytime,
                "nighttime": nighttime,
            }
    return daily_metrics


def summarize_period(people, assignments, daily_metrics=None):
    if daily_metrics is None:
        daily_metrics = assignment_period_metrics(people, assignments)
    period_minutes = {
        person.pk: {
            "days": 0,
            "worked": 0,
            "overtime": 0,
            "daytime": 0,
            "nighttime": 0,
        }
        for person in people
    }
    for index, metrics in daily_metrics.items():
        person_id = assignments[index][1]
        person_minutes = period_minutes[person_id]
        person_minutes["days"] += 1
        for key in ("worked", "overtime", "daytime", "nighttime"):
            person_minutes[key] += metrics[key]

    summaries = {}
    totals = {"days": 0, "worked": 0.0, "overtime": 0.0, "daytime": 0.0, "nighttime": 0.0}
    for person_id, values in period_minutes.items():
        summary = {
            "days": values["days"],
            "worked": values["worked"] / 60,
            "overtime": values["overtime"] / 60,
            "daytime": values["daytime"] / 60,
            "nighttime": values["nighttime"] / 60,
        }
        summaries[person_id] = summary
        for key, value in summary.items():
            totals[key] += value
    return summaries, totals
