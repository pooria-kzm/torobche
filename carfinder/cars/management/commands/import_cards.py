import json
from pathlib import Path

from cars.card_builder import title_key
from cars.models import CarCard
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Import card names and describtions from JSON into CarCard."

    def add_arguments(self, parser):
        parser.add_argument("--input", default="car_card_titles.json")

    def handle(self, *args, **options):
        try:
            data = json.loads(Path(options["input"]).read_text(encoding="utf-8"))
            records = data.get("cards", data) if isinstance(data, dict) else data
            if not isinstance(records, list):
                raise TypeError("expected a JSON list or an object with cards")
            with transaction.atomic():
                existing = {title_key(card.title): card for card in CarCard.objects.all()}
                imported = 0
                for record in records:
                    if isinstance(record, str):
                        title, description = record, ""
                    elif isinstance(record, dict):
                        title = record.get("title", record.get("name", ""))
                        description = record.get("describtion", record.get("description", "")) or ""
                    else:
                        continue
                    title = str(title).strip()
                    if not title:
                        continue
                    key = title_key(title)
                    card = existing.get(key) or CarCard(title=title)
                    card.describtion = str(description)
                    card.save()
                    existing[key] = card
                    imported += 1
        except Exception as exc:
            raise CommandError(f"Card import failed: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"Imported {imported} cards."))
