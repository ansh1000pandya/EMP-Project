from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import current_user
from decorators import role_required
from models import db, User, ExaminerProfile, Course, Exam, Rubric, ExamExaminer
from datetime import datetime

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# ------------------------------------------------------------------
# DASHBOARD
# ------------------------------------------------------------------
@admin_bp.route('/dashboard')
@role_required('admin')
def dashboard():
    counts = {
        'courses': Course.query.count(),
        'exams': Exam.query.count(),
        'examiners': User.query.filter_by(role='examiner').count(),
        'students': User.query.filter_by(role='student').count(),
        'pending_examiners': ExaminerProfile.query.filter_by(status='Pending').count(),
    }
    return render_template('admin/dashboard.html', counts=counts)


# ------------------------------------------------------------------
# COURSES CRUD
# ------------------------------------------------------------------
@admin_bp.route('/courses')
@role_required('admin')
def courses():
    all_courses = Course.query.order_by(Course.code).all()
    return render_template('admin/courses.html', courses=all_courses)


@admin_bp.route('/courses/add', methods=['GET', 'POST'])
@role_required('admin')
def add_course():
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()

        if not code or not name:
            flash('Code and Name are required.', 'danger')
            return redirect(url_for('admin.add_course'))

        if Course.query.filter_by(code=code).first():
            flash('Course code already exists.', 'danger')
            return redirect(url_for('admin.add_course'))

        course = Course(code=code, name=name, description=description or None)
        db.session.add(course)
        db.session.commit()
        flash('Course added successfully.', 'success')
        return redirect(url_for('admin.courses'))

    return render_template('admin/course_form.html', course=None)


@admin_bp.route('/courses/<int:id>/edit', methods=['GET', 'POST'])
@role_required('admin')
def edit_course(id):
    course = Course.query.get_or_404(id)

    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()

        if not code or not name:
            flash('Code and Name are required.', 'danger')
            return redirect(url_for('admin.edit_course', id=id))

        existing = Course.query.filter(Course.code == code, Course.id != id).first()
        if existing:
            flash('Course code already exists.', 'danger')
            return redirect(url_for('admin.edit_course', id=id))

        course.code = code
        course.name = name
        course.description = description or None
        db.session.commit()
        flash('Course updated successfully.', 'success')
        return redirect(url_for('admin.courses'))

    return render_template('admin/course_form.html', course=course)


@admin_bp.route('/courses/<int:id>/delete', methods=['POST'])
@role_required('admin')
def delete_course(id):
    course = Course.query.get_or_404(id)
    if course.exams:
        flash('Cannot delete course that has exams. Delete exams first.', 'danger')
        return redirect(url_for('admin.courses'))
    db.session.delete(course)
    db.session.commit()
    flash('Course deleted.', 'success')
    return redirect(url_for('admin.courses'))


# ------------------------------------------------------------------
# EXAMS CRUD
# ------------------------------------------------------------------
@admin_bp.route('/exams')
@role_required('admin')
def exams():
    all_exams = Exam.query.order_by(Exam.created_at.desc()).all()
    return render_template('admin/exams.html', exams=all_exams)


@admin_bp.route('/exams/add', methods=['GET', 'POST'])
@role_required('admin')
def add_exam():
    courses = Course.query.order_by(Course.code).all()
    if request.method == 'POST':
        course_id = request.form.get('course_id')
        title = request.form.get('title', '').strip()
        exam_type = request.form.get('exam_type')
        status = request.form.get('status', 'Draft')
        description = request.form.get('description', '').strip()

        # Time windows (optional at creation)
        slot_start = request.form.get('slot_creation_start') or None
        slot_end   = request.form.get('slot_creation_end') or None
        book_start = request.form.get('booking_start') or None
        book_end   = request.form.get('booking_end') or None

        if not course_id or not title or not exam_type:
            flash('Course, Title and Type are required.', 'danger')
            return redirect(url_for('admin.add_exam'))

        exam = Exam(
            course_id=int(course_id),
            title=title,
            exam_type=exam_type,
            status=status,
            description=description or None,
            slot_creation_start=datetime.fromisoformat(slot_start) if slot_start else None,
            slot_creation_end=datetime.fromisoformat(slot_end) if slot_end else None,
            booking_start=datetime.fromisoformat(book_start) if book_start else None,
            booking_end=datetime.fromisoformat(book_end) if book_end else None,
        )
        db.session.add(exam)
        db.session.commit()
        flash('Exam created successfully.', 'success')
        return redirect(url_for('admin.exams'))

    return render_template('admin/exam_form.html', exam=None, courses=courses)


@admin_bp.route('/exams/<int:id>/edit', methods=['GET', 'POST'])
@role_required('admin')
def edit_exam(id):
    exam = Exam.query.get_or_404(id)
    courses = Course.query.order_by(Course.code).all()

    if request.method == 'POST':
        exam.course_id = int(request.form.get('course_id'))
        exam.title = request.form.get('title', '').strip()
        exam.exam_type = request.form.get('exam_type')
        exam.status = request.form.get('status')
        exam.description = request.form.get('description', '').strip() or None

        slot_start = request.form.get('slot_creation_start') or None
        slot_end   = request.form.get('slot_creation_end') or None
        book_start = request.form.get('booking_start') or None
        book_end   = request.form.get('booking_end') or None

        exam.slot_creation_start = datetime.fromisoformat(slot_start) if slot_start else None
        exam.slot_creation_end   = datetime.fromisoformat(slot_end) if slot_end else None
        exam.booking_start       = datetime.fromisoformat(book_start) if book_start else None
        exam.booking_end         = datetime.fromisoformat(book_end) if book_end else None

        db.session.commit()
        flash('Exam updated successfully.', 'success')
        return redirect(url_for('admin.exams'))

    return render_template('admin/exam_form.html', exam=exam, courses=courses)


