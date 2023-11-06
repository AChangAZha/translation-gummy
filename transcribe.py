import subprocess
import traceback
import os
import hashlib
import json
import os
import urllib.parse as urlparse
from urllib.parse import urlencode
from translation_gummy.utils import is_audio_file_or_video_file, check_white_keyword


transcribe_log_file = open("transcribe.log", "w")
origin_subtitle_base_path = ""
tmp_subtitle_base_path = ""
url = os.environ.get("URL", "")
word_timestamps = os.environ.get("WORD_TIMESTAMPS", "True") == "True"


def get_task():
    task = database.get_top_transcribe_task()
    if task is None:
        return None
    task.transcribe_status = "processing"
    task.save()
    return task


def run_cmd(cmd, stdout=transcribe_log_file, stderr=transcribe_log_file):
    transcribe_log_file.write(f"\nRunning command: {cmd}\n")
    subprocess.run(cmd, shell=True, stdout=stdout, stderr=stderr)


def get_bilibili_first_video_url(url):
    url_parsed = urlparse.urlparse(url)
    query = dict(urlparse.parse_qsl(url_parsed.query))
    query["p"] = 1
    url_parsed = url_parsed._replace(query=urlencode(query))
    return urlparse.urlunparse(url_parsed)


def download_file(url):
    if urlparse.urlparse(url).netloc == "www.bilibili.com":
        url = get_bilibili_first_video_url(url)
    run_cmd(f"rm -rf video/")
    run_cmd(f"pip install yt-dlp")
    run_cmd(f'yt-dlp "{url}" --paths video/ --age-limit 0 --write-info-json')
    if not os.path.exists("video") or not any(
        is_audio_file_or_video_file(f) for f in os.listdir("video")
    ):
        run_cmd(f"rm -rf video/")
        run_cmd(f'wget "{url}" -P video/')
    files = os.listdir("video")
    if not os.path.exists("video") or not files:
        raise Exception("No audio or video file found")
    info_json = {}
    for f in files:
        if not is_audio_file_or_video_file(f):
            if f.endswith(".info.json"):
                with open(f"video/{f}") as info_json_file:
                    info_json = json.load(info_json_file)
            run_cmd(f'rm -rf "video/{f}"')
    files = os.listdir("video")
    if len(files) == 0:
        raise Exception("No audio or video file found")
    elif len(files) > 1:
        raise Exception("More than one audio or video file found")
    return info_json


def check_file_md5(task, md5):
    existing_task = database.get_task_by_file_md5(md5)
    if existing_task is not None and existing_task.task_id != task.task_id:
        task.redirect = existing_task.task_id
        task.save()
        raise Exception("Redirect to existing task")
    else:
        task.file_md5 = md5
    task.save()


def get_chapters():
    run_cmd("sudo apt update")
    run_cmd("sudo apt install -y ffmpeg")
    run_cmd(
        'ffprobe -v quiet -print_format json -show_chapters "video/$(ls video/)"',
        stdout=open("chapters.json", "w"),
    )


def split_video(series, split_transcribes):
    run_cmd("rm -rf split")
    run_cmd("mkdir split")
    with open("chapters.json") as f:
        detailed_chapters = json.load(f)["chapters"]
    split_parts = split(series, split_transcribes, detailed_chapters)
    for i, part in enumerate(split_parts):
        run_cmd(
            f'ffmpeg -i "video/$(ls video/)" -ss {part[0]} -to {part[1]} -c copy -copyts -avoid_negative_ts make_zero -y "split/{i}.mp4"'
        )
    return split_parts


def install_transcribe_dependencies():
    run_cmd("git clone https://huggingface.co/spaces/aadnk/faster-whisper-webui")
    run_cmd("cd faster-whisper-webui/ && pip install -r requirements.txt")


def transcribe(dir, split_transcribes=None, split_parts=[], initial_prompt=""):
    if split_transcribes is not None:
        split_transcribes = list(split_transcribes)
    else:
        split_transcribes = []
    if len(split_transcribes) > 0 and len(split_transcribes) == len(split_parts):
        initial_prompts = [part.transcribe_initial_prompt for part in split_transcribes]
    else:
        initial_prompts = [initial_prompt]
    files = os.listdir(dir)
    files.sort()
    for i, f in enumerate(files):
        f_initial_prompt = (
            ('"' + initial_prompts[i] + '"')
            if initial_prompts[i] != ""
            else initial_prompt
        )
        run_cmd(
            f'cd faster-whisper-webui/ && python cli.py "../{dir}/{f}" '
            + f"--output_dir ../{dir} --model large-v2 --vad none --word_timestamps {word_timestamps} "
            + f'{(" --initial_prompt " + f_initial_prompt) if f_initial_prompt != "" else ""}'
        )
    for f in os.listdir(dir):
        if not is_audio_file_or_video_file(f) and not f.endswith(".srt"):
            run_cmd(f'rm -rf "{dir}/{f}"')


