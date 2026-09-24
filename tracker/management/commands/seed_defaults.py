from django.core.management.base import BaseCommand
from tracker.models import CandidateProfile, JobSearch


DEFAULT_PROFILE = """Fähigkeiten: Python, SQL, Datenpipelines, pandas, Grundkenntnisse ML, REST-APIs
Gesucht wird: Remote oder Hybrid, Raum Berlin, keine Rufbereitschaft, keine vertriebslastigen Rollen
Von Vorteil: Home Office möglich, moderner Tech-Stack, kleines bis mittleres Unternehmen
Vermeiden: reine Zeitarbeitsfirmen, Rollen mit Deutschkenntnissen auf C2-Niveau, viel Reisetätigkeit"""


class Command(BaseCommand):
    help = "Create the default candidate profile and a Berlin/Python job search."

    def handle(self, *args, **options):
        CandidateProfile.objects.get_or_create(
            name="Default candidate",
            version=1,
            defaults={"profile_text": DEFAULT_PROFILE, "active": True},
        )
        JobSearch.objects.get_or_create(
            name="Python Berlin",
            defaults={"was": "Python", "wo": "Berlin", "radius_km": 50, "page_size": 25, "active": True},
        )
        self.stdout.write(self.style.SUCCESS("Defaults created."))