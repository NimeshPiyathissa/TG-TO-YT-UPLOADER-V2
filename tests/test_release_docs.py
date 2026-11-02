"""Release checks for the documentation: links, anchors, images, placeholders, version.

Runs in CI so a renamed heading or a moved file can't silently break the README or the guides.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = sorted([ROOT / "README.md", ROOT / "CHANGELOG.md", ROOT / "CONTRIBUTING.md", ROOT / "SECURITY.md",
               ROOT / "THIRD_PARTY_NOTICES.md", *(ROOT / "docs").glob("*.md")])
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)|(?:href|src)=\"([^\"]+)\"")
FENCE = re.compile(r"^\s*(```|~~~)")


def without_code(text: str) -> str:
    """Markdown text with fenced code blocks and inline code removed (links there aren't rendered)."""
    out, fenced = [], False
    for line in text.splitlines():
        if FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            out.append(re.sub(r"`[^`]*`", "", line))
    return "\n".join(out)


def github_anchors(path: Path) -> set[str]:
    """Anchors GitHub generates for a Markdown file's headings, plus explicit <a id="..."> anchors."""
    text = path.read_text(encoding="utf-8")
    anchors = set(re.findall(r"<a id=\"([^\"]+)\"", text))
    seen: dict[str, int] = {}
    fenced = False
    for line in text.splitlines():
        if FENCE.match(line):
            fenced = not fenced
            continue
        m = None if fenced else re.match(r"^#{1,6}\s+(.*?)\s*#*\s*$", line)
        if not m:
            continue
        title = re.sub(r"<[^>]+>", "", m.group(1))
        title = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", title)
        slug = re.sub(r"[^\w\- ]", "", title.strip().lower()).replace(" ", "-")
        n = seen.get(slug, 0)
        seen[slug] = n + 1
        anchors.add(slug if n == 0 else f"{slug}-{n}")
    return anchors


def links(path: Path) -> list[str]:
    return [a or b for a, b in LINK.findall(without_code(path.read_text(encoding="utf-8")))]


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_relative_links_and_anchors_resolve(doc: Path):
    broken = []
    for target in links(doc):
        if re.match(r"^[a-z]+:", target):              # http(s):, mailto:, tg: ...
            continue
        file_part, _, anchor = target.partition("#")
        dest = (doc.parent / file_part).resolve() if file_part else doc
        if not dest.exists():
            broken.append(f"{target}: no such file")
        elif anchor and dest.suffix == ".md" and anchor not in github_anchors(dest):
            broken.append(f"{target}: no heading with anchor #{anchor}")
    assert not broken, "\n".join(broken)


def test_readme_starts_with_the_saas_thumbnail():
    first = next(line for line in (ROOT / "README.md").read_text(encoding="utf-8").splitlines() if line.strip())
    assert first == "![TG → YT Uploader V2 SaaS Preview](docs/images/saas-thumbnail-youtube.png)"
    image = ROOT / "docs" / "images" / "saas-thumbnail-youtube.png"
    assert image.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_no_unfilled_placeholders():
    leftovers = []
    for path in [*DOCS, ROOT / "install.sh", ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml"]:
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"__[A-Z_]{4,}__", line) and "!= *__GITHUB_REPO__*" not in line:   # install.sh's own guard
                leftovers.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()}")
    assert not leftovers, "\n".join(leftovers)


def test_installer_default_repository_is_configured():
    text = (ROOT / "install.sh").read_text(encoding="utf-8")
    url = re.search(r'TGYT_REPO_URL="\$\{TGYT_REPO_URL:-([^}]+)\}"', text).group(1)
    assert url == "https://github.com/NimeshPiyathissa/TG-TO-YT-UPLOADER-V2.git"
    assert "__GITHUB_REPO__" not in url                 # otherwise the guard stops every one-line install


def test_version_matches_latest_changelog_release():
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    released = re.findall(r"^## \[(\d+\.\d+\.\d+)\]", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), re.M)
    assert released and released[0] == version
    assert f"release-v{version}-" in (ROOT / "README.md").read_text(encoding="utf-8")


# SHA-256 of the maintainer's staging domain and IP. Only hashes are kept here, so the values themselves are never published.
STAGING_HASHES = {
    "c750d4481941a75e14530df6d168a2d68deff918b1956111cf06eef95ece16f8",
    "5c0f8355006fd47e8a2050b3ed519aa7a439c89ffab0ba4f7bb2e536ac8654ea",
}
CANDIDATE = re.compile(r"\b(?:\d{1,3}(?:\.\d{1,3}){3}|(?:[a-z0-9-]+\.)+[a-z]{2,})\b", re.I)


def test_no_staging_environment_details_in_published_files():
    """Docs use placeholders (example.com, 203.0.113.10); the maintainer's own test server must not leak into them."""
    hits = []
    for p in [*DOCS, ROOT / ".env.example", ROOT / "deploy" / "install.conf.example"]:
        for token in set(CANDIDATE.findall(p.read_text(encoding="utf-8"))):
            # a hostname can appear as a suffix: upload.<domain> must match the domain's hash too
            parts = token.lower().split(".")
            for i in range(len(parts) - 1):
                if hashlib.sha256(".".join(parts[i:]).encode()).hexdigest() in STAGING_HASHES:
                    hits.append(f"{p.relative_to(ROOT)}: a staging host/IP")
    assert not hits, "\n".join(sorted(set(hits)))