@admin_bp.route('/exams/<int:id>/delete', methods=['POST'])
@role_required('admin')
def delete_exam(id):
    exam = Exam.query.get_or_404(id)
    db.session.delete(exam)
    db.session.commit()
    flash('Exam deleted.', 'success')
    return redirect(url_for('admin.exams'))


# ------------------------------------------------------------------
# RUBRICS (per exam)
# ------------------------------------------------------------------
@admin_bp.route('/exams/<int:exam_id>/rubrics')
@role_required('admin')
def rubrics(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    return render_template('admin/rubrics.html', exam=exam, rubrics=exam.rubrics)


@admin_bp.route('/exams/<int:exam_id>/rubrics/add', methods=['GET', 'POST'])
@role_required('admin')
def add_rubric(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    if request.method == 'POST':
        criterion = request.form.get('criterion', '').strip()
        max_marks = request.form.get('max_marks')
        description = request.form.get('description', '').strip()

        if not criterion or not max_marks:
            flash('Criterion and Max Marks are required.', 'danger')
            return redirect(url_for('admin.add_rubric', exam_id=exam_id))

        rubric = Rubric(
            exam_id=exam_id,
            criterion=criterion,
            max_marks=float(max_marks),
            description=description or None
        )
        db.session.add(rubric)
        db.session.commit()
        flash('Rubric added.', 'success')
        return redirect(url_for('admin.rubrics', exam_id=exam_id))

    return render_template('admin/rubric_form.html', exam=exam, rubric=None)


@admin_bp.route('/rubrics/<int:id>/edit', methods=['GET', 'POST'])
@role_required('admin')
def edit_rubric(id):
    rubric = Rubric.query.get_or_404(id)
    if request.method == 'POST':
        rubric.criterion = request.form.get('criterion', '').strip()
        rubric.max_marks = float(request.form.get('max_marks'))
        rubric.description = request.form.get('description', '').strip() or None
        db.session.commit()
        flash('Rubric updated.', 'success')
        return redirect(url_for('admin.rubrics', exam_id=rubric.exam_id))

    return render_template('admin/rubric_form.html', exam=rubric.exam, rubric=rubric)


@admin_bp.route('/rubrics/<int:id>/delete', methods=['POST'])
@role_required('admin')
def delete_rubric(id):
    rubric = Rubric.query.get_or_404(id)
    exam_id = rubric.exam_id
    db.session.delete(rubric)
    db.session.commit()
    flash('Rubric deleted.', 'success')
    return redirect(url_for('admin.rubrics', exam_id=exam_id))


# ------------------------------------------------------------------
# EXAMINER MANAGEMENT
# ------------------------------------------------------------------
@admin_bp.route('/examiners')
@role_required('admin')
def examiners():
    examiners = User.query.filter_by(role='examiner').order_by(User.full_name).all()
    return render_template('admin/examiners.html', examiners=examiners)


@admin_bp.route('/examiners/<int:user_id>/approve', methods=['POST'])
@role_required('admin')
def approve_examiner(user_id):
    user = User.query.get_or_404(user_id)
    if user.role != 'examiner' or not user.examiner_profile:
        flash('Invalid examiner.', 'danger')
        return redirect(url_for('admin.examiners'))

    user.examiner_profile.status = 'Approved'
    db.session.commit()
    flash(f'{user.full_name} has been approved.', 'success')
    return redirect(url_for('admin.examiners'))


@admin_bp.route('/examiners/<int:user_id>/deactivate', methods=['POST'])
@role_required('admin')
def deactivate_examiner(user_id):
    user = User.query.get_or_404(user_id)
    if user.role != 'examiner' or not user.examiner_profile:
        flash('Invalid examiner.', 'danger')
        return redirect(url_for('admin.examiners'))

    user.examiner_profile.status = 'Deactivated'
    db.session.commit()
    flash(f'{user.full_name} has been deactivated.', 'warning')
    return redirect(url_for('admin.examiners'))


# ------------------------------------------------------------------
# ASSIGN EXAMINERS TO EXAMS
# ------------------------------------------------------------------
@admin_bp.route('/exams/<int:exam_id>/assign', methods=['GET', 'POST'])
@role_required('admin')
def assign_examiners(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    # Only approved examiners
    approved = User.query.join(ExaminerProfile).filter(
        User.role == 'examiner',
        ExaminerProfile.status == 'Approved'
    ).order_by(User.full_name).all()

    # Currently assigned examiner IDs
    assigned_ids = {ae.examiner_id for ae in exam.assigned_examiners}

    if request.method == 'POST':
        selected = request.form.getlist('examiner_ids')
        selected_ids = set(int(x) for x in selected)

        # Remove unselected
        for ae in list(exam.assigned_examiners):
            if ae.examiner_id not in selected_ids:
                db.session.delete(ae)

        # Add newly selected
        for eid in selected_ids:
            if eid not in assigned_ids:
                db.session.add(ExamExaminer(exam_id=exam_id, examiner_id=eid))

        db.session.commit()
        flash('Examiner assignments updated.', 'success')
        return redirect(url_for('admin.exams'))

    return render_template('admin/assign_examiners.html',
                           exam=exam,
                           approved=approved,
                           assigned_ids=assigned_ids)