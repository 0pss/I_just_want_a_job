import hashlib
from datetime import timedelta
import imaplib
import json
import re
import subprocess
import time
from email import message_from_bytes
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from .models import (
    Application,
    ApplicationDocument,
    ApplicationEvent,
    BlacklistEntry,
    CandidateProfile,
    EmailMessage,
    Job,
    JobEvaluation,
)


BUZZWORDS = [
    "python", "sql", "pandas", "numpy", "scikit-learn", "machine learning", "ml", "ai",
    "data engineering", "data analytics", "analytics", "etl", "elt", "datenpipeline", "datenpipelines",
    "rest", "api", "apis", "fastapi", "django", "flask", "postgresql", "postgres", "mysql",
    "git", "github", "gitlab", "ci/cd", "docker", "kubernetes", "terraform", "aws", "azure", "gcp",
    "cloud", "airflow", "spark", "kafka", "microservices", "linux", "automatisierung",
    "automation", "agile", "scrum", "kanban", "remote", "hybrid", "homeoffice", "flexibel",
    "modern", "modernem tech-stack", "eigenverantwortung", "eigenverantwortlich", "gestaltungsfreiheit",
    "team", "kleines team", "mittelständisch", "mittelstand", "startup", "innovation", "nachhaltig",
    "berlin", "deutschland", "data platform", "backend", "softwareentwicklung", "software engineering",
]

SCORING_PROMPT_VERSION = "job-fit-v2"
EMAIL_PROMPT_VERSION = "email-classifier-v1"
DOCUMENT_PROMPT_VERSION = "application-doc-v1"

SYSTEM_PROMPT = """You evaluate a German job posting for one candidate. Return ONLY valid JSON.
Use a 1-10 fit score. Consider technical match, working model, location, travel, language requirements,
and role type. Be conservative: explicit hard mismatches matter more than vague positive wording.
Return exactly:
{"score": 1-10, "pro": ["short phrase"], "contra": ["short phrase"]}
Use at most 4 pro and 4 contra items. Do not invent facts not supported by the job description.
"""

EMAIL_SYSTEM_PROMPT = """Classify an employer email for a job application. Return ONLY valid JSON.
Possible classification values: rejected, interview_invited, interview_done, offer, auto_reply, other.
Also return a confidence from 0 to 1 and a one-sentence rationale.
Format: {"classification":"...","confidence":0.0,"rationale":"..."}
"""

DOCUMENT_SYSTEM_PROMPT = """Write professional German application material for a job.
Use only information in the candidate profile; do not invent employers, degrees, dates, achievements, or technologies.
Keep it specific to the job and natural, not generic.
"""


def is_blacklisted(company: str) -> bool:
    if not company:
        return False
    company_lower = company.lower()
    return any(term.lower() in company_lower for term in BlacklistEntry.objects.values_list("term", flat=True))


def parse_source_datetime(value):
    if not value:
        return None
    dt = parse_datetime(value)
    if dt:
        return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
    return None


def upsert_job(data: dict) -> tuple[Job, bool]:
    ref = data.get("referenznummer")
    if not ref:
        raise ValueError("referenznummer is required")
    defaults = {
        "titel": data.get("titel", ""),
        "firma": data.get("firma", ""),
        "beruf": data.get("beruf", ""),
        "ort": data.get("ort", ""),
        "plz": data.get("plz", ""),
        "strasse": data.get("strasse", ""),
        "entfernung_km": data.get("entfernung_km"),
        "latitude": data.get("latitude"),
        "longitude": data.get("longitude"),
        "vollzeit": data.get("vollzeit"),
        "homeoffice": data.get("homeoffice"),
        "stellenangebotsart": data.get("stellenangebotsart", ""),
        "homeofficetyp": data.get("homeofficetyp", ""),
        "eintrittsdatum": parse_date(data.get("eintrittsdatum")) if data.get("eintrittsdatum") else None,
        "published_at": parse_source_datetime(data.get("published_at")),
        "source_updated_at": parse_source_datetime(data.get("source_updated_at")),
        "source": data.get("source", "arbeitsagentur"),
    }
    job, created = Job.objects.update_or_create(referenznummer=ref, defaults=defaults)
    job.last_seen = timezone.now()
    job.save(update_fields=["last_seen"])
    return job, created


