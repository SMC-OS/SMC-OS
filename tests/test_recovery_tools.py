"""Offline safety contracts for the Sprint 019 matched-upload recovery tools."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import errno
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RECOVERY_DIR = PROJECT_ROOT / "scripts" / "recovery"
CREATE_SCRIPT = RECOVERY_DIR / "matched_bundle.py"
RESTORE_SCRIPT = RECOVERY_DIR / "restore_upload_bundle.py"
RUNBOOK = PROJECT_ROOT / "docs" / "STAGING_RUNBOOK.md"
NONPORTABLE_RELATIVE_PATHS = (
    "nested/CON.txt",
    "nested/trailing.",
    "nested/trailing ",
    "nested/bad<name>.pdf",
)


def load_script(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(path.parent))
    return module


def run_script(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *map(str, args)],
        check=False,
        capture_output=True,
        text=True,
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_archive(path: Path, members: list[tuple[str, bytes, bytes | None]]) -> None:
    """Write a deliberately controllable tar archive for hostile-input tests.

    Each member is ``(name, content, link_target)``; a non-None link target
    creates a symbolic-link entry without creating a real filesystem symlink.
    """
    with tarfile.open(path, "w") as archive:
        for name, content, link_target in members:
            info = tarfile.TarInfo(name)
            if link_target is None:
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
            else:
                info.type = tarfile.SYMTYPE
                info.linkname = link_target.decode("utf-8")
                archive.addfile(info)


def manifest_for(archive: Path, files: list[tuple[str, bytes]], **overrides: object) -> dict[str, object]:
    manifest: dict[str, object] = {
        "archive_sha256": sha256(archive),
        "created_at": "2026-08-18T12:00:00Z",
        "database_recovery_point": "db-rp-2026-08-18T12:00:00Z",
        "entries": [
            {"relative_path": name, "sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content)}
            for name, content in files
        ],
    }
    manifest.update(overrides)
    return manifest


def write_manifest(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_creator_preserves_sorted_relative_paths_and_deterministic_manifest(tmp_path):
    source = tmp_path / "uploads"
    (source / "nested" / "deeper").mkdir(parents=True)
    (source / "z-last.bin").write_bytes(b"last")
    (source / "nested" / "b.txt").write_bytes(b"bravo")
    (source / "nested" / "deeper" / "a.txt").write_bytes(b"alpha")
    archive = tmp_path / "outside" / "uploads.tar"
    manifest = tmp_path / "outside" / "uploads.json"
    archive.parent.mkdir()

    result = run_script(
        CREATE_SCRIPT,
        "--source-dir", source,
        "--archive-path", archive,
        "--manifest-path", manifest,
        "--database-recovery-point", "railway-pitr-123",
        "--created-at", "2026-08-18T12:00:00Z",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["database_recovery_point"] == "railway-pitr-123"
    assert payload["created_at"] == "2026-08-18T12:00:00Z"
    assert payload["archive_sha256"] == sha256(archive)
    assert payload["entries"] == [
        {"relative_path": "nested/b.txt", "sha256": hashlib.sha256(b"bravo").hexdigest(), "size_bytes": 5},
        {"relative_path": "nested/deeper/a.txt", "sha256": hashlib.sha256(b"alpha").hexdigest(), "size_bytes": 5},
        {"relative_path": "z-last.bin", "sha256": hashlib.sha256(b"last").hexdigest(), "size_bytes": 4},
    ]
    assert "railway-pitr-123" in result.stdout
    assert "nested/b.txt" not in result.stdout


def test_creator_rejects_symlink_and_escaping_source_without_artifacts(tmp_path):
    source = tmp_path / "uploads"
    source.mkdir()
    (source / "real.txt").write_text("real", encoding="utf-8")
    target = tmp_path / "outside.txt"
    target.write_text("outside", encoding="utf-8")
    link = source / "linked.txt"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    archive = tmp_path / "archive.tar"
    manifest = tmp_path / "manifest.json"

    result = run_script(CREATE_SCRIPT, "--source-dir", source, "--archive-path", archive, "--manifest-path", manifest, "--database-recovery-point", "rp", "--created-at", "2026-08-18T12:00:00Z")

    assert result.returncode != 0
    assert not archive.exists()
    assert not manifest.exists()
    assert "linked.txt" not in result.stdout + result.stderr


def test_creator_symlink_rejection_branch_without_os_symlink_privilege(tmp_path, monkeypatch):
    source = tmp_path / "uploads"
    source.mkdir()
    linked = source / "linked.txt"
    linked.write_bytes(b"ordinary file presented as a reparse entry")
    archive = tmp_path / "archive.tar"
    manifest = tmp_path / "manifest.json"
    creator = load_script(CREATE_SCRIPT, "matched_bundle_creator_injected_symlink")
    original_is_symlink = creator.Path.is_symlink

    def injected_is_symlink(path):
        return path == linked or original_is_symlink(path)

    monkeypatch.setattr(creator.Path, "is_symlink", injected_is_symlink)

    with pytest.raises((creator.RecoveryError, OSError)):
        creator.create_bundle(
            source, archive, manifest, "rp", "2026-08-18T12:00:00Z"
        )

    assert not archive.exists()
    assert not manifest.exists()


def test_creator_rejects_multi_link_source_file_without_artifacts(tmp_path):
    source = tmp_path / "uploads"
    source.mkdir()
    original = source / "document.pdf"
    linked = tmp_path / "outside-hardlink.pdf"
    original.write_bytes(b"sensitive")
    try:
        os.link(original, linked)
    except OSError as exc:
        pytest.skip(f"hardlinks unavailable: {exc}")
    archive = tmp_path / "archive.tar"
    manifest = tmp_path / "manifest.json"

    result = run_script(
        CREATE_SCRIPT,
        "--source-dir", source,
        "--archive-path", archive,
        "--manifest-path", manifest,
        "--database-recovery-point", "rp",
        "--created-at", "2026-08-18T12:00:00Z",
    )

    assert result.returncode != 0
    assert not archive.exists()
    assert not manifest.exists()


def test_creator_rejects_source_file_path_swap_during_archive(tmp_path, monkeypatch):
    source = tmp_path / "uploads"
    source.mkdir()
    payload = source / "document.pdf"
    payload.write_bytes(b"original")
    replacement = tmp_path / "replacement.pdf"
    replacement.write_bytes(b"attacker")
    archive = tmp_path / "archive.tar"
    manifest = tmp_path / "manifest.json"
    creator = load_script(CREATE_SCRIPT, "matched_bundle_creator_source_swap")
    original_read = creator._HashingReader.read
    swapped = False

    def swap_after_open(reader, size=-1):
        nonlocal swapped
        chunk = original_read(reader, size)
        if chunk and not swapped:
            swapped = True
            os.replace(replacement, payload)
        return chunk

    monkeypatch.setattr(creator._HashingReader, "read", swap_after_open)

    with pytest.raises((creator.RecoveryError, OSError)):
        creator.create_bundle(
            source, archive, manifest, "rp", "2026-08-18T12:00:00Z"
        )

    assert swapped
    assert not archive.exists()
    assert not manifest.exists()


def test_creator_rejects_source_parent_swap_during_archive(tmp_path, monkeypatch):
    source = tmp_path / "uploads"
    source.mkdir()
    (source / "document.pdf").write_bytes(b"document")
    moved = tmp_path / "uploads-moved"
    archive = tmp_path / "archive.tar"
    manifest = tmp_path / "manifest.json"
    creator = load_script(CREATE_SCRIPT, "matched_bundle_creator_parent_swap")
    original_write = creator._write_archive
    attempted = False

    def swap_parent_after_write(*args, **kwargs):
        nonlocal attempted
        entries = original_write(*args, **kwargs)
        attempted = True
        source.rename(moved)
        source.mkdir()
        return entries

    monkeypatch.setattr(creator, "_write_archive", swap_parent_after_write)

    with pytest.raises((creator.RecoveryError, OSError)):
        creator.create_bundle(
            source, archive, manifest, "rp", "2026-08-18T12:00:00Z"
        )

    assert attempted
    assert not archive.exists()
    assert not manifest.exists()


def test_creator_rejects_outputs_inside_repository_or_active_upload_mount(tmp_path):
    source = tmp_path / "uploads"
    source.mkdir()
    (source / "document.pdf").write_bytes(b"document")
    repo_output = PROJECT_ROOT / "recovery-test-output.tar"
    active_output = Path("/var/lib/simo-os/uploads/recovery-test-output.tar")
    manifest = tmp_path / "manifest.json"

    repo_result = run_script(CREATE_SCRIPT, "--source-dir", source, "--archive-path", repo_output, "--manifest-path", manifest, "--database-recovery-point", "rp", "--created-at", "2026-08-18T12:00:00Z")
    mount_result = run_script(CREATE_SCRIPT, "--source-dir", source, "--archive-path", tmp_path / "safe.tar", "--manifest-path", active_output, "--database-recovery-point", "rp", "--created-at", "2026-08-18T12:00:00Z")

    assert repo_result.returncode != 0
    assert mount_result.returncode != 0
    assert not repo_output.exists()
    assert "document.pdf" not in repo_result.stdout + repo_result.stderr + mount_result.stdout + mount_result.stderr


def test_creator_writes_identical_manifest_for_identical_inputs(tmp_path):
    source = tmp_path / "uploads"
    source.mkdir()
    (source / "document.pdf").write_bytes(b"document")
    first_archive, first_manifest = tmp_path / "first.tar", tmp_path / "first.json"
    second_archive, second_manifest = tmp_path / "second.tar", tmp_path / "second.json"
    arguments = ("--source-dir", source, "--database-recovery-point", "rp", "--created-at", "2026-08-18T12:00:00Z")

    assert run_script(CREATE_SCRIPT, *arguments, "--archive-path", first_archive, "--manifest-path", first_manifest).returncode == 0
    assert run_script(CREATE_SCRIPT, *arguments, "--archive-path", second_archive, "--manifest-path", second_manifest).returncode == 0

    assert first_manifest.read_bytes() == second_manifest.read_bytes()
    assert sha256(first_archive) == sha256(second_archive)


def test_creator_publication_never_clobbers_racing_target(tmp_path, monkeypatch):
    source = tmp_path / "uploads"
    source.mkdir()
    (source / "document.pdf").write_bytes(b"document")
    archive = tmp_path / "uploads.tar"
    manifest = tmp_path / "uploads.json"
    creator = load_script(CREATE_SCRIPT, "matched_bundle_creator_target_race")
    original_link = creator.os.link
    injected = False

    def create_target_before_link(source_path, target_path, *args, **kwargs):
        nonlocal injected
        if Path(target_path) == archive and not injected:
            injected = True
            archive.write_bytes(b"attacker-owned")
        return original_link(source_path, target_path, *args, **kwargs)

    monkeypatch.setattr(creator.os, "link", create_target_before_link)

    with pytest.raises((creator.RecoveryError, OSError)):
        creator.create_bundle(
            source, archive, manifest, "rp", "2026-08-18T12:00:00Z"
        )

    assert injected
    assert archive.read_bytes() == b"attacker-owned"
    assert not manifest.exists()


def test_creator_rolls_back_exact_archive_when_manifest_publication_fails(tmp_path, monkeypatch):
    source = tmp_path / "uploads"
    source.mkdir()
    (source / "document.pdf").write_bytes(b"document")
    archive = tmp_path / "uploads.tar"
    manifest = tmp_path / "uploads.json"
    creator = load_script(CREATE_SCRIPT, "matched_bundle_creator_second_publish")
    original_link = creator.os.link
    calls = 0

    def fail_second_publication(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected manifest publication failure")
        return original_link(*args, **kwargs)

    monkeypatch.setattr(creator.os, "link", fail_second_publication)

    with pytest.raises((creator.RecoveryError, OSError)):
        creator.create_bundle(
            source, archive, manifest, "rp", "2026-08-18T12:00:00Z"
        )

    assert calls == 2
    assert not archive.exists()
    assert not manifest.exists()


def test_creator_rejects_output_parent_replacement_before_publication(tmp_path, monkeypatch):
    source = tmp_path / "uploads"
    source.mkdir()
    (source / "document.pdf").write_bytes(b"document")
    output = tmp_path / "output"
    moved = tmp_path / "output-moved"
    output.mkdir()
    archive = output / "uploads.tar"
    manifest = output / "uploads.json"
    creator = load_script(CREATE_SCRIPT, "matched_bundle_creator_output_parent_swap")
    original_link = creator.os.link
    attempted = False

    def swap_parent_before_link(*args, **kwargs):
        nonlocal attempted
        if not attempted:
            attempted = True
            output.rename(moved)
            output.mkdir()
        return original_link(*args, **kwargs)

    monkeypatch.setattr(creator.os, "link", swap_parent_before_link)

    with pytest.raises((creator.RecoveryError, OSError)):
        creator.create_bundle(
            source, archive, manifest, "rp", "2026-08-18T12:00:00Z"
        )

    assert attempted
    assert not archive.exists()
    assert not manifest.exists()


def test_creator_rejects_temporary_archive_path_replacement(tmp_path, monkeypatch):
    source = tmp_path / "uploads"
    source.mkdir()
    (source / "document.pdf").write_bytes(b"document")
    archive = tmp_path / "uploads.tar"
    manifest = tmp_path / "uploads.json"
    creator = load_script(CREATE_SCRIPT, "matched_bundle_creator_temp_race")
    original_write_archive = creator._write_archive

    def replace_temporary_after_write(temp_path, source_files, *args, **kwargs):
        entries = original_write_archive(temp_path, source_files, *args, **kwargs)
        replacement = temp_path.with_suffix(".replacement")
        replacement.write_bytes(b"attacker-owned")
        os.replace(replacement, temp_path)
        return entries

    monkeypatch.setattr(creator, "_write_archive", replace_temporary_after_write)

    with pytest.raises((creator.RecoveryError, OSError)):
        creator.create_bundle(
            source, archive, manifest, "rp", "2026-08-18T12:00:00Z"
        )

    assert not archive.exists()
    assert not manifest.exists()


def test_creator_rejects_windows_equivalent_source_paths_without_artifacts(tmp_path, monkeypatch):
    source = tmp_path / "uploads"
    source.mkdir()
    first = source / "first.bin"
    second = source / "second.bin"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    archive = tmp_path / "uploads.tar"
    manifest = tmp_path / "uploads.json"
    creator = load_script(CREATE_SCRIPT, "matched_bundle_creator_collision")
    monkeypatch.setattr(
        creator,
        "_source_files",
        lambda _source: [("Report.pdf", first), ("report.PDF", second)],
    )

    with pytest.raises(creator.RecoveryError):
        creator.create_bundle(
            source,
            archive,
            manifest,
            "db-rp-2026-08-18T12:00:00Z",
            "2026-08-18T12:00:00Z",
        )

    assert not archive.exists()
    assert not manifest.exists()


@pytest.mark.parametrize("relative_path", NONPORTABLE_RELATIVE_PATHS)
def test_creator_rejects_nonportable_source_path_before_artifacts(tmp_path, monkeypatch, relative_path):
    source = tmp_path / "uploads"
    source.mkdir()
    payload = source / "payload.bin"
    payload.write_bytes(b"payload")
    archive = tmp_path / "uploads.tar"
    manifest = tmp_path / "uploads.json"
    creator = load_script(CREATE_SCRIPT, f"matched_bundle_creator_{len(relative_path)}_{ord(relative_path[-1])}")
    monkeypatch.setattr(creator, "_source_files", lambda _source: [(relative_path, payload)])

    with pytest.raises(creator.RecoveryError):
        creator.create_bundle(
            source,
            archive,
            manifest,
            "db-rp-2026-08-18T12:00:00Z",
            "2026-08-18T12:00:00Z",
        )

    assert not archive.exists()
    assert not manifest.exists()


@pytest.mark.parametrize(
    ("limit_name", "limit", "source_files"),
    [
        ("MAX_ENTRIES", 0, [("a", b"a")]),
        ("MAX_MEMBER_BYTES", 0, [("a", b"a")]),
        ("MAX_TOTAL_BYTES", 1, [("a", b"a"), ("b", b"b")]),
        ("MAX_MANIFEST_BYTES", 16, [("a", b"a")]),
        ("MAX_PATH_UTF8_BYTES", 5, [("ééé", b"a")]),
        ("MAX_COMPONENT_UTF8_BYTES", 5, [("ééé", b"a")]),
        ("MAX_PATH_UTF16_UNITS", 3, [("😀😀", b"a")]),
        ("MAX_COMPONENT_UTF16_UNITS", 3, [("😀😀", b"a")]),
    ],
)
def test_creator_enforces_shared_restore_limits_before_publication(
    tmp_path, monkeypatch, limit_name, limit, source_files
):
    source = tmp_path / "uploads"
    source.mkdir()
    for relative_path, content in source_files:
        (source / relative_path).write_bytes(content)
    archive = tmp_path / "uploads.tar"
    manifest = tmp_path / "uploads.json"
    creator = load_script(CREATE_SCRIPT, f"matched_bundle_shared_limit_{limit_name}")
    safety = sys.modules[creator.validate_portable_relative_path.__module__]
    monkeypatch.setattr(safety, limit_name, limit, raising=False)

    with pytest.raises(creator.RecoveryError):
        creator.create_bundle(
            source,
            archive,
            manifest,
            "db-rp-2026-08-18T12:00:00Z",
            "2026-08-18T12:00:00Z",
        )

    assert not archive.exists()
    assert not manifest.exists()


def test_creator_shared_policy_stays_within_pax_free_size_boundary():
    creator = load_script(CREATE_SCRIPT, "matched_bundle_pax_size_policy")
    largest_pax_free_size = 8**11 - 1

    assert creator.safety.add_member_size(0, largest_pax_free_size) == largest_pax_free_size
    member_size = creator.safety.add_member_size(0, creator.safety.MAX_MEMBER_BYTES)
    member = tarfile.TarInfo("payload.bin")
    member.size = member_size

    encoded_header = member.create_pax_header(member.get_info(), "utf-8")

    assert len(encoded_header) == tarfile.BLOCKSIZE
    with pytest.raises(ValueError):
        creator.safety.add_member_size(0, 8**11)


def test_creator_bundle_at_shared_unicode_and_pax_boundaries_restores(tmp_path, monkeypatch):
    source = tmp_path / "uploads"
    source.mkdir()
    relative_path = "é" * 48 + ".txt"
    content = b"boundary"
    (source / relative_path).write_bytes(content)
    archive = tmp_path / "uploads.tar"
    manifest = tmp_path / "uploads.json"
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    creator = load_script(CREATE_SCRIPT, "matched_bundle_shared_boundary_creator")
    restore = load_script(RESTORE_SCRIPT, "matched_bundle_shared_boundary_restore")
    safety = sys.modules[creator.validate_portable_relative_path.__module__]
    monkeypatch.setattr(safety, "MAX_ENTRIES", 1, raising=False)
    monkeypatch.setattr(safety, "MAX_MEMBER_BYTES", 8, raising=False)
    monkeypatch.setattr(safety, "MAX_TOTAL_BYTES", 8, raising=False)
    monkeypatch.setattr(safety, "MAX_PATH_UTF8_BYTES", 100, raising=False)
    monkeypatch.setattr(safety, "MAX_COMPONENT_UTF8_BYTES", 100, raising=False)
    monkeypatch.setattr(safety, "MAX_PATH_UTF16_UNITS", 52, raising=False)
    monkeypatch.setattr(safety, "MAX_COMPONENT_UTF16_UNITS", 52, raising=False)

    creator.create_bundle(
        source,
        archive,
        manifest,
        "db-rp-2026-08-18T12:00:00Z",
        "2026-08-18T12:00:00Z",
    )
    with tarfile.open(archive, "r:") as bundle:
        member = bundle.getmembers()[0]
        assert set(member.pax_headers) <= getattr(safety, "PERMITTED_PAX_FIELDS", {"path"})
    restored_count, _digest, _recovery_point = restore.restore_bundle(
        archive, manifest, scratch
    )

    assert restored_count == 1
    assert (scratch / relative_path).read_bytes() == content


@pytest.mark.parametrize(
    ("recovery_point", "created_at"),
    [
        ("rp\ninjected", "2026-08-18T12:00:00Z"),
        ("rp with spaces", "2026-08-18T12:00:00Z"),
        ("valid-rp", "now"),
        ("valid-rp", "2026-08-18T12:00:00"),
        ("valid-rp", "2026-02-30T12:00:00Z"),
    ],
)
def test_creator_rejects_noncanonical_recovery_metadata(tmp_path, recovery_point, created_at):
    source = tmp_path / "uploads"
    source.mkdir()
    (source / "document.pdf").write_bytes(b"document")
    archive = tmp_path / "archive.tar"
    manifest = tmp_path / "manifest.json"

    result = run_script(
        CREATE_SCRIPT,
        "--source-dir", source,
        "--archive-path", archive,
        "--manifest-path", manifest,
        "--database-recovery-point", recovery_point,
        "--created-at", created_at,
    )

    assert result.returncode != 0
    assert not archive.exists()
    assert not manifest.exists()
    assert recovery_point not in result.stdout + result.stderr


@pytest.mark.parametrize(
    ("archive_members", "manifest_files", "manifest_changes"),
    [
        ([('document.pdf', b'bytes', None)], [('document.pdf', b'bytes')], {"archive_sha256": "0" * 64}),
        ([], [('document.pdf', b'bytes')], {}),
        ([('document.pdf', b'bytes', None), ('extra.pdf', b'extra', None)], [('document.pdf', b'bytes')], {}),
        ([('document.pdf', b'first', None), ('document.pdf', b'second', None)], [('document.pdf', b'first')], {}),
        ([('/absolute.pdf', b'bytes', None)], [('/absolute.pdf', b'bytes')], {}),
        ([('../escape.pdf', b'bytes', None)], [('../escape.pdf', b'bytes')], {}),
        ([('link.pdf', b'', b'elsewhere')], [('link.pdf', b'')], {}),
    ],
    ids=("archive_digest", "missing_member", "extra_member", "duplicate_member", "absolute_member", "traversal_member", "symlink_member"),
)
def test_restore_rejects_invalid_archive_or_manifest_without_extraction(tmp_path, archive_members, manifest_files, manifest_changes):
    archive = tmp_path / "uploads.tar"
    manifest = tmp_path / "uploads.json"
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    write_archive(archive, archive_members)
    write_manifest(manifest, manifest_for(archive, manifest_files, **manifest_changes))

    result = run_script(RESTORE_SCRIPT, "--archive-path", archive, "--manifest-path", manifest, "--scratch-upload-dir", scratch)

    assert result.returncode != 0
    assert list(scratch.iterdir()) == []
    assert "document.pdf" not in result.stdout + result.stderr
    assert "elsewhere" not in result.stdout + result.stderr


def test_restore_rejects_duplicate_manifest_path_absolute_or_traversal_path_without_extraction(tmp_path):
    archive = tmp_path / "uploads.tar"
    manifest = tmp_path / "uploads.json"
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    write_archive(archive, [("document.pdf", b"bytes", None)])
    base = manifest_for(archive, [("document.pdf", b"bytes")])

    for entries in (
        [base["entries"][0], base["entries"][0]],
        [{"relative_path": "/absolute.pdf", "sha256": hashlib.sha256(b"bytes").hexdigest(), "size_bytes": 5}],
        [{"relative_path": "../escape.pdf", "sha256": hashlib.sha256(b"bytes").hexdigest(), "size_bytes": 5}],
    ):
        write_manifest(manifest, {**base, "entries": entries})
        result = run_script(RESTORE_SCRIPT, "--archive-path", archive, "--manifest-path", manifest, "--scratch-upload-dir", scratch)
        assert result.returncode != 0
        assert list(scratch.iterdir()) == []


def test_restore_rejects_windows_equivalent_paths_without_extraction(tmp_path):
    archive = tmp_path / "uploads.tar"
    manifest = tmp_path / "uploads.json"
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    files = [("Report.pdf", b"first"), ("report.PDF", b"second")]
    write_archive(archive, [(name, content, None) for name, content in files])
    write_manifest(manifest, manifest_for(archive, files))

    result = run_script(
        RESTORE_SCRIPT,
        "--archive-path", archive,
        "--manifest-path", manifest,
        "--scratch-upload-dir", scratch,
    )

    assert result.returncode != 0
    assert list(scratch.iterdir()) == []


@pytest.mark.parametrize("relative_path", NONPORTABLE_RELATIVE_PATHS)
def test_restore_rejects_nonportable_path_without_extraction(tmp_path, relative_path):
    archive = tmp_path / "uploads.tar"
    manifest = tmp_path / "uploads.json"
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    files = [("safe.txt", b"safe"), (relative_path, b"hostile")]
    write_archive(archive, [(name, content, None) for name, content in files])
    write_manifest(manifest, manifest_for(archive, files))

    result = run_script(
        RESTORE_SCRIPT,
        "--archive-path", archive,
        "--manifest-path", manifest,
        "--scratch-upload-dir", scratch,
    )

    assert result.returncode != 0
    assert list(scratch.iterdir()) == []


def test_restore_requires_empty_non_active_scratch_directory_and_restores_exact_bytes(tmp_path):
    archive = tmp_path / "uploads.tar"
    manifest = tmp_path / "uploads.json"
    write_archive(archive, [("nested/document.pdf", b"bytes", None)])
    write_manifest(manifest, manifest_for(archive, [("nested/document.pdf", b"bytes")]))
    nonempty = tmp_path / "nonempty"
    nonempty.mkdir()
    (nonempty / "keep.txt").write_text("keep", encoding="utf-8")

    nonempty_result = run_script(RESTORE_SCRIPT, "--archive-path", archive, "--manifest-path", manifest, "--scratch-upload-dir", nonempty)
    active_result = run_script(RESTORE_SCRIPT, "--archive-path", archive, "--manifest-path", manifest, "--scratch-upload-dir", "/var/lib/simo-os/uploads")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    success = run_script(RESTORE_SCRIPT, "--archive-path", archive, "--manifest-path", manifest, "--scratch-upload-dir", scratch)

    assert nonempty_result.returncode != 0
    assert (nonempty / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert active_result.returncode != 0
    assert success.returncode == 0, success.stderr
    assert (scratch / "nested" / "document.pdf").read_bytes() == b"bytes"
    assert "nested/document.pdf" not in success.stdout
    assert "db-rp-2026-08-18T12:00:00Z" in success.stdout


def test_restore_rejects_archive_regular_file_replacement_after_preflight(tmp_path, monkeypatch):
    archive = tmp_path / "uploads.tar"
    replacement = tmp_path / "replacement.tar"
    manifest = tmp_path / "uploads.json"
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    write_archive(archive, [("document.pdf", b"bytes", None)])
    replacement.write_bytes(archive.read_bytes())
    write_manifest(manifest, manifest_for(archive, [("document.pdf", b"bytes")]))
    restore = load_script(RESTORE_SCRIPT, "restore_upload_bundle_archive_swap")
    original_preflight = restore._preflight_archive

    def replace_after_preflight(*args, **kwargs):
        original_preflight(*args, **kwargs)
        try:
            os.replace(replacement, archive)
        except OSError as exc:
            raise restore.RecoveryError("archive replacement was rejected") from exc

    monkeypatch.setattr(restore, "_preflight_archive", replace_after_preflight)

    with pytest.raises(restore.RecoveryError):
        restore.restore_bundle(archive, manifest, scratch)


def test_restore_rejects_manifest_regular_file_replacement_after_validation(tmp_path, monkeypatch):
    archive = tmp_path / "uploads.tar"
    manifest = tmp_path / "uploads.json"
    replacement = tmp_path / "replacement.json"
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    write_archive(archive, [("document.pdf", b"bytes", None)])
    write_manifest(manifest, manifest_for(archive, [("document.pdf", b"bytes")]))
    replacement.write_bytes(manifest.read_bytes())
    restore = load_script(RESTORE_SCRIPT, "restore_upload_bundle_manifest_swap")
    original_load_manifest = restore._load_manifest

    def replace_after_validation(*args, **kwargs):
        result = original_load_manifest(*args, **kwargs)
        try:
            os.replace(replacement, manifest)
        except OSError as exc:
            raise restore.RecoveryError("manifest replacement was rejected") from exc
        return result

    monkeypatch.setattr(restore, "_load_manifest", replace_after_validation)

    with pytest.raises(restore.RecoveryError):
        restore.restore_bundle(archive, manifest, scratch)


def test_restore_rejects_windows_reparse_regular_file_artifact(tmp_path, monkeypatch):
    archive = tmp_path / "uploads.tar"
    write_archive(archive, [("document.pdf", b"bytes", None)])
    restore = load_script(RESTORE_SCRIPT, "restore_upload_bundle_reparse_artifact")
    original_lstat = restore.Path.lstat
    actual = archive.lstat()
    reparse_regular = SimpleNamespace(
        st_mode=actual.st_mode,
        st_ino=actual.st_ino,
        st_dev=actual.st_dev,
        st_file_attributes=getattr(restore.stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400),
    )

    def inject_reparse_attribute(path):
        return reparse_regular if path == archive else original_lstat(path)

    def open_and_close_if_accepted():
        handle, _opened = restore._open_regular_file(archive)
        handle.close()

    monkeypatch.setattr(restore.Path, "lstat", inject_reparse_attribute)

    with pytest.raises(restore.RecoveryError):
        open_and_close_if_accepted()


@pytest.mark.parametrize(
    ("manifest_changes", "secret"),
    [
        ({"created_at": None}, ""),
        ({"created_at": "now"}, "now"),
        ({"database_recovery_point": "rp\ninjected"}, "injected"),
        ({"database_recovery_point": "rp with spaces"}, "rp with spaces"),
        ({"database_recovery_point": "rp\x1b[31m"}, "31m"),
    ],
)
def test_restore_rejects_noncanonical_recovery_metadata_without_echo(
    tmp_path, manifest_changes, secret
):
    archive = tmp_path / "uploads.tar"
    manifest = tmp_path / "uploads.json"
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    write_archive(archive, [("document.pdf", b"bytes", None)])
    write_manifest(
        manifest,
        manifest_for(archive, [("document.pdf", b"bytes")], **manifest_changes),
    )

    result = run_script(
        RESTORE_SCRIPT,
        "--archive-path", archive,
        "--manifest-path", manifest,
        "--scratch-upload-dir", scratch,
    )

    assert result.returncode != 0
    assert list(scratch.iterdir()) == []
    if secret:
        assert secret not in result.stdout + result.stderr


def test_restore_rejects_manifest_over_byte_limit_without_extraction(tmp_path, monkeypatch):
    archive = tmp_path / "uploads.tar"
    manifest = tmp_path / "uploads.json"
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    write_archive(archive, [("document.pdf", b"bytes", None)])
    write_manifest(manifest, manifest_for(archive, [("document.pdf", b"bytes")]))
    restore = load_script(RESTORE_SCRIPT, "restore_upload_bundle_manifest_limit")
    monkeypatch.setattr(restore.safety, "MAX_MANIFEST_BYTES", 16)

    with pytest.raises(restore.RecoveryError):
        restore.restore_bundle(archive, manifest, scratch)

    assert list(scratch.iterdir()) == []


@pytest.mark.parametrize(
    ("limit_name", "limit", "files"),
    [
        ("MAX_ENTRIES", 0, [("a", b"a")]),
        ("MAX_PATH_UTF8_BYTES", 3, [("long", b"a")]),
        ("MAX_COMPONENT_UTF8_BYTES", 3, [("long", b"a")]),
        ("MAX_MEMBER_BYTES", 0, [("a", b"a")]),
        ("MAX_TOTAL_BYTES", 1, [("a", b"a"), ("b", b"b")]),
    ],
)
def test_restore_enforces_explicit_resource_limits(
    tmp_path, monkeypatch, limit_name, limit, files
):
    archive = tmp_path / "uploads.tar"
    manifest = tmp_path / "uploads.json"
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    write_archive(archive, [(name, content, None) for name, content in files])
    write_manifest(manifest, manifest_for(archive, files))
    restore = load_script(RESTORE_SCRIPT, f"restore_limit_{limit_name}")
    monkeypatch.setattr(restore.safety, limit_name, limit)

    with pytest.raises(restore.RecoveryError):
        restore.restore_bundle(archive, manifest, scratch)

    assert list(scratch.iterdir()) == []


def test_restore_rejects_compressed_archive_without_extraction(tmp_path):
    archive = tmp_path / "uploads.tar.gz"
    manifest = tmp_path / "uploads.json"
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with tarfile.open(archive, "w:gz") as compressed:
        info = tarfile.TarInfo("document.pdf")
        info.size = 5
        compressed.addfile(info, io.BytesIO(b"bytes"))
    write_manifest(manifest, manifest_for(archive, [("document.pdf", b"bytes")]))

    result = run_script(
        RESTORE_SCRIPT,
        "--archive-path", archive,
        "--manifest-path", manifest,
        "--scratch-upload-dir", scratch,
    )

    assert result.returncode != 0
    assert list(scratch.iterdir()) == []


def test_restore_failure_after_extraction_leaves_scratch_empty(tmp_path, monkeypatch):
    archive = tmp_path / "uploads.tar"
    manifest = tmp_path / "uploads.json"
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    write_archive(archive, [("nested/document.pdf", b"bytes", None)])
    write_manifest(manifest, manifest_for(archive, [("nested/document.pdf", b"bytes")]))
    restore = load_script(RESTORE_SCRIPT, "restore_upload_bundle_late_failure")
    original_hash = restore._sha256_open_file
    calls = 0

    def mutate_digest_after_extraction(handle):
        nonlocal calls
        calls += 1
        digest = original_hash(handle)
        return "0" * 64 if calls >= 6 else digest

    monkeypatch.setattr(restore, "_sha256_open_file", mutate_digest_after_extraction)

    with pytest.raises(restore.RecoveryError):
        restore.restore_bundle(archive, manifest, scratch)

    assert list(scratch.iterdir()) == []


def test_restore_rejects_scratch_path_swap_without_external_write(tmp_path, monkeypatch):
    archive = tmp_path / "uploads.tar"
    manifest = tmp_path / "uploads.json"
    scratch = tmp_path / "scratch"
    original_scratch = tmp_path / "scratch-original"
    scratch.mkdir()
    write_archive(archive, [("nested/document.pdf", b"bytes", None)])
    write_manifest(manifest, manifest_for(archive, [("nested/document.pdf", b"bytes")]))
    restore = load_script(RESTORE_SCRIPT, "restore_upload_bundle_scratch_swap")
    original_mkdir = restore.Path.mkdir
    swapped = False

    def swap_scratch_on_nested_mkdir(path, *args, **kwargs):
        nonlocal swapped
        if path.name == "nested" and not swapped:
            swapped = True
            scratch.rename(original_scratch)
            original_mkdir(scratch)
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(restore.Path, "mkdir", swap_scratch_on_nested_mkdir)

    with pytest.raises(restore.RecoveryError):
        restore.restore_bundle(archive, manifest, scratch)

    assert list(scratch.iterdir()) == []
    incomplete = list(original_scratch.iterdir())
    assert len(incomplete) == 1
    assert incomplete[0].name.startswith(".simo-restore-incomplete-")
    assert incomplete[0].is_dir()


def test_restore_creates_files_with_private_permissions(tmp_path):
    archive = tmp_path / "uploads.tar"
    manifest = tmp_path / "uploads.json"
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    write_archive(archive, [("document.pdf", b"bytes", None)])
    write_manifest(manifest, manifest_for(archive, [("document.pdf", b"bytes")]))

    result = run_script(
        RESTORE_SCRIPT,
        "--archive-path", archive,
        "--manifest-path", manifest,
        "--scratch-upload-dir", scratch,
    )

    assert result.returncode == 0, result.stderr
    restored_mode = stat.S_IMODE((scratch / "document.pdf").stat().st_mode)
    if os.name == "nt":
        # The Windows CRT reports writable files as 0666 even after chmod(0600).
        assert restored_mode == 0o666
    else:
        assert restored_mode == 0o600


def test_restore_publishes_multiple_top_level_entries_atomically(tmp_path):
    archive = tmp_path / "uploads.tar"
    manifest = tmp_path / "uploads.json"
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    files = [("a.txt", b"a"), ("nested/b.txt", b"b")]
    write_archive(archive, [(name, content, None) for name, content in files])
    write_manifest(manifest, manifest_for(archive, files))

    result = run_script(
        RESTORE_SCRIPT,
        "--archive-path", archive,
        "--manifest-path", manifest,
        "--scratch-upload-dir", scratch,
    )

    assert result.returncode == 0, result.stderr
    assert (scratch / "a.txt").read_bytes() == b"a"
    assert (scratch / "nested" / "b.txt").read_bytes() == b"b"


def test_restore_stages_on_scratch_volume_before_publication(tmp_path, monkeypatch):
    archive = tmp_path / "uploads.tar"
    manifest = tmp_path / "uploads.json"
    scratch = tmp_path / "mounted-scratch"
    scratch.mkdir()
    files = [("a.txt", b"a"), ("nested/b.txt", b"b")]
    write_archive(archive, [(name, content, None) for name, content in files])
    write_manifest(manifest, manifest_for(archive, files))
    restore = load_script(RESTORE_SCRIPT, "restore_upload_bundle_same_volume")
    original_link = restore.os.link
    original_rename = restore.os.rename
    publications: list[tuple[Path, Path]] = []

    def require_scratch_volume(operation):
        def checked(source, target, *args, **kwargs):
            source_path = Path(source)
            target_path = Path(target)
            try:
                source_path.relative_to(scratch)
            except ValueError as exc:
                raise OSError(errno.EXDEV, "simulated cross-device publication") from exc
            assert source_path.lstat().st_dev == target_path.parent.lstat().st_dev
            publications.append((source_path, target_path))
            return operation(source, target, *args, **kwargs)

        return checked

    monkeypatch.setattr(restore.os, "link", require_scratch_volume(original_link))
    monkeypatch.setattr(restore.os, "rename", require_scratch_volume(original_rename))

    count, _digest, _recovery_point = restore.restore_bundle(
        archive, manifest, scratch
    )

    assert count == 2
    assert publications
    assert sorted(path.relative_to(scratch).as_posix() for path in scratch.rglob("*")) == [
        "a.txt",
        "nested",
        "nested/b.txt",
    ]


def _runbook_subsection(heading: str) -> str:
    text = RUNBOOK.read_text(encoding="utf-8")
    marker = f"### {heading}\n"
    assert marker in text, f"missing runbook subsection: {heading}"
    body = text.split(marker, 1)[1]
    return body.split("\n### ", 1)[0]


def test_runbook_does_not_issue_recovery_actions_before_first_owner_gate():
    recovery = RUNBOOK.read_text(encoding="utf-8").split("## Backup and restore\n", 1)[1]
    pre_gate = recovery.split(
        "### STOP — owner approval before backup/PITR configuration or creation\n",
        1,
    )[0]

    assert "does not authorize an operator action" in pre_gate
    assert not any(
        line.startswith(("Enable ", "Create ", "Retain ", "Restore ", "Upload ", "Delete "))
        for line in pre_gate.splitlines()
    )


@pytest.mark.parametrize(
    ("gate_heading", "required_terms"),
    [
        ("STOP — owner approval before backup/PITR configuration or creation", ("PITR", "backup")),
        ("STOP — owner approval before Google Drive access or upload", ("Drive", "upload")),
        ("STOP — owner approval before paid scratch Railway resources", ("scratch", "create")),
        ("STOP — owner approval before any restore", ("restore", "PITR")),
        ("STOP — owner approval before scratch cleanup", ("cleanup", "delete")),
    ],
)
def test_runbook_has_explicit_fail_closed_owner_gates(gate_heading, required_terms):
    gate = _runbook_subsection(gate_heading)

    assert "Do not proceed" in gate
    assert "written owner approval" in gate
    assert all(term.casefold() in gate.casefold() for term in required_terms)


@pytest.mark.parametrize(
    ("phase_heading", "variable_prefix"),
    [
        ("Independent SHA-256 verification before Google Drive upload", "$Recovery"),
        ("Independent SHA-256 verification before restore or use", "$DownloadedRecovery"),
    ],
)
def test_runbook_independently_hashes_every_recovery_artifact_in_each_phase(
    phase_heading, variable_prefix
):
    phase = _runbook_subsection(phase_heading)

    for artifact_suffix in (
        "Archive",
        "Manifest",
        "Dump",
        "CorrelationEvidence",
    ):
        artifact_variable = f"{variable_prefix}{artifact_suffix}"
        assert (
            f"Get-FileHash -LiteralPath {artifact_variable} -Algorithm SHA256 "
            "| Select-Object -ExpandProperty Hash"
        ) in phase
    assert "approved out-of-band hash evidence" in phase
    assert "manifest's `archive_sha256`" in phase
    assert "must not" in phase
    assert "SIMO OS Recovery / Staging / Sprint 019" not in phase


def test_runbook_rebinds_downloaded_artifacts_before_restore_hashing():
    phase = _runbook_subsection(
        "Independent SHA-256 verification before restore or use"
    )

    assert (
        "Remove-Variable -Name DownloadedRecoveryArchive,DownloadedRecoveryManifest,"
        "DownloadedRecoveryDump,DownloadedRecoveryCorrelationEvidence,"
        "DownloadedRecoveryDirectory -ErrorAction SilentlyContinue"
    ) in phase
    assert "$DownloadedRecoveryDirectory = Read-HiddenLiteralPath" in phase
    for suffix in ("Archive", "Manifest", "Dump", "CorrelationEvidence"):
        downloaded = f"$DownloadedRecovery{suffix}"
        source = f"$Recovery{suffix}"
        assert f"{downloaded} = Read-HiddenLiteralPath" in phase
        assert (
            f"Get-FileHash -LiteralPath {downloaded} -Algorithm SHA256 "
            "| Select-Object -ExpandProperty Hash"
        ) in phase
        assert source not in "\n".join(
            line for line in phase.splitlines() if line.startswith("Get-FileHash")
        )
    assert "GetFullPath" in phase
    assert "GetDirectoryName" in phase
    assert "download directory" in phase.casefold()
    assert "source recovery path" in phase.casefold()
    assert "STOP" in phase


def test_runbook_uses_hidden_history_safe_literal_path_input():
    phase = _runbook_subsection(
        "Independent SHA-256 verification before Google Drive upload"
    )

    assert "Read-Host" in phase
    assert "-AsSecureString" in phase
    assert "PtrToStringBSTR" in phase
    assert "ZeroFreeBSTR" in phase
    assert "PowerShell history" in phase
