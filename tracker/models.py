from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone


class BlacklistEntry(models.Model):
    term = models.CharField(max_length=200, unique=True)
    reason = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["term"]
        verbose_name_plural = "blacklist entries"

    def __str__(self):
        return self.term


class CandidateProfile(models.Model):
    name = models.CharField(max_length=200)
    profile_text = models.TextField()
    version = models.PositiveIntegerField(default=1)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version", "name"]

    def __str__(self):
        return f"{self.name} v{self.version}"


class JobSearch(models.Model):
    name = models.CharField(max_length=200, unique=True)
    was = models.CharField(max_length=300, blank=True)
    wo = models.CharField(max_length=200, default="Berlin")
    radius_km = models.PositiveIntegerField(default=50)
    page_size = models.PositiveIntegerField(default=25)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class JobSyncRun(models.Model):
    search = models.ForeignKey(JobSearch, on_delete=models.CASCADE, related_name="sync_runs")
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    jobs_seen = models.PositiveIntegerField(default=0)
    jobs_created = models.PositiveIntegerField(default=0)
    jobs_updated = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]


class Job(models.Model):
    referenznummer = models.CharField(max_length=100, primary_key=True)
    titel = models.CharField(max_length=500)
    firma = models.CharField(max_length=300, blank=True)
    beruf = models.CharField(max_length=300, blank=True)

    ort = models.CharField(max_length=200, blank=True)
    plz = models.CharField(max_length=20, blank=True)
    strasse = models.CharField(max_length=300, blank=True)
    entfernung_km = models.FloatField(null=True, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    vollzeit = models.BooleanField(null=True, blank=True)
    homeoffice = models.BooleanField(null=True, blank=True)
    stellenangebotsart = models.CharField(max_length=100, blank=True)
    homeofficetyp = models.CharField(max_length=100, blank=True)

    eintrittsdatum = models.DateField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    source_updated_at = models.DateTimeField(null=True, blank=True)
    source = models.CharField(max_length=50, default="arbeitsagentur")

    beschreibung = models.TextField(blank=True)
    bewerbungslink = models.URLField(max_length=1500, blank=True)
    description_fetched_at = models.DateTimeField(null=True, blank=True)
    description_hash = models.CharField(max_length=64, blank=True)

    # Cached read-model fields; complete evaluation history lives in JobEvaluation.
    llm_score = models.FloatField(null=True, blank=True)
    llm_pro = models.JSONField(default=list, blank=True)
    llm_contra = models.JSONField(default=list, blank=True)
    llm_model = models.CharField(max_length=200, blank=True)
    llm_prompt_version = models.CharField(max_length=50, blank=True)
    llm_scored_at = models.DateTimeField(null=True, blank=True)

    buzzword_score = models.FloatField(null=True, blank=True)
    buzzword_hits = models.JSONField(default=list, blank=True)
    buzzword_scored_at = models.DateTimeField(null=True, blank=True)
    score_divergence = models.FloatField(null=True, blank=True)
    manual_review = models.BooleanField(default=False)

    first_seen = models.DateTimeField(default=timezone.now)
    last_seen = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-first_seen"]
        indexes = [
            models.Index(fields=["-first_seen"]),
            models.Index(fields=["-llm_score"]),
            models.Index(fields=["firma"]),
            models.Index(fields=["ort"]),
            models.Index(fields=["manual_review"]),
        ]

    def __str__(self):
        return f"{self.titel} @ {self.firma}"

    def get_absolute_url(self):
        return reverse("tracker:job_detail", args=[self.referenznummer])

    @property
    def application(self):
        prefetched = getattr(self, "_prefetched_applications", None)
        if prefetched is not None:
            return prefetched[0] if prefetched else None
        return self.applications.order_by("-created_at").first()


class JobEvaluation(models.Model):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="evaluations")
    profile = models.ForeignKey(CandidateProfile, on_delete=models.PROTECT, related_name="evaluations")
    score = models.FloatField()
    pro = models.JSONField(default=list, blank=True)
    contra = models.JSONField(default=list, blank=True)
    model_name = models.CharField(max_length=200)
    prompt_version = models.CharField(max_length=50)
    raw_response = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["job", "-created_at"])]


