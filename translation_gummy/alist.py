import os
import requests
from requests_toolbelt import MultipartEncoder
from urllib.parse import quote_plus

username = os.environ.get("ALIST_USERNAME")
password = os.environ.get("ALIST_PASSWORD")
host = os.environ.get("ALIST_HOST")


def get_token(username=username, password=password):
    url = f"{host}/api/auth/login"
    response = requests.post(
        url,
        json={"username": username, "password": password},
        headers={"Content-Type": "application/json"},
    )
    return response.json()["data"]["token"]


def upload_file(origin_file_path, upload_file_path, token=""):
    with open(origin_file_path, "rb") as file:
        url = f"{host}/api/fs/form"
        data = MultipartEncoder(
            fields={"file": (os.path.basename(origin_file_path), file)}
        )
        response = requests.put(
            url,
            headers={
                "Content-Type": data.content_type,
                "Authorization": token,
                "File-Path": quote_plus(upload_file_path),
            },
            data=data,
        )
        print(response.json())


def get_info(file_path, token=""):
    url = f"{host}/api/fs/get"
    response = requests.post(
        url,
        headers={"Authorization": token},
        json={"path": file_path},
    )
    return response.json()


def mkdir(file_path, token=""):
    url = f"{host}/api/fs/mkdir"
    response = requests.post(
        url,
        headers={"Authorization": token},
        json={"path": file_path},
    )
    return response.json()
