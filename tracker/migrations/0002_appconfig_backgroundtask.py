from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("tracker", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="AppConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=100, unique=True)),
                ("candidate_profile", models.TextField(blank=True, default="")),
                ("system_prompt", models.TextField(blank=True, default="")),
                ("buzzwords", models.JSONField(blank=True, default=list)),
                ("divergence_threshold", models.FloatField(default=3.0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="BackgroundTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("search","Job search"),("descriptions","Job descriptions"),("score","LLM rating"),("full_pipeline","Full pipeline")], max_length=30)),
                ("status", models.CharField(choices=[("queued","Queued"),("running","Running"),("done","Done"),("failed","Failed")], default="queued", max_length=20)),
                ("progress", models.PositiveIntegerField(default=0)),
                ("total", models.PositiveIntegerField(default=0)),
                ("message", models.CharField(blank=True, max_length=500)),
                ("error", models.TextField(blank=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering":["-created_at"]},
        ),
    ]
