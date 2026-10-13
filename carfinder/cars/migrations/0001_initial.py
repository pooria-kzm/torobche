from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [migrations.CreateModel(
        name="Car",
        fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("source", models.CharField(choices=[("bama", "باما"), ("karnameh", "کارنامه"), ("hamrah", "همراه مکانیک"), ("khodro45", "خودرو۴۵"), ("divar", "دیوار"), ("sheypoor", "شیپور")], max_length=16)),
            ("source_url", models.URLField(unique=True)), ("title", models.CharField(max_length=255)),
            ("brand", models.CharField(blank=True, max_length=80)), ("model_name", models.CharField(blank=True, max_length=120)),
            ("year", models.PositiveIntegerField(blank=True, null=True)), ("price", models.BigIntegerField(blank=True, help_text="Toman", null=True)),
            ("mileage", models.PositiveIntegerField(blank=True, null=True)), ("city", models.CharField(blank=True, max_length=80)),
            ("transmission", models.CharField(blank=True, max_length=32)), ("fuel", models.CharField(blank=True, max_length=32)),
            ("body_type", models.CharField(blank=True, max_length=32)), ("image_url", models.URLField(blank=True)),
            ("description", models.TextField(blank=True)), ("is_active", models.BooleanField(default=True)),
            ("first_seen_at", models.DateTimeField(auto_now_add=True)), ("last_seen_at", models.DateTimeField(auto_now=True)),
        ], options={"ordering": ["-last_seen_at"], "indexes": [models.Index(fields=["price"], name="cars_car_price_2c93d1_idx"), models.Index(fields=["year"], name="cars_car_year_7a2c31_idx"), models.Index(fields=["brand"], name="cars_car_brand_8f69cf_idx")]},
    )]
