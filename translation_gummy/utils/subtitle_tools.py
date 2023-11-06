import srt
import datetime
import requests
import os


def format_time(time) -> str:
    time = int(float(time) * 1000)
    ms = time % 1000
    time //= 1000
    s = time % 60
    time //= 60
    m = time % 60
    time //= 60
    h = time
    return "{:02d}:{:02d}:{:02d}.{:03d}".format(h, m, s, ms)


def replace_word(dir, replace_words, log):
    for replace_word in replace_words:
        for file in os.listdir(dir):
            if file.endswith(".srt"):
                with open(f"{dir}/{file}", "r+") as f:
                    text = f.read()
                text = text.replace(replace_word.word, replace_word.replace_word)
                with open(f"{dir}/{file}", "w") as f:
                    f.write(text)
                if log is not None:
                    log.write(
                        f"{replace_word.word} -> {replace_word.replace_word} in {file}\n"
                    )


def get_seconds(time):
    time = time.split(":")
    seconds = int(time[0]) * 3600 + int(time[1]) * 60 + float(time[2])
    return seconds


def merge_subtitle(dir, split_parts, file_extension):
    if split_parts is None or len(split_parts) == 0:
        return
    subs = []
    for i, part in enumerate(split_parts):
        srt_file = srt.parse(open(f"{dir}/{i}{file_extension}.srt").read())
        for sub in srt_file:
            delta = datetime.timedelta(seconds=get_seconds(part[0]))
            sub.start = sub.start + delta
            sub.end = sub.end + delta
            subs.append(sub)
    with open(f"{dir}/merged.srt", "w") as f:
        f.write(srt.compose(subs))


def replace_subtitles(
    dir,
    origin_file_name_without_extension,
    series,
    detailed_chapters,
    target_language="whisper",
):
    if series is None:
        return
    replace_subtitles = (
        series.replace_origin_subtitles
        if target_language == "whisper"
        else series.replace_translation_subtitles
    )
    if replace_subtitles is None:
        return
    replace_subtitles = list(replace_subtitles)
    if len(replace_subtitles) == 0:
        return
    subs = []
    times = []
    chapters = list(series.chapters) if series.chapters is not None else []
    for replace_subtitle in replace_subtitles:
        srt_file = srt.parse(requests.get(replace_subtitle.url).text)
        srt_file = list(srt_file)
        start_time = None
        end_time = None
        for i, sub in enumerate(srt_file):
            if replace_subtitle.start_no == 0:
                delta = datetime.timedelta(
                    seconds=get_seconds(replace_subtitle.start_time)
                )
            elif len(detailed_chapters) != len(chapters):
                return
            else:
                delta = datetime.timedelta(
                    seconds=get_seconds(
                        format_time(
                            detailed_chapters[replace_subtitle.start_no - 1][
                                "start_time"
                            ]
                        )
                    )
                )
            sub.start += delta
            sub.end += delta
            if i == 0:
                start_time = sub.start
            elif i == len(srt_file) - 1:
                end_time = sub.end
            subs.append(sub)
        times.append((start_time, end_time))
    input_srt_file = None
    with open(
        f"{dir}/{origin_file_name_without_extension}.origin-{target_language}.srt", "w"
    ) as f:
        with open(
            f"{dir}/{origin_file_name_without_extension}.{target_language}.srt", "r"
        ) as o:
            text = o.read()
            f.write(text)
            input_srt_file = srt.parse(text)
    for sub in input_srt_file:
        if any(
            (start_time <= sub.start <= end_time or start_time <= sub.end <= end_time)
            for start_time, end_time in times
        ):
            continue
        subs.append(sub)
    with open(
        f"{dir}/{origin_file_name_without_extension}.{target_language}.srt", "w"
    ) as f:
        f.write(srt.compose(subs))


def split(series, split_info, detailed_chapters):
    if split_info is None:
        return []
    split_info = list(split_info)
    if len(split_info) == 0:
        return []
    chapters = list(series.chapters) if series.chapters is not None else []
    split_parts = []
    for part in split_info:
        if part.start_no == 0:
            start_time = part.start_time
            end_time = part.end_time
        elif len(detailed_chapters) != len(chapters):
            return []
        else:
            start_time = format_time(detailed_chapters[part.start_no - 1]["start_time"])
            end_time = format_time(detailed_chapters[part.end_no - 1]["end_time"])
        split_parts.append((start_time, end_time))
    return split_parts
