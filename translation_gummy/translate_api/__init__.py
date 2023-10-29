import srt
import subprocess
import os
from pathlib import Path


def google_translate(subtitle, target_language, source_language="auto"):
    global google_usage_limit_reached
    subs = []
    with open(subtitle, "r") as file:
        subs = list(srt.parse(file.read()))
    text_to_translate = "\n".join([" ".join(sub.content.split("\n")) for sub in subs])
    try:
        result = subprocess.run(
            [
                "node",
                os.path.join(
                    Path(__file__).with_name("google_translate"), "google_translate.mjs"
                ),
                text_to_translate,
                target_language,
                source_language,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode == 0 and result.stdout != "":
            translated_text = result.stdout.strip().split("\n")
            for i, sub in enumerate(subs):
                sub.content = translated_text[i]
            with open(
                f"{subtitle[: -len('.whisper.srt')]}.{target_language}.srt", "w"
            ) as file:
                file.write(srt.compose(subs))
        else:
            raise Exception(result.stderr)
    except Exception as e:
        google_usage_limit_reached = True
        print(e)
        return []


def gpt_translate(file_path, target_language, api_key, movie_name, description):
    output_file = f'{file_path[: -len(".whisper.srt")]}.{"zh-CN" if target_language == "Simplified Chinese" else target_language}.srt'
    cmd = (
        f'python3 "{os.path.join(Path(__file__).with_name("gpt-subtrans"), "gpt-subtrans.py")}" '
        + f'"{file_path}" --ratelimit 5 --apikey {api_key} --target_language "{target_language}" '
        + f'--output "{output_file}" --instructionfile "{Path(__file__).with_name("instructions.txt")}" '
        + (
            f'-m "{movie_name}" '
            if (movie_name is not None and movie_name != "")
            else ""
        )
        + (
            f'--description "{description}" '
            if (description is not None and description != "")
            else ""
        )
    )
    print(cmd)
    result = subprocess.run(
        cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    if not os.path.exists(output_file):
        raise Exception("API key is invalid or usage limit reached")
