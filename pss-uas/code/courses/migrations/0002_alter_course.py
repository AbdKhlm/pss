
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("courses", "0001_initial"),
    ]

    operations = [
        # Rename title to name
        migrations.RenameField(
            model_name="course",
            old_name="title",
            new_name="name",
        ),
        # Add price, image, updated_at
        migrations.AddField(
            model_name="course",
            name="price",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="course",
            name="image",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="course",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
    ]
