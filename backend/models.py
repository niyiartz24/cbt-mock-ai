from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Course(db.Model):
    __tablename__ = 'courses'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    published = db.Column(db.Boolean, default=False)

    questions = db.relationship('Question', backref='course', lazy=True, cascade='all, delete-orphan')
    summaries = db.relationship('Summary', backref='course', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        approved_q = [q for q in self.questions if q.approved]
        return {
            'id': self.id,
            'name': self.name,
            'created_at': self.created_at.isoformat(),
            'published': self.published,
            'question_count': len(approved_q),
            'total_questions': len(self.questions),
            'has_summary': len(self.summaries) > 0,
            'ready': len(approved_q) >= 40 and len(self.summaries) > 0,
        }


class Question(db.Model):
    __tablename__ = 'questions'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    question = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.Text, nullable=False)
    option_b = db.Column(db.Text, nullable=False)
    option_c = db.Column(db.Text, nullable=False)
    option_d = db.Column(db.Text, nullable=False)
    correct_answer = db.Column(db.String(1), nullable=False)  # A, B, C, D
    explanation = db.Column(db.Text, nullable=True)
    approved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self, include_answer=True):
        data = {
            'id': self.id,
            'course_id': self.course_id,
            'question': self.question,
            'option_a': self.option_a,
            'option_b': self.option_b,
            'option_c': self.option_c,
            'option_d': self.option_d,
            'explanation': self.explanation,
            'approved': self.approved,
        }
        if include_answer:
            data['correct_answer'] = self.correct_answer
        return data


class Summary(db.Model):
    __tablename__ = 'summaries'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'course_id': self.course_id,
            'content': self.content,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }


class TestSession(db.Model):
    __tablename__ = 'test_sessions'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    score = db.Column(db.Integer)
    total = db.Column(db.Integer)
    answers = db.Column(db.Text)  # JSON string of {question_id: chosen_answer}
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        import json
        return {
            'id': self.id,
            'course_id': self.course_id,
            'score': self.score,
            'total': self.total,
            'answers': json.loads(self.answers) if self.answers else {},
            'completed_at': self.completed_at.isoformat(),
        }
