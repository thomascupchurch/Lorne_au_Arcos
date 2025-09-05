from app import create_app
import os

app = create_app()

if __name__ == '__main__':
    debug = os.getenv('FLASK_DEBUG','1') == '1'
    app.run(debug=debug, host='127.0.0.1', port=5000)

# app.run(host='0.0.0.0', port=5000)
# http://172.16.1.155:5000
