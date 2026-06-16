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
from pytubefix.exceptions import BotDetection, PoTokenRequired


BASE_DIR = Path(__file__).resolve().parent
IA_VIDEO_DIR = BASE_DIR / "cache" / "ia-video"


class GeminiQuotaError(Exception):
    pass


class GeminiModelError(Exception):
    pass


class YouTubeAccessError(Exception):
    pass


class NoCaptionError(Exception):
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


def _is_youtube_access_error(error: Exception) -> bool:
    error_text = str(error).lower()
    return isinstance(error, (BotDetection, PoTokenRequired)) or "detected as a bot" in error_text or "po_token" in error_text


def _handle_youtube_error(error: Exception):
    if _is_youtube_access_error(error):
        print("[ia-summary] YouTube bloqueou a requisicao:", type(error).__name__, error)
        raise YouTubeAccessError(
            "O YouTube bloqueou a requisicao feita pelo servidor. Tente novamente; se persistir, sera necessario configurar PO Token/proxy ou outro provedor."
        ) from error

    raise error


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


def _video_metadata(yt: YouTube, url: str, video_key: str) -> dict:
    return {
        "video_id": video_key,
        "url": url,
        "title": yt.title,
        "author": yt.author,
    }


def _download_video(yt: YouTube, url: str, video_key: str) -> tuple[Path, dict]:
    video_dir = _ensure_video_dir()
    output_path = video_dir / f"{video_key}_summary.mp4"
    metadata = _video_metadata(yt, url, video_key)

    if output_path.exists():
        print("[ia-summary] Video ja existe, reutilizando:", output_path)
        return output_path, metadata

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
        raise ValueError("Nao foi possivel encontrar um video MP4 para baixar.")

    print("[ia-summary] Baixando video:", yt.title)
    downloaded_path = stream.download(output_path=str(video_dir), filename=output_path.name)
    if downloaded_path is None:
        raise ValueError("Erro ao baixar o video.")

    print("[ia-summary] Video baixado em:", downloaded_path)
    return Path(downloaded_path), metadata


def _get_caption_text(yt: YouTube) -> tuple[str, str]:
    print("[ia-summary] Tentando usar legenda antes de baixar video")
    captions = yt.captions
    if not captions:
        raise NoCaptionError("Esse video nao possui legenda disponivel.")

    preferred_codes = ("pt-BR", "pt", "a.pt", "en", "a.en")
    selected_caption = None

    for code in preferred_codes:
        selected_caption = captions.get(code)
        if selected_caption:
            print("[ia-summary] Legenda selecionada:", code)
            break

    if selected_caption is None:
        selected_caption = next(iter(captions.values()))
        print("[ia-summary] Usando primeira legenda disponivel:", selected_caption.code)

    caption_text = selected_caption.generate_txt_captions()
    if not caption_text:
        raise NoCaptionError("Nao foi possivel extrair texto da legenda desse video.")

    print("[ia-summary] Legenda extraida. Tamanho:", len(caption_text))
    return caption_text, selected_caption.code


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


