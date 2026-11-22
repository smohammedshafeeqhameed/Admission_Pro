import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('admission_system', '0022_college_letterhead_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='application',
            name='commission_status',
            field=models.CharField(
                choices=[
                    ('Not Applied', 'Not Applied'),
                    ('Pending', 'Pending Finance Review'),
                    ('Finance Approved', 'Pending Executive Approval'),
                    ('Approved', 'Approved'),
                    ('Settled', 'Settled'),
                    ('Rejected', 'Rejected'),
                ],
                default='Not Applied',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='application',
            name='commission_receipt',
            field=models.FileField(
                blank=True, null=True, upload_to='commission/receipts/',
                help_text='Payment receipt / bill uploaded by the Finance Manager as proof the CRE has actually been paid. Set when the commission is settled.',
            ),
        ),
        migrations.AddField(
            model_name='application',
            name='commission_settled_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='commission_settlements', to=settings.AUTH_USER_MODEL,
                help_text='Finance Manager who uploaded the payment receipt and marked this commission as settled.',
            ),
        ),
        migrations.AddField(
            model_name='application',
            name='commission_settled_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
