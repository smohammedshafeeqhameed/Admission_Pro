from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admission_system', '0024_addoncourse_unique_together'),
    ]

    operations = [
        migrations.AlterField(
            model_name='student',
            name='category',
            field=models.CharField(
                max_length=50,
                null=True,
                blank=True,
                choices=[
                    ('', '----------'),
                    ('General', 'General / OC'),
                    ('OBC', 'OBC'),
                    ('SC', 'SC'),
                    ('ST', 'ST'),
                    ('EWS', 'EWS'),
                    ('Other', 'Other'),
                ],
            ),
        ),
    ]
