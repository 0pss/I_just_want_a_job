from django.contrib import admin
from .models import (
    Application,
    ApplicationDocument,
    ApplicationEvent,
    BlacklistEntry,
    CandidateProfile,
    EmailMessage,
    Job,
    JobEvaluation,
    JobSearch,
    JobSyncRun,
)


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("referenznummer", "titel", "firma", "llm_score", "buzzword_score", "score_divergence", "manual_review", "first_seen")
    list_filter = ("manual_review", "vollzeit", "homeoffice", "ort")
    search_fields = ("referenznummer", "titel", "firma", "beruf")
    ordering = ("-first_seen",)


@admin.register(JobEvaluation)
class JobEvaluationAdmin(admin.ModelAdmin):
    list_display = ("job", "profile", "score", "model_name", "created_at")
    list_filter = ("profile", "model_name")
    search_fields = ("job__titel", "job__firma")
    ordering = ("-created_at",)


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("job", "current_status", "applied_at", "updated_at")
    list_filter = ("current_status",)
    search_fields = ("job__titel", "job__firma")


@admin.register(ApplicationEvent)
class ApplicationEventAdmin(admin.ModelAdmin):
    list_display = ("application", "event_type", "status", "source", "timestamp", "confidence")
    list_filter = ("event_type", "status", "source")
    ordering = ("-timestamp",)


@admin.register(EmailMessage)
class EmailMessageAdmin(admin.ModelAdmin):
    list_display = ("received_at", "sender", "subject", "application", "classification", "parsed")
    list_filter = ("parsed", "classification")
    search_fields = ("message_id", "sender", "subject", "body_text")
    ordering = ("-received_at",)


@admin.register(ApplicationDocument)
class ApplicationDocumentAdmin(admin.ModelAdmin):
    list_display = ("job", "document_type", "title", "created_at")
    list_filter = ("document_type",)
    search_fields = ("job__titel", "job__firma", "title", "content")


@admin.register(CandidateProfile)
class CandidateProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "version", "active", "created_at")
    list_filter = ("active",)


@admin.register(JobSearch)
class JobSearchAdmin(admin.ModelAdmin):
    list_display = ("name", "was", "wo", "radius_km", "active")
    list_filter = ("active",)


@admin.register(JobSyncRun)
class JobSyncRunAdmin(admin.ModelAdmin):
    list_display = ("search", "started_at", "finished_at", "jobs_seen", "jobs_created", "jobs_updated")
    ordering = ("-started_at",)


@admin.register(BlacklistEntry)
class BlacklistEntryAdmin(admin.ModelAdmin):
    list_display = ("term", "reason", "created_at")
    search_fields = ("term", "reason")