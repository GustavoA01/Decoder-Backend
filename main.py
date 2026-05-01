from flask import Flask, request, jsonify
from utils.download import download

app = Flask(__name__)


@app.route("/upload", methods=["POST"])
def upload():
    body = request.get_json() or {}
    mode = body.get("mode")
    video_url = body.get("url")
    output_dir = body.get("output_dir")
    
    if not video_url or not mode:
        return jsonify({"error": "URL e modo são obrigatórios"}), 400
    
    download(video_url, mode)
    return jsonify({"message": "Download iniciado com sucesso!"}), 200


if __name__ == "__main__":
    app.run(debug=True, port=5000)
