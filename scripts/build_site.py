#!/usr/bin/env python3
"""Render the Markdown documentation into a static HTML site.

    python scripts/task.py site        # or: python scripts/build_site.py

Output goes to ``site/`` and is fully self-contained: the CSS is inlined, there
is no JavaScript and nothing is fetched from the network, so ``site/index.html``
opens straight from a clone, offline.

``--extra-section DIR`` renders a separately maintained set of pages from that
directory in front of the documentation. It is repeatable; pair each one with
``--extra-title`` in the same order to name it in the navigation.

Markdown stays the source of truth — never edit the generated HTML.
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
OUTPUT = ROOT / "site"

# Import Markdown from the backend virtualenv when the script is run with a
# bare interpreter, so `python scripts/build_site.py` works too.
try:
    import markdown
except ModuleNotFoundError:  # pragma: no cover - depends on how it was started
    for candidate in BACKEND.glob(".venv/lib/python*/site-packages"):
        sys.path.insert(0, str(candidate))
    try:
        import markdown
    except ModuleNotFoundError:
        raise SystemExit(
            "The 'markdown' package is missing.\n"
            "  Install the backend dev dependencies first:\n"
            "      python scripts/task.py setup"
        ) from None


@dataclass(frozen=True)
class Page:
    source: Path  # markdown file, relative to the repository root
    target: Path  # html file, relative to the output directory
    section: str  # directory the page came from
    label: str  # short label for the navigation
    badge: str = ""  # small marker in front of the label


def _pages(section: str, entries: list[tuple[str, str, str]]) -> list[Page]:
    """Build the page list from (stem, label, badge) triples."""
    return [
        Page(
            source=Path(section) / f"{stem}.md",
            target=Path(section) / f"{'index' if stem == 'README' else stem}.html",
            section=section,
            label=label,
            badge=badge,
        )
        for stem, label, badge in entries
    ]


#: Additional (title, pages) groups rendered in front of the documentation.
EXTRA_GROUPS: list[tuple[str, list[Page]]] = []


def extra_pages() -> list[Page]:
    return [page for _, pages in EXTRA_GROUPS for page in pages]


def group_title_of(page: Page) -> str:
    for title, pages in EXTRA_GROUPS:
        if any(item.target == page.target for item in pages):
            return title
    return "Documentation"


def discover(section: Path) -> list[Page]:
    """Every Markdown file in ``section``, ordered by filename.

    ``README.md`` becomes the section index; a leading number in the filename
    (``01-foo.md``) becomes the small marker shown next to the label.
    """
    pages: list[Page] = []
    for source in sorted((ROOT / section).glob("*.md")):
        stem = source.stem
        if stem.startswith("_") or stem == "TEMPLATE":
            continue
        title = page_title(source.read_text(encoding="utf-8"), stem)
        label = title.split("—")[-1].strip() if "—" in title else title
        badge = stem.split("-")[0] if stem[:1].isdigit() else ""
        pages.append(
            Page(
                source=section / source.name,
                target=section / f"{'index' if stem == 'README' else stem}.html",
                section=section.as_posix(),
                label=label,
                badge=badge.lstrip("0") or "0" if badge else "",
            )
        )
    pages.sort(key=lambda item: (item.source.name != "README.md", item.source.name))
    return pages


DOCS = _pages(
    "docs",
    [
        ("architecture", "Architecture", ""),
        ("domain-model", "Domain model", ""),
        ("order-state-machine", "Order state machine", ""),
        ("api-overview", "API overview", ""),
        ("business-goals-and-acceptance", "Requirements", ""),
        ("testing-guide", "Testing guide", ""),
        ("performance", "Performance tooling", ""),
    ],
)

PAGES = DOCS

STYLESHEET = (Path(__file__).resolve().parent / "site_style.css").read_text(
    encoding="utf-8"
)


def markdown_renderer():
    return markdown.Markdown(
        extensions=["tables", "fenced_code", "sane_lists", "attr_list", "md_in_html"],
        output_format="html",
    )


def page_title(text: str, fallback: str) -> str:
    match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else fallback


def rewrite_links(body: str, page: Page) -> str:
    """Point Markdown links at the generated HTML instead of the .md sources."""
    known = {str(item.source): item.target for item in PAGES}

    def replace(match: re.Match[str]) -> str:
        href = match.group(1)
        if href.startswith(("http://", "https://", "#", "mailto:")):
            return match.group(0)

        # Resolve the link relative to the directory of the source file.
        anchor = ""
        if "#" in href:
            href, anchor = href.split("#", 1)
            anchor = "#" + anchor
        if not href:
            return match.group(0)

        resolved = (page.source.parent / href).resolve()
        try:
            key = str(resolved.relative_to(ROOT))
        except ValueError:
            return match.group(0)

        if key in known:
            relative = _relative(page.target, known[key])
            return f'href="{relative}{anchor}"'
        if key == "README.md":
            return f'href="../index.html{anchor}"'
        # Anything else (source files) stays a link into the repository tree.
        depth = len(page.target.parts) - 1
        return f'href="{"../" * (depth + 1)}{key}{anchor}"'

    return re.sub(r'href="([^"]+)"', replace, body)


def _relative(from_target: Path, to_target: Path) -> str:
    """Relative href from one generated page to another."""
    up = "../" * (len(from_target.parts) - 1)
    return up + "/".join(to_target.parts)


def navigation(current: Page | None) -> str:
    groups = [*EXTRA_GROUPS, ("Documentation", DOCS)]
    base = current.target if current else Path("index.html")
    out = []
    for title, pages in groups:
        links = []
        for page in pages:
            classes = (
                "nav-link current"
                if current and page.target == current.target
                else "nav-link"
            )
            badge = (
                f'<span class="nav-badge">{html.escape(page.badge)}</span>'
                if page.badge
                else ""
            )
            links.append(
                f'<a class="{classes}" href="{_relative(base, page.target)}">'
                f"{badge}<span>{html.escape(page.label)}</span></a>"
            )
        out.append(
            f'<div class="nav-group"><p class="nav-title">{title}</p>'
            f'<div class="nav-links">{"".join(links)}</div></div>'
        )
    return "".join(out)


def pager(page: Page) -> str:
    order = [item for item in PAGES if item.section == page.section]
    index = order.index(page)
    previous = order[index - 1] if index > 0 else None
    following = order[index + 1] if index < len(order) - 1 else None
    parts = []
    if previous:
        parts.append(
            f'<a href="{_relative(page.target, previous.target)}">'
            f'<span class="dir">← Previous</span>{html.escape(previous.label)}</a>'
        )
    if following:
        parts.append(
            f'<a class="next" href="{_relative(page.target, following.target)}">'
            f'<span class="dir">Next →</span>{html.escape(following.label)}</a>'
        )
    return f'<nav class="pager">{"".join(parts)}</nav>' if parts else ""


def wrap(title: str, page: Page | None, body: str, eyebrow: str = "") -> str:
    base = page.target if page else Path("index.html")
    up = "../" * (len(base.parts) - 1)
    eyebrow_html = f'<p class="eyebrow">{html.escape(eyebrow)}</p>' if eyebrow else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · Alya-FIIT</title>
<style>{STYLESHEET}</style>
</head>
<body>
<div class="layout">
<aside class="sidebar">
  <a class="brand" href="{up}index.html">Alya<span>FIIT</span></a>
  <p class="brand-sub">Documentation</p>
  {navigation(page)}
</aside>
<main class="content">
<article class="page">
{eyebrow_html}
{body}
{pager(page) if page else ""}
<footer class="site">
  Generated from the Markdown sources — edit those, then run
  <code>python scripts/task.py site</code>.
</footer>
</article>
</main>
</div>
</body>
</html>
"""


