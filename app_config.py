"""Configuración y utilidades compartidas de la aplicación."""
import os
import re
from datetime import date, timedelta

import flet as ft

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "turnos.db")

DAYS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
WORK_SCHEDULES = [
    ("06:00", "14:00"),
    ("08:00", "13:00"),
    ("13:00", "18:00"),
    ("14:00", "22:00"),
    ("22:00", "06:00"),
]
LEGACY_SHIFTS = {
    "Mañana": ("06:00", "14:00"),
    "Tarde": ("14:00", "22:00"),
    "Noche": ("22:00", "06:00"),
}
REST_COLOR = "#8A929C"
SELECTED_WEEK_KEY = "turnos.selected_week"
ANALYSIS_PASSWORD = "pao123"
BRANCH_PALETTE = [
    "#2F6FED", "#12A37F", "#E59A1D", "#8B5CF6", "#E5534B", "#14A9C2",
    "#7FA81B", "#DB4F8E", "#5865F2", "#D9772B", "#3E9B8F", "#A16B4A",
]
AVATAR_COLORS = ["#2F6FED", "#12A37F", "#E59A1D", "#8B5CF6", "#E5534B", "#14A9C2", "#DB4F8E", "#7FA81B"]
SEED_PEOPLE = [
    "Ana Torres", "Luis Pérez", "María Gómez", "Carlos Ruiz", "Sofía Díaz",
    "Jorge Castro", "Lucía Vega", "Pedro Silva", "Valeria Mora", "Diego Rojas",
    "Camila Núñez", "Andrés Soto", "Paula Ibarra", "Martín Ortiz", "Elena Paz",
    "Raúl Medina", "Natalia Cruz", "Hugo Salas", "Daniela León", "Tomás Rey",
]
SEED_BRANCHES = [
    "Centro", "Norte", "Sur", "Este", "Oeste", "Plaza Mayor",
    "Aeropuerto", "Universidad", "Terminal", "Puerto", "Mercado",
]


def normalize_time(value):
    """Devuelve HH:MM o None si el valor no es una hora válida."""
    text = (value or "").strip()
    match = re.fullmatch(r"(\d{1,2}):([0-5]\d)", text)
    if not match:
        return None
    hour = int(match.group(1))
    if hour > 23:
        return None
    return f"{hour:02d}:{match.group(2)}"


def clean_dni(value):
    value = " ".join(str(value or "").split())
    return value or None


def _pick_color(*names):
    for name in names:
        color = getattr(ft.Colors, name, None)
        if color is not None:
            return color
    return ft.Colors.SURFACE


PAGE_BG = _pick_color("SURFACE_CONTAINER_LOW", "SURFACE_CONTAINER", "SURFACE_CONTAINER_HIGHEST")


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())
