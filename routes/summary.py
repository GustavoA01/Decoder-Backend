import traceback
from threading import Lock, Thread
from uuid import uuid4

from flask import Blueprint, jsonify, request

from ia import GeminiModelError, GeminiQuotaError, YouTubeAccessError, summarize_youtube_video

summary_bp = Blueprint("summary", __name__)

summary_jobs = {}
summary_jobs_lock = Lock()


def _get_url_from_request():
    body = request.get_json(silent=True) or {}
    return (
        body.get("url")
        or body.get("link")
        or body.get("youtubeUrl")
        or request.form.get("url")
        or request.form.get("link")
        or request.form.get("youtubeUrl")
    )


def _get_content_type_from_request():
    body = request.get_json(silent=True) or {}
    return (
        body.get("content_type")
        or body.get("contentType")
        or body.get("video_type")
        or body.get("videoType")
        or request.form.get("content_type")
        or request.form.get("contentType")
        or request.form.get("video_type")
        or request.form.get("videoType")
        or "auto"
    )


def _set_job(job_id: str, **changes):
    with summary_jobs_lock:
        current_job = summary_jobs.get(job_id, {})
        current_job.update(changes)
        summary_jobs[job_id] = current_job


def _get_job(job_id: str):
    with summary_jobs_lock:
        job = summary_jobs.get(job_id)
        return dict(job) if job else None


def _error_response(error):
    if isinstance(error, ValueError):
        return str(error), 400

    if isinstance(error, GeminiQuotaError):
        return str(error), 429

    if isinstance(error, GeminiModelError):
        return str(error), 400

    return f"{type(error).__name__}: {error}", 500


def _run_summary_job(job_id: str, url: str, content_type: str):
    def update_status(message: str):
        print(f"[ia-summary-job] {job_id}: {message}")
        _set_job(job_id, message=message)

    try:
        _set_job(job_id, status="processing", message="Verificando video")
        summary_data = summarize_youtube_video(url, status_callback=update_status, content_type=content_type)
        _set_job(
            job_id,
            status="success",
            message="Resumo gerado com sucesso",
            result={
                "status": "success",
                "message": "Resumo gerado com sucesso",
                **summary_data,
            },
        )
    except Exception as error:
        error_message, status_code = _error_response(error)
        print("[ia-summary-job] Erro:", type(error).__name__, error)
        traceback.print_exc()
        _set_job(
            job_id,
            status="error",
            message=error_message,
            error={"error": error_message, "status_code": status_code},
        )


@summary_bp.route("/ia-summary", methods=["POST"])
def ia_summary():
    print("[ia-summary] Requisicao recebida")
    print("[ia-summary] Content-Type:", request.content_type)

    url = _get_url_from_request()
    print("[ia-summary] URL detectada:", url)

    if not url:
        print("[ia-summary] Erro: nenhuma URL encontrada no body/form")
        body = request.get_json(silent=True) or {}
        return jsonify({
            "error": "URL e obrigatoria",
            "received_fields": list(body.keys()) or list(request.form.keys()),
        }), 400

    try:
        print("[ia-summary] Chamando summarize_youtube_video")
        summary_data = summarize_youtube_video(url, content_type=_get_content_type_from_request())
        print("[ia-summary] Resumo retornado com sucesso")

        return jsonify({
            "status": "success",
            "message": "Resumo gerado com sucesso",
            **summary_data,
        }), 200
    except Exception as error:
        error_message, status_code = _error_response(error)
        print("[ia-summary] Erro:", type(error).__name__, error)
        traceback.print_exc()
        return jsonify({"error": error_message}), status_code


@summary_bp.route("/ia-summary-jobs", methods=["POST"])
def create_ia_summary_job():
    url = _get_url_from_request()
    print("[ia-summary-job] URL detectada:", url)

    if not url:
        body = request.get_json(silent=True) or {}
        return jsonify({
            "error": "URL e obrigatoria",
            "received_fields": list(body.keys()) or list(request.form.keys()),
        }), 400

    job_id = uuid4().hex
    _set_job(job_id, status="queued", message="Resumo na fila", result=None, error=None)

    content_type = _get_content_type_from_request()
    thread = Thread(target=_run_summary_job, args=(job_id, url, content_type), daemon=True)
    thread.start()

    return jsonify({
        "job_id": job_id,
        "status": "queued",
        "message": "Resumo na fila",
    }), 202


@summary_bp.route("/ia-summary-jobs/<job_id>", methods=["GET"])
def get_ia_summary_job(job_id):
    job = _get_job(job_id)

    if not job:
        return jsonify({"error": "Job nao encontrado"}), 404

    return jsonify({
        "job_id": job_id,
        **job,
    }), 200




