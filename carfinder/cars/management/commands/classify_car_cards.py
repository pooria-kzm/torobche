from cars.card_builder import DEFAULT_MODEL, classify_car_cards
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Classify existing cars into card titles from a saved JSON file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--input",
            default="car_card_titles.json",
            help="Card-title JSON file (default: car_card_titles.json).",
        )
        parser.add_argument("--batch-size", type=int, default=100)
        parser.add_argument("--model", default=DEFAULT_MODEL)

    def handle(self, *args, **options):
        if options["batch_size"] < 1:
            raise CommandError("--batch-size must be positive")
        try:
            result = classify_car_cards(
                options["input"],
                batch_size=options["batch_size"],
                model=options["model"],
                progress=lambda message: self.stdout.write(message),
            )
        except Exception as exc:
            raise CommandError(f"Car classification failed: {exc}") from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {result['assigned']} cars assigned across {result['batches']} batches; "
                f"{result['created']} cards created."
            )
        )
