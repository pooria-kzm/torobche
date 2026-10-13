from cars.card_builder import process_car_cards
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Run title extraction and car classification in one combined operation."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Number of unmatched car titles per LLM request (default: 100).",
        )
        parser.add_argument("--model", default="Qwen/Qwen3.8-27B")

    def handle(self, *args, **options):
        if options["batch_size"] < 1:
            raise CommandError("--batch-size must be positive")
        try:
            result = process_car_cards(
                batch_size=options["batch_size"],
                model=options["model"],
                progress=lambda message: self.stdout.write(message),
            )
        except Exception as exc:
            raise CommandError(f"Card processing failed: {exc}") from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {result['cars']} cars across {result['batches']} batches; "
                f"{result['assigned']} assigned and {result['created']} cards created."
            )
        )
