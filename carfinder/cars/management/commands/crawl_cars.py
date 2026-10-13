from cars.services import crawl_sources
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Scroll public marketplace listings, then assign cars to comparison cards."

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
            count = crawl_sources(options["source"], limit=options["limit"])
        except Exception as exc:
            raise CommandError(f"Crawl failed: {exc}") from exc
        self.stdout.write(
            self.style.SUCCESS(f"Imported/updated {count} listings and processed comparison cards.")
        )
