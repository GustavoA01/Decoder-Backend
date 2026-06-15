import hashlib
import mimetypes
import os
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pytubefix import YouTube


BASE_DIR = Path(__file__).resolve().parent
IA_VIDEO_DIR = BASE_DIR / "cache" / "ia-video"


class GeminiQuotaError(Exception):
    pass


class GeminiModelError(Exception):
    pass


def _ensure_video_dir() -> Path:
    IA_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    return IA_VIDEO_DIR


def _get_video_key(url: str) -> str:
    parsed_url = urlparse(url)

    if parsed_url.netloc.endswith("youtu.be"):
        video_id = parsed_url.path.strip("/")
        if video_id:
            return video_id

    query_video_id = parse_qs(parsed_url.query).get("v", [None])[0]
    if query_video_id:
        return query_video_id

    path_parts = [part for part in parsed_url.path.split("/") if part]
    for marker in ("shorts", "embed", "live"):
        if marker in path_parts:
            marker_index = path_parts.index(marker)
            if len(path_parts) > marker_index + 1:
                return path_parts[marker_index + 1]

    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _get_gemini_client() -> tuple[genai.Client, str]:
    print("[ia-summary] Carregando .env")
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise ValueError("GEMINI_API_KEY nao foi configurada no .env")

    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    print("[ia-summary] Modelo Gemini:", model)
    return genai.Client(api_key=api_key), model


def _is_quota_error(error: Exception) -> bool:
    error_text = str(error)
    return "RESOURCE_EXHAUSTED" in error_text or "429" in error_text


def _is_model_error(error: Exception) -> bool:
    error_text = str(error)
    return "NOT_FOUND" in error_text or "404" in error_text or "not found for API version" in error_text



def _resolution_value(stream) -> int:
    resolution = getattr(stream, "resolution", None) or "0p"
    try:
        return int(resolution.replace("p", ""))
    except ValueError:
        return 0


def _select_summary_stream(yt: YouTube):
    streams = list(
        yt.streams
        .filter(progressive=True, file_extension="mp4")
        .order_by("resolution")
        .asc()
    )

    if not streams:
        return None

    preferred = [stream for stream in streams if 360 <= _resolution_value(stream) <= 480]
    if preferred:
        return preferred[0]

    return streams[0]

def _download_video(url: str) -> tuple[Path, dict]:
    print("[ia-summary] Abrindo YouTube")
    yt = YouTube(url)
    video_key = _get_video_key(url)
    video_dir = _ensure_video_dir()
    output_path = video_dir / f"{video_key}_summary.mp4"

    if output_path.exists():
        print("[ia-summary] Video ja existe, reutilizando:", output_path)
        return output_path, {
            "video_id": video_key,
            "url": url,
            "title": yt.title,
            "author": yt.author,
        }

    print("[ia-summary] Procurando stream MP4 leve para resumo")
    stream = _select_summary_stream(yt)

    if stream is None:
        print("[ia-summary] Stream progressiva nao encontrada; tentando MP4 qualquer")
        stream = (
            yt.streams
            .filter(file_extension="mp4")
            .order_by("resolution")
            .asc()
            .first()
        )

    if stream is not None:
        print("[ia-summary] Stream escolhida:", getattr(stream, "resolution", None), getattr(stream, "mime_type", None))

    if stream is None:
        raise ValueError(
            "Nao foi possivel encontrar um video MP4 para baixar.")

    print("[ia-summary] Baixando video:", yt.title)
    downloaded_path = stream.download(
        output_path=str(video_dir), filename=output_path.name)
    if downloaded_path is None:
        raise ValueError("Erro ao baixar o video.")

    print("[ia-summary] Video baixado em:", downloaded_path)
    return Path(downloaded_path), {
        "video_id": video_key,
        "url": url,
        "title": yt.title,
        "author": yt.author,
    }


