from django.contrib import admin

from .models import Car, CarCard


@admin.register(Car)
class CarAdmin(admin.ModelAdmin):
    list_display = ("title", "type", "source", "price", "year", "mileage", "city", "last_seen_at")
    list_filter = ("source", "transmission", "fuel", "city")
    search_fields = ("title", "type", "brand", "model_name", "city")


@admin.register(CarCard)
class CarCardAdmin(admin.ModelAdmin):
    list_display = ("title", "listing_count", "updated_at")
    search_fields = ("title",)
    filter_horizontal = ("cars",)

    @admin.display(description="آگهی‌ها")
    def listing_count(self, card):
        return card.cars.count()
