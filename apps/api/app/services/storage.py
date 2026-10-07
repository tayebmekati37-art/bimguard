import hashlib
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.core.config import get_settings

ALLOWED_EXTENSIONS = {".ifc", ".json", ".pdf", ".csv", ".xlsx", ".dwg", ".rvt"}
CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class StoredFile:
    relative_path: str
    original_name: str
    extension: str
    size: int
    checksum: str


def safe_filename(name: str) -> str:
    base = Path(name.replace("\\", "/")).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", base).strip("._")
    return cleaned[:150] or "file"


def _root() -> Path:
    return Path(get_settings().storage_dir).resolve()


def _check_signature(extension: str, head: bytes) -> None:
    stripped = head.lstrip()
    ok = True
    if extension == ".ifc":
        ok = stripped.startswith(b"ISO-10303-21")
    elif extension == ".pdf":
        ok = head.startswith(b"%PDF")
    elif extension == ".json":
        ok = stripped[:1] in (b"{", b"[")
    if not ok:
        raise HTTPException(422, f"The file content does not look like a valid {extension} file.")


def save_upload(upload: UploadFile, project_id: str, document_id: str) -> StoredFile:
    original = safe_filename(upload.filename or "")
    extension = Path(original).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(422, f"File type '{extension or 'none'}' is not supported. Allowed types: {allowed}.")

    head = upload.file.read(64)
    upload.file.seek(0)
    _check_signature(extension, head)

    root = _root()
    target_dir = (root / project_id / document_id).resolve()
    if root not in target_dir.parents:
        raise HTTPException(400, "Invalid storage location.")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{uuid.uuid4().hex}{extension}"

    limit = get_settings().max_upload_mb * 1024 * 1024
    digest = hashlib.sha256()
    size = 0
    try:
        with target.open("wb") as out:
            while chunk := upload.file.read(CHUNK_SIZE):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, f"File is larger than the {get_settings().max_upload_mb} MB upload limit.")
                digest.update(chunk)
                out.write(chunk)
        if size == 0:
            raise HTTPException(422, "The uploaded file is empty.")
    except BaseException:
        target.unlink(missing_ok=True)
        raise

    return StoredFile(target.relative_to(root).as_posix(), original, extension, size, digest.hexdigest())


def delete_stored(relative_path: str) -> None:
    try:
        resolve_stored(relative_path).unlink(missing_ok=True)
    except HTTPException:
        pass


def delete_project_files(project_id: str) -> None:
    shutil.rmtree(_root() / project_id, ignore_errors=True)


def resolve_stored(relative_path: str) -> Path:
    root = _root()
    path = (root / relative_path).resolve()
    if root not in path.parents:
        raise HTTPException(404, "File not found.")
    if not path.is_file():
        raise HTTPException(404, "The stored file for this revision is missing on the server.")
    return path
