import ffmpeg
from pathlib import Path
from uuid import uuid4
import os
from pytubefix import YouTube
from pytubefix.cli import on_progress


BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
visitor_data = os.getenv("YOUTUBE_VISITOR_DATA")
po_token = os.getenv("YOUTUBE_PO_TOKEN")


def _ensure_download_dir() -> Path:
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    return DOWNLOAD_DIR


def download_video(video_path: str, output_filename: str, audio_path: str | None = None):
    output_video_file = DOWNLOAD_DIR / output_filename

    if audio_path:
        video_input = ffmpeg.input(video_path)
        audio_input = ffmpeg.input(audio_path)
        (
            ffmpeg
            .output(video_input, audio_input, str(output_video_file), vcodec="copy", acodec="aac")
            .run(overwrite_output=True)
        )
    else:
        (
            ffmpeg
            .input(video_path)
            .output(str(output_video_file), vcodec="copy", acodec="copy")
            .run(overwrite_output=True)
        )

    return output_filename,


def download_audio(audio_path: str, output_filename: str):
    output_audio_file = DOWNLOAD_DIR / output_filename
    (
        ffmpeg.input(audio_path)
        .output(str(output_audio_file), acodec="libmp3lame", audio_bitrate="192k")
        .run(overwrite_output=True)
    )

    return output_filename,


def download(url: str, mode: str):
    _ensure_download_dir()

    yt = YouTube(url, client="ANDROID", on_progress_callback=on_progress)

    file_id = uuid4().hex

    video_stream = (
        yt.streams
        .filter(adaptive=True, only_video=True, file_extension="mp4")
        .order_by("resolution")
        .desc()
        .first()
    )
    audio_stream = (
        yt.streams
        .filter(only_audio=True)
        .order_by("abr")
        .desc()
        .first()
    )

    try:
        if mode == "video":
            if video_stream is None:
                raise ValueError("Erro ao encontrar stream de video")

            video_path = video_stream.download(
                output_path=str(DOWNLOAD_DIR),
                filename=f"{file_id}_video_original.mp4"
            )
            if video_path is None:
                raise ValueError("Erro ao baixar stream de video")

            audio_path = (
                audio_stream.download(output_path=str(
                    DOWNLOAD_DIR), filename=f"{file_id}_audio_original")
                if audio_stream
                else None
            )
            return download_video(video_path, f"{file_id}_video.mp4", audio_path)

        if mode == "audio":
            if audio_stream is None:
                raise ValueError("Erro ao encontrar stream de audio")

            audio_path = audio_stream.download(output_path=str(
                DOWNLOAD_DIR), filename=f"{file_id}_audio_original")
            if audio_path is None:
                raise ValueError("Erro ao baixar stream de audio")

            return download_audio(audio_path, f"{file_id}_audio.mp3")

        raise ValueError("Modo invalido. Use 'video' ou 'audio'.")
    except ffmpeg.Error as e:
        print(f"An error occurred: {e.stderr.decode('utf8')}")
        raise

    # response = client.models.generate_content(
    #     model="gemini-2.0-flash",
    #     contents=[
    #         "Descreva o que acontece no video detalhadamente",
    #         video_upload
    #     ],
    # )

    # return response.text
