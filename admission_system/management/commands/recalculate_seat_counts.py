"""
P0 fix / data-integrity tool for the "Campus dashboard seat count is wrong"
bug report (Al Shifa: only 1 student actually admitted, but the dashboard
showed 3 of 40 seats filled, 37 available).

Root cause: Course.occupied_seats is a single running counter that is only
ever incremented/decremented by Application.admit()/unadmit() - it has no
academic-year dimension. Everywhere seat capacity is displayed (Campus
Manager, Admin and Executive dashboards) reads this counter directly rather
than counting current Admitted applications live. If it ever drifted out of
sync with reality - e.g. from admits made before the admit()/unadmit()
race-safety guards existed, manual database edits, or a student being
admitted and the seat never released - the stale number persists forever,
because nothing ever recomputes it.

This command is the safe corrective action: it recalculates every course's
occupied_seats from the actual, current COUNT of Application rows with
status='Admitted', and corrects any drift. It is idempotent and safe to
re-run at any time (e.g. on a schedule, or whenever a seat count looks
wrong) - it never touches total_seats or anything else.

Usage:
    python manage.py recalculate_seat_counts            # apply fixes
    python manage.py recalculate_seat_counts --dry-run   # report only
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Q

from admission_system.models import Course


class Command(BaseCommand):
    help = "Recalculate Course.occupied_seats from the actual count of Admitted applications, fixing any drift."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help="Report mismatches without writing any changes.",
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        courses = Course.objects.annotate(
            actual_admitted=Count('applications', filter=Q(applications__status='Admitted'))
        )

        mismatches = 0
        with transaction.atomic():
            for course in courses:
                if course.occupied_seats != course.actual_admitted:
                    mismatches += 1
                    self.stdout.write(
                        f"{course.college.name} / {course.name}: "
                        f"occupied_seats={course.occupied_seats} -> {course.actual_admitted} "
                        f"(total_seats={course.total_seats})"
                    )
                    if not dry_run:
                        course.occupied_seats = course.actual_admitted
                        course.save(update_fields=['occupied_seats'])
            if dry_run:
                # Roll back - this transaction only exists to make the
                # annotate() query consistent with the save loop, not to
                # commit anything in dry-run mode.
                transaction.set_rollback(True)

        if mismatches == 0:
            self.stdout.write(self.style.SUCCESS("No drift found - every course's occupied_seats matches its actual Admitted application count."))
        elif dry_run:
            self.stdout.write(self.style.WARNING(f"{mismatches} course(s) would be corrected. Re-run without --dry-run to apply."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Corrected {mismatches} course(s)."))