def _file_state_name(uploaded_file) -> str | None:
    state = getattr(uploaded_file, "state", None)
    if state is None:
        return None
    return getattr(state, "name", str(state))


def _wait_until_file_is_ready(client: genai.Client, uploaded_file):
    file_name = getattr(uploaded_file, "name", None)
    if not file_name:
        return uploaded_file

    for _ in range(30):
        state_name = _file_state_name(uploaded_file)
        print("[ia-summary] Estado do arquivo no Gemini:", state_name)

        if state_name in (None, "ACTIVE"):
            return uploaded_file

        if state_name == "FAILED":
            raise ValueError("Falha ao processar o video no Gemini.")

        time.sleep(2)
        uploaded_file = client.files.get(name=file_name)

    raise ValueError("O Gemini demorou demais para processar o video.")



def _build_summary_prompt(title: str, author: str) -> str:
    return f"""
Voce e um analista de videos. Assista ao video enviado e responda em portugues do Brasil.

Titulo: {title}
Canal: {author}

Regras importantes:
- Retorne somente Markdown.
- Nao comece com "Aqui esta" ou frases de apresentacao.
- Seja especifico sobre cenas, acontecimentos e contexto visual.
- Se algo nao estiver claro no video, diga isso sem inventar.
- Use frases curtas e organizadas.

Formato obrigatorio:

## Resumo
Escreva um paragrafo de 4 a 6 linhas explicando o que acontece no video.

## O que acontece no video
- Liste os acontecimentos principais em ordem logica.
- Cada item deve ser concreto e facil de entender.

## Pontos principais
- Liste de 3 a 6 pontos importantes.

## Ideia central
Uma frase direta resumindo a mensagem ou proposta do video.
""".strip()


def _prepare_video_for_gemini(client: genai.Client, video_path: Path):
    mime_type = mimetypes.guess_type(video_path.name)[0] or "video/mp4"

    print("[ia-summary] Enviando arquivo para Gemini:", video_path)
    print("[ia-summary] Mime type:", mime_type)
    uploaded_file = client.files.upload(
        file=video_path,
        config=types.UploadFileConfig(mime_type=mime_type),
    )
    return _wait_until_file_is_ready(client, uploaded_file)


def _handle_gemini_error(error: Exception, model: str):
    if _is_quota_error(error):
        print("[ia-summary] Quota do Gemini excedida")
        raise GeminiQuotaError(
            "Quota do Gemini excedida. Tente novamente mais tarde ou configure outra chave/modelo."
        ) from error

    if _is_model_error(error):
        print("[ia-summary] Modelo Gemini invalido ou indisponivel:", model)
        raise GeminiModelError(
            f"Modelo Gemini invalido ou indisponivel: {model}. Confira o nome em AI Studio > API keys > Model rate limits."
        ) from error

    print("[ia-summary] Erro Gemini:", type(error).__name__, error)
    raise error

def _summarize_video_with_gemini(video_path: Path, title: str, author: str) -> str:
    client, model = _get_gemini_client()

    try:
        uploaded_file = _prepare_video_for_gemini(client, video_path)
        prompt = _build_summary_prompt(title, author)

        print("[ia-summary] Pedindo resumo ao Gemini")
        response = client.models.generate_content(
            model=model,
            contents=[prompt, uploaded_file],
            config=types.GenerateContentConfig(temperature=0.2),
        )
    except Exception as error:
        _handle_gemini_error(error, model)

    print("[ia-summary] Resumo recebido")
    return response.text or ""


def summarize_youtube_video(url: str) -> dict:
    print("[ia-summary] Inicio do fluxo basico")
    video_path, metadata = _download_video(url)
    summary = _summarize_video_with_gemini(
        video_path=video_path,
        title=metadata["title"],
        author=metadata["author"],
    )

    print("[ia-summary] Fim do fluxo basico")
    return {
        **metadata,
        "video_file": video_path.name,
        "summary_source": "video_file",
        "summary": summary,
    }




