"""Cálculos de horas y resúmenes para reportes."""
from app_config import DAY_SHIFT_END_HOUR, DAY_SHIFT_START_HOUR


def shift_metrics(start_time, end_time):
    start_hour, start_minute = map(int, start_time.split(":"))
    end_hour, end_minute = map(int, end_time.split(":"))
    start = start_hour * 60 + start_minute
    duration = end_hour * 60 + end_minute - start
    if duration <= 0:
        duration += 24 * 60

    overtime_start = min(8 * 60, duration)
    overtime_minutes = max(0, duration - overtime_start)
    daytime_overtime = 0
    nighttime_overtime = 0
    for offset in range(overtime_start, duration):
        clock_minute = (start + offset) % (24 * 60)
        if DAY_SHIFT_START_HOUR * 60 <= clock_minute < DAY_SHIFT_END_HOUR * 60:
            daytime_overtime += 1
        else:
            nighttime_overtime += 1

    return duration / 60, overtime_minutes / 60, daytime_overtime / 60, nighttime_overtime / 60


def summarize_period(people, assignments):
    summaries = {
        pid: {"days": 0, "worked": 0.0, "overtime": 0.0, "daytime": 0.0, "nighttime": 0.0}
        for pid, _, _ in people
    }
    totals = {"days": 0, "worked": 0.0, "overtime": 0.0, "daytime": 0.0, "nighttime": 0.0}

    for _, pid, branch_id, start_time, end_time in assignments:
        if branch_id is None or not start_time or not end_time or pid not in summaries:
            continue
        summaries[pid]["days"] += 1
        totals["days"] += 1
        metrics = shift_metrics(start_time, end_time)
        for key, value in zip(("worked", "overtime", "daytime", "nighttime"), metrics):
            summaries[pid][key] += value
            totals[key] += value

    return summaries, totals
