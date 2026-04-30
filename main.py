from flask import Flask, request, jsonify
from utils.download_video import download_video

app = Flask(__name__)


@app.route("/upload", methods=["POST"])
def upload():
    body = request.get_json() or {}
    video_url = body.get("url")
    output_dir = body.get("output_dir")
    if not video_url:
        return jsonify({"error": "URL do vídeo não fornecida"}), 400
    try:
        ia_response, mp3_path = download_video(video_url, output_dir=output_dir)
        return jsonify({"response": ia_response, "mp3_path": mp3_path}, 200)
    except Exception as e:
        return jsonify({"error": f"Erro ao processar o vídeo: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
