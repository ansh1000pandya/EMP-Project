from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

# ---------- USER (single table for Admin / Examiner / Student) ----------
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'admin', 'examiner', 'student'
    full_name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # One-to-one with ExaminerProfile (only for examiners)
    examiner_profile = db.relationship('ExaminerProfile', backref='user', uselist=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'


# ---------- EXAMINER PROFILE ----------
class ExaminerProfile(db.Model):
    __tablename__ = 'examiner_profiles'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    department = db.Column(db.String(100))
    contact = db.Column(db.String(20))
    status = db.Column(db.String(20), default='Pending')  # Pending / Approved / Deactivated
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ---------- COURSE ----------
class Course(db.Model):
    __tablename__ = 'courses'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    exams = db.relationship('Exam', backref='course', lazy=True)


# ---------- EXAM ----------
class Exam(db.Model):
    __tablename__ = 'exams'
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    exam_type = db.Column(db.String(30), nullable=False)  # Viva / Practical / Project Demo / Assessment
    status = db.Column(db.String(30), default='Draft')    # Draft / Slot Creation / Booking Open / Closed / Completed
    description = db.Column(db.Text)

    # Time windows (server-side enforcement)
    slot_creation_start = db.Column(db.DateTime)
    slot_creation_end   = db.Column(db.DateTime)
    booking_start       = db.Column(db.DateTime)
    booking_end         = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    rubrics = db.relationship('Rubric', backref='exam', lazy=True, cascade='all, delete-orphan')
    slots   = db.relationship('Slot', backref='exam', lazy=True)
    bookings = db.relationship('Booking', backref='exam', lazy=True)
    assigned_examiners = db.relationship('ExamExaminer', backref='exam', lazy=True)


# ---------- EXAM–EXAMINER ASSIGNMENT (strict) ----------
class ExamExaminer(db.Model):
    __tablename__ = 'exam_examiners'
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), nullable=False)
    examiner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)

    examiner = db.relationship('User', backref='assigned_exams')

    __table_args__ = (db.UniqueConstraint('exam_id', 'examiner_id', name='uq_exam_examiner'),)


# ---------- RUBRIC ----------
class Rubric(db.Model):
    __tablename__ = 'rubrics'
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), nullable=False)
    criterion = db.Column(db.String(150), nullable=False)
    max_marks = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)


# ---------- SLOT ----------
class Slot(db.Model):
    __tablename__ = 'slots'
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), nullable=False)
    examiner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    capacity = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.String(20), default='Available')  # Available / Full / Cancelled / Completed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    examiner = db.relationship('User', backref='created_slots')
    bookings = db.relationship('Booking', backref='slot', lazy=True)


# ---------- BOOKING ----------
class Booking(db.Model):
    __tablename__ = 'bookings'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), nullable=False)
    slot_id = db.Column(db.Integer, db.ForeignKey('slots.id'), nullable=False)
    status = db.Column(db.String(20), default='Booked')  # Booked / Cancelled / Completed
    booked_at = db.Column(db.DateTime, default=datetime.utcnow)
    cancelled_at = db.Column(db.DateTime)
    published = db.Column(db.Boolean, default=False)  # results visible to student?

    student = db.relationship('User', backref='bookings')
    evaluations = db.relationship('Evaluation', backref='booking', lazy=True, cascade='all, delete-orphan')

    # Prevents duplicate booking for the same exam (DB-level enforcement)
    __table_args__ = (db.UniqueConstraint('student_id', 'exam_id', name='uq_student_exam'),)


# ---------- EVALUATION (per rubric criterion) ----------
class Evaluation(db.Model):
    __tablename__ = 'evaluations'
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=False)
    rubric_id = db.Column(db.Integer, db.ForeignKey('rubrics.id'), nullable=False)
    marks = db.Column(db.Float)
    remarks = db.Column(db.Text)
    evaluated_at = db.Column(db.DateTime, default=datetime.utcnow)

    rubric = db.relationship('Rubric')