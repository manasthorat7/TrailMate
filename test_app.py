from app import create_app

# This script runs the app using the 'test_trekking.db' database on port 5001.
# It is completely separate from your main 'app.py' which runs 'trekking.db' on port 5000.

app = create_app(db_name='test_trekking.db')

if __name__ == '__main__':
    print("==================================================")
    print("STARTING TEST ENVIRONMENT")
    print("Database: test_trekking.db")
    print("Port: 5001")
    print("==================================================")
    app.run(port=5001, debug=True)
