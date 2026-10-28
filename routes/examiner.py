from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import current_user
from decorators import approved_examiner_required
from models import db, Exam, Slot, ExamExaminer, Booking
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