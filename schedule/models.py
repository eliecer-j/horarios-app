from datetime import date

from django.conf import settings
from django.db import connection, models, transaction
from django.utils import timezone


class Person(models.Model):
    name = models.CharField(max_length=200)
    dni = models.CharField(max_length=100, null=True, blank=True)
    vacation_start = models.DateField(null=True, blank=True)
    vacation_end = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "people"
        ordering = ("name", "id")

    def __str__(self):
        return self.name

    def delete(self, *args, **kwargs):
        """Limpia los datos relacionados antes de borrar a la persona.

        Se ejecuta aunque el borrado venga del administrador de Django.
        """
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM assignments WHERE person_id = %s", [self.pk])
            AssignmentNovelty.objects.filter(person_id=self.pk).delete()
            VacationPeriod.objects.filter(person_id=self.pk).delete()
            return super().delete(*args, **kwargs)


class VacationPeriod(models.Model):
    person_id = models.IntegerField()
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        db_table = "vacation_periods"
        constraints = [
            models.UniqueConstraint(
                fields=("person_id", "start_date", "end_date"),
                name="unique_person_vacation_period",
            ),
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="vacation_period_date_order",
            ),
        ]


class Branch(models.Model):
    name = models.CharField(max_length=200, unique=True)
    color = models.CharField(max_length=7)
    is_active = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "branches"
        ordering = ("name",)

    def __str__(self):
        return self.name

    def delete(self, *args, **kwargs):
        """Archiva las novedades y borra los turnos de la sucursal.

        Se ejecuta aunque el borrado venga del administrador de Django.
        """
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT week_start, person_id, day FROM assignments WHERE branch_id = %s",
                    [self.pk],
                )
                assignment_keys = cursor.fetchall()
                cursor.execute("DELETE FROM assignments WHERE branch_id = %s", [self.pk])
            for week_start, person_id, day in assignment_keys:
                AssignmentNovelty.objects.filter(
                    week_start=date.fromisoformat(week_start),
                    person_id=person_id,
                    day=day,
                ).filter(archived_at__isnull=True).update(archived_at=timezone.now())
            return super().delete(*args, **kwargs)


class AssignmentNovelty(models.Model):
    LATE_ARRIVAL = "late_arrival"
    DID_NOT_ATTEND = "did_not_attend"
    CALAMITY = "calamity"
    KIND_CHOICES = (
        (LATE_ARRIVAL, "Llegada tarde"),
        (DID_NOT_ATTEND, "No se presentó"),
        (CALAMITY, "Calamidad"),
    )

    week_start = models.DateField()
    person_id = models.IntegerField()
    day = models.PositiveSmallIntegerField()
    kind = models.CharField(max_length=24, choices=KIND_CHOICES, default=LATE_ARRIVAL)
    actual_start_time = models.TimeField(null=True, blank=True)
    actual_start_time_2 = models.TimeField(null=True, blank=True)
    observation = models.TextField(blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "assignment_novelties"
        constraints = [
            models.UniqueConstraint(
                fields=("week_start", "person_id", "day"),
                condition=models.Q(archived_at__isnull=True),
                name="unique_assignment_novelty",
            ),
            models.CheckConstraint(
                condition=models.Q(day__gte=0, day__lte=6),
                name="assignment_novelty_day_range",
            ),
        ]


class AuditLog(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    action = models.CharField(max_length=120)
    details = models.TextField(blank=True)

    class Meta:
        db_table = "audit_logs"
        ordering = ("-created_at", "-pk")

    @property
    def user_label(self):
        if not self.user_id:
            return "—"
        return self.user.get_username()
