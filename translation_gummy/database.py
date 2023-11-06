from peewee import *
import os
import datetime


db = MySQLDatabase(
    os.environ["DB_NAME"],
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    host=os.environ["DB_HOST"],
    port=int(os.environ["DB_PORT"]),
    charset="utf8mb4",
)
db.connect()


class BaseModel(Model):
    class Meta:
        database = db


class OneDriveConfigModel(BaseModel):
    client_id = CharField()
    client_secret = CharField()
    redirect_uri = CharField()
    refresh_token = CharField(max_length=4096)
    access_token = CharField(max_length=4096)


class WorkModel(BaseModel):
    path = CharField(max_length=1024)
    sort_name = CharField(unique=True, null=True)
    block = BooleanField(default=False)
    transcribe_only = BooleanField(default=False)
    ai_translate = BooleanField(default=False)
    transcribe_initial_prompt = TextField()
    translate_prompt_name = CharField()
    translate_prompt_description = CharField()
    metadata = TextField()
    series = BooleanField(default=True)
    check_keyword = BooleanField(default=False)


class KeywordModel(BaseModel):
    keyword = CharField()
    block = BooleanField(default=False)


class TaskModel(BaseModel):
    task_id = CharField(primary_key=True)
    redirect = CharField()
    url = CharField(max_length=1024)
    file_md5 = CharField()
    transcribe_status = CharField(default="pending")
    translate_status = CharField(default="pending")
    translate_engine = CharField()
    origin_subtitle_path = CharField(max_length=1024)
    translated_subtitle_path = CharField(max_length=1024)
    transcribe_only = BooleanField()
    create_time = DateTimeField(default=datetime.datetime.now)
    update_time = DateTimeField(default=datetime.datetime.now)
    series_id = ForeignKeyField(WorkModel, backref="tasks", null=True)
    video_url = CharField(max_length=1024)
    message = TextField()
    word_timestamps = BooleanField(default=True)


class ReplaceOriginSubtitleModel(BaseModel):
    work_id = ForeignKeyField(WorkModel, backref="replace_origin_subtitles")
    url = CharField(max_length=1024)
    start_time = CharField(default="00:00:00.000", null=True)
    start_no = IntegerField(default=0)


class ReplaceTranslationSubtitleModel(BaseModel):
    work_id = ForeignKeyField(WorkModel, backref="replace_translation_subtitles")
    url = CharField(max_length=1024)
    start_time = CharField(default="00:00:00.000", null=True)
    start_no = IntegerField(default=0)


class ChapterModel(BaseModel):
    work_id = ForeignKeyField(WorkModel, backref="chapters")
    chapter_no = IntegerField()
    chapter_name = CharField()
    chapter_start_time = CharField()
    chapter_end_time = CharField()


class SplitTranscribeModel(BaseModel):
    work_id = ForeignKeyField(WorkModel, backref="split_transcribes")
    start_no = IntegerField()
    end_no = IntegerField()
    start_time = CharField()
    end_time = CharField()
    transcribe_initial_prompt = CharField()


class SplitTranslateModel(BaseModel):
    work_id = ForeignKeyField(WorkModel, backref="split_translates")
    start_no = IntegerField()
    end_no = IntegerField()
    start_time = CharField()
    end_time = CharField()
    translate_prompt_name = CharField()
    translate_prompt_description = CharField()


class ReplaceWordModel(BaseModel):
    work_id = ForeignKeyField(WorkModel, backref="replace_words")
    word = CharField()
    replace_word = CharField()


class ReplaceTranslationModel(BaseModel):
    work_id = ForeignKeyField(WorkModel, backref="replace_translations")
    word = CharField()
    replace_word = CharField()


def get_white_keywords() -> list:
    try:
        query = KeywordModel.select().where(KeywordModel.block == False)
        return list(query)
    except DoesNotExist:
        return []


def get_task(task_id) -> TaskModel:
    try:
        if task_id == "":
            return None
        task = TaskModel.get(TaskModel.task_id == task_id)
        return task
    except DoesNotExist:
        return None


