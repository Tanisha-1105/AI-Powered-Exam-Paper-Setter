# routes.py
#Navigation
import json
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
from app import app, db
# NOTE: Submission is removed from imports
from models import User, Admin, Paper, AppFeedback
from ai_services import generate_questions
from utils import generate_pdf, generate_word_doc, create_file_response
from sqlalchemy import or_
from sqlalchemy.sql import func

@app.route('/')
def index():
    return render_template('index.html')

# Admin routes
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        admin = Admin.query.filter_by(username=username).first()
        if admin and admin.check_password(password):
            login_user(admin)
            session['user_type'] = 'admin'
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid credentials', 'error')
    
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    # Get statistics
    total_users = User.query.count()
    total_teachers = User.query.filter_by(role='teacher').count()
    total_students = User.query.filter_by(role='student').count()
    total_papers = Paper.query.count()
    
    # 1. Query the database for the average of all ratings
    avg_rating_result = db.session.query(func.avg(AppFeedback.rating)).scalar() 

    # 2. Format the result
    if avg_rating_result is not None:
        average_rating = round(avg_rating_result, 1)
    else:
        average_rating = "N/A"
    
    # --- START MODIFICATION: Fetch Categorized Rating Distribution Data ---
    
    # Query to count ratings (1-5) grouped by user role
    rating_distribution = db.session.query(
        User.role,
        AppFeedback.rating,
        func.count(AppFeedback.rating)
    ).join(User, AppFeedback.user_id == User.id
    ).filter(AppFeedback.rating.isnot(None) # Only count papers with a rating
    ).group_by(User.role, AppFeedback.rating
    ).all()

    # Initialize data structures: Index 0 for 1-star, Index 4 for 5-star
    teacher_ratings = [0] * 5
    student_ratings = [0] * 5

    for role, rating, count in rating_distribution:
        # Rating is 1-5, so the index is rating - 1
        if role == 'teacher':
            teacher_ratings[rating - 1] = count
        elif role == 'student':
            student_ratings[rating - 1] = count
            
    # Combine data into a dictionary for Jinja rendering
    rating_data = {
        'teacher_data': teacher_ratings,
        'student_data': student_ratings,
    }

    # --- END MODIFICATION ---

    # Get recent users
    recent_users = User.query.order_by(User.created_at.desc()).limit(10).all()
    
    return render_template('admin_dashboard.html',
                       total_users=total_users,
                       total_teachers=total_teachers,
                       total_students=total_students,
                       total_papers=total_papers,
                       recent_users=recent_users,
                       average_rating=average_rating,
                       rating_data=rating_data) # ADDED: rating_data
@app.route('/teacher/login', methods=['GET', 'POST'])
def teacher_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username, role='teacher').first()
        if user and user.check_password(password):
            login_user(user)
            session['user_type'] = 'teacher'
            return redirect(url_for('teacher_dashboard'))
        else:
            flash('Invalid credentials', 'error')
    
    return render_template('teacher_login.html')

@app.route('/teacher/register', methods=['GET', 'POST'])
def teacher_register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        full_name = request.form['full_name']
        
        # Check if user exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return render_template('teacher_register.html')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return render_template('teacher_register.html')
        
        # Create new teacher
        user = User(
            username=username,
            email=email,
            role='teacher',
            full_name=full_name
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('teacher_login'))
    
    return render_template('teacher_register.html')

@app.route('/teacher/dashboard')
@login_required
def teacher_dashboard():
    if session.get('user_type') != 'teacher':
        return redirect(url_for('index'))
    
    # Get teacher's papers
    papers = Paper.query.filter_by(teacher_id=current_user.id).order_by(Paper.created_at.desc()).all()
    
    # NOTE: Submissions section is removed for simplicity, teacher only manages papers
    
    return render_template('teacher_dashboard.html', papers=papers)