def sync_ba_jobs(was="", wo="Berlin", size=25, page=1, umkreis=50):
    url = settings.JOBTRACKER["ARBEITSAGENTUR_API_URL"]
    headers = {"X-API-Key": settings.JOBTRACKER["ARBEITSAGENTUR_API_KEY"]}
    params = {"suchbereich": "jobs", "was": was, "wo": wo, "size": size, "page": page, "umkreis": umkreis}
    response = requests.get(url, headers=headers, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    created = updated = 0
    jobs = data.get("ergebnisliste", [])
    rows = []
    for raw in jobs:
        location = (raw.get("stellenlokationen") or [{}])[0]
        address = location.get("adresse", {})
        row = {
            "titel": raw.get("stellenangebotsTitel") or "",
            "firma": raw.get("firma") or "",
            "beruf": raw.get("hauptberuf") or "",
            "ort": address.get("ort") or "",
            "plz": address.get("plz") or "",
            "strasse": f"{address.get('strasse', '')} {address.get('hausnummer', '')}".strip(),
            "entfernung_km": raw.get("entfernung"),
            "latitude": location.get("breite"),
            "longitude": location.get("laenge"),
            "vollzeit": raw.get("arbeitszeitVollzeit"),
            "homeoffice": raw.get("homeofficemoeglich"),
            "homeofficetyp": raw.get("homeofficetyp") or "",
            "stellenangebotsart": raw.get("stellenangebotsart") or "",
            "eintrittsdatum": (raw.get("eintrittszeitraum") or {}).get("von"),
            "published_at": raw.get("datumErsteVeroeffentlichung"),
            "source_updated_at": raw.get("aenderungsdatum"),
            "referenznummer": raw.get("referenznummer"),
        }
        if not row["referenznummer"] or is_blacklisted(row["firma"]):
            continue
        before = Job.objects.filter(referenznummer=row["referenznummer"]).exists()
        upsert_job(row)
        created += int(not before)
        updated += int(before)
        rows.append(row)
    return data, rows, created, updated


def fetch_job_description(referenznummer: str, sleep_seconds: float = 0.5):
    url = f"{settings.JOBTRACKER['JOBDETAIL_BASE_URL']}/{referenznummer}"
    headers = {"User-Agent": "Mozilla/5.0 GothamJobTracker/1.0"}
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    desc_div = soup.select_one("#detail-beschreibung-text-container")
    description = desc_div.get_text(separator="\\n", strip=True) if desc_div else ""
    apply_link = ""
    if desc_div:
        for anchor in desc_div.find_all("a", href=True):
            href = anchor["href"]
            if href.startswith("http"):
                apply_link = href
                break
    time.sleep(sleep_seconds)
    return description, apply_link


def update_job_description(job: Job):
    description, apply_link = fetch_job_description(job.referenznummer)
    job.beschreibung = description
    if apply_link:
        job.bewerbungslink = apply_link
    job.description_hash = hashlib.sha256(description.encode("utf-8")).hexdigest() if description else ""
    job.description_fetched_at = timezone.now()
    job.save(update_fields=["beschreibung", "bewerbungslink", "description_hash", "description_fetched_at"])
    return job


def get_app_config():
    cfg, _ = AppConfig.objects.get_or_create(key="default", defaults={"candidate_profile": "", "system_prompt": SYSTEM_PROMPT, "buzzwords": BUZZWORDS})
    return cfg

def score_buzzwords(text: str):
    if not text:
        return 0.0, []
    normalized = re.sub(r"\s+", " ", text.lower())
    words = re.findall(r"\b[\wäöüß+#./-]+\b", normalized)
    word_count = max(len(words), 1)
    hits = []
    for term in (get_app_config().buzzwords or BUZZWORDS):
        if re.search(r"(?<!\w)" + re.escape(term.lower()) + r"(?!\w)", normalized):
            hits.append(term)
    # Unique-term density prevents long descriptions from winning purely through repetition.
    density_per_100 = len(hits) / word_count * 100
    score = min(10.0, round(density_per_100 * 1.75, 1))
    return score, hits


def extract_json(text: str):
    text = (text or "").strip().replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
        return None


class LlamaServer:
    def __init__(self):
        cfg = settings.JOBTRACKER
        self.base_url = cfg["LLAMA_SERVER_URL"].rstrip("/")
        self.workdir = Path(cfg["LLAMA_CPP_DIR"]).expanduser()
        self.model = Path(cfg["LLAMA_MODEL_PATH"]).expanduser()
        self.port = cfg["LLAMA_PORT"]
        self.context = cfg["LLAMA_CONTEXT"]
        self.log_level = cfg["LLAMA_LOG_LEVEL"]
        self.timeout = cfg["LLAMA_READY_TIMEOUT"]
        self.process = None
        self.started_here = False
        self.log_path = Path(settings.BASE_DIR) / "llama-server.log"

    def healthcheck(self):
        try:
            response = requests.get(f"{self.base_url}/health", timeout=2)
            return response.ok
        except requests.RequestException:
            return False

    def start(self):
        if self.healthcheck():
            return
        binary = self.workdir / "build" / "bin" / "llama-server"
        if not binary.exists():
            raise FileNotFoundError(f"llama-server not found: {binary}")
        if not self.model.exists():
            raise FileNotFoundError(f"llama model not found: {self.model}")

        log_file = open(self.log_path, "a", encoding="utf-8")
        self.process = subprocess.Popen(
            [
                str(binary),
                "-m", str(self.model),
                "-c", str(self.context),
                "--port", str(self.port),
                "-lv", str(self.log_level),
            ],
            cwd=str(self.workdir),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self.started_here = True
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"llama-server exited early. See {self.log_path}")
            if self.healthcheck():
                return
            time.sleep(1)
        self.stop()
        raise TimeoutError(f"Timed out waiting for llama-server at {self.base_url}/health")

    def stop(self):
        if not self.started_here or not self.process:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.process = None
        self.started_here = False

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stop()


def llama_chat(messages, temperature=0.1, max_tokens=500):
    payload = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    response = requests.post(
        f"{settings.JOBTRACKER['LLAMA_SERVER_URL'].rstrip('/')}/v1/chat/completions",
        json=payload,
        timeout=300,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def get_active_profile():
    profile = CandidateProfile.objects.filter(active=True).order_by("-version").first()
    if not profile:
        raise RuntimeError("No active CandidateProfile exists. Run: python manage.py seed_defaults")
    return profile


@transaction.atomic
def evaluate_job(job: Job, profile: CandidateProfile, llama_server=None):
    buzz_score, buzz_hits = score_buzzwords(job.beschreibung)
    messages = [
        {"role": "system", "content": get_app_config().system_prompt or SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"CANDIDATE PROFILE:
{profile.profile_text}

JOB TITLE: {job.titel}
COMPANY: {job.firma}
DESCRIPTION:
{job.beschreibung[:9000]}",
        },
    ]
    if llama_server is None:
        with LlamaServer():
            raw = llama_chat(messages, temperature=0.1, max_tokens=350)
    else:
        raw = llama_chat(messages, temperature=0.1, max_tokens=350)
    parsed = extract_json(raw)
    if not parsed or not isinstance(parsed.get("score"), (int, float)):
        raise ValueError(f"Unparseable LLM response: {raw[:300]}")

    llm_score = max(1.0, min(10.0, float(parsed["score"])))
    pro = [str(x)[:100] for x in parsed.get("pro", [])][:4]
    contra = [str(x)[:100] for x in parsed.get("contra", [])][:4]
    divergence = round(abs(llm_score - buzz_score), 1)
    threshold = get_app_config().divergence_threshold

    evaluation = JobEvaluation.objects.create(
        job=job,
        profile=profile,
        score=llm_score,
        pro=pro,
        contra=contra,
        model_name="local-llama.cpp",
        prompt_version=SCORING_PROMPT_VERSION,
        raw_response=parsed,
    )
    job.llm_score = llm_score
    job.llm_pro = pro
    job.llm_contra = contra
    job.llm_model = evaluation.model_name
    job.llm_prompt_version = SCORING_PROMPT_VERSION
    job.llm_scored_at = timezone.now()
    job.buzzword_score = buzz_score
    job.buzzword_hits = buzz_hits
    job.buzzword_scored_at = timezone.now()
    job.score_divergence = divergence
    job.manual_review = divergence >= threshold
    job.save(update_fields=[
        "llm_score", "llm_pro", "llm_contra", "llm_model", "llm_prompt_version", "llm_scored_at",
        "buzzword_score", "buzzword_hits", "buzzword_scored_at", "score_divergence", "manual_review",
    ])
    return evaluation


def classify_email(email_message: EmailMessage):
    content = f"FROM: {email_message.sender}
SUBJECT: {email_message.subject}

{email_message.body_text[:12000]}"
    raw = llama_chat(
        [
            {"role": "system", "content": EMAIL_SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        temperature=0.0,
        max_tokens=220,
    )
    parsed = extract_json(raw)
    if not parsed:
        raise ValueError(f"Unparseable email classification: {raw[:300]}")
    email_message.classification = str(parsed.get("classification", "other"))
    email_message.classification_confidence = float(parsed.get("confidence", 0.0))
    email_message.parsed = True
    email_message.save(update_fields=["classification", "classification_confidence", "parsed"])
    return parsed


def match_email_to_application(email_message: EmailMessage):
    haystack = f"{email_message.subject}
{email_message.body_text}".lower()
    ref_matches = [job for job in Job.objects.all() if job.referenznummer.lower() in haystack]
    if len(ref_matches) == 1:
        email_message.application = ref_matches[0].application
        email_message.save(update_fields=["application"])
        return email_message.application

    candidates = []
    for app in Application.objects.select_related("job"):
        company = (app.job.firma or "").strip().lower()
        title = (app.job.titel or "").strip().lower()
        company_match = company and company in haystack
        title_words = [w for w in re.findall(r"\w+", title) if len(w) >= 5]
        title_match = title_words and sum(w in haystack for w in title_words) >= max(1, min(2, len(title_words)))
        if company_match and title_match:
            candidates.append(app)

    if len(candidates) == 1:
        email_message.application = candidates[0]
        email_message.save(update_fields=["application"])
        return candidates[0]
    return None


def apply_email_classification(email_message: EmailMessage):
    app = email_message.application or match_email_to_application(email_message)
    if not app:
        return None
    classification = email_message.classification
    confidence = email_message.classification_confidence or 0.0
    mapping = {
        "rejected": Application.Status.REJECTED,
        "interview_invited": Application.Status.INTERVIEW_INVITED,
        "interview_done": Application.Status.INTERVIEW_DONE,
        "offer": Application.Status.OFFER,
    }
    if classification == "auto_reply":
        ApplicationEvent.objects.get_or_create(
            application=app,
            email_message=email_message,
            event_type=ApplicationEvent.EventType.AUTO_REPLY,
            defaults={
                "source": ApplicationEvent.Source.LLM_CLASSIFIED,
                "note": "Automatic employer acknowledgement",
                "timestamp": email_message.received_at,
                "confidence": confidence,
            },
        )
        return app
    status = mapping.get(classification)
    if status:
        ApplicationEvent.objects.get_or_create(
            application=app,
            email_message=email_message,
            event_type=ApplicationEvent.EventType.STATUS_CHANGED,
            defaults={
                "status": status,
                "source": ApplicationEvent.Source.LLM_CLASSIFIED,
                "note": classification,
                "timestamp": email_message.received_at,
                "confidence": confidence,
            },
        )
        # Do not regress a terminal status based on a low-confidence email.
        if confidence >= 0.65 and app.current_status not in [Application.Status.OFFER, Application.Status.WITHDRAWN]:
            app.current_status = status
            app.save(update_fields=["current_status", "updated_at"])
    return app


def decode_header_value(value):
    if not value:
        return ""
    return str(make_header(decode_header(value)))


def extract_email_bodies(msg):
    text_parts, html_parts = [], []
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        if part.get_content_maintype() == "multipart":
            continue
        content_type = part.get_content_type()
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        charset = part.get_content_charset() or "utf-8"
        text = payload.decode(charset, errors="replace")
        if content_type == "text/plain":
            text_parts.append(text)
        elif content_type == "text/html":
            html_parts.append(text)
    return "

".join(text_parts), "

".join(html_parts)


def sync_imap_messages(limit=100):
    cfg = settings.JOBTRACKER
    if not cfg["IMAP_HOST"] or not cfg["IMAP_USERNAME"] or not cfg["IMAP_PASSWORD"]:
        raise RuntimeError("IMAP is not configured. Set IMAP_HOST, IMAP_USERNAME and IMAP_PASSWORD in .env.")

    client = imaplib.IMAP4_SSL(cfg["IMAP_HOST"], cfg["IMAP_PORT"]) if cfg["IMAP_SSL"] else imaplib.IMAP4(cfg["IMAP_HOST"], cfg["IMAP_PORT"])
    client.login(cfg["IMAP_USERNAME"], cfg["IMAP_PASSWORD"])
    client.select(cfg["IMAP_MAILBOX"], readonly=True)
    status, data = client.search(None, "ALL")
    if status != "OK":
        client.logout()
        raise RuntimeError("IMAP search failed")

    ids = data[0].split()[-limit:]
    created = 0
    for msg_id in ids:
        status, fetched = client.fetch(msg_id, "(RFC822)")
        if status != "OK" or not fetched:
            continue
        raw_bytes = next((part[1] for part in fetched if isinstance(part, tuple)), None)
        if not raw_bytes:
            continue
        msg = message_from_bytes(raw_bytes)
        message_id = (msg.get("Message-ID") or f"imap:{msg_id.decode(errors='ignore')}").strip()
        if EmailMessage.objects.filter(message_id=message_id).exists():
            continue
        body_text, body_html = extract_email_bodies(msg)
        received = parsedate_to_datetime(msg.get("Date")) if msg.get("Date") else timezone.now()
        if timezone.is_naive(received):
            received = timezone.make_aware(received)
        EmailMessage.objects.create(
            provider="imap",
            message_id=message_id,
            thread_id=msg.get("Thread-Index") or msg.get("References") or "",
            sender=decode_header_value(msg.get("From"))[:254],
            recipients=decode_header_value(msg.get("To")),
            subject=decode_header_value(msg.get("Subject")),
            received_at=received,
            body_text=body_text,
            body_html=body_html,
        )
        created += 1
    client.logout()
    return created


def generate_document(job: Job, document_type: str, profile: CandidateProfile):
    prompts = {
        "cover_letter": "Write a concise, tailored German cover letter (roughly 250-350 words) for this job.",
        "cv": "Write a tailored German CV profile and a suggested skills/experience emphasis for this job. This is a template, not an invented CV. Keep it to roughly 350-500 words.",
        "email": "Write a concise German application email for this job, including subject line and body.",
    }
    if document_type not in prompts:
        raise ValueError("Unsupported document type")
    with LlamaServer():
        content = llama_chat(
            [
                {"role": "system", "content": DOCUMENT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"{prompts[document_type]}

CANDIDATE PROFILE:
{profile.profile_text}

JOB:
{job.titel} @ {job.firma}
{job.beschreibung[:9000]}",
                },
            ],
            temperature=0.2,
            max_tokens=900,
        )
    return ApplicationDocument.objects.create(
        job=job,
        application=job.application,
        document_type=document_type,
        title=f"Generated {document_type.replace('_', ' ').title()}",
        content=content.strip(),
        model_name="local-llama.cpp",
        prompt_version=DOCUMENT_PROMPT_VERSION,
    )


def compute_kpis():
    applications = Application.objects.all()
    total_applied = applications.count()
    replied_statuses = [
        Application.Status.REJECTED,
        Application.Status.INTERVIEW_INVITED,
        Application.Status.INTERVIEW_DONE,
        Application.Status.OFFER,
    ]
    replied_count = applications.filter(current_status__in=replied_statuses).count()
    interview_count = applications.filter(current_status__in=[Application.Status.INTERVIEW_INVITED, Application.Status.INTERVIEW_DONE, Application.Status.OFFER]).count()
    active_count = applications.filter(current_status__in=[Application.Status.APPLIED, Application.Status.INTERVIEW_INVITED]).count()

    deltas = []
    for app in applications.prefetch_related("events"):
        applied_events = list(app.events.filter(status=Application.Status.APPLIED).order_by("timestamp"))
        if not applied_events:
            applied_at = app.applied_at
        else:
            applied_at = applied_events[0].timestamp
        reply = app.events.filter(
            timestamp__gt=applied_at,
            event_type=ApplicationEvent.EventType.STATUS_CHANGED,
        ).exclude(status="").order_by("timestamp").first()
        if reply:
            deltas.append((reply.timestamp - applied_at).total_seconds() / 86400)

    return {
        "total_jobs": Job.objects.count(),
        "new_jobs_24h": Job.objects.filter(first_seen__gte=timezone.now() - timedelta(days=1)).count(),
        "unscored_jobs": Job.objects.filter(llm_score__isnull=True).count(),
        "manual_review_jobs": Job.objects.filter(manual_review=True).count(),
        "total_applied": total_applied,
        "reply_rate": round(replied_count / total_applied * 100, 1) if total_applied else 0,
        "interview_rate": round(interview_count / total_applied * 100, 1) if total_applied else 0,
        "active_count": active_count,
        "avg_reply_days": round(sum(deltas) / len(deltas), 1) if deltas else None,
    }


def trend_series(queryset, date_field):
    counts = queryset.values(date_field).annotate(count=Count("id")).order_by(date_field)
    return [{"date": row[date_field].isoformat() if row[date_field] else None, "count": row["count"]} for row in counts]


def sankey_edges():
    edges = {}
    for application in Application.objects.prefetch_related("events"):
        previous = None
        for event in application.events.order_by("timestamp"):
            status = event.status
            if not status:
                continue
            if previous and previous != status:
                key = (previous, status)
                edges[key] = edges.get(key, 0) + 1
            previous = status
    return [{"source": s, "target": t, "value": v} for (s, t), v in edges.items()]

from concurrent.futures import ThreadPoolExecutor
_TASK_EXECUTOR = ThreadPoolExecutor(max_workers=2)

def _run_background(task_id, fn):
    task = BackgroundTask.objects.get(pk=task_id)
    task.status = BackgroundTask.Status.RUNNING
    task.started_at = timezone.now()
    task.save(update_fields=["status", "started_at"])
    try:
        fn(task)
        task.status = BackgroundTask.Status.DONE
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "finished_at"])
    except Exception as exc:
        task.status = BackgroundTask.Status.FAILED
        task.error = str(exc)
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "error", "finished_at"])

