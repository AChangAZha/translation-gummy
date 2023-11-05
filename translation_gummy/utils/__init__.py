import mimetypes


def is_audio_file_or_video_file(file_path):
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type is not None and (
        mime_type.startswith("audio/") or mime_type.startswith("video/")
    ):
        return True
    return False


def check_white_keyword(keywords, text):
    for keyword in keywords:
        if keyword.block:
            continue
        else:
            if keyword.keyword in text:
                return True
    return False
