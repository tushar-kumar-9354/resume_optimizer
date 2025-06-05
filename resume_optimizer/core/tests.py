# In the new migration file (e.g., 0002_remove_redundant_fields.py)
from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='challenge',
            name='mcq_answer',
        ),
        migrations.RemoveField(
            model_name='challenge',
            name='mcq_options',
        ),
    ]