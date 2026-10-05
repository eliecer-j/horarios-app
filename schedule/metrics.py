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


def summarize_period(people, assignments):
    period_minutes = {
        person.pk: {
            "days": 0,
            "worked": 0,
            "daytime_overtime": 0,
            "nighttime_overtime": 0,
        }
        for person in people
    }
    for assignment in assignments:
        _, person_id, branch_id, start_time, end_time = assignment[:5]
        actual_start_time = assignment[5] if len(assignment) > 5 else None
        novelty_kind = assignment[6] if len(assignment) > 6 else None
        if branch_id is None or not start_time or not end_time or person_id not in period_minutes:
            continue
        if novelty_kind in ("did_not_attend", "calamity"):
            continue
        person_minutes = period_minutes[person_id]
        person_minutes["days"] += 1
        metrics = shift_metrics(actual_start_time or start_time, end_time)
        person_minutes["worked"] += round(metrics[0] * 60)
        person_minutes["daytime_overtime"] += round(metrics[2] * 60)
        person_minutes["nighttime_overtime"] += round(metrics[3] * 60)

    summaries = {}
    totals = {"days": 0, "worked": 0.0, "overtime": 0.0, "daytime": 0.0, "nighttime": 0.0}
    for person_id, values in period_minutes.items():
        gross_daytime = values["daytime_overtime"]
        gross_nighttime = values["nighttime_overtime"]
        gross_overtime = gross_daytime + gross_nighttime
        net_overtime = max(0, values["worked"] - values["days"] * 8 * 60)
        if gross_overtime:
            daytime_overtime = round(net_overtime * gross_daytime / gross_overtime)
        else:
            daytime_overtime = 0
        nighttime_overtime = net_overtime - daytime_overtime
        summary = {
            "days": values["days"],
            "worked": values["worked"] / 60,
            "overtime": net_overtime / 60,
            "daytime": daytime_overtime / 60,
            "nighttime": nighttime_overtime / 60,
        }
        summaries[person_id] = summary
        for key, value in summary.items():
            totals[key] += value
    return summaries, totals
