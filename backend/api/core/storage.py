from __future__ import annotations

import mimetypes
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif", "pdf"}
ALLOWED_FOLDERS = {"products", "categories", "announcements", "library", "documents"}
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
MAGIC_HEADERS = {
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "gif": (b"GIF87a", b"GIF89a"),
    "pdf": (b"%PDF-",),
}


def file_extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def stream_size(file_storage: FileStorage) -> int:
    stream = file_storage.stream
    position = stream.tell()
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(position)
    return size


def validate_magic_header(file_storage: FileStorage, extension: str) -> None:
    stream = file_storage.stream
    position = stream.tell()
    stream.seek(0)
    header = stream.read(16)
    stream.seek(position)

    if extension == "webp":
        if not (header.startswith(b"RIFF") and header[8:12] == b"WEBP"):
            raise ValueError("El archivo WEBP no tiene una firma valida.")
        return

    allowed_headers = MAGIC_HEADERS.get(extension)
    if allowed_headers and not any(header.startswith(signature) for signature in allowed_headers):
        raise ValueError(f"El archivo .{extension} no tiene una firma valida.")


def validate_declared_mime(file_storage: FileStorage, extension: str) -> None:
    content_type = (file_storage.mimetype or "").lower()
    if not content_type or content_type == "application/octet-stream":
        return
    if extension in IMAGE_EXTENSIONS and not content_type.startswith("image/"):
        raise ValueError("El tipo MIME no coincide con una imagen valida.")
    if extension == "pdf" and content_type != "application/pdf":
        raise ValueError("El tipo MIME no coincide con un PDF valido.")


def validate_upload(file_storage: FileStorage, max_bytes: int = 0) -> str:
    filename = secure_filename(file_storage.filename or "")
    extension = file_extension(filename)
    if not filename or extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise ValueError(f"Archivo no permitido. Formatos validos: {allowed}.")
    if max_bytes and stream_size(file_storage) > max_bytes:
        raise ValueError(f"Archivo demasiado grande. Maximo permitido: {max_bytes // (1024 * 1024)} MB.")
    validate_declared_mime(file_storage, extension)
    validate_magic_header(file_storage, extension)
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


def key_from_public_url(
    url: str,
    *,
    public_base_url: str = "",
    bucket: str = "",
    endpoint_url: str = "",
    local_upload_prefix: str = "/static/uploads/",
) -> str:
    value = str(url or "").strip()
    if not value:
        return ""
    if value.startswith(local_upload_prefix):
        return value[len(local_upload_prefix):].lstrip("/")
    if public_base_url and value.startswith(public_base_url.rstrip("/") + "/"):
        return value[len(public_base_url.rstrip("/") + "/"):].lstrip("/")

    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return ""
    path = parsed.path.lstrip("/")
    if endpoint_url:
        endpoint = urlparse(endpoint_url.rstrip("/"))
        if parsed.netloc == endpoint.netloc and bucket and path.startswith(bucket.strip("/") + "/"):
            return path[len(bucket.strip("/") + "/"):].lstrip("/")
    if bucket and parsed.netloc.startswith(f"{bucket}."):
        return path
    return ""


def generate_s3_signed_url(
    key: str,
    *,
    bucket: str,
    region: str,
    endpoint_url: str = "",
    expires_in: int = 300,
) -> str:
    if not key or not bucket:
        return ""

    import boto3

    client_kwargs = {"region_name": region}
    if endpoint_url:
        client_kwargs["endpoint_url"] = endpoint_url
    client = boto3.client("s3", **client_kwargs)
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=max(60, int(expires_in or 300)),
    )


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
        raise ValueError("FVENTAS_S3_BUCKET es obligatorio cuando FVENTAS_STORAGE_BACKEND=s3.")

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
    max_bytes: int = 0,
) -> str:
    if not file_storage or not file_storage.filename:
        return ""

    filename = validate_upload(file_storage, max_bytes=max_bytes)
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
