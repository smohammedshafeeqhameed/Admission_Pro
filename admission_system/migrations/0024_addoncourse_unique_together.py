from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('admission_system', '0024_dedupe_addoncourse_duplicates'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='addoncourse',
            unique_together={('course', 'name')},
        ),
    ]
