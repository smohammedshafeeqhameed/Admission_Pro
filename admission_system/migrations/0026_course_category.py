from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admission_system', '0025_student_category_choices'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='category',
            field=models.CharField(
                max_length=20,
                blank=True,
                default='',
                choices=[
                    ('', '— No category —'),
                    ('btech', 'B.Tech Engineering'),
                    ('diploma', 'Diploma'),
                    ('mgmt', 'Management'),
                ],
            ),
        ),
    ]
