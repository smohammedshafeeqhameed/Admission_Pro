from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('admission_system', '0023_commission_settlement'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='addoncourse',
            unique_together={('course', 'name')},
        ),
    ]
