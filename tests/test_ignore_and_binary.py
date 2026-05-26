from __future__ import annotations

from pathlib import Path

from synapse.indexer.scanner import RepositoryScanner


def test_gitignore_compliance(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    # Create files
    (repo / "source.py").write_text("print('hello')", encoding="utf-8")
    (repo / "secret.txt").write_text("super secret token", encoding="utf-8")
    (repo / "nested").mkdir()
    (repo / "nested" / "hidden.log").write_text("some log data", encoding="utf-8")
    (repo / "nested" / "keep.py").write_text("pass", encoding="utf-8")

    # Write gitignore
    (repo / ".gitignore").write_text("secret.txt\n*.log\n", encoding="utf-8")

    scanner = RepositoryScanner(repository_path=repo)
    scan = scanner.scan()

    relative_paths = {f.relative_path for f in scan.files}

    assert "source.py" in relative_paths
    assert "nested/keep.py" in relative_paths
    assert "secret.txt" not in relative_paths
    assert "nested/hidden.log" not in relative_paths


def test_binary_file_skipping(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    # Text file
    txt_file = repo / "valid.txt"
    txt_file.write_text("Hello, this is regular text.", encoding="utf-8")

    # Binary by extension
    bin_ext_file = repo / "image.png"
    bin_ext_file.write_bytes(b"some non-null mock png data")

    # Binary by control characters (high density of low bytes)
    bin_content_file = repo / "raw.dat"
    bin_content_file.write_bytes(bytes([1, 2, 3, 4, 5, 0, 7, 8, 9, 11] * 20))

    scanner = RepositoryScanner(repository_path=repo)
    scan = scanner.scan()

    relative_paths = {f.relative_path for f in scan.files}

    assert "valid.txt" in relative_paths
    assert "image.png" not in relative_paths
    assert "raw.dat" not in relative_paths
