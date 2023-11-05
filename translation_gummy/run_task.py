import mimetypes
import subprocess
import os
import json
import uuid
import json
from pathlib import Path
from . import database
from . import onedrive
from .utils import check_white_keyword


env_kaggle_username = os.environ.get("KAGGLE_USERNAME", "")
env_kaggle_key = os.environ.get("KAGGLE_KEY", "")
env_gpt_api_key = os.environ.get("GPT_API_KEY", "")


kernel_metadata = {
    "id": "",
    "title": "Translation Gummy",
    "code_file": "kaggle_main.py",
    "language": "python",
    "kernel_type": "script",
    "is_private": True,
    "enable_gpu": True,
    "enable_tpu": False,
    "enable_internet": True,
    "keywords": [],
    "dataset_sources": [],
    "kernel_sources": [],
    "competition_sources": [],
    "model_sources": [],
}


def run_cmd(cmd, env):
    return subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
    )


def run_transcribe(
    url="",
    kaggle_username=env_kaggle_username,
    kaggle_key=env_kaggle_key,
    word_timestamps=True,
):
    uuid_str = str(uuid.uuid4())
    os.mkdir(f"/tmp/{uuid_str}")
    copy_env = get_copy_env(kaggle_username, kaggle_key)
    kernel_metadata["id"] = f"{kaggle_username}/translation-gummy"
    with open(f"/tmp/{uuid_str}/kernel-metadata.json", "w") as new_f:
        json.dump(kernel_metadata, new_f)
    with open(Path(__file__).with_name("kaggle_main.py"), "r") as f:
        lines = f.readlines()
        lines[0] = f'url = "{url}"\n'
        lines[1] = f"word_timestamps = {word_timestamps}\n"
        with open(f"/tmp/{uuid_str}/kaggle_main.py", "w") as new_f:
            new_f.writelines(lines)
    if (
        check_kaggle_status(kernel_metadata["id"], kaggle_username, kaggle_key)
        == "running"
    ):
        return False
    result = run_cmd(f"kaggle kernels push -p /tmp/{uuid_str}", copy_env)
    if "successfully" in result.stdout:
        return True
    else:
        print(result.stderr)
        return False


def get_copy_env(kaggle_username, kaggle_key):
    copy_env = os.environ.copy()
    if kaggle_username != "" and kaggle_key != "":
        copy_env["KAGGLE_USERNAME"] = kaggle_username
        copy_env["KAGGLE_KEY"] = kaggle_key
    return copy_env


def check_kaggle_status(kernel, kaggle_username, kaggle_key):
    result = run_cmd(
        f"kaggle kernels status {kernel}",
        get_copy_env(kaggle_username, kaggle_key),
    )
    if "complete" in result.stdout:
        return "complete"
    elif "error" in result.stdout:
        return "error"
    elif "running" in result.stdout:
        return "running"
    else:
        return result.stderr


def get_kaggle_result(kernel, kaggle_username, kaggle_key):
    if check_kaggle_status(kernel, kaggle_username, kaggle_key) == "complete":
        uuid_str = str(uuid.uuid4())
        output_dir = f"/tmp/{uuid_str}"
        run_cmd(
            f"kaggle kernels output {kernel} -p {output_dir}",
            get_copy_env(kaggle_username, kaggle_key),
        )
        return output_dir
    else:
        return None


def is_valid_file(file_path):
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type is not None and (
        mime_type.startswith("audio/") or mime_type.startswith("video/")
    ):
        return True
    return False


def get_priority_transcribe(kaggle_username, kaggle_key):
    output_dir = get_kaggle_result(
        f"{kaggle_username}/translation-gummy", kaggle_username, kaggle_key
    )
    if output_dir is None:
        return None
    if not os.path.exists(f"{output_dir}/info.json"):
        return None
    info_json = json.load(open(f"{output_dir}/info.json", "r"))
    file_md5 = info_json["file_md5"]
    url = info_json["url"]
    message = info_json["message"]
    info = info_json["info"]
    task_redirect = database.get_task_by_file_md5(file_md5)
    task = database.get_task_by_url(url)
    if task is None:
        return None
    if task.transcribe_status != "priority" or task.redirect != "":
        return None
    hit_white_keyword = True
    series = database.get_work_by_id(task.series_id)
    keywords = []
    if series is not None and series.check_keyword:
        keywords = database.get_white_keywords()
        hit_white_keyword = check_white_keyword(keywords, str(info))
    try:
        if message != "":
            raise Exception(message)
        if task_redirect is not None and task_redirect.task_id != task.task_id:
            if (
                task_redirect.transcribe_status == "processing"
                or task_redirect.transcribe_status == "success"
            ):
                task.redirect = task_redirect.task_id
                task.transcribe_status = "failed"
                task.save()
                return task
            task_redirect.redirect = task.task_id
            task_redirect.file_md5 = ""
            task_redirect.save()
        video_file = None
        srt_file = None
        if not os.path.exists(f"{output_dir}/video"):
            raise Exception("No video folder found")
        for file in os.listdir(f"{output_dir}/video"):
            if is_valid_file(f"{output_dir}/video/{file}"):
                video_file = file
            elif file.endswith(".srt"):
                srt_file = file
                if not hit_white_keyword:
                    srt_text = open(f"{output_dir}/video/{file}", "r").read()
                    hit_white_keyword = check_white_keyword(keywords, srt_text)
        if not hit_white_keyword:
            raise Exception("该视频暂不支持。")
        if video_file is None or srt_file is None:
            raise Exception("No video or srt file found")
        task.file_md5 = file_md5
        os.chdir(output_dir)
        onedrive.upload_transcribe(
            task,
            ".".join(video_file.split(".")[:-1]),
            os.environ.get("TMP_SUBTITLE_BASE_PATH"),
            os.environ.get("ORIGIN_SUBTITLE_BASE_PATH"),
        )
        task.transcribe_status = "success"
    except Exception as e:
        task.transcribe_status = "failed"
        task.message = str(e)
    task.save()
    return task
