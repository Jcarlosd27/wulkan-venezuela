from __future__ import annotations

import mimetypes
import time
from pathlib import Path
from urllib.parse import urljoin

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif", "pdf"}
ALLOWED_FOLDERS = {"products", "categories", "announcements", "library"}


def file_extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def validate_upload(file_storage: FileStorage) -> str:
    filename = secure_filename(file_storage.filename or "")
    extension = file_extension(filename)
    if not filename or extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise ValueError(f"Archivo no permitido. Formatos validos: {allowed}.")
    return filename


def object_key(folder: str, filename: str, prefix: str = "") -> str:
    safe_folder = folder if folder in ALLOWED_FOLDERS else "library"
    safe_prefix = prefix.strip("/")
    name = f"{int(time.time())}-{filename}"
    parts = [part for part in [safe_prefix, safe_folder, name] if part]
    return "/".join(parts)


def public_url(base_url: str, key: str) -> str:
    if not base_url:
        return ""
    return urljoin(base_url.rstrip("/") + "/", key)


def save_local(file_storage: FileStorage, folder: str, upload_folder: Path, filename: str) -> str:
    safe_folder = folder if folder in ALLOWED_FOLDERS else "library"
    upload_root = upload_folder / safe_folder
    upload_root.mkdir(parents=True, exist_ok=True)
    key = object_key(safe_folder, filename)
    target = upload_folder / key
    target.parent.mkdir(parents=True, exist_ok=True)
    file_storage.save(target)
    return f"/static/uploads/{key}"


def save_s3(
    file_storage: FileStorage,
    folder: str,
    filename: str,
    bucket: str,
    region: str,
    endpoint_url: str,
    prefix: str,
    public_base_url: str,
    acl: str = "",
) -> str:
    if not bucket:
        raise ValueError("WULKAN_S3_BUCKET es obligatorio cuando WULKAN_STORAGE_BACKEND=s3.")

    import boto3

    key = object_key(folder, filename, prefix)
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    client_kwargs = {"region_name": region}
    if endpoint_url:
        client_kwargs["endpoint_url"] = endpoint_url
    client = boto3.client("s3", **client_kwargs)

    extra_args = {"ContentType": content_type}
    if acl:
        extra_args["ACL"] = acl
    file_storage.stream.seek(0)
    client.upload_fileobj(file_storage.stream, bucket, key, ExtraArgs=extra_args)

    if public_base_url:
        return public_url(public_base_url, key)
    if endpoint_url:
        return public_url(f"{endpoint_url.rstrip('/')}/{bucket}", key)
    return f"https://{bucket}.s3.{region}.amazonaws.com/{key}"


def save_uploaded_file(
    file_storage: FileStorage | None,
    folder: str,
    upload_folder: Path,
    storage_backend: str,
    public_base_url: str,
    s3_bucket: str,
    s3_region: str,
    s3_endpoint_url: str,
    s3_prefix: str,
    s3_acl: str = "",
) -> str:
    if not file_storage or not file_storage.filename:
        return ""

    filename = validate_upload(file_storage)
    backend = storage_backend.strip().lower()
    if backend == "s3":
        return save_s3(
            file_storage=file_storage,
            folder=folder,
            filename=filename,
            bucket=s3_bucket,
            region=s3_region,
            endpoint_url=s3_endpoint_url,
            prefix=s3_prefix,
            public_base_url=public_base_url,
            acl=s3_acl,
        )
    if backend != "local":
        raise ValueError(f"Storage backend no soportado: {storage_backend}.")
    return save_local(file_storage, folder, upload_folder, filename)
