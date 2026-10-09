import re

from django import forms
from .models import AssignmentNovelty, Branch, Person


BRANCH_PALETTE = (
    "#2F6FED", "#12A37F", "#E59A1D", "#8B5CF6", "#E5534B", "#14A9C2",
    "#7FA81B", "#DB4F8E", "#5865F2", "#D9772B", "#3E9B8F", "#A16B4A",
)


class PersonForm(forms.Form):
    name = forms.CharField(max_length=200, label="Nombre completo")
    dni = forms.CharField(max_length=100, required=False, label="DNI (opcional)")
    vacation_start = forms.DateField(
        required=False,
        label="Desde",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    vacation_end = forms.DateField(
        required=False,
        label="Hasta",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )

    def __init__(self, *args, person=None, **kwargs):
        self.person = person
        initial = kwargs.setdefault("initial", {})
        if person:
            initial.update({
                "name": person.name,
                "dni": person.dni or "",
                "vacation_start": person.vacation_start,
                "vacation_end": person.vacation_end,
            })
        super().__init__(*args, **kwargs)
        self._style_widgets()

    def _style_widgets(self):
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())

    def clean_dni(self):
        return " ".join(self.cleaned_data.get("dni", "").split()) or None

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("vacation_start")
        end = cleaned.get("vacation_end")
        if bool(start) != bool(end):
            raise forms.ValidationError("Selecciona ambas fechas de vacaciones o quita el período.")
        if start and end and start > end:
            self.add_error("vacation_end", "La fecha final debe ser igual o posterior a la inicial.")

        name = cleaned.get("name")
        dni = cleaned.get("dni")
        people = Person.objects.all()
        if self.person:
            people = people.exclude(pk=self.person.pk)
        if name and not dni and people.filter(name__iexact=name).exists():
            self.add_error("name", "Ya existe una persona con ese nombre. Agrega su DNI para diferenciarla.")
        if dni and people.filter(dni__iexact=dni).exists():
            self.add_error("dni", "Ya existe una persona con ese DNI.")
        return cleaned


class BranchForm(forms.Form):
    name = forms.CharField(max_length=200, label="Nombre de la sucursal")
    color = forms.ChoiceField(choices=[(color, color) for color in BRANCH_PALETTE], label="Color")

    def __init__(self, *args, branch=None, **kwargs):
        self.branch = branch
        initial = kwargs.setdefault("initial", {})
        if branch:
            initial.update({"name": branch.name, "color": branch.color})
        elif "color" not in initial:
            initial["color"] = BRANCH_PALETTE[0]
        super().__init__(*args, **kwargs)
        self._style_widgets()

    def _style_widgets(self):
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())

    def clean(self):
        cleaned = super().clean()
        name = cleaned.get("name")
        branches = Branch.objects.all()
        if self.branch:
            branches = branches.exclude(pk=self.branch.pk)
        if name and branches.filter(name__iexact=name).exists():
            self.add_error("name", "Ya existe una sucursal con ese nombre.")
        return cleaned


class AssignmentForm(forms.Form):
    STATUS_CHOICES = (
        ("work", "Turno"),
        ("rest", "Descanso"),
        ("incapacity", "Incapacidad"),
        ("unassigned", "Sin asignar"),
    )
    status = forms.ChoiceField(choices=STATUS_CHOICES, label="Tipo", initial="work")
    branch = forms.ModelChoiceField(queryset=Branch.objects.none(), required=False, label="Sucursal")
    start_time = forms.CharField(
        required=False,
        label="Inicio",
        widget=forms.TextInput(attrs={
            "placeholder": "12:00",
            "maxlength": "5",
            "inputmode": "numeric",
            "pattern": r"(?:[01]\d|2[0-3]):[0-5]\d",
            "title": "Usa el formato de 24 horas HH:MM, por ejemplo 12:00.",
            "autocomplete": "off",
        }),
    )
    end_time = forms.CharField(
        required=False,
        label="Fin",
        widget=forms.TextInput(attrs={
            "placeholder": "17:00",
            "maxlength": "5",
            "inputmode": "numeric",
            "pattern": r"(?:[01]\d|2[0-3]):[0-5]\d",
            "title": "Usa el formato de 24 horas HH:MM, por ejemplo 17:00.",
            "autocomplete": "off",
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["branch"].queryset = Branch.objects.all()
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"

    def clean_start_time(self):
        value = self.cleaned_data.get("start_time", "").strip()
        if value and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise forms.ValidationError("Usa formato HH:MM.")
        return value

    def clean_end_time(self):
        value = self.cleaned_data.get("end_time", "").strip()
        if value and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise forms.ValidationError("Usa formato HH:MM.")
        return value

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("status") == "work":
            if not cleaned.get("branch"):
                self.add_error("branch", "Selecciona una sucursal.")
            if not cleaned.get("start_time"):
                self.add_error("start_time", "Indica la hora de inicio.")
            if not cleaned.get("end_time"):
                self.add_error("end_time", "Indica la hora de fin.")
            if cleaned.get("start_time") and cleaned.get("start_time") == cleaned.get("end_time"):
                self.add_error("end_time", "La hora de inicio y la hora de fin no pueden ser iguales.")
        return cleaned


class AnalysisPasswordForm(forms.Form):
    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password"].widget.attrs["class"] = "form-control"


class LateArrivalForm(forms.Form):
    NO_NOVELTY = ""

    kind = forms.ChoiceField(
        required=False,
        choices=(
            (NO_NOVELTY, "Sin novedad"),
            *AssignmentNovelty.KIND_CHOICES,
        ),
        label="Tipo de novedad",
        initial=AssignmentNovelty.LATE_ARRIVAL,
    )
    actual_start_time = forms.TimeField(
        required=False,
        label="Hora real de llegada",
        input_formats=["%H:%M"],
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "00:00",
                "maxlength": "5",
                "inputmode": "numeric",
                "pattern": r"(?:[01]\d|2[0-3]):[0-5]\d",
                "title": "Usa el formato de 24 horas HH:MM, por ejemplo 09:30.",
                "autocomplete": "off",
                "data-novelty-late-field": "",
            },
        ),
    )
    observation = forms.CharField(
        required=False,
        max_length=1000,
        label="Observación (opcional)",
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
        }),
    )

    def __init__(self, *args, start_time, end_time, **kwargs):
        self.start_time = start_time
        self.end_time = end_time
        super().__init__(*args, **kwargs)
        self.fields["kind"].widget.attrs.update({
            "class": "form-control",
            "data-novelty-kind-select": "",
        })

    def clean_actual_start_time(self):
        if self.cleaned_data.get("kind") != AssignmentNovelty.LATE_ARRIVAL:
            return None
        raw_value = self.data.get("actual_start_time", "")
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", raw_value):
            raise forms.ValidationError("Usa formato HH:MM, por ejemplo 09:30.")
        actual_time = self.cleaned_data["actual_start_time"]
        start_minutes = int(self.start_time[:2]) * 60 + int(self.start_time[3:])
        end_minutes = int(self.end_time[:2]) * 60 + int(self.end_time[3:])
        actual_minutes = actual_time.hour * 60 + actual_time.minute
        duration = (end_minutes - start_minutes) % (24 * 60)
        arrival_offset = (actual_minutes - start_minutes) % (24 * 60)
        if not 0 < arrival_offset < duration:
            raise forms.ValidationError(
                "La hora real debe ser posterior al inicio del turno y anterior a su fin."
            )
        return actual_time

    def clean_observation(self):
        return self.cleaned_data["observation"].strip()
