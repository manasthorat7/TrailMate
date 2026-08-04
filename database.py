from flask_sqlalchemy import SQLAlchemy

# Initialize the SQLAlchemy object here.
# By keeping this in a separate file, we avoid circular imports
# when we need to import 'db' into app.py and models.py.
db = SQLAlchemy()
