DAY_SHIFT_START_HOUR = 6
DAY_SHIFT_END_HOUR = 19

REGULAR_DAY_MINUTES = 7 * 60
LUNCH_MINUTES = 60
LUNCH_START_MINUTES = 13 * 60
# Fin exclusivo: la ventana de almuerzo es 13:00–13:59.
LUNCH_END_MINUTES = 14 * 60
# El almuerzo aplica desde 6 h de presencia programada, no desde la jornada normal de 7 h.
LUNCH_MINIMUM_SHIFT_MINUTES = 6 * 60


def _minutes_from_time(value):
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def _shift_duration(start_time, end_time):
    start = _minutes_from_time(start_time)
    end = _minutes_from_time(end_time)
    duration = (end - start) % (24 * 60)
    return duration or 24 * 60


def shift_touches_lunch(start_time, end_time):
    start = _minutes_from_time(start_time)
    end = _minutes_from_time(end_time)
    # Un turno que empieza a las 14:00 o después no descuenta almuerzo.
    if start >= LUNCH_END_MINUTES:
        return False
    if end <= start:
        return start < LUNCH_END_MINUTES or end > LUNCH_START_MINUTES
    return start < LUNCH_END_MINUTES and end > LUNCH_START_MINUTES


def shift_metrics(start_time, end_time):
    lunch_minutes = 0
    if (
        _shift_duration(start_time, end_time) >= LUNCH_MINIMUM_SHIFT_MINUTES
        and shift_touches_lunch(start_time, end_time)
    ):
        lunch_minutes = LUNCH_MINUTES
    return shift_segments_metrics(
        ((start_time, end_time),), lunch_minutes=lunch_minutes
    )


def shift_segments_metrics(segments, lunch_minutes=0):
    worked_minutes = 0
    regular_minutes_remaining = REGULAR_DAY_MINUTES + lunch_minutes
    daytime_gross = nighttime_gross = night_surcharge = 0
    for start_time, end_time in segments:
        start = _minutes_from_time(start_time)
        end = _minutes_from_time(end_time)
        duration = (end - start) % (24 * 60)
        if duration == 0:
            duration = 24 * 60
        overtime_start = min(regular_minutes_remaining, duration)
        for offset in range(duration):
            clock_minute = (start + offset) % (24 * 60)
            is_daytime = (
                DAY_SHIFT_START_HOUR * 60
                <= clock_minute
                < DAY_SHIFT_END_HOUR * 60
            )
            if not is_daytime:
                night_surcharge += 1
            if offset < overtime_start:
                continue
            if is_daytime:
                daytime_gross += 1
            else:
                nighttime_gross += 1
        regular_minutes_remaining = max(0, regular_minutes_remaining - duration)
        worked_minutes += duration

    worked_minutes = max(0, worked_minutes - lunch_minutes)
    overtime = daytime_gross + nighttime_gross
    return (
        worked_minutes / 60,
        overtime / 60,
        daytime_gross / 60,
        nighttime_gross / 60,
        night_surcharge / 60,
    )


def assignment_period_metrics(people, assignments):
    person_rows = {}
    for index, assignment in enumerate(assignments):
        _, person_id, branch_id, start_time, end_time = assignment[:5]
        actual_start_time = assignment[5] if len(assignment) > 5 else None
        novelty_kind = assignment[6] if len(assignment) > 6 else None
        assignment_type = assignment[8] if len(assignment) > 8 else "work"
        start_time_2 = assignment[9] if len(assignment) > 9 else None
        end_time_2 = assignment[10] if len(assignment) > 10 else None
        actual_start_time_2 = assignment[11] if len(assignment) > 11 else None
        if branch_id is None or not start_time or not end_time:
            continue
        if novelty_kind in ("did_not_attend", "calamity"):
            continue
        is_split_shift = (
            assignment_type == "split_shift" and start_time_2 and end_time_2
        )
        lunch_minutes = 0
        if (
            not is_split_shift
            and _shift_duration(start_time, end_time) >= LUNCH_MINIMUM_SHIFT_MINUTES
            and shift_touches_lunch(actual_start_time or start_time, end_time)
        ):
            lunch_minutes = LUNCH_MINUTES
        segments = [(actual_start_time or start_time, end_time)]
        if is_split_shift:
            segments.append((actual_start_time_2 or start_time_2, end_time_2))
        metrics = shift_segments_metrics(segments, lunch_minutes=lunch_minutes)
        person_rows.setdefault(person_id, []).append({
            "index": index,
            "worked": round(metrics[0] * 60),
            "daytime_gross": round(metrics[2] * 60),
            "nighttime_gross": round(metrics[3] * 60),
            "night_surcharge": round(metrics[4] * 60),
            "daytime_shortfall": max(0, REGULAR_DAY_MINUTES - round(metrics[0] * 60)),
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
                "night_surcharge": row["night_surcharge"],
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
            "night_surcharge": 0,
        }
        for person in people
    }
    for index, metrics in daily_metrics.items():
        person_id = assignments[index][1]
        person_minutes = period_minutes[person_id]
        person_minutes["days"] += 1
        for key in ("worked", "overtime", "daytime", "nighttime", "night_surcharge"):
            person_minutes[key] += metrics[key]

    summaries = {}
    totals = {
        "days": 0,
        "worked": 0.0,
        "overtime": 0.0,
        "daytime": 0.0,
        "nighttime": 0.0,
        "night_surcharge": 0.0,
    }
    for person_id, values in period_minutes.items():
        summary = {
            "days": values["days"],
            "worked": values["worked"] / 60,
            "overtime": values["overtime"] / 60,
            "daytime": values["daytime"] / 60,
            "nighttime": values["nighttime"] / 60,
            "night_surcharge": values["night_surcharge"] / 60,
        }
        summaries[person_id] = summary
        for key, value in summary.items():
            totals[key] += value
    return summaries, totals
