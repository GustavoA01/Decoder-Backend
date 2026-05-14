from flask import Blueprint, jsonify, request
from ia import GeminiModelError, GeminiQuotaError, summarize_youtube_video

summary_bp = Blueprint("summary", __name__)


@summary_bp.route("/ia-summary", methods=["POST"])
def ia_summary():
    body = request.get_json(silent=True) or {}
    print("[ia-summary] Requisicao recebida")
    print("[ia-summary] Content-Type:", request.content_type)
    print("[ia-summary] JSON recebido:", body)
    print("[ia-summary] Form recebido:", request.form.to_dict())

    url = (
        body.get("url")
        or body.get("link")
        or body.get("youtubeUrl")
        or request.form.get("url")
        or request.form.get("link")
        or request.form.get("youtubeUrl")
    )
    print("[ia-summary] URL detectada:", url)

    if not url:
        print("[ia-summary] Erro: nenhuma URL encontrada no body/form")
        return jsonify({
            "error": "URL Ã© obrigatÃ³ria",
            "received_fields": list(body.keys()) or list(request.form.keys()),
        }), 400

    try:
        print("[ia-summary] Chamando summarize_youtube_video")
        summary_data = summarize_youtube_video(url)
        print("[ia-summary] Resumo retornado com sucesso")

        return jsonify({
            "status": "success",
            "message": "Resumo gerado com sucesso",
            **summary_data,
        }), 200
    except ValueError as error:
        print("[ia-summary] ValueError:", error)
        return jsonify({"error": str(error)}), 400
    except GeminiQuotaError as error:
        print("[ia-summary] GeminiQuotaError:", error)
        return jsonify({"error": str(error)}), 429
    except GeminiModelError as error:
        print("[ia-summary] GeminiModelError:", error)
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        print("[ia-summary] Erro inesperado:", type(error).__name__, error)
        return jsonify({"error": "Erro interno ao gerar resumo com IA"}), 500
