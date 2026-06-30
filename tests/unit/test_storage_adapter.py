from pathlib import Path

import pytest

from app.integrations.storage.local import LocalStorageAdapter, StorageDeleteError


def test_local_storage_adapter_deletes_report_and_profile_files(tmp_path: Path) -> None:
    report_root = tmp_path / "storage" / "reports"
    report_file = report_root / "profile-id" / "2026" / "report.pdf"
    image_file = tmp_path / "storage" / "profile-images" / "profile.png"
    report_file.parent.mkdir(parents=True)
    image_file.parent.mkdir(parents=True)
    report_file.write_text("pdf", encoding="utf-8")
    image_file.write_text("png", encoding="utf-8")

    adapter = LocalStorageAdapter(str(report_root))

    adapter.delete_report_keys(["profile-id/2026/report.pdf"])
    adapter.delete_profile_image("profile-images/profile.png")

    assert not report_file.exists()
    assert not image_file.exists()


def test_local_storage_adapter_accepts_storage_prefixed_report_keys(tmp_path: Path) -> None:
    report_root = tmp_path / "storage" / "reports"
    report_file = report_root / "profile-id" / "2026" / "report.pdf"
    report_file.parent.mkdir(parents=True)
    report_file.write_text("pdf", encoding="utf-8")

    adapter = LocalStorageAdapter(str(report_root))

    adapter.delete_report_keys(["reports/profile-id/2026/report.pdf"])

    assert not report_file.exists()


def test_local_storage_adapter_skips_remote_profile_images(tmp_path: Path) -> None:
    adapter = LocalStorageAdapter(str(tmp_path / "storage" / "reports"))

    adapter.delete_profile_image("https://example.com/profile.png")


def test_local_storage_adapter_blocks_path_traversal(tmp_path: Path) -> None:
    adapter = LocalStorageAdapter(str(tmp_path / "storage" / "reports"))

    with pytest.raises(StorageDeleteError):
        adapter.delete_report_keys(["../outside.pdf"])
