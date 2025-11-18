import uuid
import datetime
from django.conf import settings
from django.db import models, transaction
from django.utils.text import slugify
from django.core.validators import RegexValidator
from django.utils import timezone
from django.db.models import Q, UniqueConstraint, Index

# Optional dependency for Bikram Sambat (BS) conversion:
# pip install nepali-datetime
try:
    import nepali_datetime
    _NEPALI_AVAILABLE = True
except Exception:
    nepali_datetime = None
    _NEPALI_AVAILABLE = False

# Simple numeric validator for computer_code
DIGIT_ONLY = RegexValidator(r'^\d+$', 'Only digits are allowed.')

# ------------------------
# Utility functions
# ------------------------
def gregorian_to_nepali_string(dt: datetime.datetime) -> str:
    """
    Convert a datetime to a Nepali (Bikram Sambat) date+time string if possible.
    Fallback: formatted Gregorian local datetime string.
    Output format: "YYYY-MM-DD HH:MM:SS"
    """
    if not dt:
        return ""
    # Ensure timezone-aware and convert to current timezone
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    local_dt = timezone.localtime(dt)
    if _NEPALI_AVAILABLE:
        try:
            nd = nepali_datetime.date.from_datetime_date(local_dt.date())
            return f"{nd.year:04d}-{nd.month:02d}-{nd.day:02d} {local_dt.strftime('%H:%M:%S')}"
        except Exception:
            pass
    return local_dt.strftime('%Y-%m-%d %H:%M:%S')


def unique_slugify(instance, value, slug_field_name='slug', queryset=None, separator='-'):
    """
    Create a unique slug. If slug exists, add -1, -2, ...
    You can pass a custom queryset (e.g. scoped to a parent) to enforce uniqueness within that scope.
    """
    slug = slugify(value)[:180]
    Model = instance.__class__
    if queryset is None:
        queryset = Model._default_manager.all()
    slug_field = slug_field_name
    original_slug = slug
    next_ = 1
    if instance.pk:
        queryset = queryset.exclude(pk=instance.pk)
    while queryset.filter(**{slug_field: slug}).exists():
        slug = f"{original_slug}{separator}{next_}"
        next_ += 1
    setattr(instance, slug_field, slug)


# ------------------------
# Auditable mixin with Nepali datetime fields
# ------------------------
class AuditableModel(models.Model):
    """
    Abstract base model providing:
    - created_at (DateTimeField auto_now_add)
    - updated_at (DateTimeField auto_now)
    - created_at_nepali (CharField populated automatically)
    - updated_at_nepali (CharField populated automatically)
    - created_by (optional FK to AUTH_USER_MODEL)
    """
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)
    created_at_nepali = models.CharField(max_length=64, blank=True, editable=False)
    updated_at_nepali = models.CharField(max_length=64, blank=True, editable=False)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_%(class)ss'
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """
        Ensure Nepali string fields are set. Uses two-step save for new instances so that
        auto_now_add fields are populated before converting.
        """
        is_new = self.pk is None
        if is_new:
            # initial save to populate created_at and updated_at
            super().save(*args, **kwargs)
            # compute and persist nepali fields
            self.created_at_nepali = gregorian_to_nepali_string(self.created_at)
            self.updated_at_nepali = gregorian_to_nepali_string(self.updated_at)
            # update only nepali fields to avoid recursion issues
            super().save(update_fields=['created_at_nepali', 'updated_at_nepali'])
            return
        else:
            # normal save to update updated_at
            super().save(*args, **kwargs)
            # recompute and persist updated_at_nepali
            self.updated_at_nepali = gregorian_to_nepali_string(self.updated_at)
            super().save(update_fields=['updated_at_nepali'])


