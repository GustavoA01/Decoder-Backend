from flask import Blueprint, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename
from utils import DOWNLOAD_DIR, download

file_bp = Blueprint("file", __name__)


@file_bp.route("/download", methods=["POST"])
def upload():
    body = request.get_json() or {}
    mode = body.get("mode")
    url = body.get("url")

    if not url or not mode:
        return jsonify({"error": "URL e modo são obrigatórios"}), 400

    try:
        name = download(url, mode)
        return jsonify({
            "status": "success",
            "message": "Processamento concluído",
            "filename": name
        }), 200
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        print("Erro ao processar download:", error)
        return jsonify({"error": "Erro interno ao processar o download"}), 500


@file_bp.route("/get-file/<filename>")
def get_file(filename):
    safe_filename = secure_filename(filename)

    if safe_filename != filename:
        return jsonify({"error": "Nome de arquivo inválido"}), 400

    return send_from_directory(
        DOWNLOAD_DIR,
        safe_filename,
        as_attachment=True,
        download_name=safe_filename
    )