def add_table_wrappers(body: str) -> str:
    """Let wide tables scroll instead of breaking the layout."""
    return body.replace("<table>", '<div class="table-wrap"><table>').replace(
        "</table>", "</table></div>"
    )


def build_index() -> str:
    doc_links = "".join(
        f'<li><a href="{"/".join(page.target.parts)}">{html.escape(page.label)}</a></li>'
        for page in DOCS
    )
    intro = """
<h1>Alya-FIIT</h1>
<p>Alya-FIIT is an electronics e-shop with an integrated warehouse back office.
These pages are the project documentation: architecture, domain rules, the order
lifecycle, the API, the product requirements and the tooling around tests and
performance.</p>
"""
    sections = []
    for title, pages in EXTRA_GROUPS:
        cards = []
        for page in pages:
            if page.target.name == "index.html":
                continue  # the section index is reached through the navigation
            number = (
                f'<div class="card-num">{html.escape(page.badge)}</div>'
                if page.badge
                else ""
            )
            cards.append(
                f'<a class="card" href="{"/".join(page.target.parts)}">'
                f'{number}<div class="card-title">{html.escape(page.label)}</div></a>'
            )
        if cards:
            sections.append(
                f"<h2>{html.escape(title)}</h2>"
                f'<div class="card-grid">{"".join(cards)}</div>'
            )
    extra_section = "\n".join(sections)
    body = f"""
{intro}
{extra_section}
<h2>Documentation</h2>
<ul>{doc_links}</ul>

<h2>Quick reference</h2>
<div class="table-wrap"><table>
<thead><tr><th>Command</th><th>What it does</th></tr></thead>
<tbody>
<tr><td><code>python scripts/task.py --list</code></td><td>Every available target</td></tr>
<tr><td><code>python scripts/task.py seed-small</code></td><td>Reset and reload the development dataset</td></tr>
<tr><td><code>python scripts/task.py test</code></td><td>Unit, integration and E2E tests</td></tr>
<tr><td><code>python scripts/task.py lint</code></td><td>Ruff, mypy, Bandit, ESLint, tsc</td></tr>
<tr><td><code>python scripts/task.py metrics</code></td><td>Radon complexity and maintainability</td></tr>
<tr><td><code>python scripts/task.py benchmark-report</code></td><td>Performance benchmark (needs the large dataset)</td></tr>
</tbody>
</table></div>
"""
    return wrap("Alya-FIIT", None, body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the documentation to HTML")
    parser.add_argument("--output", type=Path, default=OUTPUT, help="output directory")
    parser.add_argument(
        "--extra-section",
        type=Path,
        action="append",
        default=None,
        metavar="DIR",
        help="directory with additional Markdown pages to render before the docs "
        "(repeatable)",
    )
    parser.add_argument(
        "--extra-title",
        action="append",
        default=None,
        metavar="TITLE",
        help="heading for the matching --extra-section, in the same order",
    )
    args = parser.parse_args(argv)

    global PAGES
    sections = args.extra_section or []
    titles = args.extra_title or []
    if len(titles) > len(sections):
        raise SystemExit("--extra-title given more times than --extra-section")

    for index, section in enumerate(sections):
        if not (ROOT / section).is_dir():
            raise SystemExit(f"--extra-section: no such directory: {section}")
        title = titles[index] if index < len(titles) else "Guides"
        EXTRA_GROUPS.append((title, discover(section)))
    if EXTRA_GROUPS:
        PAGES = extra_pages() + DOCS

    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    for page in PAGES:
        (output / page.target).parent.mkdir(parents=True, exist_ok=True)

    renderer = markdown_renderer()
    for page in PAGES:
        source = ROOT / page.source
        if not source.exists():
            raise SystemExit(f"missing source file: {page.source}")
        text = source.read_text(encoding="utf-8")
        renderer.reset()
        body = renderer.convert(text)
        body = add_table_wrappers(body)
        body = rewrite_links(body, page)
        title = page_title(text, page.label)
        if page.section == "docs":
            eyebrow = "Documentation"
        elif page.badge:
            eyebrow = f"{group_title_of(page).rstrip('s')} {page.badge}"
        else:
            eyebrow = group_title_of(page)
        (output / page.target).write_text(
            wrap(title, page, body, eyebrow), encoding="utf-8"
        )

    (output / "index.html").write_text(build_index(), encoding="utf-8")

    count = len(PAGES) + 1
    print(f"generated {count} pages in {output}")
    print(f"open {output / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
