import re
from collections import Counter
from urllib.parse import quote

from django.core.paginator import Paginator
from django.db.models import Case, IntegerField, Max, Q, Value, When
from django.shortcuts import get_object_or_404, redirect, render

from .models import Car, CarCard


def number(value):
    """Accept Persian/Arabic digits and comma-separated numbers."""
    if not value:
        return None
    value = str(value).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    found = re.sub(r"[^0-9]", "", value)
    return int(found) if found else None


def normalize_text(value):
    return (
        (value or "")
        .translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
        .replace("ي", "ی")
        .replace("ك", "ک")
        .strip()
    )


def filtered_cars(request):
    q = request.GET.get("q", "").strip()
    cars = Car.objects.filter(is_active=True)
    if q:
        tokens = [t for t in re.split(r"\s+", q) if t]
        score = Case(
            When(title__icontains=q, then=Value(30)), default=Value(0), output_field=IntegerField()
        )
        for token in tokens:
            score += Case(
                When(
                    Q(title__icontains=token)
                    | Q(brand__icontains=token)
                    | Q(model_name__icontains=token)
                    | Q(type__icontains=token),
                    then=Value(8),
                ),
                default=Value(0),
                output_field=IntegerField(),
            )
        cars = (
            cars.annotate(relevance=score)
            .filter(relevance__gt=0)
            .order_by("-relevance", "-last_seen_at")
        )
    filters = {
        "brand": [brand for brand in request.GET.getlist("brand") if brand],
        "transmission": request.GET.get("transmission", ""),
    }
    if filters["brand"]:
        brand_query = Q()
        for brand in filters["brand"]:
            brand_query |= Q(brand__icontains=brand)
        cars = cars.filter(brand_query)
    if filters["transmission"]:
        cars = cars.filter(transmission=filters["transmission"])
    return cars, filters


def brand_options():
    counts = Counter()
    for value in Car.objects.filter(is_active=True).values_list("brand", flat=True):
        for brand in re.split(r"[,،]", value or ""):
            brand = normalize_text(brand)
            if len(brand) >= 3 and brand != "فروش" and brand != "حواله":
                counts[brand] += 1
    return counts.most_common(10)


def query_without_page(request):
    params = request.GET.copy()
    params.pop("page", None)
    return params.urlencode()


def search(request):
    q = request.GET.get("q", "").strip()
    cars, filters = filtered_cars(request)
    cards = CarCard.objects.filter(cars__in=cars).distinct().prefetch_related("cars")
    page = Paginator(cards, 12).get_page(request.GET.get("page"))
    context = {
        "page": page,
        "cards": page.object_list,
        "count": cards.count(),
        "q": q,
        "filters": filters,
        "brand_options": brand_options(),
        "pagination_params": query_without_page(request),
    }
    return render(request, "cars/search.html", context)


def model_choices(request):
    q = request.GET.get("q", "").strip()
    return redirect(f"/?q={quote(q)}")


def model_listings(request, model_name):
    return redirect(f"/?q={quote(model_name)}")


def card_listings(request, pk):
    card = get_object_or_404(CarCard.objects.prefetch_related("cars"), pk=pk)
    cars = card.cars.filter(is_active=True).order_by("price", "-last_seen_at")
    filters = {
        key: number(request.GET.get(key, ""))
        for key in ("min_price", "max_price", "min_year", "max_year", "max_mileage")
    }
    if filters["min_price"] is not None:
        cars = cars.filter(price__gte=filters["min_price"])
    if filters["max_price"] is not None:
        cars = cars.filter(price__lte=filters["max_price"])
    if filters["min_year"] is not None:
        cars = cars.filter(year__gte=filters["min_year"])
    if filters["max_year"] is not None:
        cars = cars.filter(year__lte=filters["max_year"])
    if filters["max_mileage"] is not None:
        cars = cars.filter(mileage__lte=filters["max_mileage"])
    page = Paginator(cars, 12).get_page(request.GET.get("page"))
    max_mileage = (
        card.cars.filter(is_active=True).aggregate(max_value=Max("mileage"))["max_value"] or 300000
    )
    return render(
        request,
        "cars/card_listings.html",
        {
            "card": card,
            "cars": page.object_list,
            "page": page,
            "filters": filters,
            "max_mileage_limit": max_mileage,
            "pagination_params": query_without_page(request),
        },
    )


def outbound(request, pk):
    car = get_object_or_404(Car, pk=pk, is_active=True)
    return redirect(car.source_url)
