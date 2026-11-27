from collections import defaultdict

from django.db import migrations


def dedupe_addoncourses(apps, schema_editor):
    """
    This migration adds unique_together = ('course', 'name') to AddonCourse,
    but some databases have a duplicated (course_id, name) pair (e.g.
    course_id=184, name="Ethical hacking & Cyber Security"), which makes the
    unique index creation fail with a UniqueViolation.

    For each duplicated (course_id, name) pair, keep the lowest-id row and
    delete the rest before the constraint is added. Nothing else has a
    foreign key onto AddonCourse (it's only looked up by course_id/name in
    forms.py and views.py), so deleting the extra rows is safe.
    """
    AddonCourse = apps.get_model('admission_system', 'AddonCourse')

    seen = defaultdict(list)
    for addon_id, course_id, name in AddonCourse.objects.order_by('id').values_list(
        'id', 'course_id', 'name'
    ):
        seen[(course_id, name)].append(addon_id)

    duplicate_ids = []
    for ids in seen.values():
        if len(ids) > 1:
            # keep the first (lowest id), drop the rest
            duplicate_ids.extend(ids[1:])

    if duplicate_ids:
        AddonCourse.objects.filter(id__in=duplicate_ids).delete()


def noop_reverse(apps, schema_editor):
    # Deleted duplicate rows can't be meaningfully restored; nothing to do.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('admission_system', '0023_commission_settlement'),
    ]

    operations = [
        migrations.RunPython(dedupe_addoncourses, noop_reverse),
        migrations.AlterUniqueTogether(
            name='addoncourse',
            unique_together={('course', 'name')},
        ),
    ]
