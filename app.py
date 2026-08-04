import os
from flask import Flask
from database import db

def create_app():
    """
    Creates and configures the Flask application.
    This factory pattern is standard and helps with testing and organization.
    """
    app = Flask(__name__)
    
    # Configure the secret key for session management and flash messages
    app.config['SECRET_KEY'] = 'trailmate-secret-key-123'
    
    # Configure the SQLite database location
    # This points to instance/trekking.db
    basedir = os.path.abspath(os.path.dirname(__name__))
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'trekking.db')
    
    # Disable modification tracking to save resources
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize the database with this specific app instance
    db.init_app(app)
    
    # Initialize Flask-Login
    from flask_login import LoginManager
    from models import User
    
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login' # Redirect here if not logged in
    login_manager.login_message_category = 'warning'
    login_manager.init_app(app)
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
        
    # Register Blueprints
    from routes.auth import auth_bp
    app.register_blueprint(auth_bp)

    
    # Programmatically create the database and default Admin user
    from models import User, Trek, Booking # Import here to ensure db knows about them
    
    with app.app_context():
        db.create_all() # Creates tables if they do not exist
        
        # Check if an admin already exists, if not, create the pre-existing admin
        admin = User.query.filter_by(role='admin').first()
        if not admin:
            from werkzeug.security import generate_password_hash
            default_admin = User(
                name='System Admin',
                email='admin@trailmate.com',
                password=generate_password_hash('admin123'), # Securely hashed
                role='admin',
                status='Active'
            )
            db.session.add(default_admin)
            db.session.commit()
            print("Default Admin created successfully!")
            
    return app

if __name__ == '__main__':
    # Start the application in debug mode for development
    app = create_app()
    app.run(debug=True)
