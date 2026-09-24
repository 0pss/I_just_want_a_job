from django.core.management.base import BaseCommand
from tracker.services import sync_imap_messages


class Command(BaseCommand):
    help = "Ingest inbox messages into EmailMessage without modifying application state."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        count = sync_imap_messages(limit=options["limit"])
        self.stdout.write(self.style.SUCCESS(f"Imported {count} new messages."))