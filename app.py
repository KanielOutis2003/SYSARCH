from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
from datetime import timedelta
import logging
from functools import wraps
import os
from werkzeug.utils import secure_filename
import uuid

app = Flask(__name__, static_folder='static')
app.secret_key = 'your_very_secure_secret_key_here'
app.permanent_session_lifetime = timedelta(minutes=30)  # Session expires after 30 minutes

# Ensure you have a folder for storing uploaded images
UPLOAD_FOLDER = 'static/profile_pictures'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Create upload folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Database connection
def get_db_connection():
    try:
        # First try to connect without specifying a database
        connection = mysql.connector.connect(
            host='localhost',
            user='root',  # replace with your XAMPP MySQL username
            password=''   # replace with your XAMPP MySQL password
        )
        cursor = connection.cursor()
        
        # Create the database if it doesn't exist
        cursor.execute("CREATE DATABASE IF NOT EXISTS students")
        cursor.execute("USE students")
        connection.commit()
        cursor.close()
        
        # Now reconnect with the database specified
        connection = mysql.connector.connect(
            host='localhost',
            user='root',  # replace with your XAMPP MySQL username
            password='',  # replace with your XAMPP MySQL password
            database='students'  # now we can safely use this database
        )
        return connection
    except Exception as e:
        print(f"Database connection error: {str(e)}")
        raise e

