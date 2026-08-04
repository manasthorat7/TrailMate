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
    
    # We will register our blueprints (routes) here later
    
    return app

if __name__ == '__main__':
    # Start the application in debug mode for development
    app = create_app()
    app.run(debug=True)
