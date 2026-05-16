import uuid
import io
import requests
from django.conf import settings
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


def _upload_bytes_to_s3(file_bytes: bytes, filename: str, mime_type: str) -> str:
    """
    Upload raw bytes to S3 via a presigned URL API.

    Reads S3_UPLOAD_API and S3_BUCKET_NAME from Django settings (which in turn
    read from environment variables).  Returns the public URL of the uploaded
    object so it can be persisted to the database.
    """
    api_url = getattr(settings, "S3_UPLOAD_API", None)
    if not api_url:
        raise Exception(
            "S3_UPLOAD_API is not configured. "
            "Set it in the environment or Django settings."
        )

    project_name = getattr(settings, "S3_BUCKET_NAME", None)

    # Build a collision-free S3 key using the UUID as the filename
    unique_id = uuid.uuid4().hex
    if "." in filename:
        ext = filename.rsplit(".", 1)[-1]
        s3_key = f"uploads/{unique_id}.{ext}"
    else:
        s3_key = f"uploads/{unique_id}"

    payload = {
        "project": project_name,
        "mimeType": mime_type,
        "fileName": s3_key,
    }

    # 1. Obtain a presigned upload URL from the API
    try:
        presign_resp = requests.post(
            api_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        presign_resp.raise_for_status()
        presign_data = presign_resp.json()
    except Exception as e:
        raise Exception(f"Failed to get presigned URL from {api_url}: {e}")

    upload_url = presign_data.get("uploadURL")
    if not upload_url:
        raise Exception(
            f"S3 Upload API response missing 'uploadURL': {presign_data}"
        )

    # 2. PUT the file bytes directly to S3
    try:
        put_resp = requests.put(
            upload_url,
            data=file_bytes,
            headers={"Content-Type": mime_type},
            timeout=30,
        )
        put_resp.raise_for_status()
    except Exception as e:
        raise Exception(f"Failed to upload file to S3: {e}")

    # 3. Strip query-string and return the clean public URL
    public_url = upload_url.split("?")[0]
    return public_url


@deconstructible
class S3PresignedStorage(Storage):
    """
    Django custom storage backend that uploads every media file to S3 via
    a presigned URL API instead of writing to the local filesystem.

    The full public S3 URL is stored in the database field, so no local
    /media/ directory is required — ideal for serverless / Lambda deployments.
    """

    def _save(self, name: str, content) -> str:
        """Read the file, detect MIME type, upload to S3, return the public URL."""
        file_bytes = content.read()

        # Determine MIME type from name extension (simple heuristic)
        mime_type = self._guess_mime_type(name)

        public_url = _upload_bytes_to_s3(
            file_bytes=file_bytes,
            filename=self._filename_only(name),
            mime_type=mime_type,
        )
        # Return the absolute URL — Django will store this as the file "name"
        return public_url

    def url(self, name: str) -> str:
        """
        The stored name IS already a full URL (e.g. https://bucket.s3.amazonaws.com/…),
        so return it unchanged.
        """
        return name

    def exists(self, name: str) -> bool:
        """
        We don't track existence server-side; returning False tells Django it
        can always proceed with uploading (no collision check needed).
        """
        return False

    def delete(self, name: str):
        """
        Deletion via presigned URLs is not implemented.
        Override if you need server-side deletes.
        """
        pass

    def size(self, name: str) -> int:
        """Not supported for remote URLs; return 0."""
        return 0

    def open(self, name: str, mode: str = "rb"):
        """Download a file from its public URL and return as a file-like object."""
        response = requests.get(name, timeout=30)
        response.raise_for_status()
        return io.BytesIO(response.content)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _filename_only(name: str) -> str:
        """Extract just the base filename from a possibly path-prefixed name."""
        return name.split("/")[-1]

    @staticmethod
    def _guess_mime_type(filename: str) -> str:
        """Return a sensible MIME type based on file extension."""
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        mime_map = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "webp": "image/webp",
            "pdf": "application/pdf",
            "doc": "application/msword",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "xls": "application/vnd.ms-excel",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "csv": "text/csv",
            "txt": "text/plain",
            "zip": "application/zip",
        }
        return mime_map.get(ext, "application/octet-stream")
