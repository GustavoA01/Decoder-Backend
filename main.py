from flask import Flask
from routes.file import file_bp
from routes.summary import summary_bp

app = Flask(__name__)

app.register_blueprint(file_bp)
app.register_blueprint(summary_bp)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
