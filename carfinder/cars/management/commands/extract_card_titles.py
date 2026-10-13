from cars.card_builder import DEFAULT_MODEL, extract_card_titles
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Extract and reduce trusted-site car titles with one LLM call into a JSON file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default="car_card_titles.json",
            help="JSON file to write (default: car_card_titles.json).",
        )
        parser.add_argument("--model", default=DEFAULT_MODEL)

    def handle(self, *args, **options):
        try:
            result = extract_card_titles(
                options["output"],
                model=options["model"],
                progress=lambda message: self.stdout.write(message),
            )
        except Exception as exc:
            raise CommandError(f"Card-title extraction failed: {exc}") from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {result['unique']} unique titles reduced to {result['cards']} cards in {result['path']}"
            )
        )