def rename_subtitle(dir, filename, file_extension, split_parts=[]):
    if os.path.exists(f"{dir}/merged.srt"):
        run_cmd(f'mv "{dir}/merged.srt" "video/{filename}.whisper.srt"')
        for i, part in enumerate(split_parts):
            part_0 = part[0].replace(":", "-").replace(".", "-")
            part_1 = part[1].replace(":", "-").replace(".", "-")
            run_cmd(
                f'mv "{dir}/{i}{file_extension}-subs.srt" "{dir}/{i}-{part_0}-{part_1}.srt"'
            )
            run_cmd(
                f'mv "{dir}/{i}{file_extension}" "{dir}/{i}-{part_0}-{part_1}{file_extension}"'
            )
    else:
        run_cmd(
            f'mv "{dir}/{filename}{file_extension}-subs.srt" "video/{filename}.whisper.srt"'
        )
    if not os.path.exists(f"video/{filename}.whisper.srt"):
        raise Exception("No subtitle file found")


task = None
md5 = ""
message = ""
info_json = {}
try:
    if url == "":
        from translation_gummy import database
        from translation_gummy.onedrive import upload_transcribe
        from translation_gummy.utils.subtitle_tools import (
            replace_word,
            merge_subtitle,
            replace_subtitles,
            split,
        )

        origin_subtitle_base_path = os.environ.get("ORIGIN_SUBTITLE_BASE_PATH")
        tmp_subtitle_base_path = os.environ.get("TMP_SUBTITLE_BASE_PATH")
        task = get_task()
        if task is None:
            exit(0)
        url = task.url
        word_timestamps = task.word_timestamps
    info_json = download_file(url)
    md5 = hashlib.md5(open("video/" + os.listdir("video")[0], "rb").read()).hexdigest()
    get_chapters()
    install_transcribe_dependencies()
    dir = "video"
    filename, file_extension = os.path.splitext(os.listdir(dir)[0])
    if task is not None:
        check_file_md5(task, md5)
        series = database.get_work_by_id(task.series_id)
        split_parts = None
        split_transcribes = None
        transcribe_initial_prompt = ""
        words = []
        hit_white_keyword = True
        keywords = []
        if series is not None:
            split_transcribes = series.split_transcribes
            split_parts = split_video(series, split_transcribes)
            if os.path.exists("split") and os.listdir("split"):
                dir = "split"
            transcribe_initial_prompt = series.transcribe_initial_prompt
            words = database.sort_replace_words(
                series.replace_words,
            )
            words = list(words) if words is not None else []
            if series.check_keyword:
                keywords = database.get_white_keywords()
                hit_white_keyword = check_white_keyword(keywords, str(info_json))
        transcribe(dir, split_transcribes, split_parts, transcribe_initial_prompt)
        replace_word(dir, words, transcribe_log_file)
        merge_subtitle(dir, split_parts, f"{file_extension}-subs")
        rename_subtitle(dir, filename, file_extension, split_parts)
        with open("chapters.json") as f:
            detailed_chapters = json.load(f)["chapters"]
            replace_subtitles("video", filename, series, detailed_chapters)
        if not hit_white_keyword:
            srt_text = open(f"video/{filename}.whisper.srt", "r").read()
            hit_white_keyword = check_white_keyword(keywords, srt_text)
        if not hit_white_keyword:
            raise Exception("该视频暂不支持。")
        upload_transcribe(
            task, filename, tmp_subtitle_base_path, origin_subtitle_base_path
        )
        task.transcribe_status = "success"
        task.save()
    else:
        transcribe(dir)
        rename_subtitle(dir, filename, file_extension)
except Exception as e:
    message = str(e)
    if task is not None:
        task.transcribe_status = "failed"
        task.message = str(e)
        task.save()
    transcribe_log_file.write(f"\n{traceback.format_exc()}\n")
finally:
    with open("info.json", "w") as f:
        json.dump(
            {"url": url, "file_md5": md5, "message": message, "info": info_json},
            f,
            indent=4,
        )
    run_cmd("rm -rf faster-whisper-webui/")
    transcribe_log_file.close()
