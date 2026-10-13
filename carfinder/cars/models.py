from django.db import models


class Car(models.Model):
    class Source(models.TextChoices):
        BAMA = "bama", "باما"
        KARNAMEH = "karnameh", "کارنامه"
        HAMRAH = "hamrah", "همراه مکانیک"
        KHODRO45 = "khodro45", "خودرو۴۵"
        DIVAR = "divar", "دیوار"
        SHEYPOOR = "sheypoor", "شیپور"

    source = models.CharField(max_length=16, choices=Source.choices)
    source_url = models.URLField(unique=True)
    title = models.CharField(max_length=255)
    type = models.CharField(max_length=255, null=True, blank=True)
    brand = models.CharField(max_length=80, blank=True)
    model_name = models.CharField(max_length=120, blank=True)
    year = models.PositiveIntegerField(null=True, blank=True)
    price = models.BigIntegerField(null=True, blank=True, help_text="Toman")
    mileage = models.PositiveIntegerField(null=True, blank=True)
    city = models.CharField(max_length=80, blank=True)
    transmission = models.CharField(max_length=32, blank=True)
    fuel = models.CharField(max_length=32, blank=True)
    body_type = models.CharField(max_length=32, blank=True)
    image_url = models.URLField(blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-last_seen_at",)
        indexes = (
            models.Index(fields=("price",)),
            models.Index(fields=("year",)),
            models.Index(fields=("brand",)),
        )

    def __str__(self):
        return self.title


class CarCard(models.Model):
    """One comparable make/model/trim containing independent marketplace ads."""

    title = models.CharField(max_length=255, unique=True)
    describtion = models.TextField(blank=True)
    image_url = models.URLField(blank=True)
    cars = models.ManyToManyField(Car, related_name="comparison_cards")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("title",)

    def __str__(self):
        return self.title