@app.route('/teacher/create_paper', methods=['GET', 'POST'])
@login_required
def create_paper():
    if session.get('user_type') != 'teacher':
        return redirect(url_for('index'))

    if request.method == 'POST':
        title = request.form['title']
        subject = request.form['subject']
        difficulty = request.form['difficulty']
        duration = int(request.form['duration'])
        
        # *** Capture specific question counts ***
        try:
            num_mcq = int(request.form.get('num_mcq', 0))
            num_short = int(request.form.get('num_short', 0))
            num_essay = int(request.form.get('num_essay', 0))
        except ValueError:
            flash('Invalid number of questions entered.', 'error')
            return render_template('create_paper.html')

        question_counts = {
            'mcq': num_mcq,
            'short': num_short,
            'essay': num_essay
        }
        total_questions = sum(question_counts.values())

        if total_questions == 0:
            flash('Please specify at least one question.', 'error')
            return render_template('create_paper.html')

        # 1. Generate questions using AI
        questions_data = generate_questions(subject, difficulty, question_counts)
        
        # Calculate total marks
        total_marks = sum(q.get('marks', 1) for q in questions_data.get('questions', []))
        
        # 2. Save in DB immediately
        paper = Paper(
            title=title,
            subject=subject,
            difficulty=difficulty,
            duration=duration,
            total_marks=total_marks,
            questions=json.dumps(questions_data),
            teacher_id=current_user.id
        )
        db.session.add(paper)
        db.session.commit()

        # 3. Redirect immediately to dashboard
        flash('Paper successfully generated and saved! You can now deploy or download it.', 'success')
        # ADDED: Flash message to prompt teacher for feedback
        flash(f'How was the quality of the generated questions? Please provide feedback for Paper ID: {paper.id}. <a href="{url_for("give_feedback", role="teacher", paper_id=paper.id)}" class="btn btn-sm btn-warning ms-2">Give Feedback Now</a>', 'feedback')

        return redirect(url_for('teacher_dashboard'))
    
    # For GET requests, render the form normally
    return render_template('create_paper.html')


@app.route('/teacher/deploy_paper/<int:paper_id>')
@login_required
def deploy_paper(paper_id):
    if session.get('user_type') != 'teacher':
        return redirect(url_for('index'))
    
    paper = Paper.query.get_or_404(paper_id)
    if paper.teacher_id != current_user.id:
        flash('Unauthorized access', 'error')
        return redirect(url_for('teacher_dashboard'))
    
    paper.is_deployed = not paper.is_deployed
    db.session.commit()
    
    status = 'deployed' if paper.is_deployed else 'undeployed'
    flash(f'Paper {status} successfully!', 'success')
    return redirect(url_for('teacher_dashboard'))

