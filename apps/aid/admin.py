"""Operational records are read-only here; staff use workflow forms."""
from django.contrib import admin
from .models import Category, Item, HelpRequest, Reservation, VolunteerTask, Transfer, AuditLog

admin.site.site_header = 'NordSec · администрирование'
admin.site.site_title = 'NordSec'
admin.site.index_title = 'Справочники и техническое управление'


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'order']
    prepopulated_fields = {'slug': ['name']}

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return request.user.is_coordinator

    def has_view_permission(self, request, obj=None):
        return request.user.is_coordinator

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


for model in [Item, HelpRequest, Reservation, VolunteerTask, Transfer, AuditLog]:
    admin.site.register(model, ReadOnlyAdmin)
