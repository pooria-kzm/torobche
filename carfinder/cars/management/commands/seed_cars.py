from cars.models import Car
from django.core.management.base import BaseCommand

SAMPLES = [
    (
        "bama",
        "پژو 206 تیپ 2",
        "پژو",
        "206 تیپ 2",
        1389,
        948000000,
        124000,
        "تهران",
        "دنده‌ای",
        "بنزینی",
    ),
    (
        "bama",
        "ام وی ام X22 اتوماتیک اسپرت",
        "ام وی ام",
        "X22",
        1397,
        2080000000,
        45000,
        "تهران",
        "اتوماتیک",
        "بنزینی",
    ),
    (
        "bama",
        "تویوتا پرادو چهار در",
        "تویوتا",
        "پرادو",
        2010,
        17000000000,
        155000,
        "تهران",
        "اتوماتیک",
        "بنزینی",
    ),
    (
        "karnameh",
        "کوییک دنده‌ای ساده",
        "کوییک",
        "دنده‌ای",
        1401,
        676175000,
        85000,
        "تهران",
        "دنده‌ای",
        "بنزینی",
    ),
    (
        "karnameh",
        "رنو ساندرو اتوماتیک",
        "رنو",
        "ساندرو",
        1395,
        1415250000,
        117000,
        "تهران",
        "اتوماتیک",
        "بنزینی",
    ),
    (
        "karnameh",
        "فونیکس FX پریمیوم",
        "فونیکس",
        "FX",
        1403,
        3365150000,
        35000,
        "تهران",
        "اتوماتیک",
        "بنزینی",
    ),
]


class Command(BaseCommand):
    help = "Load a small local demo catalog. It never overwrites live crawled listings."

    def handle(self, *args, **options):
        for i, row in enumerate(SAMPLES, 1):
            source, title, brand, model_name, year, price, mileage, city, transmission, fuel = row
            Car.objects.get_or_create(
                source_url=f"https://example.local/{source}/{i}",
                defaults={
                    "source": source,
                    "title": title,
                    "brand": brand,
                    "model_name": model_name,
                    "year": year,
                    "price": price,
                    "mileage": mileage,
                    "city": city,
                    "transmission": transmission,
                    "fuel": fuel,
                    "body_type": "سواری",
                },
            )
        self.stdout.write(self.style.SUCCESS("Demo catalog is ready."))
