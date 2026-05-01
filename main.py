from flask import Flask
from routes.file import file_bp

app = Flask(__name__)

app.register_blueprint(file_bp)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
