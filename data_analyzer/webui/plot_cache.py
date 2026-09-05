"""Shared helpers for cached HTML plot pages."""

from datetime import datetime
from pathlib import Path


CACHE_BANNER_STYLE = (
    'font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;'
    'font-size: 14px;'
    'font-weight: 600;'
    'color: #333;'
    'background: #f7f8fa;'
    'border-bottom: 1px solid #e4e8ee;'
    'padding: 10px 16px;'
    'margin: 0;'
)


def format_cache_stamp(cached_at=None):
    if isinstance(cached_at, datetime):
        moment = cached_at
    elif isinstance(cached_at, str) and cached_at.strip():
        text = cached_at.strip()
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S'):
            try:
                moment = datetime.strptime(text, fmt)
                break
            except ValueError:
                moment = None
        else:
            moment = datetime.now()
    else:
        moment = datetime.now()
    return moment.strftime('%Y-%m-%d -> %H:%M:%S')


def cache_banner_html(cached_at=None):
    stamp = format_cache_stamp(cached_at)
    return (
        f'<div id="cache-banner" style="{CACHE_BANNER_STYLE}">'
        f'Cached: {stamp}'
        f'</div>'
    )


def inject_cache_banner(html_path, cached_at=None):
    path = Path(html_path)
    if not path.exists():
        return False

    html = path.read_text(encoding='utf-8')
    banner = cache_banner_html(cached_at)

    if 'id="cache-banner"' in html:
        import re
        html = re.sub(
            r'<div id="cache-banner"[^>]*>.*?</div>',
            banner,
            html,
            count=1,
            flags=re.DOTALL,
        )
    elif '<body>' in html:
        html = html.replace('<body>', f'<body>\n{banner}', 1)
    elif '<body ' in html.lower():
        import re
        html = re.sub(
            r'(<body[^>]*>)',
            rf'\1\n{banner}',
            html,
            count=1,
            flags=re.IGNORECASE,
        )
    else:
        html = banner + html

    path.write_text(html, encoding='utf-8')
    return True
