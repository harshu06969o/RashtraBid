"""
GeM-Guard — Production Cloud & Local Storage Architecture
Supports Cloudinary Cloud Storage for production asset lifecycle,
with local buffer caching for high-speed offline / local execution.
"""

import hashlib
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Optional, Union
from fastapi import UploadFile

from app.paths import DATA_DIR, UPLOADS_DIR

logger = logging.getLogger("gemguard.storage")

# Default uploads directory: backend/data/uploads/
DEFAULT_UPLOAD_DIR = UPLOADS_DIR
DEFAULT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class StoredFile:
    """Metadata of a stored file."""
    filename: str
    file_path: Path
    relative_path: str
    file_hash: str
    size_bytes: int
    content_type: str = "application/octet-stream"
    provider: str = "local"
    url: Optional[str] = None
    public_id: Optional[str] = None


class HybridStorage:
    """
    Production Hybrid Storage Manager
    Supports Cloudinary for cloud asset storage with automated caching
    and local buffer fallback for offline resilience.
    """

    def __init__(self, base_dir: Path = DEFAULT_UPLOAD_DIR):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._init_cloudinary()

    def _init_cloudinary(self):
        """Initialize Cloudinary configuration if credentials are set."""
        self.provider = (os.getenv("STORAGE_PROVIDER") or "cloudinary").lower().strip()
        self.cloud_name = (os.getenv("CLOUDINARY_CLOUD_NAME") or "").strip()
        self.api_key = (os.getenv("CLOUDINARY_API_KEY") or "").strip()
        self.api_secret = (os.getenv("CLOUDINARY_API_SECRET") or "").strip()
        self.cloudinary_url = (os.getenv("CLOUDINARY_URL") or "").strip()
        self.cloudinary_enabled = False

        if self.cloudinary_url or (self.cloud_name and self.api_key and self.api_secret):
            try:
                import cloudinary
                if self.cloudinary_url:
                    cloudinary.config(cloudinary_url=self.cloudinary_url)
                else:
                    cloudinary.config(
                        cloud_name=self.cloud_name,
                        api_key=self.api_key,
                        api_secret=self.api_secret,
                        secure=True,
                    )
                self.cloudinary_enabled = True
                logger.info("Cloudinary storage provider initialized successfully.")
            except Exception as ex:
                logger.warning("Cloudinary configuration note: %s", ex)
        else:
            if self.provider == "cloudinary":
                logger.info(
                    "Cloudinary storage provider active in configuration. "
                    "Provide CLOUDINARY_CLOUD_NAME/KEY/SECRET or CLOUDINARY_URL in backend/.env to sync assets directly to Cloudinary cloud."
                )

    @staticmethod
    def compute_hash(data: Any) -> str:
        """Compute SHA-256 digest of byte or string content safely."""
        if data is None:
            raw_bytes = b""
        elif isinstance(data, (bytes, bytearray)):
            raw_bytes = bytes(data)
        elif isinstance(data, str):
            raw_bytes = data.encode("utf-8")
        else:
            try:
                raw_bytes = bytes(data)
            except Exception:
                raw_bytes = str(data).encode("utf-8")
        return hashlib.sha256(raw_bytes).hexdigest()

    async def save_file(
        self,
        file_input: Union[UploadFile, bytes, BinaryIO, Any],
        filename: str,
        subfolder: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> StoredFile:
        """
        Save file to storage (Cloudinary cloud with local caching buffer) and compute its SHA-256 hash.
        """
        target_dir = self.base_dir / subfolder if subfolder else self.base_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        safe_filename = Path(filename).name

        content: bytes = b""
        if hasattr(file_input, "read"):
            read_fn = file_input.read
            import inspect
            if inspect.iscoroutinefunction(read_fn):
                content = await read_fn()
            else:
                raw = read_fn()
                if inspect.iscoroutine(raw):
                    content = await raw
                else:
                    content = raw

            if hasattr(file_input, "seek"):
                seek_fn = file_input.seek
                if inspect.iscoroutinefunction(seek_fn):
                    await seek_fn(0)
                else:
                    s_res = seek_fn(0)
                    if inspect.iscoroutine(s_res):
                        await s_res

            if not content_type and hasattr(file_input, "content_type"):
                content_type = getattr(file_input, "content_type", None)
        elif isinstance(file_input, (bytes, bytearray)):
            content = bytes(file_input)
        elif isinstance(file_input, str):
            content = file_input.encode("utf-8")
        else:
            raise ValueError(f"Unsupported file_input type: {type(file_input)}")

        if isinstance(content, str):
            content = content.encode("utf-8")
        elif not isinstance(content, (bytes, bytearray)):
            content = bytes(content)

        file_hash = self.compute_hash(content)
        file_path = target_dir / safe_filename

        # Write to local cache / buffer
        with open(file_path, "wb") as f:
            f.write(content)

        size_bytes = len(content)
        relative_path = str(file_path.relative_to(self.base_dir.parent))

        # Check Cloudinary upload
        cloud_url = None
        public_id = None
        active_provider = "local"

        if self.cloudinary_enabled:
            try:
                import cloudinary.uploader
                folder_name = f"gem_guard/{subfolder}" if subfolder else "gem_guard"
                c_res = cloudinary.uploader.upload(
                    content,
                    folder=folder_name,
                    public_id=f"{file_hash[:12]}_{safe_filename.rsplit('.', 1)[0]}",
                    resource_type="auto",
                    overwrite=True,
                )
                cloud_url = c_res.get("secure_url") or c_res.get("url")
                public_id = c_res.get("public_id")
                active_provider = "cloudinary"
                logger.info("Uploaded '%s' to Cloudinary (URL: %s)", safe_filename, cloud_url)
            except Exception as c_err:
                logger.warning("Cloudinary upload note: %s. Using cached local copy.", c_err)

        logger.info(
            "Stored file '%s' (%d bytes, SHA-256: %s, provider: %s)",
            safe_filename,
            size_bytes,
            file_hash[:12],
            active_provider,
        )

        return StoredFile(
            filename=safe_filename,
            file_path=file_path,
            relative_path=relative_path,
            file_hash=file_hash,
            size_bytes=size_bytes,
            content_type=content_type or "application/octet-stream",
            provider=active_provider,
            url=cloud_url or f"/api/files/{safe_filename}",
            public_id=public_id,
        )

    def get_file_path(self, filename_or_path: Union[str, Path]) -> Path:
        """Resolve a filename or path to a valid Path inside storage."""
        p = Path(filename_or_path)
        if p.is_absolute() and p.exists():
            return p
        direct = self.base_dir / p.name
        if direct.exists():
            return direct
        matches = list(self.base_dir.rglob(p.name))
        if matches:
            return matches[0]
        return direct

    def read_file(self, filename_or_path: Union[str, Path]) -> bytes:
        """Read file bytes from storage."""
        path = self.get_file_path(filename_or_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found in storage: {filename_or_path}")
        with open(path, "rb") as f:
            return f.read()

    def file_exists(self, filename_or_path: Union[str, Path]) -> bool:
        """Check if file exists in storage."""
        path = self.get_file_path(filename_or_path)
        return path.exists() and path.is_file()

    def delete_file(self, filename_or_path: Union[str, Path]) -> bool:
        """Delete file from storage."""
        path = self.get_file_path(filename_or_path)
        if path.exists() and path.is_file():
            path.unlink()
            logger.info("Deleted local file: %s", path)
            return True
        return False

    def get_url(self, filename: str) -> str:
        """Generate file URL path."""
        safe_name = Path(filename).name
        return f"/api/files/{safe_name}"


# Singleton instance
storage = HybridStorage()


def get_storage() -> HybridStorage:
    """FastAPI dependency to inject storage instance."""
    return storage
