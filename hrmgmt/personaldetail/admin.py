from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from django.db import transaction

from .models import (
    Province, District, Municipality, Ward,
    Post,
    Bank, BankBranch, BankAccount,
    SpecificWork,
    Person, PhoneNumber, EmailAddress
)


# -----------------------------
# Generic helpers & mixins
# -----------------------------
class NepaliReadonlyMixin:
    """Adds Nepali created/updated fields as readonly and shows them in fieldsets."""
    readonly_fields = ('created_at', 'updated_at', 'created_at_nepali', 'updated_at_nepali', 'created_by')

    def get_readonly_fields(self, request, obj=None):
        # allow superclasses to append readonly fields
        return tuple(getattr(self, 'readonly_fields', ()))


class SoftDeleteAdminActionMixin:
    """Provides admin actions for soft-delete and restore for models with is_active/deleted_at."""

    @admin.action(description='Soft-delete selected objects')
    def action_soft_delete(self, request, queryset):
        now = timezone.now()
        with transaction.atomic():
            updated = queryset.update(is_active=False, deleted_at=now)
        self.message_user(request, f"Soft-deleted {updated} objects.")

    @admin.action(description='Restore selected objects')
    def action_restore(self, request, queryset):
        with transaction.atomic():
            updated = queryset.update(is_active=True, deleted_at=None)
        self.message_user(request, f"Restored {updated} objects.")


# -----------------------------
# Inlines
# -----------------------------
class DistrictInline(admin.TabularInline):
    model = District
    extra = 0
    fields = ('name', 'slug', 'created_at',)
    readonly_fields = ('created_at',)
    show_change_link = True


class MunicipalityInline(admin.TabularInline):
    model = Municipality
    extra = 0
    fields = ('name', 'slug', 'created_at',)
    readonly_fields = ('created_at',)
    show_change_link = True


class WardInline(admin.TabularInline):
    model = Ward
    extra = 0
    fields = ('ward_no', 'slug', 'created_at',)
    readonly_fields = ('created_at',)
    show_change_link = True


class BankBranchInline(admin.TabularInline):
    model = BankBranch
    extra = 0
    fields = ('name', 'ward', 'address_line', 'slug', 'created_at')
    readonly_fields = ('created_at',)
    show_change_link = True
    autocomplete_fields = ('ward',)


class PhoneNumberInline(admin.TabularInline):
    model = PhoneNumber
    extra = 0
    fields = ('number', 'is_primary', 'created_at')
    readonly_fields = ('created_at',)


class EmailAddressInline(admin.TabularInline):
    model = EmailAddress
    extra = 0
    fields = ('email', 'is_primary', 'created_at')
    readonly_fields = ('created_at',)


class BankAccountInline(admin.TabularInline):
    model = BankAccount
    extra = 0
    fields = ('bank', 'branch', 'account_number', 'is_primary', 'created_at')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('bank', 'branch')


# -----------------------------
# Province / District / Municipality / Ward admins
# -----------------------------
@admin.register(Province)
class ProvinceAdmin(NepaliReadonlyMixin, admin.ModelAdmin):
    list_display = ('name', 'slug', 'created_at', 'created_at_nepali')
    search_fields = ('name',)
    ordering = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    inlines = (DistrictInline,)
    list_per_page = 30


@admin.register(District)
class DistrictAdmin(NepaliReadonlyMixin, admin.ModelAdmin):
    list_display = ('name', 'province', 'slug', 'created_at')
    search_fields = ('name', 'province__name')
    list_filter = ('province',)
    ordering = ('province__name', 'name')
    prepopulated_fields = {'slug': ('name',)}
    inlines = (MunicipalityInline,)
    autocomplete_fields = ('province',)
    list_select_related = ('province',)


@admin.register(Municipality)
class MunicipalityAdmin(NepaliReadonlyMixin, admin.ModelAdmin):
    list_display = ('name', 'district', 'slug', 'created_at')
    search_fields = ('name', 'district__name')
    list_filter = ('district__province', 'district')
    ordering = ('district__name', 'name')
    prepopulated_fields = {'slug': ('name',)}
    inlines = (WardInline,)
    autocomplete_fields = ('district',)
    list_select_related = ('district', 'district__province')


@admin.register(Ward)
class WardAdmin(NepaliReadonlyMixin, admin.ModelAdmin):
    list_display = ('__str__', 'municipality', 'ward_no', 'slug', 'created_at')
    search_fields = ('municipality__name',)
    list_filter = ('municipality__district__province', 'municipality')
    ordering = ('municipality__name', 'ward_no')
    prepopulated_fields = {'slug': ('ward_no',)}
    autocomplete_fields = ('municipality',)
    list_select_related = ('municipality', 'municipality__district')


