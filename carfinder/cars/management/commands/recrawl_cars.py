from cars.services import recrawl_sources
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Refresh listings, hide stale cars, and restore cars seen again by image URL."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            choices=["all", "bama", "karnameh", "hamrah", "khodro45", "divar", "sheypoor"],
            default="all",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=500,
            help="Maximum listings from each source (default: 500).",
        )

    def handle(self, *args, **options):
        try:
            count = recrawl_sources(options["source"], limit=options["limit"])
        except Exception as exc:
            raise CommandError(f"Recrawl failed: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"Recrawled and imported {count} listings."))
