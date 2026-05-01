from pytubefix.cli import on_progress
from dotenv import load_dotenv
from pytubefix import YouTube
from google import genai
import ffmpeg
import time
import os

load_dotenv()
gem_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=gem_key)


def download_video(caminho_arquivo: str):
    output_video_file = "video.mp4"
    (
        ffmpeg.input(caminho_arquivo)
        .output(output_video_file, vf="scale=-2:360", vcodec="libx264", crf=28)
        .run(overwrite_output=True)
    )

    print("Fazendo upload do vídeo para o Google...")
    video_upload = client.files.upload(file=output_video_file)
    file_name = video_upload.name

    if not file_name:
        raise Exception("Falha ao obter o identificador do arquivo no Google.")

    while video_upload.state and video_upload.state.name == "PROCESSING":
        print("Aguardando processamento do vídeo...")
        time.sleep(2)
        video_upload = client.files.get(name=file_name)

    if video_upload.state and video_upload.state.name == "FAILED":
        raise Exception("Falha no processamento do vídeo pela IA")

    return output_video_file,


def download_audio(caminho_arquivo: str):
    output_audio_file = "audio.mp3"
    (
        ffmpeg.input(caminho_arquivo)
        .output(output_audio_file, acodec="libmp3lame", audio_bitrate="192k")
        .run(overwrite_output=True)
    )

    return output_audio_file,


def download(url: str, mode: str):
    yt = YouTube(url, on_progress_callback=on_progress)
    ys = yt.streams.get_highest_resolution()
    caminho_arquivo: str | None

    if ys is not None:
        caminho_arquivo = ys.download(filename="video_para_descrever.mp4")
    else:
        print("Erro ao fazer download")
        raise Exception("Erro ao fazer download")

    try:
        if mode == "video" and caminho_arquivo:
            return download_video(caminho_arquivo)
        elif mode == "audio" and caminho_arquivo:
            return download_audio(caminho_arquivo)
    except ffmpeg.Error as e:
        print(f"An error occurred: {e.stderr.decode('utf8')}")

    # response = client.models.generate_content(
    #     model="gemini-2.0-flash",
    #     contents=[
    #         "Descreva o que acontece no vídeo detalhadamente",
    #         video_upload
    #     ],
    # )

    # return response.text
