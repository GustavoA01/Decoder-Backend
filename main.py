from flask import Flask, jsonify
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


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "status": "ok",
        "message": "Decoder Backend is running",
        "routes": [
            "/health",
            "/download",
            "/get-file/<filename>",
            "/ia-summary",
            "/ia-summary-jobs",
            "/ia-summary-jobs/<job_id>",
        ],
    }), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


app.register_blueprint(file_bp)
app.register_blueprint(summary_bp)


if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)
