import requests
import os
from urllib.parse import quote
from . import database
from .utils import is_audio_file_or_video_file

BASE_URL = "https://graph.microsoft.com/v1.0/me/drive/"


def get_access_token():
    return database.get_onedrive_config().access_token


def refresh_token(client_id, client_secret, redirect_uri, refresh_token):
    response = requests.post(
        "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )
    return response.json()


def get_item(path):
    path = quote(path)
    access_token = get_access_token()
    if path != "":
        if path.startswith("/"):
            path = path[1:]
        path = f":/{path}"
    response = requests.get(
        BASE_URL + f"root{path}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    return response.json()


def create_upload_session(item_id, file_name):
    file_name = quote(file_name)
    access_token = get_access_token()
    response = requests.post(
        BASE_URL + f"items/{item_id}:/{file_name}:/createUploadSession",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
    )
    return response.json()


def upload_file(upload_url, file_path):
    jsons = []
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(10 * 1024 * 1024)
            if not chunk:
                break
            response = requests.put(
                upload_url,
                data=chunk,
                headers={
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {f.tell() - len(chunk)}-{f.tell() - 1}/{os.path.getsize(file_path)}",
                },
            )
            jsons.append(response.json())
    return jsons


def create_folder(folder_name):
    folder_name = quote(folder_name)
    access_token = get_access_token()
    if folder_name.startswith("/"):
        folder_name = folder_name[1:]
    response = requests.patch(
        BASE_URL + f"root:/{folder_name}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={
            "folder": {},
            "@microsoft.graph.conflictBehavior": "fail",
        },
    )
    return response.json()


def move_item(item_id, folder_id):
    access_token = get_access_token()
    response = requests.patch(
        BASE_URL + f"items/{item_id}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={
            "parentReference": {"id": folder_id},
        },
    )
    return response.json()


onedrive_config = database.get_onedrive_config()
if get_item("").get("error", None) is not None:
    json = refresh_token(
        onedrive_config.client_id,
        onedrive_config.client_secret,
        onedrive_config.redirect_uri,
        onedrive_config.refresh_token,
    )
    onedrive_config.access_token = json["access_token"]
    onedrive_config.refresh_token = json["refresh_token"]
    onedrive_config.save()


def upload_transcribe(
    task, filename, tmp_subtitle_base_path, origin_subtitle_base_path
):
    upload_folder = None
    if (
        task.origin_subtitle_path.startswith(tmp_subtitle_base_path)
        or task.origin_subtitle_path == ""
    ):
        upload_folder = os.path.join(tmp_subtitle_base_path, task.task_id)
        upload_folder_id = create_folder(upload_folder).get(
            "id", get_item(upload_folder)["id"]
        )
        for file in os.listdir("video"):
            if is_audio_file_or_video_file(file):
                task.video_url = f"{tmp_subtitle_base_path}/{task.task_id}/{file}"
            elif file.endswith(".whisper.srt"):
                task.origin_subtitle_path = (
                    f"{tmp_subtitle_base_path}/{task.task_id}/{file}"
                )
            else:
                continue
            upload_url = create_upload_session(upload_folder_id, file).get(
                "uploadUrl", ""
            )
            if upload_url != "":
                upload_file(
                    upload_url,
                    f"video/{file}",
                )
            task.save()
    else:
        video_folder = "/".join(task.origin_subtitle_path.split("/")[:-1])
        upload_folder = os.path.join(
            origin_subtitle_base_path, video_folder[1:], filename
        )
        upload_folder_id = create_folder(upload_folder).get(
            "id", get_item(upload_folder)["id"]
        )
        video_subtitle_upload_folder_id = get_item(video_folder)["id"]
        upload_url = create_upload_session(
            video_subtitle_upload_folder_id, f"{filename}.whisper.srt"
        ).get("uploadUrl", "")
        if upload_url != "":
            upload_file(
                upload_url,
                f"video/{filename}.whisper.srt",
            )
    upload_url = create_upload_session(
        upload_folder_id,
        f"chapters.json",
    ).get("uploadUrl", "")
    if upload_url != "":
        upload_file(
            upload_url,
            f"chapters.json",
        )
    if os.path.exists(f"video/{filename}.origin-whisper.srt"):
        subtitles_upload_folder = os.path.join(upload_folder, "subtitles")
        upload_folder_id = create_folder(subtitles_upload_folder).get(
            "id", get_item(subtitles_upload_folder)["id"]
        )
        upload_url = create_upload_session(
            upload_folder_id, f"{filename}.origin-whisper.srt"
        ).get("uploadUrl", "")
        if upload_url != "":
            upload_file(
                upload_url,
                f"video/{filename}.origin-whisper.srt",
            )
    if os.path.exists("split") and os.listdir("split"):
        split_upload_folder = os.path.join(upload_folder, "split")
        upload_folder_id = create_folder(split_upload_folder).get(
            "id", get_item(split_upload_folder)["id"]
        )
        for file in os.listdir("split"):
            upload_url = create_upload_session(upload_folder_id, file).get(
                "uploadUrl", ""
            )
            if upload_url != "":
                upload_file(
                    upload_url,
                    f"split/{file}",
                )


def upload_translate(
    task,
    backup_base_folder,
    target_language,
    origin_subtitle_name_without_ext,
):
    update_time = task.update_time.strftime("%Y%m%d%H%M%S")
    backup_folder = os.path.join(backup_base_folder, "subtitles", update_time)
    backup_folder_id = create_folder(backup_folder).get(
        "id", get_item(backup_folder)["id"]
    )
    origin_subtitle_id = get_item(task.origin_subtitle_path).get("id", None)
    if origin_subtitle_id is not None:
        move_item(
            origin_subtitle_id,
            backup_folder_id,
        )
    task.origin_subtitle_path = os.path.join(
        backup_folder,
        origin_subtitle_name_without_ext + ".whisper.srt",
    )
    if task.translated_subtitle_path is None or task.translated_subtitle_path == "":
        task.translated_subtitle_path = os.path.join(
            backup_base_folder,
            origin_subtitle_name_without_ext + "." + target_language + ".srt",
        )
    path = task.translated_subtitle_path.split("/")
    translated_upload_folder = "/".join(path[:-1])
    folder_id = create_folder(translated_upload_folder).get(
        "id", get_item(translated_upload_folder)["id"]
    )
    translated_subtitle_id = get_item(task.translated_subtitle_path).get("id", None)
    if translated_subtitle_id is not None:
        move_item(
            translated_subtitle_id,
            backup_folder_id,
        )
    upload_url = create_upload_session(
        folder_id,
        path[-1],
    ).get("uploadUrl", "")
    if upload_url != "":
        upload_file(
            upload_url,
            f"subs/{task.task_id}/subtitles/{path[-1]}",
        )
    origin_file_name = (
        f"{origin_subtitle_name_without_ext}.origin-{target_language}.srt"
    )
    origin_file_name_with_path = f"subs/{task.task_id}/subtitles/{origin_file_name}"
    if os.path.exists(origin_file_name_with_path):
        upload_url = create_upload_session(backup_folder_id, origin_file_name).get(
            "uploadUrl", ""
        )
        if upload_url != "":
            upload_file(
                upload_url,
                origin_file_name_with_path,
            )
    task.save()
