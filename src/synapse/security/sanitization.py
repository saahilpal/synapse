from __future__ import annotations

import re
from urllib.parse import urlparse

from markdown_it import MarkdownIt

# Whitelisted schemes
SAFE_SCHEMES = {"http", "https", "file", "git"}

# Match href and src attributes in HTML
HREF_RE = re.compile(r'href=["\']([^"\']*)["\']', re.IGNORECASE)
SRC_RE = re.compile(r'src=["\']([^"\']*)["\']', re.IGNORECASE)


class SafeMarkdownRenderer:
    """Renders untrusted markdown to secure HTML, preventing XSS and link injections."""

    def __init__(self) -> None:
        self.md = MarkdownIt()
        self.md.options["html"] = False

    def render(self, content: str) -> str:
        if not content:
            return ""

        # Render markdown to HTML (safely escaping raw HTML elements)
        rendered_html = self.md.render(content)

        # Sanitize link targets
        def sanitize_href(match: re.Match[str]) -> str:
            url = match.group(1)
            if self._is_safe_url(url):
                return match.group(0)
            return 'href="#"'

        def sanitize_src(match: re.Match[str]) -> str:
            url = match.group(1)
            if self._is_safe_url(url):
                return match.group(0)
            return 'src="#"'

        rendered_html = HREF_RE.sub(sanitize_href, rendered_html)
        rendered_html = SRC_RE.sub(sanitize_src, rendered_html)

        return rendered_html

    def _is_safe_url(self, url: str) -> bool:
        if not url:
            return True
        # Trim whitespace
        url = url.strip()
        # Prevent javascript: protocol
        if url.lower().startswith("javascript:"):
            return False
        try:
            parsed = urlparse(url)
            if not parsed.scheme:
                # Relative link or anchor
                return True
            return parsed.scheme.lower() in SAFE_SCHEMES
        except Exception:
            return False