@app.route('/teacher/download_paper/<int:paper_id>/<format>')
@login_required
def download_paper(paper_id, format):
    if session.get('user_type') != 'teacher':
        return redirect(url_for('index'))
    
    paper = Paper.query.get_or_404(paper_id)
    if paper.teacher_id != current_user.id:
        flash('Unauthorized access', 'error')
        return redirect(url_for('teacher_dashboard'))
    
    paper_data = {
        'title': paper.title,
        'subject': paper.subject,
        'difficulty': paper.difficulty,
        'duration': paper.duration,
        'total_marks': paper.total_marks,
        'questions': paper.questions
    }
    
    if format == 'pdf':
        file_buffer = generate_pdf(paper_data)
        filename = f"{paper.title.replace(' ', '_')}.pdf"
        return create_file_response(file_buffer, filename, 'application/pdf')
    
    elif format == 'word':
        file_buffer = generate_word_doc(paper_data)
        filename = f"{paper.title.replace(' ', '_')}.docx"
        return create_file_response(file_buffer, filename, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    
    flash('Invalid format', 'error')
    return redirect(url_for('teacher_dashboard'))

# NOTE: grade_submission_route and teacher_edit_submission are REMOVED

# Student routes
@app.route('/student/login', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username, role='student').first()
        if user and user.check_password(password):
            login_user(user)
            session['user_type'] = 'student'
            return redirect(url_for('student_dashboard'))
        else:
            flash('Invalid credentials', 'error')
    
    return render_template('student_login.html')

@app.route('/student/register', methods=['GET', 'POST'])
def student_register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        full_name = request.form['full_name']
        
        # Check if user exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return render_template('student_register.html')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return render_template('teacher_register.html')
        
        # Create new student
        user = User(
            username=username,
            email=email,
            role='student',
            full_name=full_name
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('student_login'))
    
    return render_template('student_register.html')

@app.route('/student/dashboard')
@login_required
def student_dashboard():
    if session.get('user_type') != 'student':
        return redirect(url_for('index'))
    
    search_query = request.args.get('search', '').strip()
    
    paper_query = Paper.query.filter_by(is_deployed=True)
    
    if search_query:
        paper_query = paper_query.filter(
            or_(
                Paper.title.ilike(f'%{search_query}%'),
                Paper.subject.ilike(f'%{search_query}%')
            )
        )
        
    available_papers = paper_query.order_by(Paper.created_at.desc()).all()
    
    # NOTE: Submissions query is REMOVED
    
    return render_template('student_dashboard.html', papers=available_papers) # Only passing papers


@app.route('/student/view_paper/<int:paper_id>')
@login_required
def view_paper(paper_id):
    if session.get('user_type') != 'student':
        return redirect(url_for('index'))
    
    paper = Paper.query.get_or_404(paper_id)
    if not paper.is_deployed:
        flash('Paper is not available', 'error')
        return redirect(url_for('student_dashboard'))
    
    # NOTE: Submission placeholder logic is REMOVED
    
    questions_data = json.loads(paper.questions)
    return render_template('view_paper.html', 
                           paper=paper, 
                           questions=questions_data['questions'])


@app.route('/student/download_paper/<int:paper_id>/pdf')
@login_required
def student_download_paper(paper_id):
    if session.get('user_type') != 'student':
        return redirect(url_for('index'))
    
    paper = Paper.query.get_or_404(paper_id)
    if not paper.is_deployed:
        flash('Paper is not available for download', 'error')
        return redirect(url_for('student_dashboard'))
    
    paper_data = {
        'title': paper.title,
        'subject': paper.subject,
        'difficulty': paper.difficulty,
        'duration': paper.duration,
        'total_marks': paper.total_marks,
        'questions': paper.questions 
    }
    
    file_buffer = generate_pdf(paper_data)
    filename = f"{paper.title.replace(' ', '')}{paper.subject}_Paper.pdf"
    
    return create_file_response(file_buffer, filename, 'application/pdf')

# Feedback Route for both Teacher and Student (REMAINS)
@app.route('/<role>/give_feedback/<int:paper_id>', methods=['GET', 'POST'])
@login_required
def give_feedback(role, paper_id):
    if session.get('user_type') not in ['teacher', 'student'] or session.get('user_type') != role:
        flash('Unauthorized access or incorrect role context.', 'error')
        return redirect(url_for('index'))
    
    paper = Paper.query.get_or_404(paper_id)
    
    existing_feedback = AppFeedback.query.filter_by(
        paper_id=paper_id, 
        user_id=current_user.id
    ).first()
    
    if request.method == 'POST':
        rating = request.form.get('rating', type=int)
        comments = request.form.get('comments')
        
        if existing_feedback:
            existing_feedback.rating = rating
            existing_feedback.comments = comments
            existing_feedback.submitted_at = datetime.utcnow()
            flash('Your feedback has been updated!', 'success')
        else:
            new_feedback = AppFeedback(
                paper_id=paper_id,
                user_id=current_user.id,
                rating=rating,
                comments=comments
            )
            db.session.add(new_feedback)
            flash('Thank you for your valuable feedback!', 'success')
            
        db.session.commit()
        
        if role == 'teacher':
            return redirect(url_for('teacher_dashboard'))
        else:
            return redirect(url_for('view_paper', paper_id=paper.id))
    
    return render_template(
        'give_feedback.html', 
        paper=paper, 
        existing_feedback=existing_feedback,
        role=role
    )


@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('user_type', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))