def queue_task(kind, fn):
    task = BackgroundTask.objects.create(kind=kind, status=BackgroundTask.Status.QUEUED)
    _TASK_EXECUTOR.submit(_run_background, task.pk, fn)
    return task

def background_search(task, search_ids=None):
    searches = list(JobSearch.objects.filter(active=True).order_by("pk"))
    if search_ids:
        searches = [s for s in searches if s.pk in search_ids]
    task.total = len(searches)
    task.save(update_fields=["total"])
    for idx, search in enumerate(searches, 1):
        for page in range(1, 21):
            data, rows, created, updated = sync_ba_jobs(search.was, search.wo, search.page_size, page, search.radius_km)
            if not rows or len(rows) < search.page_size:
                break
        task.progress = idx
        task.message = f"Finished search: {search.name}"
        task.save(update_fields=["progress", "message"])

def background_descriptions(task, limit=100):
    jobs = list(Job.objects.filter(beschreibung="", description_fetched_at__isnull=True).order_by("first_seen")[:limit])
    task.total = len(jobs)
    task.save(update_fields=["total"])
    for idx, job in enumerate(jobs, 1):
        update_job_description(job)
        task.progress = idx
        task.message = job.titel[:480]
        task.save(update_fields=["progress", "message"])

def background_score(task, limit=25):
    jobs = list(Job.objects.filter(beschreibung__gt="", llm_score__isnull=True).order_by("-first_seen")[:limit])
    cfg = get_app_config()
    profile = CandidateProfile.objects.filter(active=True).order_by("-version").first()
    if not profile:
        profile = CandidateProfile.objects.create(name="Web profile", profile_text=cfg.candidate_profile, version=1, active=True)
    elif cfg.candidate_profile and profile.profile_text != cfg.candidate_profile:
        profile.profile_text = cfg.candidate_profile
        profile.save(update_fields=["profile_text"])
    task.total = len(jobs)
    task.save(update_fields=["total"])
    with LlamaServer():
        for idx, job in enumerate(jobs, 1):
            evaluate_job(job, profile)
            task.progress = idx
            task.message = job.titel[:480]
            task.save(update_fields=["progress", "message"])
