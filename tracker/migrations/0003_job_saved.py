from django.db import migrations, models
class Migration(migrations.Migration):
    dependencies=[("tracker","0002_appconfig_backgroundtask")]
    operations=[migrations.AddField(model_name="job",name="saved",field=models.BooleanField(default=False))]
