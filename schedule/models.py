from django.db import models


class Person(models.Model):
    name = models.CharField(max_length=200)
    dni = models.CharField(max_length=100, null=True, blank=True)
    vacation_start = models.DateField(null=True, blank=True)
    vacation_end = models.DateField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "people"
        ordering = ("name", "id")

    def __str__(self):
        return self.name


class Branch(models.Model):
    name = models.CharField(max_length=200, unique=True)
    color = models.CharField(max_length=7)

    class Meta:
        managed = False
        db_table = "branches"
        ordering = ("name",)

    def __str__(self):
        return self.name


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
    observation = models.TextField(blank=True)

    class Meta:
        db_table = "assignment_novelties"
        constraints = [
            models.UniqueConstraint(
                fields=("week_start", "person_id", "day"),
                name="unique_assignment_novelty",
            ),
            models.CheckConstraint(
                condition=models.Q(day__gte=0, day__lte=6),
                name="assignment_novelty_day_range",
            ),
        ]
