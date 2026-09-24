from django.core.management.base import BaseCommand
from tracker.models import EmailMessage
from tracker.services import LlamaServer, apply_email_classification, classify_email, match_email_to_application


class Command(BaseCommand):
    help = "Classify unparsed inbox messages with local llama.cpp and link them to applications."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        emails = EmailMessage.objects.filter(parsed=False).order_by("received_at")[: options["limit"]]
        with LlamaServer():
            for email in emails:
                try:
                    match_email_to_application(email)
                    classification = classify_email(email)
                    apply_email_classification(email)
                    self.stdout.write(self.style.SUCCESS(
                        f"{email.received_at:%Y-%m-%d} {email.subject[:60]} -> {classification.get('classification')} ({classification.get('confidence')})"
                    ))
                except Exception as exc:
                    self.stderr.write(f"{email.message_id}: {exc}")