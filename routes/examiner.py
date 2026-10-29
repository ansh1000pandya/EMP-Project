from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import current_user
from decorators import approved_examiner_required
from models import db, Exam, Slot, ExamExaminer, Booking, Evaluation
from datetime import datetime, date, time

examiner_bp = Blueprint('examiner', __name__, url_prefix='/examiner')


def _is_in_slot_creation_window(exam):
    """Return True only if current time is inside the slot-creation window."""
    now = datetime.utcnow()
    if not exam.slot_creation_start or not exam.slot_creation_end:
        return False
    return exam.slot_creation_start <= now <= exam.slot_creation_end


def _is_before_booking_start(exam):
    """Return True if booking has not started yet (slots can still be edited)."""
    if not exam.booking_start:
        return True
    return datetime.utcnow() < exam.booking_start


# ------------------------------------------------------------------
# DASHBOARD
# ------------------------------------------------------------------
@examiner_bp.route('/dashboard')
@approved_examiner_required
def dashboard():
    # Exams assigned to this examiner
    assigned = Exam.query.join(ExamExaminer).filter(
        ExamExaminer.examiner_id == current_user.id
    ).all()

    # Slots created by this examiner
    my_slots = Slot.query.filter_by(examiner_id=current_user.id).order_by(Slot.date, Slot.start_time).all()

    # Count of bookings on my slots
    booked_count = Booking.query.join(Slot).filter(
        Slot.examiner_id == current_user.id,
        Booking.status == 'Booked'
    ).count()

    return render_template('examiner/dashboard.html',
                           assigned_exams=assigned,
                           my_slots=my_slots,
                           booked_count=booked_count)


# ------------------------------------------------------------------
# LIST MY ASSIGNED EXAMS
# ------------------------------------------------------------------
@examiner_bp.route('/exams')
@approved_examiner_required
def my_exams():
    assigned = Exam.query.join(ExamExaminer).filter(
        ExamExaminer.examiner_id == current_user.id
    ).order_by(Exam.title).all()
    return render_template('examiner/exams.html', exams=assigned)


# ------------------------------------------------------------------
# SLOTS FOR ONE EXAM
# ------------------------------------------------------------------
@examiner_bp.route('/exams/<int:exam_id>/slots')
@approved_examiner_required
def exam_slots(exam_id):
    # Security: examiner must be assigned to this exam
    assignment = ExamExaminer.query.filter_by(
        exam_id=exam_id, examiner_id=current_user.id
    ).first()
    if not assignment:
        flash('You are not assigned to this exam.', 'danger')
        return redirect(url_for('examiner.my_exams'))

    exam = Exam.query.get_or_404(exam_id)
    slots = Slot.query.filter_by(exam_id=exam_id, examiner_id=current_user.id)\
                      .order_by(Slot.date, Slot.start_time).all()

    can_create = _is_in_slot_creation_window(exam)
    can_edit   = _is_before_booking_start(exam)

    return render_template('examiner/slots.html',
                           exam=exam,
                           slots=slots,
                           can_create=can_create,
                           can_edit=can_edit)


