"""Извлечение видимого текста и ссылок из HTML."""

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

_BLOCK_TAGS = frozenset({
    "address", "article", "aside", "blockquote", "dd", "div", "dl", "dt",
    "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header",
    "li", "main", "nav", "ol", "p", "pre", "section", "table", "tr", "ul",
})
_IGNORED_TAGS = frozenset({"script", "style", "template", "noscript", "svg"})


def normalize_text(value: str) -> str:
    """Свернуть HTML-пробелы, сохранив границы абзацев."""
    lines = []
    for raw_line in re.split(r"\n+", value.replace("\r", "\n")):
        line = " ".join(raw_line.split())
        if line:
            lines.append(line)
    return "\n".join(lines)


class _Extractor(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.parts = []
        self.links = []
        self._link_ids = {}
        self._ignored = 0
        self._anchors = []

    def _reference(self, href):
        if not isinstance(href, str) or not href.strip():
            return None
        try:
            target = urljoin(self.base_url, href.strip())
            parts = urlsplit(target)
            if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
                return None
        except ValueError:
            return None
        if target not in self._link_ids:
            self._link_ids[target] = len(self.links) + 1
            self.links.append(target)
        return self._link_ids[target]

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _IGNORED_TAGS:
            self._ignored += 1
            return
        if self._ignored:
            return
        if tag in _BLOCK_TAGS or tag == "br":
            self.parts.append("\n")
        if tag == "a":
            attributes = dict(attrs)
            self._anchors.append(self._reference(attributes.get("href")))

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _IGNORED_TAGS:
            self._ignored = max(0, self._ignored - 1)
            return
        if self._ignored:
            return
        if tag == "a" and self._anchors:
            reference = self._anchors.pop()
            if reference is not None:
                prefix = "" if not self.parts or self.parts[-1].endswith("\n") else " "
                self.parts.append(f"{prefix}[{reference}]")
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._ignored:
            return
        self.parts.append(data)


def extract_html(source: str, base_url: str) -> tuple[str, list[str]]:
    """Вернуть видимый текст и уникальные HTTP(S)-ссылки по порядку."""
    parser = _Extractor(base_url)
    parser.feed(source)
    parser.close()
    return normalize_text("".join(parser.parts)), parser.links
