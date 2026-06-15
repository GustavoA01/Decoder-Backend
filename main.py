from flask import Flask, jsonify, make_response, request
from routes.file import file_bp
from routes.summary import summary_bp

app = Flask(__name__)


def _add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = request.headers.get("Origin", "*")
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Max-Age"] = "86400"
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = make_response("", 204)
        return _add_cors_headers(response)

    return None


@app.after_request
def add_cors_headers(response):
    return _add_cors_headers(response)


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
