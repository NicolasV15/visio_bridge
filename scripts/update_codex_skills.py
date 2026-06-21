#!/usr/bin/env python3
"""Sync this repo's Codex skills into the local Codex skills directory."""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from urllib.parse import quote, urlencode
from pathlib import Path

DEFAULT_REPO = "NicolasV15/visio_bridge"
DEFAULT_REF = "main"

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_SKILLS_ROOT = REPO_ROOT / "skills"
DEFAULT_DEST = Path.home() / ".codex" / "skills"


class UpdateError(RuntimeError):
    """Raised when a skill sync cannot complete."""


def _discover_skills() -> list[str]:
    if not LOCAL_SKILLS_ROOT.is_dir():
        raise UpdateError(f"Missing skills directory: {LOCAL_SKILLS_ROOT}")

    names = [
        entry.name
        for entry in LOCAL_SKILLS_ROOT.iterdir()
        if entry.is_dir() and (entry / "SKILL.md").is_file()
    ]
    if not names:
        raise UpdateError(f"No skills found under {LOCAL_SKILLS_ROOT}")
    return sorted(names)


def _skill_files(skill_name: str) -> list[Path]:
    skill_dir = LOCAL_SKILLS_ROOT / skill_name
    if not skill_dir.is_dir():
        raise UpdateError(f"Unknown skill: {skill_name}")
    return sorted(path for path in skill_dir.rglob("*") if path.is_file())


def _github_contents_url(repo: str, ref: str, rel_path: Path) -> str:
    query = urlencode({"ref": ref})
    return (
        f"https://api.github.com/repos/{repo}/contents/"
        f"{quote(rel_path.as_posix(), safe='/')}?{query}"
    )


def _fetch_github_file(repo: str, ref: str, rel_path: Path) -> bytes:
    request = urllib.request.Request(
        _github_contents_url(repo, ref, rel_path),
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "visio-bridge-skill-sync",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise UpdateError(
            f"Failed to fetch {rel_path.as_posix()} from {repo}@{ref}: HTTP {exc.code}"
        ) from exc
    except urllib.error.URLError as exc:
        raise UpdateError(
            f"Failed to fetch {rel_path.as_posix()} from {repo}@{ref}: {exc.reason}"
        ) from exc

    if payload.get("type") != "file":
        raise UpdateError(f"Remote path is not a file: {rel_path.as_posix()}")

    encoding = payload.get("encoding")
    content = payload.get("content", "")
    if encoding != "base64" or not content:
        raise UpdateError(f"Unexpected payload for {rel_path.as_posix()}")

    return base64.b64decode(content.encode("ascii"))


def _stage_skill(repo: str, ref: str, skill_name: str, stage_root: Path) -> Path:
    staged_skill_root = stage_root / skill_name
    skill_dir = LOCAL_SKILLS_ROOT / skill_name
    for local_file in _skill_files(skill_name):
        rel_inside_skill = local_file.relative_to(skill_dir)
        remote_rel = Path("skills") / skill_name / rel_inside_skill
        target = staged_skill_root / rel_inside_skill
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_fetch_github_file(repo, ref, remote_rel))
    return staged_skill_root


def _install_staged_skill(staged_skill_root: Path, dest_root: Path, skill_name: str) -> Path:
    dest_dir = dest_root / skill_name
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    shutil.copytree(staged_skill_root, dest_dir)
    return dest_dir


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Codex skills from GitHub.")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="owner/repo")
    parser.add_argument("--ref", default=DEFAULT_REF, help="Git tag, branch, or commit")
    parser.add_argument(
        "--dest",
        default=str(DEFAULT_DEST),
        help="Destination Codex skills directory",
    )
    parser.add_argument(
        "--skills",
        nargs="*",
        help="Specific skills to sync; defaults to all skills in this repo",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    try:
        skill_names = args.skills or _discover_skills()
        dest_root = Path(args.dest).expanduser()
        dest_root.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="codex-skill-sync-") as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)
            staged_roots: list[tuple[str, Path]] = []
            for skill_name in skill_names:
                staged_roots.append(
                    (skill_name, _stage_skill(args.repo, args.ref, skill_name, tmp_dir))
                )

            installed = []
            for skill_name, staged_skill_root in staged_roots:
                installed.append(
                    _install_staged_skill(staged_skill_root, dest_root, skill_name)
                )

        for dest_dir in installed:
            print(f"Installed {dest_dir.name} to {dest_dir}")
        return 0
    except UpdateError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
