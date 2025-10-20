# app.py
import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "my_super_secret_key")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

mysql_host = "localhost"
mysql_user = "root"           # or flaskuser if you created that
mysql_password = "root"   # or flaskpassword if you created that
mysql_database = "ai_paper_setter"
mysql_port = "3306"

mysql_url = f"mysql+pymysql://{mysql_user}:{mysql_password}@{mysql_host}:{mysql_port}/{mysql_database}"
app.config["SQLALCHEMY_DATABASE_URI"] = mysql_url

app.config["SQLALCHEMY_DATABASE_URI"] = mysql_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ECHO"] = True  # <-- this will print all SQL queries to console

# Use MySQL if credentials are provided, otherwise fallback to SQLite for development
if os.environ.get("MYSQL_HOST") or os.environ.get("MYSQL_PASSWORD"):
    app.config["SQLALCHEMY_DATABASE_URI"] = mysql_url
    logging.info("Using MySQL database")
else:
    # Fallback to SQLite for local development
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///ai_paper_setter.db"
    logging.info("Using SQLite database for development")

app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Initialize the app with the extension
db.init_app(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'teacher_login'

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))

with app.app_context():
    # Import models to create tables
    import models
    db.create_all()
    
    # Create default admin user if not exists
    from models import Admin
    from werkzeug.security import generate_password_hash
    
    if not Admin.query.filter_by(username='admin').first():
        admin = Admin(
            username='admin',
            email='admin@example.com',
            password_hash=generate_password_hash('admin123')
        )
        db.session.add(admin)
        db.session.commit()
        logging.info("Default admin user created: admin/admin123")