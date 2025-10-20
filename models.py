# models.py
# Database models for the AI Paper Setter application
from datetime import datetime
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'teacher' or 'student'
    full_name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Admin(UserMixin, db.Model):
    __tablename__ = 'admins'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Paper(db.Model):
    __tablename__ = 'papers'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    difficulty = db.Column(db.String(20), nullable=False)  # 'easy', 'medium', 'hard'
    duration = db.Column(db.Integer, nullable=False)  # in minutes
    total_marks = db.Column(db.Integer, nullable=False)
    questions = db.Column(db.Text, nullable=False)  # JSON string of questions
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    is_deployed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    teacher = db.relationship('User', backref='papers')
    
class AppFeedback(db.Model):
    __tablename__ = 'app_feedback'
    id = db.Column(db.Integer, primary_key=True)
    paper_id = db.Column(db.Integer, db.ForeignKey('papers.id'), nullable=True) 
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False) 
    rating = db.Column(db.Integer) 
    comments = db.Column(db.Text)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='app_feedback')
    paper = db.relationship('Paper', backref='app_feedback_paper')