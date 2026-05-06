from pytubefix.cli import on_progress
from pytubefix import YouTube
import ffmpeg


def download_video(video_path: str, audio_path: str | None = None):
    output_video_file = "video.mp4"

    if audio_path:
        video_input = ffmpeg.input(video_path)
        audio_input = ffmpeg.input(audio_path)
        (
            ffmpeg
            .output(video_input, audio_input, output_video_file, vcodec="copy", acodec="aac")
            .run(overwrite_output=True)
        )
    else:
        (
            ffmpeg
            .input(video_path)
            .output(output_video_file, vcodec="copy", acodec="copy")
            .run(overwrite_output=True)
        )

    return output_video_file,


def download_audio(audio_path: str):
    output_audio_file = "audio.mp3"
    (
        ffmpeg.input(audio_path)
        .output(output_audio_file, acodec="libmp3lame", audio_bitrate="192k")
        .run(overwrite_output=True)
    )

    return output_audio_file,


def download(url: str, mode: str):
    yt = YouTube(url, on_progress_callback=on_progress)

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
                raise Exception("Erro ao encontrar stream de video")

            video_path = video_stream.download(filename="video_original.mp4")
            audio_path = audio_stream.download(filename="audio_original") if audio_stream else None
            return download_video(video_path, audio_path)

        if mode == "audio":
            if audio_stream is None:
                raise Exception("Erro ao encontrar stream de audio")

            audio_path = audio_stream.download(filename="audio_original")
            return download_audio(audio_path)

        raise Exception("Modo invalido. Use 'video' ou 'audio'.")
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
