from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import current_user
from decorators import role_required
from models import db, Exam, Slot, Booking, Course
from datetime import datetime

student_bp = Blueprint('student', __name__, url_prefix='/student')


def _is_in_booking_window(exam):
    now = datetime.utcnow()
    if not exam.booking_start or not exam.booking_end:
        return False
    return exam.booking_start <= now <= exam.booking_end


# ------------------------------------------------------------------
# DASHBOARD
# ------------------------------------------------------------------
@student_bp.route('/dashboard')
@role_required('student')
def dashboard():
    # Upcoming bookings
    my_bookings = Booking.query.filter_by(student_id=current_user.id)\
                               .order_by(Booking.booked_at.desc()).all()

    # Available exams (status = Booking Open)
    available_exams = Exam.query.filter_by(status='Booking Open').all()

    return render_template('student/dashboard.html',
                           my_bookings=my_bookings,
                           available_exams=available_exams)


# ------------------------------------------------------------------
# BROWSE / SEARCH EXAMS
# ------------------------------------------------------------------
@student_bp.route('/exams')
@role_required('student')
def exams():
    q = request.args.get('q', '').strip()
    exam_type = request.args.get('type', '')

    query = Exam.query.filter(Exam.status.in_(['Booking Open', 'Closed', 'Completed']))

    if q:
        query = query.filter(Exam.title.ilike(f'%{q}%'))
    if exam_type:
        query = query.filter_by(exam_type=exam_type)

    exams = query.order_by(Exam.title).all()
    return render_template('student/exams.html', exams=exams, q=q, exam_type=exam_type)


# ------------------------------------------------------------------
# VIEW SLOTS OF ONE EXAM + BOOK
# ------------------------------------------------------------------
@student_bp.route('/exams/<int:exam_id>/slots')
@role_required('student')
def exam_slots(exam_id):
    exam = Exam.query.get_or_404(exam_id)

    # Only show Available slots
    slots = Slot.query.filter_by(exam_id=exam_id, status='Available')\
                      .order_by(Slot.date, Slot.start_time).all()

    # Does this student already have a booking for this exam?
    existing = Booking.query.filter_by(
        student_id=current_user.id,
        exam_id=exam_id,
        status='Booked'
    ).first()

    can_book = _is_in_booking_window(exam) and existing is None

    return render_template('student/slots.html',
                           exam=exam,
                           slots=slots,
                           existing_booking=existing,
                           can_book=can_book)


@student_bp.route('/slots/<int:slot_id>/book', methods=['POST'])
@role_required('student')
def book_slot(slot_id):
    slot = Slot.query.get_or_404(slot_id)
    exam = slot.exam

    # 1. Must be in booking window
    if not _is_in_booking_window(exam):
        flash('Booking is not allowed outside the booking window.', 'danger')
        return redirect(url_for('student.exam_slots', exam_id=exam.id))

    # 2. Slot must be Available
    if slot.status != 'Available':
        flash('This slot is no longer available.', 'danger')
        return redirect(url_for('student.exam_slots', exam_id=exam.id))

    # 3. No duplicate booking for same exam
    existing = Booking.query.filter_by(
        student_id=current_user.id,
        exam_id=exam.id,
        status='Booked'
    ).first()
    if existing:
        flash('You have already booked a slot for this exam.', 'danger')
        return redirect(url_for('student.exam_slots', exam_id=exam.id))

    # 4. Capacity check
    current_bookings = Booking.query.filter_by(slot_id=slot.id, status='Booked').count()
    if current_bookings >= slot.capacity:
        slot.status = 'Full'
        db.session.commit()
        flash('Sorry, this slot has just become full.', 'danger')
        return redirect(url_for('student.exam_slots', exam_id=exam.id))

    # Create booking
    booking = Booking(
        student_id=current_user.id,
        exam_id=exam.id,
        slot_id=slot.id,
        status='Booked'
    )
    db.session.add(booking)

    # Update slot status if now full
    if current_bookings + 1 >= slot.capacity:
        slot.status = 'Full'

    db.session.commit()
    flash('Slot booked successfully!', 'success')
    return redirect(url_for('student.dashboard'))


# ------------------------------------------------------------------
# CANCEL BOOKING
# ------------------------------------------------------------------
@student_bp.route('/bookings/<int:booking_id>/cancel', methods=['POST'])
@role_required('student')
def cancel_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    # Ownership
    if booking.student_id != current_user.id:
        flash('You can only cancel your own bookings.', 'danger')
        return redirect(url_for('student.dashboard'))

    if booking.status != 'Booked':
        flash('This booking cannot be cancelled.', 'danger')
        return redirect(url_for('student.dashboard'))

    exam = booking.exam

    # Can cancel only before booking window ends
    if exam.booking_end and datetime.utcnow() > exam.booking_end:
        flash('Booking deadline has passed. Cannot cancel.', 'danger')
        return redirect(url_for('student.dashboard'))

    # Soft cancel
    booking.status = 'Cancelled'
    booking.cancelled_at = datetime.utcnow()

    # Re-open the slot if it was Full
    slot = booking.slot
    current_bookings = Booking.query.filter_by(slot_id=slot.id, status='Booked').count()
    # Note: current_bookings still includes this one until commit, so we subtract 1
    if slot.status == 'Full' and (current_bookings - 1) < slot.capacity:
        slot.status = 'Available'

    db.session.commit()
    flash('Booking cancelled successfully.', 'success')
    return redirect(url_for('student.dashboard'))


# ------------------------------------------------------------------
# MY BOOKINGS / HISTORY
# ------------------------------------------------------------------
@student_bp.route('/bookings')
@role_required('student')
def my_bookings():
    bookings = Booking.query.filter_by(student_id=current_user.id)\
                            .order_by(Booking.booked_at.desc()).all()
    return render_template('student/bookings.html', bookings=bookings)