# Initialize database tables
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create students table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS students (
        id INT AUTO_INCREMENT PRIMARY KEY,
        idno VARCHAR(20) UNIQUE NOT NULL,
        lastname VARCHAR(50) NOT NULL,
        firstname VARCHAR(50) NOT NULL,
        middlename VARCHAR(50),
        course VARCHAR(100) NOT NULL,
        year_level VARCHAR(20) NOT NULL,
        email VARCHAR(100) UNIQUE NOT NULL,
        username VARCHAR(50) UNIQUE NOT NULL,
        password VARCHAR(255) NOT NULL,
        profile_picture VARCHAR(255) DEFAULT 'default.jpg',
        sessions_used INT DEFAULT 0,
        max_sessions INT DEFAULT 25,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Check if sessions_used and max_sessions columns exist, add them if they don't
    try:
        # Check if sessions_used column exists
        cursor.execute("SHOW COLUMNS FROM students LIKE 'sessions_used'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE students ADD COLUMN sessions_used INT DEFAULT 0")
            
        # Check if max_sessions column exists
        cursor.execute("SHOW COLUMNS FROM students LIKE 'max_sessions'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE students ADD COLUMN max_sessions INT DEFAULT 25")
            
        # Update max_sessions based on course for existing users
        cursor.execute("""
        UPDATE students 
        SET max_sessions = CASE 
            WHEN course IN ('1', '2', '3') THEN 30 
            ELSE 25 
        END
        WHERE max_sessions IS NULL OR (course IN ('1', '2', '3') AND max_sessions = 25) OR (course NOT IN ('1', '2', '3') AND max_sessions = 30)
        """)
        
        conn.commit()
    except Exception as e:
        print(f"Error checking/adding columns: {str(e)}")
        conn.rollback()
    
    # Create admin table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS admins (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(50) UNIQUE NOT NULL,
        password VARCHAR(255) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create sit-in sessions table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sessions (
        id INT AUTO_INCREMENT PRIMARY KEY,
        student_id INT NOT NULL,
        lab_room VARCHAR(50) NOT NULL,
        date_time DATETIME NOT NULL,
        duration INT NOT NULL,
        programming_language VARCHAR(50),
        purpose TEXT,
        status VARCHAR(20) DEFAULT 'pending',
        check_in_time DATETIME,
        check_out_time DATETIME,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    )
    ''')
    
    # Check if approval_status column exists in sessions table, add it if it doesn't
    try:
        cursor.execute("SHOW COLUMNS FROM sessions LIKE 'approval_status'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE sessions ADD COLUMN approval_status VARCHAR(20) DEFAULT 'pending'")
        
        # Check if programming_language column exists in sessions table, add it if it doesn't
        cursor.execute("SHOW COLUMNS FROM sessions LIKE 'programming_language'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE sessions ADD COLUMN programming_language VARCHAR(50)")
        
        # Check if purpose column exists in sessions table, add it if it doesn't
        cursor.execute("SHOW COLUMNS FROM sessions LIKE 'purpose'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE sessions ADD COLUMN purpose TEXT")
        
        # Check if check_in_time column exists in sessions table, add it if it doesn't
        cursor.execute("SHOW COLUMNS FROM sessions LIKE 'check_in_time'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE sessions ADD COLUMN check_in_time DATETIME")
        
        # Check if check_out_time column exists in sessions table, add it if it doesn't
        cursor.execute("SHOW COLUMNS FROM sessions LIKE 'check_out_time'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE sessions ADD COLUMN check_out_time DATETIME")
        
        conn.commit()
    except Exception as e:
        print(f"Error checking/adding columns to sessions table: {str(e)}")
        conn.rollback()
    
    # Create feedback table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS feedback (
        id INT AUTO_INCREMENT PRIMARY KEY,
        session_id INT NOT NULL,
        student_id INT NOT NULL,
        rating INT NOT NULL, /* 1-5 star rating */
        comments TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    )
    ''')
    
    # Create announcements table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS announcements (
        id INT AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(100) NOT NULL,
        content TEXT NOT NULL,
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create programming languages table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS programming_languages (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(50) UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Insert default programming languages if they don't exist
    default_languages = ['PHP', 'Java', 'Python', 'JavaScript', 'C++', 'C#', 'Ruby', 'Swift']
    for language in default_languages:
        cursor.execute("SELECT * FROM programming_languages WHERE name = %s", (language,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO programming_languages (name) VALUES (%s)", (language,))
    
    # Insert default admin if not exists
    cursor.execute("SELECT * FROM admins WHERE username = 'admin'")
    admin = cursor.fetchone()
    if not admin:
        hashed_password = generate_password_hash('admin')
        cursor.execute("INSERT INTO admins (username, password) VALUES (%s, %s)", 
                      ('admin', hashed_password))
    
    conn.commit()
    cursor.close()
    conn.close()

# Initialize the database on startup
init_db()

# Helper function to check if file extension is allowed
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# Admin required decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('user_type') != 'admin':
            flash('Admin access required', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/lab-rules')
def lab_rules():
    return render_template('lab_rules.html')

@app.route('/register', methods=['POST'])
def register():
    if request.method == 'POST':
        # Get form data
        idno = request.form['idno']
        lastname = request.form['lastname']
        firstname = request.form['firstname']
        middlename = request.form.get('middlename', '')
        course = request.form['course']
        year_level = request.form['year_level']
        email = request.form['email']
        username = request.form['username']
        password = request.form['password']
        
        # Set max sessions based on course
        # BSIT (1), BSCS (2), BSCE (3) get 30 sessions, others get 25
        max_sessions = 30 if course in ['1', '2', '3'] else 25
        
        # Hash the password
        hashed_password = generate_password_hash(password)
        
        try:
            # Make sure the database and tables exist
            with app.app_context():
                init_db()
                
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Check if username or email already exists
            cursor.execute("SELECT * FROM students WHERE username = %s", (username,))
            existing_username = cursor.fetchone()
            
            cursor.execute("SELECT * FROM students WHERE email = %s", (email,))
            existing_email = cursor.fetchone()
            
            cursor.execute("SELECT * FROM students WHERE idno = %s", (idno,))
            existing_idno = cursor.fetchone()
            
            if existing_username:
                flash('Username already exists. Please choose a different username.', 'error')
                return redirect(url_for('index'))
            
            if existing_email:
                flash('Email already exists. Please use a different email address.', 'error')
                return redirect(url_for('index'))
            
            if existing_idno:
                flash('ID number already exists. Please check your ID number.', 'error')
                return redirect(url_for('index'))
            
            # Insert new student
            cursor.execute('''
            INSERT INTO students (idno, lastname, firstname, middlename, course, year_level, email, username, password, sessions_used, max_sessions)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (idno, lastname, firstname, middlename, course, year_level, email, username, hashed_password, 0, max_sessions))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            flash('Registration successful! You can now login.', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            flash(f'Registration failed: {str(e)}', 'error')
            return redirect(url_for('index'))

@app.route('/login', methods=['POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Check if it's an admin login
        if username == 'admin':
            cursor.execute("SELECT * FROM admins WHERE username = %s", (username,))
            user = cursor.fetchone()
            
            if user and check_password_hash(user['password'], password):
                session.permanent = True
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['user_type'] = 'admin'
                flash('Welcome, Admin!', 'success')
                return redirect(url_for('admin_dashboard'))
            else:
                flash('Invalid admin credentials', 'error')
                return redirect(url_for('index'))
        
        # Check if it's a student login
        cursor.execute("SELECT * FROM students WHERE username = %s", (username,))
        user = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            # Ensure sessions_used and max_sessions exist
            if 'sessions_used' not in user or user['sessions_used'] is None:
                # Update the user record to include sessions_used if it doesn't exist
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # Set max_sessions based on course
                max_sessions = 30 if user['course'] in ['1', '2', '3'] else 25
                
                cursor.execute("""
                UPDATE students 
                SET sessions_used = 0, max_sessions = %s
                WHERE id = %s
                """, (max_sessions, user['id']))
                
                conn.commit()
                cursor.close()
                conn.close()
                
                # Update the user object
                user['sessions_used'] = 0
                user['max_sessions'] = max_sessions
            
            session.permanent = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['user_type'] = 'student'
            session['student_info'] = {
                'id': user['id'],
                'idno': user['idno'],
                'name': f"{user['firstname']} {user['lastname']}",
                'profile_picture': user['profile_picture']
            }
            flash(f'Welcome, {user["firstname"]}!', 'success')
            return redirect(url_for('student_dashboard'))
        
        flash('Invalid username or password', 'error')
        return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

@app.route('/student-dashboard')
@login_required
def student_dashboard():
    if session.get('user_type') != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get student information
    cursor.execute("SELECT * FROM students WHERE id = %s", (session['user_id'],))
    student = cursor.fetchone()
    
    if not student:
        flash('Student not found', 'error')
        cursor.close()
        conn.close()
        return redirect(url_for('logout'))
    
    # Ensure sessions_used and max_sessions exist
    if 'sessions_used' not in student or student['sessions_used'] is None:
        # Set max_sessions based on course
        max_sessions = 30 if student['course'] in ['1', '2', '3'] else 25
        
        cursor.execute("""
        UPDATE students 
        SET sessions_used = 0, max_sessions = %s
        WHERE id = %s
        """, (max_sessions, student['id']))
        
        conn.commit()
        
        # Update the student object
        student['sessions_used'] = 0
        student['max_sessions'] = max_sessions
    
    # Make sure BSIT, BSCS, BSCE students have 30 sessions
    if student['course'] in ['1', '2', '3'] and student['max_sessions'] != 30:
        cursor.execute("""
        UPDATE students 
        SET max_sessions = 30
        WHERE id = %s
        """, (student['id'],))
        
        conn.commit()
        
        # Update the student object
        student['max_sessions'] = 30
    
    # Get student's sessions
    cursor.execute("""
    SELECT * FROM sessions 
    WHERE student_id = %s 
    ORDER BY date_time DESC
    """, (session['user_id'],))
    sessions = cursor.fetchall()
    
    # If sessions is None, set it to an empty list
    if sessions is None:
        sessions = []
    
    # Get student's feedback
    try:
        cursor.execute("""
        SELECT f.*, s.lab_room 
        FROM feedback f
        JOIN sessions s ON f.session_id = s.id
        WHERE f.student_id = %s
        ORDER BY f.created_at DESC
        """, (session['user_id'],))
        feedback_list = cursor.fetchall()
    except:
        feedback_list = []
    
    # Get active announcements
    try:
        cursor.execute("""
        SELECT * FROM announcements 
        WHERE is_active = TRUE 
        ORDER BY created_at DESC
        """)
        announcements = cursor.fetchall()
    except:
        announcements = []
    
    cursor.close()
    conn.close()
    
    return render_template('student_dashboard.html', 
                          student=student, 
                          sessions=sessions,
                          feedback_list=feedback_list,
                          announcements=announcements)

@app.route('/admin-dashboard')
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get all students
    cursor.execute("""
    SELECT s.*, 
           (SELECT COUNT(*) FROM sessions WHERE student_id = s.id AND status = 'active') as active_sessions
    FROM students s
    ORDER BY lastname, firstname
    """)
    students = cursor.fetchall()
    
    # Check if approval_status column exists in sessions table
    try:
        cursor.execute("SHOW COLUMNS FROM sessions LIKE 'approval_status'")
        has_approval_status = cursor.fetchone() is not None
    except:
        has_approval_status = False
    
    # Get active sessions (approved but not completed)
    if has_approval_status:
        cursor.execute("""
        SELECT s.*, st.firstname, st.lastname, st.idno, st.course
        FROM sessions s
        JOIN students st ON s.student_id = st.id
        WHERE s.status = 'active' AND s.approval_status = 'approved'
        ORDER BY s.date_time DESC
        """)
    else:
        cursor.execute("""
        SELECT s.*, st.firstname, st.lastname, st.idno, st.course
        FROM sessions s
        JOIN students st ON s.student_id = st.id
        WHERE s.status = 'active'
        ORDER BY s.date_time DESC
        """)
    active_sessions = cursor.fetchall()
    
    # Get pending session requests
    if has_approval_status:
        cursor.execute("""
        SELECT s.*, st.firstname, st.lastname, st.idno, st.course
        FROM sessions s
        JOIN students st ON s.student_id = st.id
        WHERE s.approval_status = 'pending'
        ORDER BY s.date_time ASC
        """)
    else:
        cursor.execute("""
        SELECT s.*, st.firstname, st.lastname, st.idno, st.course
        FROM sessions s
        JOIN students st ON s.student_id = st.id
        WHERE s.status = 'pending'
        ORDER BY s.date_time ASC
        """)
    pending_sessions = cursor.fetchall()
    
    # Get current sit-ins (checked in but not checked out)
    cursor.execute("""
    SELECT s.*, st.firstname, st.lastname, st.idno, st.course
    FROM sessions s
    JOIN students st ON s.student_id = st.id
    WHERE s.status = 'active' AND s.check_in_time IS NOT NULL AND s.check_out_time IS NULL
    ORDER BY s.check_in_time DESC
    """)
    current_sit_ins = cursor.fetchall()
    
    # Get recent activity (last 10 events)
    cursor.execute("""
    (SELECT 
        s.id, 
        st.firstname, 
        st.lastname, 
        s.lab_room, 
        'Requested a session' as action, 
        s.created_at as timestamp
    FROM sessions s
    JOIN students st ON s.student_id = st.id
    ORDER BY s.created_at DESC
    LIMIT 5)
    
    UNION
    
    (SELECT 
        s.id, 
        st.firstname, 
        st.lastname, 
        s.lab_room, 
        'Checked in' as action, 
        s.check_in_time as timestamp
    FROM sessions s
    JOIN students st ON s.student_id = st.id
    WHERE s.check_in_time IS NOT NULL
    ORDER BY s.check_in_time DESC
    LIMIT 5)
    
    ORDER BY timestamp DESC
    LIMIT 10
    """)
    recent_activity = cursor.fetchall()
    
    # Get programming language statistics
    try:
        cursor.execute("""
        SELECT 
            programming_language,
            COUNT(*) as count,
            (COUNT(*) * 100.0 / (SELECT COUNT(*) FROM sessions WHERE programming_language IS NOT NULL)) as percentage
        FROM sessions
        WHERE programming_language IS NOT NULL
        GROUP BY programming_language
        ORDER BY count DESC
        """)
        language_stats = cursor.fetchall()
        
        # Ensure we have data for all default languages
        default_languages = ['PHP', 'Java', 'Python', 'JavaScript', 'C++', 'C#', 'Ruby', 'Swift']
        existing_languages = [lang['programming_language'] for lang in language_stats]
        
        # Add missing languages with count 0
        for lang in default_languages:
            if lang not in existing_languages:
                language_stats.append({
                    'programming_language': lang,
                    'count': 0,
                    'percentage': 0
                })
    except Exception as e:
        print(f"Error getting language stats: {str(e)}")
        language_stats = []
    
    # Get lab room usage statistics
    try:
        cursor.execute("""
        SELECT 
            lab_room,
            COUNT(*) as count,
            (COUNT(*) * 100.0 / (SELECT COUNT(*) FROM sessions)) as percentage,
            SUM(duration) as total_hours
        FROM sessions
        GROUP BY lab_room
        ORDER BY count DESC
        """)
        lab_stats = cursor.fetchall()
        
        # Ensure we have data for all lab rooms
        default_labs = ['Lab 1', 'Lab 2', 'Lab 3', 'Lab 4', 'Lab 5', 'Lab 6', 'Lab 7', 'Lab 8', 'Lab 9', 'Lab 10', 'Lab 11']
        existing_labs = [lab['lab_room'] for lab in lab_stats]
        
        # Add missing labs with count 0
        for lab in default_labs:
            if lab not in existing_labs:
                lab_stats.append({
                    'lab_room': lab,
                    'count': 0,
                    'percentage': 0,
                    'total_hours': 0
                })
    except Exception as e:
        print(f"Error getting lab stats: {str(e)}")
        lab_stats = []
    
    # Get feedback statistics
    try:
        cursor.execute("""
        SELECT 
            COUNT(*) as total_feedback,
            AVG(rating) as average_rating,
            SUM(CASE WHEN rating >= 4 THEN 1 ELSE 0 END) as positive_feedback,
            SUM(CASE WHEN rating <= 2 THEN 1 ELSE 0 END) as negative_feedback
        FROM feedback
        """)
        feedback_stats = cursor.fetchone()
    except:
        feedback_stats = {
            'total_feedback': 0,
            'average_rating': 0,
            'positive_feedback': 0,
            'negative_feedback': 0
        }
    
    # Get feedback list with student and session details
    try:
        cursor.execute("""
        SELECT f.*, s.lab_room, st.firstname, st.lastname, st.idno
        FROM feedback f
        JOIN sessions s ON f.session_id = s.id
        JOIN students st ON f.student_id = st.id
        ORDER BY f.created_at DESC
        """)
        feedback_list = cursor.fetchall()
    except:
        feedback_list = []
    
    # Get announcements
    try:
        cursor.execute("SELECT * FROM announcements ORDER BY created_at DESC")
        announcements = cursor.fetchall()
    except:
        announcements = []
    
    cursor.close()
    conn.close()
    
    return render_template('admin_dashboard.html', 
                          students=students, 
                          active_sessions=active_sessions,
                          pending_sessions=pending_sessions,
                          current_sit_ins=current_sit_ins,
                          recent_activity=recent_activity,
                          language_stats=language_stats,
                          lab_stats=lab_stats,
                          feedback_stats=feedback_stats,
                          feedback_list=feedback_list,
                          announcements=announcements)

@app.route('/export-report/<format>')
@admin_required
def export_report(format):
    if format not in ['csv', 'pdf', 'excel']:
        flash('Invalid export format', 'error')
        return redirect(url_for('admin_dashboard'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get all sessions
    cursor.execute("""
    SELECT s.*, st.firstname, st.lastname, st.idno, st.course
    FROM sessions s
    JOIN students st ON s.student_id = st.id
    ORDER BY s.date_time DESC
    """)
    sessions = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    if format == 'csv':
        # Generate CSV
        import csv
        from io import StringIO
        import datetime
        
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['ID', 'Student ID', 'Student Name', 'Course', 'Lab Room', 'Date & Time', 
                         'Duration', 'Programming Language', 'Purpose', 'Status'])
        
        # Map lab room codes to actual room numbers
        lab_room_mapping = {
            'Lab 1': 'Lab 524 (Lab 1)',
            'Lab 2': 'Lab 526 (Lab 2)',
            'Lab 3': 'Lab 528 (Lab 3)',
            'Lab 4': 'Lab 530 (Lab 4)',
            'Lab 5': 'Lab 532 (Lab 5)',
            'Lab 6': 'Lab 534 (Lab 6)',
            'Lab 7': 'Lab 536 (Lab 7)',
            'Lab 8': 'Lab 538 (Lab 8)',
            'Lab 9': 'Lab 540 (Lab 9)',
            'Lab 10': 'Lab 542 (Lab 10)',
            'Lab 11': 'Lab 544 (Lab 11)'
        }
        
        # Write data
        for session in sessions:
            course_name = ''
            if session['course'] == '1':
                course_name = 'BSIT'
            elif session['course'] == '2':
                course_name = 'BSCS'
            elif session['course'] == '3':
                course_name = 'BSCE'
            else:
                course_name = session['course']
            
            # Get the actual lab room name with number
            lab_room_display = lab_room_mapping.get(session['lab_room'], session['lab_room'])
                
            writer.writerow([
                session['id'],
                session['idno'],
                f"{session['firstname']} {session['lastname']}",
                course_name,
                lab_room_display,
                session['date_time'].strftime('%Y-%m-%d %H:%M') if isinstance(session['date_time'], datetime.datetime) else session['date_time'],
                session['duration'],
                session.get('programming_language', 'Not specified'),
                session.get('purpose', 'Not specified')[:50] + '...' if session.get('purpose') and len(session.get('purpose')) > 50 else session.get('purpose', 'Not specified'),
                session['status']
            ])
        
        output.seek(0)
        
        from flask import Response
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-disposition": "attachment; filename=sit_in_sessions_report.csv"}
        )
    
    elif format == 'excel':
        # For Excel, we'd typically use a library like openpyxl or xlsxwriter
        # For simplicity, we'll just return a CSV with an Excel mimetype
        import csv
        from io import StringIO
        import datetime
        
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['ID', 'Student ID', 'Student Name', 'Course', 'Lab Room', 'Date & Time', 
                         'Duration', 'Programming Language', 'Purpose', 'Status'])
        
        # Write data
        for session in sessions:
            course_name = ''
            if session['course'] == '1':
                course_name = 'BSIT'
            elif session['course'] == '2':
                course_name = 'BSCS'
            elif session['course'] == '3':
                course_name = 'BSCE'
            else:
                course_name = session['course']
            
            # Get the actual lab room name with number
            lab_room_display = lab_room_mapping.get(session['lab_room'], session['lab_room'])
                
            writer.writerow([
                session['id'],
                session['idno'],
                f"{session['firstname']} {session['lastname']}",
                course_name,
                lab_room_display,
                session['date_time'].strftime('%Y-%m-%d %H:%M') if isinstance(session['date_time'], datetime.datetime) else session['date_time'],
                session['duration'],
                session.get('programming_language', 'Not specified'),
                session.get('purpose', 'Not specified')[:50] + '...' if session.get('purpose') and len(session.get('purpose')) > 50 else session.get('purpose', 'Not specified'),
                session['status']
            ])
        
        output.seek(0)
        
        from flask import Response
        return Response(
            output.getvalue(),
            mimetype="application/vnd.ms-excel",
            headers={"Content-disposition": "attachment; filename=sit_in_sessions_report.xls"}
        )
    
    elif format == 'pdf':
        # For PDF generation, we'd typically use a library like ReportLab or WeasyPrint
        # This is a placeholder that would be implemented with a proper PDF library
        flash('PDF export is not implemented yet', 'info')
        return redirect(url_for('admin_dashboard'))

@app.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if session.get('user_type') != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        # Get form data
        lastname = request.form['lastname']
        firstname = request.form['firstname']
        middlename = request.form.get('middlename', '')
        email = request.form['email']
        
        # Handle profile picture upload
        profile_picture = None
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename != '' and allowed_file(file.filename):
                # Generate unique filename
                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4().hex}_{filename}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(file_path)
                profile_picture = unique_filename
        
        try:
            # Update student information
            if profile_picture:
                cursor.execute('''
                UPDATE students 
                SET lastname = %s, firstname = %s, middlename = %s, email = %s, profile_picture = %s
                WHERE id = %s
                ''', (lastname, firstname, middlename, email, profile_picture, session['user_id']))
                
                # Update session data with new profile picture
                session['student_info']['profile_picture'] = profile_picture
            else:
                cursor.execute('''
                UPDATE students 
                SET lastname = %s, firstname = %s, middlename = %s, email = %s
                WHERE id = %s
                ''', (lastname, firstname, middlename, email, session['user_id']))
            
            conn.commit()
            
            # Update session data
            session['student_info']['name'] = f"{firstname} {lastname}"
            
            flash('Profile updated successfully', 'success')
            return redirect(url_for('student_dashboard'))
            
        except Exception as e:
            conn.rollback()
            flash(f'Profile update failed: {str(e)}', 'error')
            return redirect(url_for('edit_profile'))
    
    # Get student information for the form
    cursor.execute("SELECT * FROM students WHERE id = %s", (session['user_id'],))
    student = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    if not student:
        flash('Student not found', 'error')
        return redirect(url_for('logout'))
    
    return render_template('edit_profile.html', student=student)

@app.route('/add-session', methods=['POST'])
@login_required
def add_session():
    if session.get('user_type') != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    lab_room = request.form['lab_room']
    date_time = request.form['date_time']
    duration = request.form['duration']
    programming_language = request.form.get('programming_language', '')
    purpose = request.form.get('purpose', '')
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Check if student has available sessions
        cursor.execute("SELECT sessions_used, max_sessions FROM students WHERE id = %s", (session['user_id'],))
        student = cursor.fetchone()
        
        if student['sessions_used'] >= student['max_sessions']:
            flash('You have used all your available sessions', 'error')
            return redirect(url_for('student_dashboard'))
        
        # Check if programming_language column exists
        cursor.execute("SHOW COLUMNS FROM sessions LIKE 'programming_language'")
        has_programming_language = cursor.fetchone() is not None
        
        # Check if purpose column exists
        cursor.execute("SHOW COLUMNS FROM sessions LIKE 'purpose'")
        has_purpose = cursor.fetchone() is not None
        
        # Check if approval_status column exists
        cursor.execute("SHOW COLUMNS FROM sessions LIKE 'approval_status'")
        has_approval_status = cursor.fetchone() is not None
        
        # Add new session with pending status
        if has_programming_language and has_purpose and has_approval_status:
            cursor.execute("""
            INSERT INTO sessions (student_id, lab_room, date_time, duration, programming_language, purpose, status, approval_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (session['user_id'], lab_room, date_time, duration, programming_language, purpose, 'pending', 'pending'))
        elif has_programming_language and has_approval_status:
            cursor.execute("""
            INSERT INTO sessions (student_id, lab_room, date_time, duration, programming_language, status, approval_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (session['user_id'], lab_room, date_time, duration, programming_language, 'pending', 'pending'))
        elif has_purpose and has_approval_status:
            cursor.execute("""
            INSERT INTO sessions (student_id, lab_room, date_time, duration, purpose, status, approval_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (session['user_id'], lab_room, date_time, duration, purpose, 'pending', 'pending'))
        elif has_approval_status:
            cursor.execute("""
            INSERT INTO sessions (student_id, lab_room, date_time, duration, status, approval_status)
            VALUES (%s, %s, %s, %s, %s, %s)
            """, (session['user_id'], lab_room, date_time, duration, 'pending', 'pending'))
        elif has_programming_language and has_purpose:
            cursor.execute("""
            INSERT INTO sessions (student_id, lab_room, date_time, duration, programming_language, purpose, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (session['user_id'], lab_room, date_time, duration, programming_language, purpose, 'pending'))
        elif has_programming_language:
            cursor.execute("""
            INSERT INTO sessions (student_id, lab_room, date_time, duration, programming_language, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            """, (session['user_id'], lab_room, date_time, duration, programming_language, 'pending'))
        elif has_purpose:
            cursor.execute("""
            INSERT INTO sessions (student_id, lab_room, date_time, duration, purpose, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            """, (session['user_id'], lab_room, date_time, duration, purpose, 'pending'))
        else:
            cursor.execute("""
            INSERT INTO sessions (student_id, lab_room, date_time, duration, status)
            VALUES (%s, %s, %s, %s, %s)
            """, (session['user_id'], lab_room, date_time, duration, 'pending'))
        
        # Note: We don't increment sessions_used until the session is approved
        
        conn.commit()
        flash('Session request submitted successfully. Waiting for admin approval.', 'success')
        
    except Exception as e:
        conn.rollback()
        flash(f'Failed to add session: {str(e)}', 'error')
        
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('student_dashboard'))

@app.route('/cancel-session/<int:session_id>', methods=['POST'])
@login_required
def cancel_session(session_id):
    if session.get('user_type') != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Check if session belongs to the student
        cursor.execute("""
        SELECT * FROM sessions 
        WHERE id = %s AND student_id = %s
        """, (session_id, session['user_id']))
        sit_in_session = cursor.fetchone()
        
        if not sit_in_session:
            flash('Session not found or not authorized', 'error')
            return redirect(url_for('student_dashboard'))
        
        # Cancel session
        cursor.execute("""
        UPDATE sessions SET status = 'cancelled'
        WHERE id = %s
        """, (session_id,))
        
        # Update sessions used
        cursor.execute("""
        UPDATE students SET sessions_used = sessions_used - 1
        WHERE id = %s
        """, (session['user_id'],))
        
        conn.commit()
        flash('Session cancelled successfully', 'success')
        
    except Exception as e:
        conn.rollback()
        flash(f'Failed to cancel session: {str(e)}', 'error')
        
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('student_dashboard'))

@app.route('/admin/complete-session/<int:session_id>', methods=['POST'])
@admin_required
def complete_session(session_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Mark session as completed
        cursor.execute("""
        UPDATE sessions SET status = 'completed'
        WHERE id = %s
        """, (session_id,))
        
        conn.commit()
        flash('Session marked as completed', 'success')
        
    except Exception as e:
        conn.rollback()
        flash(f'Failed to update session: {str(e)}', 'error')
        
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/end-student-session/<int:student_id>', methods=['POST'])
@admin_required
def end_student_session(student_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Get student information
        cursor.execute("SELECT * FROM students WHERE id = %s", (student_id,))
        student = cursor.fetchone()
        
        if not student:
            flash('Student not found', 'error')
            return redirect(url_for('admin_dashboard'))
        
        # Mark all active sessions for this student as completed
        cursor.execute("""
        UPDATE sessions SET status = 'completed'
        WHERE student_id = %s AND status = 'active'
        """, (student_id,))
        
        conn.commit()
        flash(f'All active sessions for student {student_id} have been ended', 'success')
        
    except Exception as e:
        conn.rollback()
        flash(f'Failed to end sessions: {str(e)}', 'error')
        
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/get-student-info/<int:student_id>', methods=['GET'])
@admin_required
def get_student_info(student_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Get student information
        cursor.execute("SELECT * FROM students WHERE id = %s", (student_id,))
        student = cursor.fetchone()
        
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Get student's active sessions
        cursor.execute("""
        SELECT * FROM sessions 
        WHERE student_id = %s AND status = 'active'
        ORDER BY date_time DESC
        """, (student_id,))
        sessions = cursor.fetchall()
        
        # Convert sessions to a serializable format
        serializable_sessions = []
        for s in sessions:
            session_dict = dict(s)
            session_dict['date_time'] = session_dict['date_time'].strftime('%Y-%m-%d %H:%M')
            session_dict['created_at'] = session_dict['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            serializable_sessions.append(session_dict)
        
        # Prepare student data
        student_data = {
            'id': student['id'],
            'idno': student['idno'],
            'name': f"{student['firstname']} {student['lastname']}",
            'firstname': student['firstname'],
            'lastname': student['lastname'],
            'middlename': student['middlename'],
            'course': student['course'],
            'year_level': student['year_level'],
            'email': student['email'],
            'profile_picture': student['profile_picture'],
            'sessions_used': student['sessions_used'],
            'max_sessions': student['max_sessions'],
            'active_sessions': serializable_sessions
        }
        
        return jsonify(student_data)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
        
    finally:
        cursor.close()
        conn.close()

@app.route('/admin/approve-session/<int:session_id>', methods=['POST'])
@admin_required
def approve_session(session_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Get session information
        cursor.execute("SELECT * FROM sessions WHERE id = %s", (session_id,))
        session_data = cursor.fetchone()
        
        if not session_data:
            flash('Session not found', 'error')
            return redirect(url_for('admin_dashboard'))
        
        # Update session status to approved
        cursor.execute("""
        UPDATE sessions 
        SET approval_status = 'approved', status = 'active'
        WHERE id = %s
        """, (session_id,))
        
        # Increment sessions_used for the student
        cursor.execute("""
        UPDATE students 
        SET sessions_used = sessions_used + 1
        WHERE id = %s
        """, (session_data['student_id'],))
        
        conn.commit()
        flash('Session approved successfully', 'success')
        
    except Exception as e:
        conn.rollback()
        flash(f'Failed to approve session: {str(e)}', 'error')
        
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reject-session/<int:session_id>', methods=['POST'])
@admin_required
def reject_session(session_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Update session status to rejected
        cursor.execute("""
        UPDATE sessions 
        SET approval_status = 'rejected', status = 'cancelled'
        WHERE id = %s
        """, (session_id,))
        
        conn.commit()
        flash('Session rejected', 'success')
        
    except Exception as e:
        conn.rollback()
        flash(f'Failed to reject session: {str(e)}', 'error')
        
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/check-in/<int:session_id>', methods=['POST'])
@admin_required
def check_in_student(session_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Set check-in time to current time
        cursor.execute("""
        UPDATE sessions 
        SET check_in_time = NOW()
        WHERE id = %s
        """, (session_id,))
        
        conn.commit()
        flash('Student checked in successfully', 'success')
        
    except Exception as e:
        conn.rollback()
        flash(f'Failed to check in student: {str(e)}', 'error')
        
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/check-out/<int:session_id>', methods=['POST'])
@admin_required
def check_out_student(session_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Set check-out time to current time and mark session as completed
        cursor.execute("""
        UPDATE sessions 
        SET check_out_time = NOW(), status = 'completed'
        WHERE id = %s
        """, (session_id,))
        
        conn.commit()
        flash('Student checked out successfully', 'success')
        
    except Exception as e:
        conn.rollback()
        flash(f'Failed to check out student: {str(e)}', 'error')
        
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('admin_dashboard'))

@app.route('/submit-feedback/<int:session_id>', methods=['POST'])
@login_required
def submit_feedback(session_id):
    if session.get('user_type') != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    rating = request.form.get('rating')
    comments = request.form.get('comments', '')
    
    if not rating or not rating.isdigit() or int(rating) < 1 or int(rating) > 5:
        flash('Please provide a valid rating (1-5)', 'error')
        return redirect(url_for('student_dashboard'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Check if session belongs to the student
        cursor.execute("""
        SELECT * FROM sessions 
        WHERE id = %s AND student_id = %s
        """, (session_id, session['user_id']))
        
        session_data = cursor.fetchone()
        if not session_data:
            flash('Session not found or not authorized', 'error')
            return redirect(url_for('student_dashboard'))
        
        # Check if feedback already exists
        cursor.execute("""
        SELECT * FROM feedback 
        WHERE session_id = %s AND student_id = %s
        """, (session_id, session['user_id']))
        
        existing_feedback = cursor.fetchone()
        if existing_feedback:
            # Update existing feedback
            cursor.execute("""
            UPDATE feedback 
            SET rating = %s, comments = %s
            WHERE session_id = %s AND student_id = %s
            """, (rating, comments, session_id, session['user_id']))
            flash('Feedback updated successfully', 'success')
        else:
            # Insert new feedback
            cursor.execute("""
            INSERT INTO feedback (session_id, student_id, rating, comments)
            VALUES (%s, %s, %s, %s)
            """, (session_id, session['user_id'], rating, comments))
            flash('Feedback submitted successfully', 'success')
        
        conn.commit()
        
    except Exception as e:
        conn.rollback()
        flash(f'Failed to submit feedback: {str(e)}', 'error')
        
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('student_dashboard'))

@app.route('/admin/announcements', methods=['GET'])
@admin_required
def view_announcements():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT * FROM announcements ORDER BY created_at DESC")
    announcements = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('admin_announcements.html', announcements=announcements)

@app.route('/admin/add-announcement', methods=['POST'])
@admin_required
def add_announcement():
    title = request.form.get('title')
    content = request.form.get('content')
    
    if not title or not content:
        flash('Title and content are required', 'error')
        return redirect(url_for('view_announcements'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
        INSERT INTO announcements (title, content)
        VALUES (%s, %s)
        """, (title, content))
        
        conn.commit()
        flash('Announcement added successfully', 'success')
        
    except Exception as e:
        conn.rollback()
        flash(f'Failed to add announcement: {str(e)}', 'error')
        
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('view_announcements'))

@app.route('/admin/toggle-announcement/<int:announcement_id>', methods=['POST'])
@admin_required
def toggle_announcement(announcement_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
        UPDATE announcements 
        SET is_active = NOT is_active
        WHERE id = %s
        """, (announcement_id,))
        
        conn.commit()
        flash('Announcement status updated', 'success')
        
    except Exception as e:
        conn.rollback()
        flash(f'Failed to update announcement: {str(e)}', 'error')
        
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('view_announcements'))

@app.route('/admin/delete-announcement/<int:announcement_id>', methods=['POST'])
@admin_required
def delete_announcement(announcement_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("DELETE FROM announcements WHERE id = %s", (announcement_id,))
        
        conn.commit()
        flash('Announcement deleted successfully', 'success')
        
    except Exception as e:
        conn.rollback()
        flash(f'Failed to delete announcement: {str(e)}', 'error')
        
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('view_announcements'))

@app.route('/student/announcements', methods=['GET'])
@login_required
def student_announcements():
    if session.get('user_type') != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get student information
    cursor.execute("SELECT * FROM students WHERE id = %s", (session['user_id'],))
    student = cursor.fetchone()
    
    if not student:
        flash('Student not found', 'error')
        cursor.close()
        conn.close()
        return redirect(url_for('logout'))
    
    # Get active announcements
    try:
        cursor.execute("SELECT * FROM announcements WHERE is_active = TRUE ORDER BY created_at DESC")
        announcements = cursor.fetchall()
    except:
        announcements = []
    
    cursor.close()
    conn.close()
    
    return render_template('student_announcements.html', student=student, announcements=announcements)

@app.route('/admin/delete-student/<int:student_id>', methods=['POST'])
@admin_required
def delete_student(student_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Check if student exists
        cursor.execute("SELECT * FROM students WHERE id = %s", (student_id,))
        student = cursor.fetchone()
        
        if not student:
            flash('Student not found', 'error')
            return redirect(url_for('admin_dashboard'))
        
        # Delete student's sessions
        cursor.execute("DELETE FROM sessions WHERE student_id = %s", (student_id,))
        
        # Delete student's feedback
        cursor.execute("DELETE FROM feedback WHERE student_id = %s", (student_id,))
        
        # Delete the student
        cursor.execute("DELETE FROM students WHERE id = %s", (student_id,))
        
        conn.commit()
        flash(f'Student {student["firstname"]} {student["lastname"]} has been deleted successfully', 'success')
        
    except Exception as e:
        conn.rollback()
        flash(f'Failed to delete student: {str(e)}', 'error')
        
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('admin_dashboard'))

# Make sure to run init_db() when the app starts
with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(debug=True)

