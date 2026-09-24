from django.core.management.base import BaseCommand
from django.db.models import Q
from tracker.models import Job
from tracker.services import update_job_description


class Command(BaseCommand):
    help = "Fetch missing job descriptions from the public BA jobdetail pages."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument("--all", action="store_true")

    def handle(self, *args, **options):
        qs = Job.objects.filter(Q(beschreibung="") | Q(description_fetched_at__isnull=True)).order_by("-first_seen")
        if options["all"]:
            qs = Job.objects.all().order_by("-first_seen")
        success = 0
        for job in qs[: options["limit"]]:
            try:
                update_job_description(job)
                success += 1
                self.stdout.write(f"Fetched {job.referenznummer}")
            except Exception as exc:
                self.stderr.write(f"{job.referenznummer}: {exc}")
        self.stdout.write(self.style.SUCCESS(f"Updated {success} descriptions."))