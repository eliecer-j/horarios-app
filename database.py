"""Acceso a datos SQLite para personas, sucursales y turnos."""
import random
import re
import sqlite3
from datetime import date, timedelta

from app_config import (
    BRANCH_PALETTE,
    LEGACY_SHIFTS,
    SEED_BRANCHES,
    SEED_PEOPLE,
    WORK_SCHEDULES,
    clean_dni,
    monday_of,
    normalize_time,
)


class Database:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA busy_timeout = 5000")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_schema()
        self._seed_once()

    def _columns(self, table):
        return [r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")]

    def _has_unique_single_column(self, table, column):
        for idx in self.conn.execute(f"PRAGMA index_list({table})"):
            if not idx["unique"]:
                continue
            columns = [r["name"] for r in self.conn.execute(f"PRAGMA index_info({idx['name']})")]
            if columns == [column]:
                return True
        return False

    def _migrate_schema(self):
        """Migra bases creadas por la versión anterior sin perder información."""
        people_columns = self._columns("people")
        assignments_columns = self._columns("assignments")
        migrate_people = bool(people_columns) and (
            "dni" not in people_columns or self._has_unique_single_column("people", "name")
        )
        migrate_assignments = bool(assignments_columns) and "shift" in assignments_columns

        if not migrate_people and not migrate_assignments:
            return

        self.conn.execute("PRAGMA foreign_keys = OFF")
        try:
            with self.conn:
                if migrate_people:
                    dni_expr = "NULLIF(TRIM(COALESCE(dni, '')), '')" if "dni" in people_columns else "NULL"
                    self.conn.execute(
                        """
                        CREATE TABLE people_migration (
                            id   INTEGER PRIMARY KEY AUTOINCREMENT,
                            name TEXT NOT NULL,
                            dni  TEXT
                        )
                        """
                    )
                    self.conn.execute(
                        f"INSERT INTO people_migration (id, name, dni) SELECT id, name, {dni_expr} FROM people"
                    )
                    self.conn.execute("DROP TABLE people")
                    self.conn.execute("ALTER TABLE people_migration RENAME TO people")

                if migrate_assignments:
                    self.conn.execute(
                        """
                        CREATE TABLE assignments_migration (
                            week_start TEXT    NOT NULL,
                            person_id  INTEGER NOT NULL REFERENCES people(id)   ON DELETE CASCADE,
                            day        INTEGER NOT NULL CHECK (day BETWEEN 0 AND 6),
                            branch_id  INTEGER REFERENCES branches(id) ON DELETE CASCADE,
                            start_time TEXT,
                            end_time   TEXT,
                            PRIMARY KEY (week_start, person_id, day),
                            CHECK ((start_time IS NULL AND end_time IS NULL AND branch_id IS NULL)
                                OR (start_time IS NOT NULL AND end_time IS NOT NULL AND branch_id IS NOT NULL))
                        )
                        """
                    )
                    rows = self.conn.execute(
                        "SELECT week_start, person_id, day, branch_id, shift FROM assignments"
                    ).fetchall()
                    for row in rows:
                        old_shift = row["shift"]
                        if old_shift == "Descanso" or row["branch_id"] is None:
                            branch_id, start_time, end_time = None, None, None
                        else:
                            branch_id = row["branch_id"]
                            start_time, end_time = LEGACY_SHIFTS.get(old_shift, ("08:00", "17:00"))
                            match = re.fullmatch(
                                r"\s*(\d{1,2}:\d{2})\s*[–-]\s*(\d{1,2}:\d{2})\s*", old_shift or ""
                            )
                            if match:
                                parsed_start = normalize_time(match.group(1))
                                parsed_end = normalize_time(match.group(2))
                                if parsed_start and parsed_end:
                                    start_time, end_time = parsed_start, parsed_end
                        self.conn.execute(
                            "INSERT INTO assignments_migration VALUES (?,?,?,?,?,?)",
                            (row["week_start"], row["person_id"], row["day"], branch_id, start_time, end_time),
                        )
                    self.conn.execute("DROP TABLE assignments")
                    self.conn.execute("ALTER TABLE assignments_migration RENAME TO assignments")
        finally:
            self.conn.execute("PRAGMA foreign_keys = ON")

    def _create_schema(self):
        self._migrate_schema()
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS people (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                dni  TEXT,
                vacation_start TEXT,
                vacation_end   TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS ux_people_dni
                ON people(dni) WHERE dni IS NOT NULL AND dni <> '';

            CREATE TABLE IF NOT EXISTS branches (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                name  TEXT NOT NULL UNIQUE,
                color TEXT NOT NULL
            );

            -- Una fila por persona y día. Sin fila = sin asignar; una fila con
            -- sucursal y horas nulas representa un descanso.
            CREATE TABLE IF NOT EXISTS assignments (
                week_start TEXT    NOT NULL,
                person_id  INTEGER NOT NULL REFERENCES people(id)   ON DELETE CASCADE,
                day        INTEGER NOT NULL CHECK (day BETWEEN 0 AND 6),
                branch_id  INTEGER REFERENCES branches(id) ON DELETE CASCADE,
                start_time TEXT,
                end_time   TEXT,
                PRIMARY KEY (week_start, person_id, day),
                CHECK ((start_time IS NULL AND end_time IS NULL AND branch_id IS NULL)
                    OR (start_time IS NOT NULL AND end_time IS NOT NULL AND branch_id IS NOT NULL))
            );
            CREATE INDEX IF NOT EXISTS idx_assign_branch
                ON assignments (week_start, branch_id, day);
            CREATE INDEX IF NOT EXISTS idx_assign_person
                ON assignments (week_start, person_id);
            """
        )
        people_columns = self._columns("people")
        with self.conn:
            if "vacation_start" not in people_columns:
                self.conn.execute("ALTER TABLE people ADD COLUMN vacation_start TEXT")
            if "vacation_end" not in people_columns:
                self.conn.execute("ALTER TABLE people ADD COLUMN vacation_end TEXT")
        self.conn.commit()

    def _seed_once(self):
        # user_version evita volver a sembrar si el usuario vacía las tablas
        if self.conn.execute("PRAGMA user_version").fetchone()[0] != 0:
            return
        with self.conn:
            self.conn.executemany(
                "INSERT OR IGNORE INTO people (name, dni) VALUES (?, NULL)",
                [(name,) for name in SEED_PEOPLE],
            )
            self.conn.executemany(
                "INSERT OR IGNORE INTO branches (name, color) VALUES (?, ?)",
                [(name, BRANCH_PALETTE[i % len(BRANCH_PALETTE)]) for i, name in enumerate(SEED_BRANCHES)],
            )
            self.conn.execute("PRAGMA user_version = 1")
        self.autogenerate(monday_of(date.today()).isoformat())

    def people(self):
        return [
            (row["id"], row["name"], row["dni"] or "")
            for row in self.conn.execute(
                "SELECT id, name, dni FROM people ORDER BY lower(name), name, COALESCE(dni, ''), id"
            )
        ]

    def vacations(self):
        return {
            row["id"]: (row["vacation_start"], row["vacation_end"])
            for row in self.conn.execute(
                "SELECT id, vacation_start, vacation_end FROM people "
                "WHERE vacation_start IS NOT NULL AND vacation_end IS NOT NULL"
            )
        }

    def is_on_vacation(self, pid, assigned_date):
        row = self.conn.execute(
            "SELECT vacation_start, vacation_end FROM people WHERE id=?", (pid,)
        ).fetchone()
        return bool(
            row and row["vacation_start"] and row["vacation_end"]
            and row["vacation_start"] <= assigned_date.isoformat() <= row["vacation_end"]
        )

    def _name_conflict(self, name, exclude_id=None):
        params = [name]
        sql = "SELECT id FROM people WHERE lower(name) = lower(?)"
        if exclude_id is not None:
            sql += " AND id <> ?"
            params.append(exclude_id)
        return self.conn.execute(sql, params).fetchone() is not None

    def add_person(self, name, dni=None, vacation_start=None, vacation_end=None):
        dni = clean_dni(dni)
        if dni is None and self._name_conflict(name):
            raise ValueError("Ya existe una persona con ese nombre. Agrega su DNI para diferenciarla.")
        with self.conn:
            self.conn.execute(
                "INSERT INTO people (name, dni, vacation_start, vacation_end) VALUES (?, ?, ?, ?)",
                (name, dni, vacation_start, vacation_end),
            )

    def rename_person(self, pid, name, dni=None, vacation_start=None, vacation_end=None):
        dni = clean_dni(dni)
        if dni is None and self._name_conflict(name, exclude_id=pid):
            raise ValueError("Ya existe otra persona con ese nombre. Agrega su DNI para diferenciarla.")
        with self.conn:
            self.conn.execute(
                "UPDATE people SET name=?, dni=?, vacation_start=?, vacation_end=? WHERE id=?",
                (name, dni, vacation_start, vacation_end, pid),
            )
            removed_assignments = 0
            if vacation_start and vacation_end:
                rows = self.conn.execute(
                    "SELECT week_start, day FROM assignments WHERE person_id=?", (pid,)
                ).fetchall()
                vacation_start_date = date.fromisoformat(vacation_start)
                vacation_end_date = date.fromisoformat(vacation_end)
                for row in rows:
                    assigned_date = date.fromisoformat(row["week_start"]) + timedelta(days=row["day"])
                    if vacation_start_date <= assigned_date <= vacation_end_date:
                        cursor = self.conn.execute(
                            "DELETE FROM assignments WHERE week_start=? AND person_id=? AND day=?",
                            (row["week_start"], pid, row["day"]),
                        )
                        removed_assignments += cursor.rowcount
        return removed_assignments

    def delete_person(self, pid):
        with self.conn:
            self.conn.execute("DELETE FROM people WHERE id=?", (pid,))

    def branches(self):
        return [
            (row["id"], row["name"], row["color"])
            for row in self.conn.execute("SELECT id, name, color FROM branches ORDER BY name")
        ]

    def add_branch(self, name, color):
        with self.conn:
            self.conn.execute("INSERT INTO branches (name, color) VALUES (?, ?)", (name, color))

    def update_branch(self, bid, name, color):
        with self.conn:
            self.conn.execute("UPDATE branches SET name=?, color=? WHERE id=?", (name, color, bid))

    def delete_branch(self, bid):
        with self.conn:
            self.conn.execute("DELETE FROM branches WHERE id=?", (bid,))

    def week(self, week_start):
        """{(person_id, day): (branch_id | None, start_time | None, end_time | None)}"""
        rows = self.conn.execute(
            "SELECT person_id, day, branch_id, start_time, end_time "
            "FROM assignments WHERE week_start=?",
            (week_start,),
        )
        return {
            (row["person_id"], row["day"]): (row["branch_id"], row["start_time"], row["end_time"])
            for row in rows
        }

    def assignments_between(self, start_date, end_date):
        """Devuelve turnos asignados cuyas fechas caen dentro del periodo inclusivo."""
        earliest_week = (start_date - timedelta(days=6)).isoformat()
        rows = self.conn.execute(
            """
            SELECT week_start, person_id, day, branch_id, start_time, end_time
            FROM assignments
            WHERE week_start BETWEEN ? AND ?
            ORDER BY week_start, day, person_id
            """,
            (earliest_week, end_date.isoformat()),
        )
        assignments = []
        for row in rows:
            assigned_date = date.fromisoformat(row["week_start"]) + timedelta(days=row["day"])
            if start_date <= assigned_date <= end_date:
                assignments.append((assigned_date, row["person_id"], row["branch_id"],
                                    row["start_time"], row["end_time"]))
        return assignments

    def available_weeks(self):
        return [
            row["week_start"]
            for row in self.conn.execute("SELECT DISTINCT week_start FROM assignments ORDER BY week_start")
        ]

    def set_assignment(self, week_start, pid, day, branch_id, start_time, end_time):
        assigned_date = date.fromisoformat(week_start) + timedelta(days=day)
        if self.is_on_vacation(pid, assigned_date):
            raise ValueError("No se pueden asignar turnos durante las vacaciones.")
        if branch_id is None:
            start_time, end_time = None, None
        else:
            start_time = normalize_time(start_time)
            end_time = normalize_time(end_time)
            if not start_time or not end_time:
                raise ValueError("Los horarios deben tener formato HH:MM.")
            if start_time == end_time:
                raise ValueError("La hora de inicio y la hora de fin no pueden ser iguales.")
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO assignments VALUES (?,?,?,?,?,?)",
                (week_start, pid, day, branch_id, start_time, end_time),
            )

    def clear_assignment(self, week_start, pid, day):
        with self.conn:
            self.conn.execute(
                "DELETE FROM assignments WHERE week_start=? AND person_id=? AND day=?",
                (week_start, pid, day),
            )

    def clear_week(self, week_start):
        with self.conn:
            self.conn.execute("DELETE FROM assignments WHERE week_start=?", (week_start,))

    def autogenerate(self, week_start):
        rng = random.Random()
        branch_ids = [branch[0] for branch in self.branches()]
        rows = []
        if branch_ids:
            for pid, _, _ in self.people():
                rest_days = rng.sample(range(7), 2)
                home = rng.choice(branch_ids)
                for day_index in range(7):
                    assigned_date = date.fromisoformat(week_start) + timedelta(days=day_index)
                    if self.is_on_vacation(pid, assigned_date):
                        continue
                    if day_index in rest_days:
                        rows.append((week_start, pid, day_index, None, None, None))
                    else:
                        branch_id = home if rng.random() < 0.55 else rng.choice(branch_ids)
                        start_time, end_time = rng.choice(WORK_SCHEDULES)
                        rows.append((week_start, pid, day_index, branch_id, start_time, end_time))
        with self.conn:
            self.conn.execute("DELETE FROM assignments WHERE week_start=?", (week_start,))
            self.conn.executemany("INSERT INTO assignments VALUES (?,?,?,?,?,?)", rows)

    def copy_week(self, src, dst):
        source_rows = self.conn.execute(
            "SELECT person_id, day, branch_id, start_time, end_time "
            "FROM assignments WHERE week_start=?",
            (src,),
        ).fetchall()
        with self.conn:
            self.conn.execute("DELETE FROM assignments WHERE week_start=?", (dst,))
            for row in source_rows:
                assigned_date = date.fromisoformat(dst) + timedelta(days=row["day"])
                if self.is_on_vacation(row["person_id"], assigned_date):
                    continue
                self.conn.execute(
                    "INSERT INTO assignments VALUES (?,?,?,?,?,?)",
                    (dst, row["person_id"], row["day"], row["branch_id"],
                     row["start_time"], row["end_time"]),
                )
