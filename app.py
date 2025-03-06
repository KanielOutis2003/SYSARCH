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
        WHERE max_sessions IS NULL
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
        status VARCHAR(20) DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
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
        # BSIT, BSCS, BSCE get 30 sessions, others get 25
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
            cursor.execute("SELECT * FROM students WHERE username = %s OR email = %s OR idno = %s", 
                          (username, email, idno))
            existing_user = cursor.fetchone()
            
            if existing_user:
                flash('Username, email, or ID number already exists', 'error')
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
    
    cursor.close()
    conn.close()
    
    return render_template('student_dashboard.html', student=student, sessions=sessions)

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
    
    # Get current sit-in sessions
    cursor.execute("""
    SELECT s.*, st.firstname, st.lastname, st.idno, st.course
    FROM sessions s
    JOIN students st ON s.student_id = st.id
    WHERE s.status = 'active'
    ORDER BY s.date_time DESC
    """)
    active_sessions = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('admin_dashboard.html', students=students, active_sessions=active_sessions)

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
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Check if student has available sessions
        cursor.execute("SELECT sessions_used, max_sessions FROM students WHERE id = %s", (session['user_id'],))
        student = cursor.fetchone()
        
        if student['sessions_used'] >= student['max_sessions']:
            flash('You have used all your available sessions', 'error')
            return redirect(url_for('student_dashboard'))
        
        # Add new session
        cursor.execute("""
        INSERT INTO sessions (student_id, lab_room, date_time, duration, programming_language, status)
        VALUES (%s, %s, %s, %s, %s, %s)
        """, (session['user_id'], lab_room, date_time, duration, programming_language, 'active'))
        
        # Update sessions used
        cursor.execute("""
        UPDATE students SET sessions_used = sessions_used + 1
        WHERE id = %s
        """, (session['user_id'],))
        
        conn.commit()
        flash('Session added successfully', 'success')
        
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

# Make sure to run init_db() when the app starts
with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(debug=True)

