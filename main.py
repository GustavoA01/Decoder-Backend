from flask import Flask
from routes.file import file_bp
from routes.summary import summary_bp

app = Flask(__name__)


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


app.register_blueprint(file_bp)
app.register_blueprint(summary_bp)


if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)
