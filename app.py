import os
from flask import Flask
from database import db

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'trailmate-secret-key-123'
    basedir = os.path.abspath(os.path.dirname(__file__))
    instance_path = os.path.join(basedir, 'instance')
    if not os.path.exists(instance_path):
        os.makedirs(instance_path)
        
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(instance_path, 'trekking.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    from flask_login import LoginManager
    from models import User
    
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login' # Redirect here if not logged in
    login_manager.login_message_category = 'warning'
    login_manager.init_app(app)
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.staff import staff_bp
    from routes.user import user_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(staff_bp)
    app.register_blueprint(user_bp)
    from models import User, Trek, Booking # Import here to ensure db knows about them
    
    with app.app_context():
        db.create_all() # Creates tables if they do not exist
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
    app = create_app()
    app.run(debug=True)
