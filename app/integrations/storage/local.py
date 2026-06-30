from pathlib import Path
from urllib.parse import unquote, urlparse


class StorageDeleteError(RuntimeError):
    pass


class LocalStorageAdapter:
    def __init__(self, report_storage_path: str) -> None:
        self.report_root = Path(report_storage_path).resolve(strict=False)
        self.storage_root = (
            self.report_root.parent if self.report_root.name == "reports" else self.report_root
        ).resolve(strict=False)

    def delete_report_keys(self, storage_keys: list[str]) -> None:
        for storage_key in storage_keys:
            path = self._resolve_report_key(storage_key)
            self._delete_file_if_present(path)

    def delete_profile_image(self, profile_image_url: str | None) -> None:
        if not profile_image_url:
            return

        parsed = urlparse(profile_image_url)
        if parsed.scheme in {"http", "https"}:
            return

        raw_path = unquote(parsed.path if parsed.scheme else profile_image_url)
        object_key = self._normalize_object_key(raw_path)
        if not object_key:
            return

        path = self._resolve_inside_root(self.storage_root, object_key)
        self._delete_file_if_present(path)

    def _resolve_report_key(self, storage_key: str) -> Path:
        object_key = self._normalize_object_key(storage_key)
        if not object_key:
            raise StorageDeleteError("Storage key is empty.")

        root = self.storage_root if object_key.startswith("reports/") else self.report_root
        return self._resolve_inside_root(root, object_key)

    def _normalize_object_key(self, value: str) -> str:
        normalized = value.replace("\\", "/").strip().lstrip("/")
        if normalized.startswith("storage/"):
            normalized = normalized[len("storage/") :]
        return normalized

    def _resolve_inside_root(self, root: Path, object_key: str) -> Path:
        path = (root / object_key).resolve(strict=False)
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise StorageDeleteError("Refusing to delete a file outside storage root.") from exc
        return path

    def _delete_file_if_present(self, path: Path) -> None:
        try:
            if not path.exists():
                return
            if not path.is_file():
                raise StorageDeleteError("Storage object is not a file.")
            path.unlink()
        except OSError as exc:
            raise StorageDeleteError("Failed to delete storage object.") from exc
