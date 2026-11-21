from django.contrib import admin

from .models import AssignmentNovelty, AuditLog, Branch, Person, VacationPeriod


admin.site.site_header = "Turnos · Administración"
admin.site.site_title = "Turnos"
admin.site.index_title = "Administración"


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("name", "dni", "is_active", "vacation_start", "vacation_end")
    list_filter = ("is_active",)
    search_fields = ("name", "dni")
    ordering = ("name", "id")

    def delete_queryset(self, request, queryset):
        # El borrado masivo no llama a Model.delete(); lo forzamos objeto por objeto.
        for obj in queryset:
            obj.delete()


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "color", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            obj.delete()


@admin.register(VacationPeriod)
class VacationPeriodAdmin(admin.ModelAdmin):
    list_display = ("person_id", "start_date", "end_date")
    ordering = ("-start_date",)


@admin.register(AssignmentNovelty)
class AssignmentNoveltyAdmin(admin.ModelAdmin):
    list_display = ("week_start", "person_id", "day", "kind", "archived_at")
    list_filter = ("kind", "week_start")
    ordering = ("-week_start", "person_id", "day")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "ip_address", "action", "details")
    list_filter = ("action",)
    search_fields = ("action", "details", "user__username")
    ordering = ("-created_at", "-pk")
    readonly_fields = ("created_at", "user", "ip_address", "action", "details")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
