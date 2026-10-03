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