# -----------------------------
# Post admin
# -----------------------------
@admin.register(Post)
class PostAdmin(NepaliReadonlyMixin, admin.ModelAdmin):
    list_display = ('name', 'slug', 'symbol_preview', 'created_at')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('symbol_preview',)

    def symbol_preview(self, obj):
        if obj.symbol_image and hasattr(obj.symbol_image, 'url'):
            return format_html('<img src="{}" style="height:40px;"/>', obj.symbol_image.url)
        return '-'
    symbol_preview.short_description = 'Symbol'


# -----------------------------
# Bank / Branch / Account admin
# -----------------------------
@admin.register(Bank)
class BankAdmin(NepaliReadonlyMixin, admin.ModelAdmin):
    list_display = ('name', 'code', 'slug', 'logo_preview', 'created_at')
    search_fields = ('name', 'code')
    prepopulated_fields = {'slug': ('name',)}
    inlines = (BankBranchInline,)

    def logo_preview(self, obj):
        if obj.logo and hasattr(obj.logo, 'url'):
            return format_html('<img src="{}" style="height:40px;"/>', obj.logo.url)
        return '-'
    logo_preview.short_description = 'Logo'


@admin.register(BankBranch)
class BankBranchAdmin(NepaliReadonlyMixin, admin.ModelAdmin):
    list_display = ('name', 'bank', 'ward_display', 'address_line', 'slug', 'created_at')
    search_fields = ('name', 'bank__name', 'address_line')
    list_filter = ('bank', 'ward__municipality__district__province')
    autocomplete_fields = ('bank', 'ward')
    prepopulated_fields = {'slug': ('bank', 'name')}
    list_select_related = ('bank', 'ward', 'ward__municipality')

    def ward_display(self, obj):
        return str(obj.ward) if obj.ward else '-'
    ward_display.short_description = 'Ward'


# BankAccount managed inline under Person but also register separately for convenience
@admin.register(BankAccount)
class BankAccountAdmin(NepaliReadonlyMixin, admin.ModelAdmin):
    list_display = ('person', 'bank', 'account_number', 'branch', 'is_primary', 'created_at')
    search_fields = ('person__name', 'account_number', 'bank__name')
    list_filter = ('bank', 'is_primary')
    autocomplete_fields = ('person', 'bank', 'branch')
    list_select_related = ('person', 'bank', 'branch')


# -----------------------------
# SpecificWork admin
# -----------------------------
@admin.register(SpecificWork)
class SpecificWorkAdmin(NepaliReadonlyMixin, admin.ModelAdmin):
    list_display = ('code', 'description', 'slug', 'created_at')
    search_fields = ('code', 'description')
    prepopulated_fields = {'slug': ('code',)}


# -----------------------------
# Person admin and related inlines
# -----------------------------
@admin.register(Person)
class PersonAdmin(NepaliReadonlyMixin, SoftDeleteAdminActionMixin, admin.ModelAdmin):
    list_display = ('name', 'computer_code', 'identity_no', 'post', 'is_working', 'is_active', 'created_at')
    search_fields = ('name', 'computer_code', 'identity_no', 'post__name')
    list_filter = ('post', 'is_working', 'is_active')
    ordering = ('name',)
    inlines = (PhoneNumberInline, EmailAddressInline, BankAccountInline)
    autocomplete_fields = ('post', 'branch_address')
    prepopulated_fields = {'slug': ('name', 'computer_code')}
    actions = ('action_soft_delete', 'action_restore')
    list_select_related = ('post', 'branch_address', 'branch_address__municipality')
    fieldsets = (
        (None, {
            'fields': ('post', 'name', 'photo', 'computer_code', 'identity_no', 'slug', 'is_working')
        }),
        ('Address & Works', {
            'fields': ('branch_address', 'specific_works')
        }),
        ('Meta', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at', 'created_at_nepali', 'updated_at_nepali', 'created_by')
        }),
    )

    def get_queryset(self, request):
        # show all by default including inactive; adjust if you want to hide soft-deleted by default
        qs = super().get_queryset(request)
        return qs.select_related('post', 'branch_address')

    def full_address(self, obj):
        return obj.full_address()
    full_address.short_description = 'Full address'


# -----------------------------
# PhoneNumber and Email registered for direct management (optional)
# -----------------------------
@admin.register(PhoneNumber)
class PhoneNumberAdmin(NepaliReadonlyMixin, admin.ModelAdmin):
    list_display = ('number', 'person', 'is_primary', 'created_at')
    search_fields = ('number', 'person__name')
    autocomplete_fields = ('person',)


@admin.register(EmailAddress)
class EmailAddressAdmin(NepaliReadonlyMixin, admin.ModelAdmin):
    list_display = ('email', 'person', 'is_primary', 'created_at')
    search_fields = ('email', 'person__name')
    autocomplete_fields = ('person',)


# -----------------------------
# Final niceties
# -----------------------------
# Optionally tune the site header and index title
admin.site.site_header = 'Administration'
admin.site.site_title = 'Site Admin'
admin.site.index_title = 'Admin Dashboard'