class Application(models.Model):
    class Status(models.TextChoices):
        APPLIED = "applied", "Applied"
        REJECTED = "rejected", "Rejected"
        INTERVIEW_INVITED = "interview_invited", "Interview invited"
        INTERVIEW_DONE = "interview_done", "Interview done"
        OFFER = "offer", "Offer"
        WITHDRAWN = "withdrawn", "Withdrawn"

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="applications")
    current_status = models.CharField(max_length=30, choices=Status.choices, default=Status.APPLIED)
    applied_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-applied_at"]
        indexes = [models.Index(fields=["current_status", "-applied_at"])]

    def __str__(self):
        return f"{self.job.titel} — {self.get_current_status_display()}"

    @transaction.atomic
    def set_status(self, status: str, source: str = "manual", note: str = "", email_message=None, confidence=None):
        if status not in Application.Status.values:
            raise ValueError(f"Invalid application status: {status}")
        self.current_status = status
        self.save(update_fields=["current_status", "updated_at"])
        return ApplicationEvent.objects.create(
            application=self,
            event_type=ApplicationEvent.EventType.STATUS_CHANGED,
            status=status,
            source=source,
            note=note,
            email_message=email_message,
            confidence=confidence,
        )


class EmailMessage(models.Model):
    provider = models.CharField(max_length=50, default="imap")
    message_id = models.CharField(max_length=500, unique=True)
    thread_id = models.CharField(max_length=500, blank=True)
    sender = models.EmailField(blank=True)
    recipients = models.TextField(blank=True)
    subject = models.TextField(blank=True)
    received_at = models.DateTimeField()
    body_text = models.TextField(blank=True)
    body_html = models.TextField(blank=True)

    application = models.ForeignKey(
        Application,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="emails",
    )
    parsed = models.BooleanField(default=False)
    classification = models.CharField(max_length=100, blank=True)
    classification_confidence = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at"]
        indexes = [models.Index(fields=["-received_at"])]

    def __str__(self):
        return f"{self.received_at:%Y-%m-%d} {self.subject[:80]}"


class ApplicationEvent(models.Model):
    class EventType(models.TextChoices):
        STATUS_CHANGED = "status_changed", "Status changed"
        AUTO_REPLY = "auto_reply", "Auto reply"
        EMAIL_RECEIVED = "email_received", "Email received"
        INTERVIEW_SCHEDULED = "interview_scheduled", "Interview scheduled"
        INTERVIEW_COMPLETED = "interview_completed", "Interview completed"
        NOTE = "note", "Note"

    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        EMAIL_PARSED = "email_parsed", "Email parsed"
        LLM_CLASSIFIED = "llm_classified", "LLM classified"
        SYSTEM = "system", "System"

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=40, choices=EventType.choices)
    status = models.CharField(max_length=30, choices=Application.Status.choices, blank=True)
    source = models.CharField(max_length=30, choices=Source.choices, default=Source.MANUAL)
    note = models.TextField(blank=True)
    timestamp = models.DateTimeField(default=timezone.now)
    email_message = models.ForeignKey(
        EmailMessage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="application_events",
    )
    confidence = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["timestamp"]
        constraints = [
            models.UniqueConstraint(
                fields=["application", "email_message", "event_type"],
                name="uniq_application_email_event_type",
            )
        ]


class ApplicationDocument(models.Model):
    class Type(models.TextChoices):
        COVER_LETTER = "cover_letter", "Cover letter"
        CV = "cv", "CV"
        EMAIL = "email", "Application email"

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="documents")
    application = models.ForeignKey(
        Application,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="documents",
    )
    document_type = models.CharField(max_length=30, choices=Type.choices)
    title = models.CharField(max_length=300)
    content = models.TextField()
    model_name = models.CharField(max_length=200, blank=True)
    prompt_version = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]