# ------------------------------------------------------------------
# CREATE SLOT
# ------------------------------------------------------------------
@examiner_bp.route('/exams/<int:exam_id>/slots/add', methods=['GET', 'POST'])
@approved_examiner_required
def add_slot(exam_id):
    assignment = ExamExaminer.query.filter_by(
        exam_id=exam_id, examiner_id=current_user.id
    ).first()
    if not assignment:
        flash('You are not assigned to this exam.', 'danger')
        return redirect(url_for('examiner.my_exams'))

    exam = Exam.query.get_or_404(exam_id)

    # Business rule 1: only during slot-creation window
    if not _is_in_slot_creation_window(exam):
        flash('Slot creation is not allowed outside the permitted window.', 'danger')
        return redirect(url_for('examiner.exam_slots', exam_id=exam_id))

    if request.method == 'POST':
        date_str   = request.form.get('date')
        start_str  = request.form.get('start_time')
        end_str    = request.form.get('end_time')
        capacity   = request.form.get('capacity', 1)

        if not all([date_str, start_str, end_str]):
            flash('Date, start time and end time are required.', 'danger')
            return redirect(url_for('examiner.add_slot', exam_id=exam_id))

        try:
            slot_date  = datetime.strptime(date_str, '%Y-%m-%d').date()
            start_time = datetime.strptime(start_str, '%H:%M').time()
            end_time   = datetime.strptime(end_str, '%H:%M').time()
            capacity   = int(capacity)
        except ValueError:
            flash('Invalid date or time format.', 'danger')
            return redirect(url_for('examiner.add_slot', exam_id=exam_id))

        if start_time >= end_time:
            flash('End time must be after start time.', 'danger')
            return redirect(url_for('examiner.add_slot', exam_id=exam_id))

        if capacity < 1:
            flash('Capacity must be at least 1.', 'danger')
            return redirect(url_for('examiner.add_slot', exam_id=exam_id))

        slot = Slot(
            exam_id=exam_id,
            examiner_id=current_user.id,
            date=slot_date,
            start_time=start_time,
            end_time=end_time,
            capacity=capacity,
            status='Available'
        )
        db.session.add(slot)
        db.session.commit()
        flash('Slot created successfully.', 'success')
        return redirect(url_for('examiner.exam_slots', exam_id=exam_id))

    return render_template('examiner/slot_form.html', exam=exam, slot=None)


# ------------------------------------------------------------------
# EDIT SLOT
# ------------------------------------------------------------------
@examiner_bp.route('/slots/<int:slot_id>/edit', methods=['GET', 'POST'])
@approved_examiner_required
def edit_slot(slot_id):
    slot = Slot.query.get_or_404(slot_id)

    # Ownership check
    if slot.examiner_id != current_user.id:
        flash('You can only edit your own slots.', 'danger')
        return redirect(url_for('examiner.dashboard'))

    exam = slot.exam

    # Business rule: cannot edit after booking has started
    if not _is_before_booking_start(exam):
        flash('Slots cannot be edited after booking has started.', 'danger')
        return redirect(url_for('examiner.exam_slots', exam_id=exam.id))

    if request.method == 'POST':
        date_str   = request.form.get('date')
        start_str  = request.form.get('start_time')
        end_str    = request.form.get('end_time')
        capacity   = request.form.get('capacity', 1)

        try:
            slot.date       = datetime.strptime(date_str, '%Y-%m-%d').date()
            slot.start_time = datetime.strptime(start_str, '%H:%M').time()
            slot.end_time   = datetime.strptime(end_str, '%H:%M').time()
            slot.capacity   = int(capacity)
        except ValueError:
            flash('Invalid date or time format.', 'danger')
            return redirect(url_for('examiner.edit_slot', slot_id=slot_id))

        if slot.start_time >= slot.end_time:
            flash('End time must be after start time.', 'danger')
            return redirect(url_for('examiner.edit_slot', slot_id=slot_id))

        # Recalculate status if capacity changed
        current_bookings = Booking.query.filter_by(slot_id=slot.id, status='Booked').count()
        if current_bookings >= slot.capacity:
            slot.status = 'Full'
        else:
            slot.status = 'Available'

        db.session.commit()
        flash('Slot updated successfully.', 'success')
        return redirect(url_for('examiner.exam_slots', exam_id=exam.id))

    return render_template('examiner/slot_form.html', exam=exam, slot=slot)


# ------------------------------------------------------------------
# DELETE (soft) SLOT
# ------------------------------------------------------------------
@examiner_bp.route('/slots/<int:slot_id>/delete', methods=['POST'])
@approved_examiner_required
def delete_slot(slot_id):
    slot = Slot.query.get_or_404(slot_id)

    if slot.examiner_id != current_user.id:
        flash('You can only delete your own slots.', 'danger')
        return redirect(url_for('examiner.dashboard'))

    exam = slot.exam

    if not _is_before_booking_start(exam):
        flash('Slots cannot be deleted after booking has started.', 'danger')
        return redirect(url_for('examiner.exam_slots', exam_id=exam.id))

    # Soft delete – keep history
    slot.status = 'Cancelled'
    db.session.commit()
    flash('Slot cancelled.', 'success')
    return redirect(url_for('examiner.exam_slots', exam_id=exam.id))
