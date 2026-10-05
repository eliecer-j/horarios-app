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
    summaries = {
        person.pk: {"days": 0, "worked": 0.0, "overtime": 0.0, "daytime": 0.0, "nighttime": 0.0}
        for person in people
    }
    totals = {"days": 0, "worked": 0.0, "overtime": 0.0, "daytime": 0.0, "nighttime": 0.0}
    for assignment in assignments:
        _, person_id, branch_id, start_time, end_time = assignment[:5]
        actual_start_time = assignment[5] if len(assignment) > 5 else None
        novelty_kind = assignment[6] if len(assignment) > 6 else None
        if branch_id is None or not start_time or not end_time or person_id not in summaries:
            continue
        if novelty_kind in ("did_not_attend", "calamity"):
            continue
        summaries[person_id]["days"] += 1
        totals["days"] += 1
        metrics = shift_metrics(actual_start_time or start_time, end_time)
        for key, value in zip(("worked", "overtime", "daytime", "nighttime"), metrics):
            summaries[person_id][key] += value
            totals[key] += value
    return summaries, totals
