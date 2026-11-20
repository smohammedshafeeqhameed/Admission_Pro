from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admission_system', '0021_application_executive_commission_review'),
    ]

    operations = [
        migrations.AddField(
            model_name='college',
            name='address',
            field=models.TextField(blank=True, null=True, help_text='Full postal address, shown on the application form letterhead'),
        ),
        migrations.AddField(
            model_name='college',
            name='affiliation',
            field=models.CharField(blank=True, null=True, max_length=255, help_text="e.g. 'Affiliated to Mahatma Gandhi University' - shown under the college name on the application form"),
        ),
        migrations.AddField(
            model_name='college',
            name='email',
            field=models.EmailField(blank=True, null=True, max_length=254, help_text='Admissions contact email, shown on the application form'),
        ),
        migrations.AddField(
            model_name='college',
            name='phone',
            field=models.CharField(blank=True, null=True, max_length=100, help_text='Contact phone number(s), shown on the application form'),
        ),
        migrations.AddField(
            model_name='college',
            name='website',
            field=models.URLField(blank=True, null=True, help_text='College website, shown on the application form'),
        ),
    ]