# ------------------------
# Address hierarchy
# ------------------------
class Province(AuditableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150, unique=True)
    slug = models.SlugField(max_length=180, unique=True, blank=True)

    class Meta:
        ordering = ['name']
        indexes = [Index(fields=['name']), Index(fields=['slug'])]

    def save(self, *args, **kwargs):
        if not self.slug:
            unique_slugify(self, self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class District(AuditableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    province = models.ForeignKey(Province, on_delete=models.PROTECT, related_name='districts')
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=180, blank=True)

    class Meta:
        unique_together = ('province', 'name')
        ordering = ['province__name', 'name']
        indexes = [Index(fields=['province', 'name']), Index(fields=['province', 'slug'])]
        constraints = [
            UniqueConstraint(fields=['province', 'slug'], name='unique_district_slug_per_province')
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            # scope uniqueness to province
            unique_slugify(self, self.name, queryset=District.objects.filter(province=self.province))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name}, {self.province.name}"


class Municipality(AuditableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    district = models.ForeignKey(District, on_delete=models.PROTECT, related_name='municipalities')
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=180, blank=True)

    class Meta:
        unique_together = ('district', 'name')
        ordering = ['district__name', 'name']
        indexes = [Index(fields=['district', 'name']), Index(fields=['district', 'slug'])]
        constraints = [
            UniqueConstraint(fields=['district', 'slug'], name='unique_municipality_slug_per_district')
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            unique_slugify(self, self.name, queryset=Municipality.objects.filter(district=self.district))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name}, {self.district.name}"


class Ward(AuditableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    municipality = models.ForeignKey(Municipality, on_delete=models.PROTECT, related_name='wards')
    ward_no = models.PositiveSmallIntegerField()
    slug = models.SlugField(max_length=180, blank=True)

    class Meta:
        unique_together = ('municipality', 'ward_no')
        ordering = ['municipality__name', 'ward_no']
        indexes = [Index(fields=['municipality', 'ward_no']), Index(fields=['municipality', 'slug'])]
        constraints = [
            UniqueConstraint(fields=['municipality', 'slug'], name='unique_ward_slug_per_municipality')
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            # make slug from ward number so it's predictable
            unique_slugify(self, f"ward-{self.ward_no}", queryset=Ward.objects.filter(municipality=self.municipality))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Ward {self.ward_no}, {self.municipality.name}"


# ------------------------
# Post (role/title)
# ------------------------
def symbol_image_upload_to(instance, filename):
    return f"posts/{instance.id}/{filename}"

class Post(AuditableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150, unique=True)
    symbol_image = models.ImageField(upload_to=symbol_image_upload_to, blank=True, null=True)
    slug = models.SlugField(max_length=180, unique=True, blank=True)

    class Meta:
        ordering = ['name']
        indexes = [Index(fields=['slug']), Index(fields=['name'])]

    def save(self, *args, **kwargs):
        if not self.slug:
            unique_slugify(self, self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


# ------------------------
# Bank and Branch and Account
# ------------------------
def bank_logo_upload_to(instance, filename):
    return f"banks/{instance.id}/{filename}"

class Bank(AuditableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, unique=True)
    logo = models.ImageField(upload_to=bank_logo_upload_to, blank=True, null=True)
    code = models.CharField(max_length=50, blank=True, null=True, help_text="Optional bank identifier code")
    slug = models.SlugField(max_length=180, unique=True, blank=True)

    class Meta:
        ordering = ['name']
        indexes = [Index(fields=['name']), Index(fields=['slug'])]

    def save(self, *args, **kwargs):
        if not self.slug:
            unique_slugify(self, self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class BankBranch(AuditableModel):
    """
    Represents a specific branch (location) of a bank. Branch address is normalized using Ward.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bank = models.ForeignKey(Bank, on_delete=models.CASCADE, related_name='branches')
    name = models.CharField(max_length=200, help_text="Branch display name")
    ward = models.ForeignKey(Ward, on_delete=models.PROTECT, related_name='bank_branches')
    address_line = models.CharField(max_length=255, blank=True)
    slug = models.SlugField(max_length=200, blank=True)

    class Meta:
        unique_together = ('bank', 'name', 'ward')
        indexes = [Index(fields=['bank', 'name']), Index(fields=['bank', 'slug'])]
        constraints = [
            UniqueConstraint(fields=['bank', 'slug'], name='unique_branch_slug_per_bank')
        ]

    def full_address(self):
        # Compose readable address; ward, municipality, district, province
        try:
            w = self.ward
            m = w.municipality
            d = m.district
            p = d.province
            parts = [self.address_line, f"Ward {w.ward_no}", m.name, d.name, p.name]
            return ", ".join([p for p in parts if p])
        except Exception:
            return self.address_line or str(self.ward)

    def save(self, *args, **kwargs):
        if not self.slug:
            unique_slugify(self, f"{self.bank.name} {self.name}", queryset=BankBranch.objects.filter(bank=self.bank))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.bank.name} - {self.name}"


class BankAccount(AuditableModel):
    """
    A person can have multiple bank accounts; canonical bank account links to a branch (address).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    person = models.ForeignKey('Person', on_delete=models.CASCADE, related_name='bank_accounts')
    bank = models.ForeignKey(Bank, on_delete=models.PROTECT, related_name='accounts')
    branch = models.ForeignKey(BankBranch, on_delete=models.PROTECT, related_name='accounts', null=True, blank=True)
    account_number = models.CharField(max_length=64, validators=[RegexValidator(r'^[0-9A-Za-z-]+$',
                                                                               'Only letters, digits and hyphen allowed')])
    is_primary = models.BooleanField(default=False)

    class Meta:
        unique_together = ('bank', 'account_number')
        indexes = [Index(fields=['person', 'bank'])]

    def save(self, *args, **kwargs):
        # ensure only one primary per person
        if self.is_primary:
            BankAccount.objects.filter(person=self.person, is_primary=True).update(is_primary=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.bank.name} - {self.account_number}"


# ------------------------
# Person and multi-value fields
# ------------------------
class SpecificWork(AuditableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True)
    description = models.CharField(max_length=255)
    slug = models.SlugField(max_length=180, unique=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            unique_slugify(self, self.code)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code}: {self.description}"


class PersonManager(models.Manager):
    def active(self):
        return self.get_queryset().filter(is_active=True)

    def search(self, q):
        qs = self.get_queryset()
        if not q:
            return qs
        return qs.filter(
            Q(name__icontains=q) |
            Q(identity_no__icontains=q) |
            Q(computer_code__icontains=q)
        )


def person_photo_upload_to(instance, filename):
    return f"persons/{instance.id}/{filename}"


class Person(AuditableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.ForeignKey(Post, on_delete=models.PROTECT, related_name='persons')
    name = models.CharField(max_length=200)
    photo = models.ImageField(upload_to=person_photo_upload_to, blank=True, null=True)

    # Business identifiers
    computer_code = models.CharField(max_length=30, validators=[DIGIT_ONLY], help_text="Numeric code only")
    identity_no = models.CharField(max_length=64, unique=True)
    slug = models.SlugField(max_length=220, unique=True, blank=True)

    # Working status
    is_working = models.BooleanField(default=True, db_index=True)

    # Branch address reference: the address for their bank branch or workplace address
    branch_address = models.ForeignKey(Ward, on_delete=models.SET_NULL, null=True, blank=True, related_name='persons_branch')

    # Specific work: multiple
    specific_works = models.ManyToManyField(SpecificWork, blank=True, related_name='persons')

    # soft-delete
    is_active = models.BooleanField(default=True)  # soft-delete flag
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = PersonManager()

    class Meta:
        indexes = [
            Index(fields=['name']),
            Index(fields=['computer_code']),
            Index(fields=['identity_no']),
            Index(fields=['created_at']),
            Index(fields=['slug']),
        ]
        ordering = ['name']
        constraints = [
            UniqueConstraint(fields=['computer_code'], name='unique_computer_code')
        ]

    def save(self, *args, **kwargs):
        # ensure slug is created from name + computer_code for uniqueness and readability
        if not self.slug:
            base = f"{self.name} {self.computer_code}" if self.computer_code else self.name
            unique_slugify(self, base)
        super().save(*args, **kwargs)

    def soft_delete(self):
        self.is_active = False
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_active', 'deleted_at'])

    def restore(self):
        self.is_active = True
        self.deleted_at = None
        self.save(update_fields=['is_active', 'deleted_at'])

    def full_address(self):
        if self.branch_address:
            w = self.branch_address
            m = w.municipality
            d = m.district
            p = d.province
            return f"Ward {w.ward_no}, {m.name}, {d.name}, {p.name}"
        return ""

    def __str__(self):
        return f"{self.name} ({self.computer_code})"


# Separate tables for phone numbers and emails for normalization (multiple allowed)
class PhoneNumber(AuditableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name='phone_numbers')
    number = models.CharField(max_length=30)  # flexible for +country codes
    is_primary = models.BooleanField(default=False)

    class Meta:
        unique_together = ('person', 'number')
        indexes = [Index(fields=['person', 'is_primary'])]

    def save(self, *args, **kwargs):
        # Ensure only one primary phone per person
        if self.is_primary:
            PhoneNumber.objects.filter(person=self.person, is_primary=True).update(is_primary=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.number


class EmailAddress(AuditableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name='emails')
    email = models.EmailField()
    is_primary = models.BooleanField(default=False)

    class Meta:
        unique_together = ('person', 'email')
        indexes = [Index(fields=['person', 'is_primary'])]

    def save(self, *args, **kwargs):
        # Ensure only one primary email per person
        if self.is_primary:
            EmailAddress.objects.filter(person=self.person, is_primary=True).update(is_primary=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email
