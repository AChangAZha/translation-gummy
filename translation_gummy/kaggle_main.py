url = ""
import subprocess
import os
from kaggle_secrets import UserSecretsClient


def init():
    os.environ["URL"] = url
    if url == "":
        os.environ["DB_NAME"] = UserSecretsClient().get_secret("DB_NAME")
        os.environ["DB_USER"] = UserSecretsClient().get_secret("DB_USER")
        os.environ["DB_PASSWORD"] = UserSecretsClient().get_secret("DB_PASSWORD")
        os.environ["DB_HOST"] = UserSecretsClient().get_secret("DB_HOST")
        os.environ["DB_PORT"] = UserSecretsClient().get_secret("DB_PORT")
        os.environ["ORIGIN_SUBTITLE_BASE_PATH"] = UserSecretsClient().get_secret(
            "ORIGIN_SUBTITLE_BASE_PATH"
        )
        os.environ["TMP_SUBTITLE_BASE_PATH"] = UserSecretsClient().get_secret(
            "TMP_SUBTITLE_BASE_PATH"
        )


def run_cmd(cmd):
    subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=os.environ.copy(),
        text=True,
    )


init()
run_cmd("git clone https://github.com/AChangAZha/translation-gummy.git")
run_cmd("cd translation-gummy/ && pip install -r requirements.txt")
run_cmd("python translation-gummy/transcribe.py")
run_cmd("rm -rf translation-gummy")
