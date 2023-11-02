import flask
import os
from urllib.parse import urlparse, unquote
import hashlib
import datetime
from flask_cors import CORS, cross_origin
from translation_gummy import alist, database, run_task
from translation_gummy.utils import is_audio_file_or_video_file


app = flask.Flask(__name__)


alist_host = os.environ.get("ALIST_HOST")
cros_origin = os.environ.get("CROS_ORIGIN", "").split(" ")
if cros_origin == [""]:
    cros_origin = []
cors = CORS(app, resources={r"/api/*": {"origins": cros_origin}})
video_exts = [".mp4", ".mkv", ".avi", ".rmvb", ".flv", ".mov", ".webm"]
tmp_subtitle_base_path = os.environ.get("TMP_SUBTITLE_BASE_PATH")


@cross_origin()
@app.route("/api/task", methods=["POST"])
def create_task():
    url = flask.request.json.get("url", "")
    if url == "":
        return flask.jsonify({"error": "Invalid URL"}), 400
    copy_url = url
    transcribe_only = flask.request.json.get("transcribe_only", False)
    word_timestamps = flask.request.json.get("word_timestamps", True)
    translate_engine = flask.request.json.get("translate_engine", "google")
    kaggle_username = flask.request.json.get("kaggle_username", "")
    kaggle_key = flask.request.json.get("kaggle_key", "")
    ai_key = flask.request.json.get("api_key", "")
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    if domain == "":
        return flask.jsonify({"error": "Invalid URL"}), 400
    id = ""
    transcribe_status = "pending"
    translate_status = "pending"
    if kaggle_username != "" and kaggle_key != "":
        transcribe_status = "priority"
    if ai_key != "":
        translate_status = "priority"
    if url.startswith(alist_host):
        path = parsed_url.path
        if not (url.endswith(".srt") or is_audio_file_or_video_file(url)):
            return flask.jsonify({"error": "Invalid URL"}), 400
        if path.startswith("/api") or path.endswith(".zh-CN.srt"):
            return flask.jsonify({"error": "Invalid URL"}), 400
        if path.startswith("/d"):
            path = path[2:]
            url = f"{alist_host}{path}"
        unquote_path = unquote(path)

        copy_url = url[: len(alist_host)] + "/d" + url[len(alist_host) :]
        path = unquote_path
        info = alist.get_info(path)
        if info["data"] is not None and "is_dir" in info["data"]:
            if info["data"]["is_dir"]:
                return flask.jsonify({"error": "Invalid URL"}), 400
            tmp = False
            url_without_ext = ""
            work = None
            series_id = None
            ai_translate = True
            work = database.get_work_by_path(path)
            if work is not None:
                if work.block:
                    return flask.jsonify({"error": "Invalid URL"}), 400
                if work.transcribe_only:
                    transcribe_only = True
                if work.series:
                    transcribe_status = "pending"
                    translate_status = "pending"
                ai_translate = work.ai_translate
                series_id = work.id

            if path.endswith(".whisper.srt"):
                url_without_ext = url[: -len(".whisper.srt")]
            if path.startswith(tmp_subtitle_base_path):
                id = url.split("/")[-2]
                tmp = True
            else:
                if url_without_ext == "":
                    url_without_ext = ".".join(url.split(".")[:-1])
                id = get_id(url_without_ext)
                if not ai_translate or not (
                    any(path.endswith(video_ext) for video_ext in video_exts)
                    or path.endswith(".whisper.srt")
                ):
                    tmp = True

            subtitle_path = ""
            if tmp:
                translate_engine = "google" if ai_key == "" else translate_engine
                subtitle_path = f"{tmp_subtitle_base_path}/{id}/{unquote(url_without_ext.split('/')[-1])}"
            else:
                subtitle_path = unquote(urlparse(url_without_ext).path)
            task = database.get_task(id)
            if task is not None:
                check_task(
                    task,
                    translate_engine,
                    transcribe_only,
                    series_id,
                    transcribe_status == "priority",
                    translate_status == "priority",
                )
            else:
                origin_subtitle_path = ""
                if path.endswith(".srt"):
                    transcribe_status = "success"
                    origin_subtitle_path = path
                else:
                    origin_subtitle_path = subtitle_path + ".whisper.srt"
                task = database.create_task(
                    id,
                    copy_url,
                    transcribe_status,
                    translate_status,
                    translate_engine,
                    origin_subtitle_path,
                    subtitle_path + ".zh-CN.srt",
                    transcribe_only,
                    word_timestamps,
                    series_id,
                )
                print(f"Create task {id}, URL: {url}")
        else:
            return flask.jsonify({"error": info["message"]}), 400
    else:
        work = database.get_work_by_path(url)
        if work is None or work.block:
            return flask.jsonify({"error": "Invalid URL"}), 400
        if not work.ai_translate:
            translate_engine = "google" if ai_key == "" else translate_engine
        id = get_id(url)
        task = database.get_task(id)
        if task is not None:
            check_task(
                task,
                translate_engine,
                transcribe_only,
                work.id,
                transcribe_status == "priority",
                translate_status == "priority",
            )
        else:
            origin_subtitle_path = f"{tmp_subtitle_base_path}/{id}/"
            task = database.create_task(
                id,
                url,
                transcribe_status,
                translate_status,
                translate_engine,
                origin_subtitle_path,
                "",
                transcribe_only,
                word_timestamps,
                work.id,
            )
            print(f"Create task {id}, URL: {url}")
    if transcribe_status == "priority":
        kaggle_status = run_task.check_kaggle_status(
            f"{kaggle_username}/translation-gummy", kaggle_username, kaggle_key
        )
        if kaggle_status == "complete":
            last_task = run_task.get_priority_transcribe(kaggle_username, kaggle_key)
            if last_task is not None:
                if str(task.task_id) == str(last_task.task_id):
                    return get_json(last_task)
        if kaggle_status != "running" and task.transcribe_status == "priority":
            if not run_task.run_transcribe(copy_url, kaggle_username, kaggle_key):
                task.transcribe_status = "failed"
                task.message = "Kaggle API error"
                task.save()
    else:
        run_task.run_transcribe()
    return get_json(task)