def _build_summary_prompt(title: str, author: str, transcript: str | None = None, content_type: str | None = None) -> str:
    source_instruction = "Assista ao video enviado" if transcript is None else "Use a transcricao abaixo"
    transcript_block = "" if transcript is None else f"\n\nTranscricao:\n{transcript}"

    selected_type = (content_type or "auto").strip().lower()

    return f"""
Voce e um analista de videos. {source_instruction} e responda em portugues do Brasil.

Titulo: {title}
Canal: {author}
Tipo informado pelo usuario: {selected_type}{transcript_block}

Regras importantes:
- Retorne somente Markdown.
- Nao comece com "Aqui está" ou frases de apresentação.
- Evite repetir a mesma informacão em seções diferentes.
- Escolha o nível de profundidade de acordo com o tipo/conteúdo do video.
- Seja especifico sobre acontecimentos, falas e contexto.
- Se estiver usando transcricao, nao invente detalhes visuais que nao aparecem no texto.
- Se estiver usando video, inclua contexto visual quando for relevante.
- Use frases curtas, naturais e organizadas.

Como decidir o formato:
- Se o tipo for "auto", classifique mentalmente o video antes de responder.
- Para videos simples, curtos, factuais, gameplay casual, reacts leves, trailers ou videos com poucas ideias novas, use o Formato A.
- Para politica, educacao, tutorial, debate, ensaio, review critica, analise, opiniao forte ou videos com argumentos importantes, use o Formato B.
- Se o usuario informou um tipo especifico, respeite esse tipo acima da classificacao automatica.

Formato A - video simples/factual:

## Resumo detalhado
Escreva 1 ou 2 paragrafos bem explicados, sem bullets, cobrindo as ideias principais sem repetir.

## Ideia central
Uma frase direta resumindo a mensagem ou proposta do video.

Formato B - video analitico/opinativo/educacional:

## Resumo detalhado
Escreva 1 ou 2 paragrafos que ja misturem o que aconteceu com por que isso importa. Nao crie uma lista repetindo o resumo.

## Analise
- Liste de 3 a 5 interpretacoes, conclusoes ou implicacoes do conteudo.
- Cada item deve acrescentar algo novo, nao repetir o resumo.
- Em videos de politica/debate, destaque posicoes, conflitos, interesses e consequencias.
- Em videos de aprendizado/tutorial, destaque conceitos, passos importantes e aplicacoes praticas.
- Em reviews/analises, destaque criterios, argumentos e avaliacao final.

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


def _summarize_caption_with_gemini(title: str, author: str, transcript: str, content_type: str | None = None) -> str:
    client, model = _get_gemini_client()

    try:
        prompt = _build_summary_prompt(title, author, transcript, content_type)
        print("[ia-summary] Pedindo resumo ao Gemini via legenda")
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2),
        )
    except Exception as error:
        _handle_gemini_error(error, model)

    print("[ia-summary] Resumo por legenda recebido")
    return response.text or ""


def _summarize_video_with_gemini(video_path: Path, title: str, author: str, content_type: str | None = None) -> str:
    client, model = _get_gemini_client()

    try:
        uploaded_file = _prepare_video_for_gemini(client, video_path)
        prompt = _build_summary_prompt(title, author, content_type=content_type)

        print("[ia-summary] Pedindo resumo ao Gemini via video")
        response = client.models.generate_content(
            model=model,
            contents=[prompt, uploaded_file],
            config=types.GenerateContentConfig(temperature=0.2),
        )
    except Exception as error:
        _handle_gemini_error(error, model)

    print("[ia-summary] Resumo por video recebido")
    return response.text or ""


def summarize_youtube_video(url: str, status_callback=None, content_type: str | None = None) -> dict:
    print("[ia-summary] Inicio do fluxo legenda -> video")
    if status_callback:
        status_callback("Verificando video")

    video_key = _get_video_key(url)

    print("[ia-summary] Abrindo YouTube com client WEB")
    try:
        yt = YouTube(url, client="WEB")
        metadata = _video_metadata(yt, url, video_key)
    except Exception as error:
        _handle_youtube_error(error)

    try:
        if status_callback:
            status_callback("Procurando legenda")

        transcript, caption_code = _get_caption_text(yt)

        if status_callback:
            status_callback("Escrevendo resumo")

        summary = _summarize_caption_with_gemini(yt.title, yt.author, transcript, content_type)
        if status_callback:
            status_callback("Resumo finalizado")

        print("[ia-summary] Fim do fluxo usando legenda")
        return {
            **metadata,
            "caption_code": caption_code,
            "video_file": None,
            "summary_source": "caption",
            "content_type": content_type or "auto",
            "summary": summary,
        }
    except (BotDetection, PoTokenRequired) as error:
        _handle_youtube_error(error)
    except NoCaptionError as error:
        print("[ia-summary] Legenda indisponivel, usando video:", error)
        if status_callback:
            status_callback("Legenda indisponivel. Analisando video, isso pode demorar cerca de 1 minuto")

    try:
        video_path, metadata = _download_video(yt, url, video_key)
    except Exception as error:
        _handle_youtube_error(error)

    if status_callback:
        status_callback("Enviando video para IA. Pode demorar cerca de 1 minuto")

    summary = _summarize_video_with_gemini(
        video_path=video_path,
        title=metadata["title"],
        author=metadata["author"],
        content_type=content_type,
    )

    if status_callback:
        status_callback("Resumo finalizado")

    print("[ia-summary] Fim do fluxo usando video")
    return {
        **metadata,
        "caption_code": None,
        "video_file": video_path.name,
        "summary_source": "video_file",
        "content_type": content_type or "auto",
        "summary": summary,
    }






