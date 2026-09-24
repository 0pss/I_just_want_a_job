from django.core.management.base import BaseCommand
from tracker.models import Job
from tracker.services import LlamaServer, evaluate_job, get_active_profile


class Command(BaseCommand):
    help = "Evaluate jobs with the local llama.cpp server. The server is started and stopped automatically."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=25)
        parser.add_argument("--rescore", action="store_true")
        parser.add_argument("--min-description-words", type=int, default=30)

    def handle(self, *args, **options):
        profile = get_active_profile()
        qs = Job.objects.exclude(beschreibung="").order_by("-first_seen")
        if not options["rescore"]:
            qs = qs.filter(llm_score__isnull=True)
        jobs = [j for j in qs[: options["limit"]] if len(j.beschreibung.split()) >= options["min_description_words"]]
        self.stdout.write(f"Scoring {len(jobs)} jobs with local llama.cpp...")
        with LlamaServer() as server:
            for job in jobs:
                try:
                    evaluate_job(job, profile, llama_server=server)
                    self.stdout.write(self.style.SUCCESS(
                        f"{job.referenznummer}: LLM={job.llm_score:.1f} buzz={job.buzzword_score:.1f} diff={job.score_divergence:.1f} review={job.manual_review}"
                    ))
                except Exception as exc:
                    self.stderr.write(f"{job.referenznummer}: {exc}")