def create_task(
    task_id,
    url,
    transcribe_status,
    translate_status,
    translate_engine,
    origin_subtitle_path,
    translated_subtitle_path,
    transcribe_only,
    word_timestamps,
    series_id=None,
):
    return TaskModel.create(
        task_id=task_id,
        url=url,
        transcribe_status=transcribe_status,
        translate_status=translate_status,
        translate_engine=translate_engine,
        origin_subtitle_path=origin_subtitle_path,
        translated_subtitle_path=translated_subtitle_path,
        transcribe_only=transcribe_only,
        word_timestamps=word_timestamps,
        series_id=series_id,
    )


def get_top_transcribe_task() -> TaskModel:
    return (
        TaskModel.select()
        .where((TaskModel.transcribe_status == "pending") & (TaskModel.redirect == ""))
        .order_by((TaskModel.translate_engine == "ai").desc(), TaskModel.update_time)
        .first()
    )


def get_pending_transcribe_no(task_id) -> int:
    query = (
        TaskModel.select()
        .where(
            (
                (TaskModel.transcribe_status == "pending")
                | (TaskModel.transcribe_status == "processing")
            )
            & (TaskModel.redirect == "")
        )
        .order_by((TaskModel.translate_engine == "ai").desc(), TaskModel.update_time)
    )
    count = 0
    for task in list(query):
        if task.task_id == task_id:
            return count
        count += 1
    return 0


def get_top_translate_task() -> TaskModel:
    return (
        TaskModel.select()
        .where(
            (TaskModel.translate_status == "pending")
            & (TaskModel.redirect == "")
            & (TaskModel.transcribe_status == "success")
            & (TaskModel.transcribe_only == False)
        )
        .order_by((TaskModel.translate_engine == "ai").desc(), TaskModel.update_time)
        .first()
    )


def get_pending_translate_no(task_id) -> int:
    query = (
        TaskModel.select()
        .where(
            (
                (TaskModel.translate_status == "pending")
                | (TaskModel.translate_status == "processing")
            )
            & (TaskModel.redirect == "")
            & (TaskModel.transcribe_status == "success")
            & (TaskModel.transcribe_only == False)
        )
        .order_by((TaskModel.translate_engine == "ai").desc(), TaskModel.update_time)
    )
    count = 0
    for task in list(query):
        if task.task_id == task_id:
            return count
        count += 1
    return 0


def get_task_by_file_md5(file_md5) -> TaskModel:
    try:
        if file_md5 == "":
            return None
        task = TaskModel.get(TaskModel.file_md5 == file_md5)
        return task
    except DoesNotExist:
        return None


def get_work_by_path(task_path) -> WorkModel:
    try:
        return (
            WorkModel.select()
            .order_by(fn.REGEXP_INSTR(task_path, WorkModel.path).desc())
            .first()
        )
    except DoesNotExist:
        return None


def get_task_by_url(url) -> TaskModel:
    try:
        if url == "":
            return None
        task = TaskModel.get(TaskModel.url == url)
        return task
    except DoesNotExist:
        return None


def get_work_by_id(work_id) -> WorkModel:
    try:
        if work_id == "":
            return None
        work = WorkModel.get(WorkModel.id == work_id)
        return work
    except DoesNotExist:
        return None


def sort_replace_words(replace_words, type="origin"):
    try:
        if replace_words is None:
            return None
        if type == "origin":
            return replace_words.order_by(fn.CHAR_LENGTH(ReplaceWordModel.word).desc())
        else:
            return replace_words.order_by(
                fn.CHAR_LENGTH(ReplaceTranslationModel.word).desc()
            )
    except DoesNotExist:
        return None


def get_onedrive_config() -> OneDriveConfigModel:
    try:
        config = OneDriveConfigModel.get()
        return config
    except DoesNotExist:
        return None


db.create_tables(
    [
        OneDriveConfigModel,
        WorkModel,
        TaskModel,
        ReplaceOriginSubtitleModel,
        ReplaceTranslationSubtitleModel,
        ChapterModel,
        SplitTranscribeModel,
        SplitTranslateModel,
        ReplaceWordModel,
        ReplaceTranslationModel,
        KeywordModel,
    ],
    safe=True,
)