# ------------------------------------------------------------------
# VIEW BOOKED STUDENTS FOR MY SLOTS
# ------------------------------------------------------------------
@examiner_bp.route('/evaluations')
@approved_examiner_required
def evaluations():
    # All bookings on slots created by this examiner
    bookings = Booking.query.join(Slot).filter(
        Slot.examiner_id == current_user.id,
        Booking.status.in_(['Booked', 'Completed'])
    ).order_by(Booking.booked_at.desc()).all()

    return render_template('examiner/evaluations.html', bookings=bookings)


# ------------------------------------------------------------------
# EVALUATE ONE STUDENT
# ------------------------------------------------------------------
@examiner_bp.route('/bookings/<int:booking_id>/evaluate', methods=['GET', 'POST'])
@approved_examiner_required
def evaluate(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    # Security: only the examiner who owns the slot can evaluate
    if booking.slot.examiner_id != current_user.id:
        flash('You can only evaluate students booked in your own slots.', 'danger')
        return redirect(url_for('examiner.evaluations'))

    exam = booking.exam
    rubrics = exam.rubrics

    if not rubrics:
        flash('No rubrics defined for this exam. Contact Admin.', 'warning')
        return redirect(url_for('examiner.evaluations'))

    # Existing evaluations (if any)
    existing = {ev.rubric_id: ev for ev in booking.evaluations}

    if request.method == 'POST':
        total = 0
        for rubric in rubrics:
            marks = request.form.get(f'marks_{rubric.id}')
            remarks = request.form.get(f'remarks_{rubric.id}', '').strip()

            if marks is None or marks == '':
                flash(f'Marks required for: {rubric.criterion}', 'danger')
                return redirect(url_for('examiner.evaluate', booking_id=booking_id))

            try:
                marks = float(marks)
            except ValueError:
                flash('Invalid marks value.', 'danger')
                return redirect(url_for('examiner.evaluate', booking_id=booking_id))

            if marks < 0 or marks > rubric.max_marks:
                flash(f'Marks for {rubric.criterion} must be between 0 and {rubric.max_marks}.', 'danger')
                return redirect(url_for('examiner.evaluate', booking_id=booking_id))

            # Update or create evaluation
            if rubric.id in existing:
                ev = existing[rubric.id]
                ev.marks = marks
                ev.remarks = remarks or None
                ev.evaluated_at = datetime.utcnow()
            else:
                ev = Evaluation(
                    booking_id=booking.id,
                    rubric_id=rubric.id,
                    marks=marks,
                    remarks=remarks or None
                )
                db.session.add(ev)

            total += marks

        # Mark booking as Completed
        booking.status = 'Completed'
        db.session.commit()
        flash(f'Evaluation submitted successfully. Total: {total}', 'success')
        return redirect(url_for('examiner.evaluations'))

    return render_template('examiner/evaluate.html',
                           booking=booking,
                           rubrics=rubrics,
                           existing=existing)


# ------------------------------------------------------------------
# PUBLISH / UNPUBLISH RESULT
# ------------------------------------------------------------------
@examiner_bp.route('/bookings/<int:booking_id>/publish', methods=['POST'])
@approved_examiner_required
def publish_result(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if booking.slot.examiner_id != current_user.id:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('examiner.evaluations'))

    if not booking.evaluations:
        flash('Cannot publish. Evaluation not submitted yet.', 'warning')
        return redirect(url_for('examiner.evaluations'))

    booking.published = True
    db.session.commit()
    flash('Result published. Student can now view it.', 'success')
    return redirect(url_for('examiner.evaluations'))


@examiner_bp.route('/bookings/<int:booking_id>/unpublish', methods=['POST'])
@approved_examiner_required
def unpublish_result(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if booking.slot.examiner_id != current_user.id:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('examiner.evaluations'))

    booking.published = False
    db.session.commit()
    flash('Result unpublished.', 'info')
    return redirect(url_for('examiner.evaluations'))