# CSS SIT-IN MONITORING SYSTEM

A web-based system for managing student registrations and profiles for the CSS SIT-IN MONITORING SYSTEM.

## Features

- Student registration and login
- Admin login (username: admin, password: admin)
- Student profile management with profile picture upload
- Student dashboard
- Admin dashboard with student management

## Requirements

- Python 3.7+
- Flask
- MySQL (XAMPP)
- Web browser

## Setup Instructions

### 1. Install XAMPP

Download and install XAMPP from [https://www.apachefriends.org/](https://www.apachefriends.org/)

### 2. Start MySQL and Apache in XAMPP

Open XAMPP Control Panel and start the MySQL and Apache services.

### 3. Install Python Dependencies

```bash
pip install flask mysql-connector-python werkzeug
```

### 4. Configure the Database

The application will automatically create the necessary database and tables when it starts.

### 5. Run the Application

```bash
python app.py
```

### 6. Access the Application

Open your web browser and navigate to:
```
http://localhost:5000
```

## Default Admin Credentials

- Username: admin
- Password: admin

## Directory Structure

- `app.py` - Main application file
- `templates/` - HTML templates
- `static/` - Static files (CSS, JavaScript, images)
- `static/profile_pictures/` - Uploaded profile pictures

## Usage

1. Register as a student from the main page
2. Login with your credentials
3. Access your student dashboard
4. Edit your profile and upload a profile picture

## Admin Features

1. Login with admin credentials
2. View all registered students
3. Manage student accounts

## Notes

- Make sure to keep the XAMPP MySQL service running while using the application
- Default profile pictures are provided for new users
- Student ID numbers must be unique 