def get_json(task):
    transcribe_no = 0
    translate_no = 0
    if task.transcribe_status == "pending":
        transcribe_no = database.get_pending_transcribe_no(task.task_id)
    elif task.transcribe_status == "success":
        translate_no = database.get_pending_translate_no(task.task_id)
    return flask.jsonify(
        {
            "id": task.task_id,
            "url": task.url,
            "redirect": task.redirect,
            "transcribe_status": task.transcribe_status,
            "translate_status": task.translate_status,
            "translate_engine": task.translate_engine,
            "origin_subtitle_path": task.origin_subtitle_path,
            "translated_subtitle_path": task.translated_subtitle_path,
            "transcribe_only": task.transcribe_only,
            "create_time": task.create_time,
            "update_time": task.update_time,
            "video_url": task.video_url,
            "transcribe_no": transcribe_no,
            "translate_no": translate_no,
            "message": task.message,
        }
    )


@cross_origin()
@app.route("/api/task", methods=["GET"])
def get_task():
    task_id = flask.request.args.get("id", "")
    if task_id == "":
        return flask.jsonify({"error": "Invalid ID"}), 400
    task = database.get_task(task_id)
    if task is None:
        return flask.jsonify({"error": "Not found"}), 404
    return get_json(task)


def check_task(
    task: database.TaskModel,
    translate_engine,
    transcribe_only,
    series_id=None,
    transcribe_priority=False,
    translate_priority=False,
):
    if task.redirect != "":
        return
    update_task = False
    if task.translate_status == "processing":
        return
    if not transcribe_only:
        if task.transcribe_only:
            task.transcribe_only = False
            task.translate_engine = translate_engine
            update_task = True
        elif task.translate_status == "failed" or (
            task.translate_engine != "ai" and translate_engine == "ai"
        ):
            task.translate_status = "priority" if translate_priority else "pending"
            task.translate_engine = translate_engine
            update_task = True
    if (
        task.transcribe_status == "failed"
        or (
            task.transcribe_status == "priority"
            and task.update_time < datetime.datetime.now() - datetime.timedelta(hours=1)
        )
        or task.transcribe_status == "pending"
    ):
        task.transcribe_only = transcribe_only
        task.transcribe_status = "priority" if transcribe_priority else "pending"
        task.translate_status = "priority" if translate_priority else "pending"
        update_task = True
    if str(task.series_id) != str(series_id) and task.transcribe_status == "pending":
        task.series_id = series_id
        update_task = True
    if update_task:
        task.message = ""
        task.update_time = datetime.datetime.now()
        print(f"Update task {task.task_id}, URL: {task.url}")
        task.save()


def get_id(url):
    return hashlib.md5(url.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9000, debug=False)
