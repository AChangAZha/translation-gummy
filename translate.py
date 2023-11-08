import shutil
import traceback
import requests
import os
from translation_gummy import translate_api
from translation_gummy import database
from translation_gummy import onedrive
from translation_gummy.utils.subtitle_tools import (
    split,
    merge_subtitle,
    replace_word,
    replace_subtitles,
    get_seconds,
)
import srt
import datetime


origin_subtitle_base_path = os.environ.get("ORIGIN_SUBTITLE_BASE_PATH")
tmp_subtitle_base_path = os.environ.get("TMP_SUBTITLE_BASE_PATH")
api_key = os.environ.get("GPT_API_KEY", "")
task_id = os.environ.get("TASK_ID", "")
target_language = "zh-CN"


def get_backup_folder(task):
    if task.origin_subtitle_path.startswith(tmp_subtitle_base_path):
        upload_folder = os.path.join(tmp_subtitle_base_path, task.task_id)
    else:
        upload_folder = f"{origin_subtitle_base_path}{'.'.join(task.translated_subtitle_path.split('.')[:-2])}"
    return upload_folder


def split_subtitle(series, srt_path, detailed_chapters):
    if series is None:
        return []
    split_translates = series.split_translates
    split_parts = split(series, split_translates, detailed_chapters)
    subs = []
    srt_file = list(srt.parse(open(srt_path).read()))
    os.mkdir(f"subs/{task.task_id}/split")
    new_split_parts = []
    zero_time = "00:00:00.000"
    for i, part in enumerate(split_parts):
        start = datetime.timedelta(seconds=get_seconds(part[0]))
        end = datetime.timedelta(seconds=get_seconds(part[1]))
        for sub in srt_file:
            if start <= sub.start <= end or start <= sub.end <= end:
                subs.append(sub)
        with open(f"subs/{task.task_id}/split/{i}.whisper.srt", "w") as f:
            f.write(srt.compose(subs))
        new_split_parts.append((zero_time, zero_time))
        subs = []
    return new_split_parts


def translate_subtitle(
    dir,
    translate_engine,
    split_translates,
    split_parts,
    translate_prompt_name,
    translate_prompt_description,
    target_language="zh-CN",
    api_key=None,
):
    if split_translates is not None:
        split_translates = list(split_translates)
    else:
        split_translates = []
    if len(split_translates) != 0 and len(split_translates) == len(split_parts):
        translate_prompt_names = [
            part.translate_prompt_name for part in split_translates
        ]
        translate_prompt_descriptions = [
            part.translate_prompt_description for part in split_translates
        ]
    else:
        translate_prompt_names = [translate_prompt_name]
        translate_prompt_descriptions = [translate_prompt_description]
    for i, f in enumerate(os.listdir(dir)):
        if translate_engine == "google":
            translate_api.google_translate(
                f"{dir}/{f}",
                target_language,
            )
        elif translate_engine == "ai":
            translate_api.gpt_translate(
                f"{dir}/{f}",
                "Simplified Chinese" if target_language == "zh-CN" else target_language,
                api_key,
                translate_prompt_names[i],
                translate_prompt_descriptions[i],
            )


task = None
try:
    if task_id != "":
        task = database.get_task(task_id)
    else:
        task = database.get_top_translate_task()
    if task is None:
        exit(0)
    task.translate_status = "processing"
    task.save()
    origin_subtitle_path = task.origin_subtitle_path
    translated_subtitle_path = task.translated_subtitle_path
    origin_subtitle_name = origin_subtitle_path.split("/")[-1]
    origin_subtitle_name_without_ext = origin_subtitle_name[: -len(".whisper.srt")]
    backup_folder = get_backup_folder(task)
    if os.path.exists(f"subs/{task.task_id}"):
        shutil.rmtree(f"subs/{task.task_id}")
    os.makedirs(f"subs/{task.task_id}/subtitles")
    with open(f"subs/{task.task_id}/subtitles/{origin_subtitle_name}", "wb") as f:
        f.write(
            requests.get(
                onedrive.get_item(origin_subtitle_path)["@microsoft.graph.downloadUrl"]
            ).content
        )
    series = database.get_work_by_id(task.series_id)
    detailed_chapters = (
        requests.get(
            onedrive.get_item(f"{backup_folder}/chapters.json")[
                "@microsoft.graph.downloadUrl"
            ]
        )
        .json()
        .get("chapters", [])
    )
    split_parts = split_subtitle(
        series,
        f"subs/{task.task_id}/subtitles/{origin_subtitle_name}",
        detailed_chapters,
    )
    dir = f"subs/{task.task_id}/subtitles"
    if len(split_parts) != 0:
        dir = f"subs/{task.task_id}/split"
    translate_prompt_name = None
    translate_prompt_description = None
    split_translates = None
    words = []
    if series is not None:
        translate_prompt_name = series.translate_prompt_name
        translate_prompt_description = series.translate_prompt_description
        split_translates = series.split_translates
        words = database.sort_replace_words(
            series.replace_translations,
            type="translate",
        )
        words = list(words) if words is not None else []
    translate_subtitle(
        dir,
        task.translate_engine,
        split_translates,
        split_parts,
        translate_prompt_name,
        translate_prompt_description,
        api_key=api_key,
    )
    replace_word(dir, words, None)
    merge_subtitle(dir, split_parts, f".{target_language}")
    dir = f"subs/{task.task_id}"
    if os.path.exists(f"{dir}/split/merged.srt"):
        os.rename(
            f"{dir}/split/merged.srt",
            f"{dir}/subtitles/{origin_subtitle_name_without_ext}.{target_language}.srt",
        )
    replace_subtitles(
        f"{dir}/subtitles",
        origin_subtitle_name_without_ext,
        series,
        detailed_chapters,
        target_language,
    )
    onedrive.upload_translate(
        task,
        backup_folder,
        target_language,
        origin_subtitle_name_without_ext,
    )
    task.translate_status = "success"
    task.save()
except Exception as e:
    print(traceback.format_exc())
    task.translate_status = "failed"
    task.message = str(e)
    task.save()
