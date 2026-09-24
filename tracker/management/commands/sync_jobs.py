from django.core.management.base import BaseCommand
from django.utils import timezone
from tracker.models import JobSearch, JobSyncRun
from tracker.services import sync_ba_jobs


class Command(BaseCommand):
    help = "Sync jobs from the Bundesagentur für Arbeit Jobsuche API."

    def add_arguments(self, parser):
        parser.add_argument("--was", default=None)
        parser.add_argument("--wo", default=None)
        parser.add_argument("--radius", type=int, default=None)
        parser.add_argument("--size", type=int, default=None)
        parser.add_argument("--pages", type=int, default=1)
        parser.add_argument("--all-searches", action="store_true")

    def handle(self, *args, **options):
        searches = JobSearch.objects.filter(active=True) if options["all_searches"] else None
        if searches is None:
            search = JobSearch.objects.filter(active=True).first()
            if not search:
                name = "CLI search"
                search = JobSearch.objects.create(name=name, was=options["was"] or "", wo=options["wo"] or "Berlin", radius_km=options["radius"] or 50, page_size=options["size"] or 25)
            searches = [search]

        for search in searches:
            run = JobSyncRun.objects.create(search=search, started_at=timezone.now())
            created = updated = seen = 0
            try:
                for page in range(1, options["pages"] + 1):
                    data, rows, c, u = sync_ba_jobs(
                        was=options["was"] if options["was"] is not None else search.was,
                        wo=options["wo"] if options["wo"] is not None else search.wo,
                        size=options["size"] or search.page_size,
                        page=page,
                        umkreis=options["radius"] if options["radius"] is not None else search.radius_km,
                    )
                    seen += len(rows); created += c; updated += u
                    if not rows or len(rows) < (options["size"] or search.page_size):
                        break
                run.jobs_seen = seen
                run.jobs_created = created
                run.jobs_updated = updated
                run.finished_at = timezone.now()
                run.save(update_fields=["jobs_seen", "jobs_created", "jobs_updated", "finished_at"])
                self.stdout.write(self.style.SUCCESS(f"{search.name}: seen={seen} created={created} updated={updated}"))
            except Exception as exc:
                run.error = str(exc)
                run.finished_at = timezone.now()
                run.save(update_fields=["error", "finished_at"])
                raise