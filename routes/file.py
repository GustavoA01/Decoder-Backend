from flask import Flask, request, jsonify, send_file, Blueprint
from utils.download import download

file_bp = Blueprint("file", __name__)


@file_bp.route("/download", methods=["POST"])
def upload():
    body = request.get_json() or {}
    mode = body.get("mode")
    url = body.get("url")
    output_dir = body.get("output_dir")

    if not url or not mode:
        return jsonify({"error": "URL e modo são obrigatórios"}), 400

    name = download(url, mode)
    return jsonify({
        "status": "success",
        "message": "Processamento concluído",
        "filename": name
    }), 200


@file_bp.route("/get-file/<filename>")
def get_file(filename):
    try:
        print("Tentando enviar o arquivo:", filename)
        return send_file(
            filename,
            as_attachment=True,
            download_name=filename
        )

    except FileNotFoundError:
        return "Arquivo não encontrado", 404
