"""Worst-channel plot previews for Benchtests MD-brick hover.

Picks the weakest channel from Statistics.yaml (LG / integrator metrics),
maps it to the matching *_Samples HTML under the board folder, and caches a
small PNG thumbnail beside that HTML (parsed via Plotly + kaleido).
"""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

DRIVE_BENCHTESTS = Path('/var/www/html/drive/benchtests')
WEB_BENCHTESTS_PREFIX = '/drive/benchtests'
WEB_BENCHTESTS_ORIGIN = 'https://piro-atlas-lab.fysik.su.se'

# Kaleido/Chrome is not safe to drive from multiple threads; serialize exports.
_PREVIEW_PNG_LOCK = threading.Lock()
_KALEIDO_SYNC_STARTED = False
# In-process cache: avoids re-reading 100KB Statistics.yaml on every hover.
_SLOT_PREVIEW_MEMO = {}
_SLOT_PREVIEW_MEMO_LOCK = threading.Lock()
_SLOT_PREVIEW_MEMO_TTL_S = 300.0

# Hover preview families requested for MD bricks.
PREVIEW_SPECS = (
    {
        'key': 'ADC_Linearity_Samples',
        'label': 'ADC Lin (LG)',
        'file_token': 'ADC_Linearity_Samples',
        'gain': 'LG',
        'stats_var': 'maxdev_lg',
        'worse': 'higher',
    },
    {
        'key': 'CIS_Linearity_Samples',
        'label': 'CIS Lin (LG)',
        'file_token': 'CIS_Linearity_Samples',
        'gain': 'LG',
        'stats_var': 'lg_r2',
        'worse': 'threshold_distance',
    },
    {
        'key': 'CIS_Samples',
        'label': 'CIS Samples (LG)',
        'file_token': 'CIS_Samples',
        'gain': 'LG',
        'stats_var': 'lg_center',
        'worse': 'threshold_distance',
    },
    {
        'key': 'Integrator_Linearity_Samples',
        'label': 'Integrator Lin',
        'file_token': 'Integrator_Linearity_Samples',
        'gain': None,
        'stats_var': 'maxdev',
        'worse': 'higher',
    },
)

_PNG_WIDTH = 900
_PNG_HEIGHT = 560
_CHANNEL_RE = re.compile(r'^CH(\d+)$', re.I)


def board_dir(benchtest_id, serial_no, drive_dir=DRIVE_BENCHTESTS):
    return Path(drive_dir) / f'benchtest_id_{benchtest_id}' / f'DB_{serial_no}'


def statistics_yaml_path(board_path, serial_no):
    return Path(board_path) / f'DBSNo_{serial_no}_PPrGTH_Statistics.yaml'


def plot_filename(serial_no, file_token, md_number, channel_index, gain=None):
    name = f'DBSNo_{serial_no}_PPrGTH_{file_token}_MD{int(md_number)}_CH{int(channel_index)}'
    if gain:
        name += f'_{gain}'
    return name + '.html'


def web_url_for(path, drive_dir=DRIVE_BENCHTESTS, absolute=True):
    path = Path(path)
    try:
        rel = path.resolve().relative_to(Path(drive_dir).resolve())
    except Exception:
        return None
    relative = f'{WEB_BENCHTESTS_PREFIX}/{rel.as_posix()}'
    if absolute:
        return f'{WEB_BENCHTESTS_ORIGIN}{relative}'
    return relative


def hover_previews_sidecar_path(board_path, serial_no, md_number):
    """Tiny JSON index of worst-channel hover plots for one MD (avoids YAML on hover)."""
    return (
        Path(board_path)
        / f'DBSNo_{serial_no}_PPrGTH_hover_previews_MD{int(md_number)}.json'
    )


def save_hover_previews_sidecar(board_path, serial_no, md_number, previews):
    path = hover_previews_sidecar_path(board_path, serial_no, md_number)
    payload = {
        'version': 1,
        'serial_no': serial_no,
        'md': f'MD{int(md_number)}',
        'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'previews': [
            {
                'key': entry.get('key'),
                'label': entry.get('label'),
                'stats_var': entry.get('stats_var'),
                'channel': entry.get('channel'),
                'gain': entry.get('gain'),
                'html': entry.get('html'),
                'png': entry.get('png'),
                'score': entry.get('score'),
                'mean': entry.get('mean'),
            }
            for entry in (previews or [])
        ],
    }
    try:
        path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    except OSError as exc:
        print(f'Error writing hover preview sidecar {path}: {exc}')
        return None
    return path


def load_hover_previews_sidecar(board_path, serial_no, md_number):
    path = hover_previews_sidecar_path(board_path, serial_no, md_number)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        print(f'Error reading hover preview sidecar {path}: {exc}')
        return None
    if payload.get('version') != 1 or not isinstance(payload.get('previews'), list):
        return None
    return payload


def _refresh_preview_flags(entry, board_path, drive_dir=DRIVE_BENCHTESTS):
    """Update has_html / has_png / urls from filenames on disk."""
    board_path = Path(board_path)
    html_name = entry.get('html')
    png_name = entry.get('png')
    entry['has_html'] = False
    entry['has_png'] = False
    entry['can_generate'] = False
    entry['available'] = False
    entry['html_url'] = None
    entry['png_url'] = None

    html_path = (board_path / html_name) if html_name else None
    if html_path is not None and html_path.exists():
        entry['has_html'] = True
        entry['available'] = True
        entry['html_url'] = web_url_for(html_path, drive_dir=drive_dir)
        png_path = html_path.with_suffix('.png')
        if png_path.exists() and png_path.stat().st_size > 0:
            entry['png'] = png_path.name
            entry['png_url'] = web_url_for(png_path, drive_dir=drive_dir)
            entry['has_png'] = True
        else:
            entry['can_generate'] = True
            entry['png'] = None
        return entry

    if png_name:
        png_path = board_path / png_name
        if png_path.exists() and png_path.stat().st_size > 0:
            entry['png'] = png_path.name
            entry['png_url'] = web_url_for(png_path, drive_dir=drive_dir)
            entry['has_png'] = True
            html_path = png_path.with_suffix('.html')
            if html_path.exists():
                entry['html'] = html_path.name
                entry['html_url'] = web_url_for(html_path, drive_dir=drive_dir)
                entry['has_html'] = True
                entry['available'] = True
    return entry


def _unique_family_html(board_path, serial_no, file_token, md_number, gain=None):
    """Use the single HTML/PNG for a family when --worst left only one file."""
    board_path = Path(board_path)
    if gain:
        htmls = sorted(board_path.glob(
            f'DBSNo_{serial_no}_PPrGTH_{file_token}_MD{int(md_number)}_CH*_{gain}.html'
        ))
        pngs = sorted(board_path.glob(
            f'DBSNo_{serial_no}_PPrGTH_{file_token}_MD{int(md_number)}_CH*_{gain}.png'
        ))
    else:
        htmls = [
            path for path in sorted(board_path.glob(
                f'DBSNo_{serial_no}_PPrGTH_{file_token}_MD{int(md_number)}_CH*.html'
            ))
            if '_HG.html' not in path.name and '_LG.html' not in path.name
        ]
        pngs = [
            path for path in sorted(board_path.glob(
                f'DBSNo_{serial_no}_PPrGTH_{file_token}_MD{int(md_number)}_CH*.png'
            ))
            if '_HG.png' not in path.name and '_LG.png' not in path.name
        ]
    if len(pngs) == 1:
        sibling = pngs[0].with_suffix('.html')
        return sibling if sibling.exists() else None
    if len(htmls) == 1:
        return htmls[0]
    return None


def _slot_memo_fingerprint(benchtest_id, serial_no, md_number, board_path, stats_path, sidecar_path):
    def _mtime(path):
        try:
            return Path(path).stat().st_mtime if Path(path).exists() else 0.0
        except OSError:
            return 0.0

    return (
        str(benchtest_id),
        str(serial_no),
        int(md_number),
        _mtime(stats_path),
        _mtime(sidecar_path),
        _mtime(board_path),
    )


def _channel_index(name):
    text = str(name or '').strip()
    match = _CHANNEL_RE.match(text)
    if match:
        return int(match.group(1))
    # Also accept bare integers / "MD1_CH3"
    if text.isdigit():
        return int(text)
    if '_CH' in text.upper():
        tail = text.upper().rsplit('_CH', 1)[-1]
        if tail.isdigit():
            return int(tail)
    return None


def _safe_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def _threshold_band(thresholds):
    nums = [_safe_float(t) for t in (thresholds or [])]
    nums = [n for n in nums if n is not None]
    if not nums:
        return None, None, None
    if len(nums) == 1:
        return nums[0], nums[0], nums[0]
    lo, hi = min(nums[0], nums[1]), max(nums[0], nums[1])
    return lo, hi, 0.5 * (lo + hi)


def _threshold_distance(value, thresholds):
    """Outside-band distance; 0 if inside. Single threshold → abs delta."""
    if value is None:
        return None
    lo, hi, _mid = _threshold_band(thresholds)
    if lo is None:
        return abs(value)
    if value < lo:
        return lo - value
    if value > hi:
        return value - hi
    return 0.0


def _score_channel(stats_row, thresholds, worse):
    mean = _safe_float((stats_row or {}).get('mean'))
    if mean is None:
        mean = _safe_float((stats_row or {}).get('average'))
    if mean is None:
        return None
    if worse == 'higher':
        return mean
    if worse == 'lower':
        return -mean
    if worse == 'threshold_distance':
        outside = _threshold_distance(mean, thresholds)
        if outside is None:
            return None
        _lo, _hi, mid = _threshold_band(thresholds)
        # Outside failures always rank above in-band; in-band uses |mean-mid|.
        center_delta = abs(mean - mid) if mid is not None else abs(mean)
        return float(outside) * 1_000_000.0 + center_delta
    if worse == 'farther_from_one':
        return abs(mean - 1.0)
    return mean


def extract_figure_from_plotly_html(html_path):
    """Rebuild a plotly Figure from a write_html file (brace-matched JSON)."""
    import plotly.graph_objects as go

    text = Path(html_path).read_text(encoding='utf-8', errors='ignore')
    marker = re.search(r'Plotly\.newPlot\(\s*"[^"]+"\s*,', text)
    if not marker:
        return None

    def _extract_json_value(source, start):
        opener = source[start]
        if opener not in '[{':
            return None, None
        closer = ']' if opener == '[' else '}'
        depth = 0
        in_str = False
        esc = False
        for index, ch in enumerate(source[start:], start):
            if in_str:
                if esc:
                    esc = False
                elif ch == '\\':
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
                continue
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    return source[start:index + 1], index + 1
        return None, None

    pos = marker.end()
    while pos < len(text) and text[pos].isspace():
        pos += 1
    data_txt, pos = _extract_json_value(text, pos)
    if not data_txt:
        return None
    while pos < len(text) and text[pos] in ' \n\r\t,':
        pos += 1
    layout_txt, _pos2 = _extract_json_value(text, pos)
    if not layout_txt:
        return None
    data = json.loads(data_txt)
    layout = json.loads(layout_txt)
    return go.Figure(data=data, layout=layout)


def load_statistics_yaml(path):
    path = Path(path)
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding='utf-8')
    except OSError as exc:
        print(f'Error reading statistics YAML {path}: {exc}')
        return None
    try:
        import yaml
        loader = getattr(yaml, 'CSafeLoader', None) or yaml.SafeLoader
        return yaml.load(text, Loader=loader)
    except Exception:
        pass
    try:
        from ruamel.yaml import YAML
        return YAML(typ='safe').load(text)
    except Exception as exc:
        print(f'Error parsing statistics YAML {path}: {exc}')
        return None


def pick_worst_channel(stats_doc, stats_var, worse='higher'):
    """Return {channel, score, mean, stats_var} for the worst CH* under stats_var."""
    variables = (stats_doc or {}).get('variables') or {}
    var_payload = variables.get(stats_var) or {}
    channels = var_payload.get('channels') or {}
    thresholds = var_payload.get('thresholds') or []
    best = None  # (score, channel_index, mean)
    for name, row in channels.items():
        ch_index = _channel_index(name)
        if ch_index is None:
            continue
        score = _score_channel(row, thresholds, worse)
        if score is None:
            continue
        mean = _safe_float(row.get('mean'))
        if mean is None:
            mean = _safe_float(row.get('average'))
        if best is None or score > best[0]:
            best = (score, ch_index, mean)
    if best is None:
        return None
    return {
        'channel': best[1],
        'score': best[0],
        'mean': best[2],
        'stats_var': stats_var,
    }


def find_existing_plot(board_path, serial_no, file_token, md_number, gain=None, channel_index=None):
    """Return Path to HTML if present; optionally search any CH if channel missing."""
    board_path = Path(board_path)
    if channel_index is not None:
        candidate = board_path / plot_filename(
            serial_no, file_token, md_number, channel_index, gain=gain
        )
        return candidate if candidate.exists() else None

    pattern = f'DBSNo_{serial_no}_PPrGTH_{file_token}_MD{int(md_number)}_CH*'
    if gain:
        pattern += f'_{gain}.html'
    else:
        pattern += '.html'

    def _key(path):
        match = re.search(r'_CH(\d+)', path.name)
        return int(match.group(1)) if match else 999

    matches = sorted(board_path.glob(pattern), key=_key)
    return matches[0] if matches else None


def start_preview_kaleido_server():
    """Start a single shared Kaleido Chrome (batch / long hover sessions)."""
    global _KALEIDO_SYNC_STARTED
    with _PREVIEW_PNG_LOCK:
        if _KALEIDO_SYNC_STARTED:
            return
        try:
            import kaleido
            kaleido.start_sync_server(silence_warnings=True)
            _KALEIDO_SYNC_STARTED = True
        except Exception as exc:
            print(f'Warning: could not start kaleido sync server ({exc})')


def stop_preview_kaleido_server():
    """Stop the shared Kaleido Chrome cleanly."""
    global _KALEIDO_SYNC_STARTED
    with _PREVIEW_PNG_LOCK:
        if not _KALEIDO_SYNC_STARTED:
            return
        try:
            import kaleido
            kaleido.stop_sync_server(silence_warnings=True)
        except Exception as exc:
            print(f'Warning: could not stop kaleido sync server ({exc})')
        _KALEIDO_SYNC_STARTED = False


def _annotation_text(annotation):
    if annotation is None:
        return ''
    if isinstance(annotation, dict):
        return str(annotation.get('text') or '')
    return str(getattr(annotation, 'text', None) or '')


def _annotation_y(annotation):
    if annotation is None:
        return None
    if isinstance(annotation, dict):
        return annotation.get('y')
    return getattr(annotation, 'y', None)


def _is_summary_annotation(annotation):
    """True for below-plot Summary / Pulse Centers / Traces boxes."""
    text = _annotation_text(annotation).lower()
    if 'summary' in text or 'pulse centers' in text or 'traces:' in text:
        return True
    y_val = _annotation_y(annotation)
    try:
        if y_val is not None and float(y_val) < 0:
            return True
    except (TypeError, ValueError):
        pass
    return False


def _short_preview_title(fig):
    title = fig.layout.title
    raw = ''
    if isinstance(title, dict):
        raw = str(title.get('text') or '')
    else:
        raw = str(getattr(title, 'text', None) or '')
    text = raw.replace('<br>', ' ').replace('<br/>', ' ')
    # Drop generator timestamp / long parentheticals for hover readability.
    if ' (Gen' in text:
        text = text.split(' (Gen', 1)[0].rstrip()
    if ' (BT ' in text and text.rfind(' (BT ') > 20:
        # keep BT id short form if present, strip trailing length bit later
        pass
    if len(text) > 90:
        text = text[:87].rstrip() + '…'
    return text or None


def _prepare_figure_for_preview(fig):
    """Remove cramped summary boxes and give the plot room to breathe."""
    kept = [
        ann for ann in (fig.layout.annotations or [])
        if not _is_summary_annotation(ann)
    ]
    title_text = _short_preview_title(fig)
    fig.update_layout(
        annotations=kept,
        margin=dict(l=70, r=28, t=64, b=72),
        title=dict(
            text=title_text,
            font=dict(size=15, color='#222'),
            x=0.01,
            xanchor='left',
            y=0.98,
            yanchor='top',
        ),
        font=dict(size=12, color='#222'),
        showlegend=False,
        paper_bgcolor='white',
        plot_bgcolor='white',
        autosize=False,
    )
    fig.update_xaxes(title_font=dict(size=13), tickfont=dict(size=11), automargin=True)
    fig.update_yaxes(title_font=dict(size=13), tickfont=dict(size=11), automargin=True)
    return fig


def _flatten_preview_png_rgb(png_path):
    """Flatten alpha onto white so dark tooltip backgrounds never show through."""
    try:
        from PIL import Image
        with Image.open(png_path) as image:
            rgb = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode in ('RGBA', 'LA'):
                rgb.paste(image, mask=image.split()[-1])
            else:
                rgb.paste(image.convert('RGB'))
            rgb.save(png_path, format='PNG', optimize=True)
    except Exception as flatten_exc:
        print(f'Preview PNG flatten skipped for {Path(png_path).name}: {flatten_exc}')


def write_preview_png_from_figure(
    fig,
    png_path,
    *,
    width=_PNG_WIDTH,
    height=_PNG_HEIGHT,
    mutate=False,
):
    """
    Export a hover-style RGB PNG (900×560) from a Plotly figure.

    Same layout strip / white flatten used by generate_extra_plots_cache.
    By default copies the figure so the caller's HTML fig is untouched.
    """
    import plotly.graph_objects as go

    png_path = Path(png_path)
    export_fig = fig if mutate else go.Figure(fig)
    try:
        _prepare_figure_for_preview(export_fig)
        with _PREVIEW_PNG_LOCK:
            export_fig.write_image(
                str(png_path), format='png', width=width, height=height, scale=1,
            )
        _flatten_preview_png_rgb(png_path)
        return png_path if png_path.exists() else None
    except Exception as exc:
        print(f'Preview PNG failed for {png_path.name}: {exc}')
        return None


def ensure_preview_png(html_path, *, width=_PNG_WIDTH, height=_PNG_HEIGHT, force=False):
    """Create sibling .png from Plotly HTML if missing (or force). Return Path or None."""
    html_path = Path(html_path)
    if not html_path.exists():
        return None
    png_path = html_path.with_suffix('.png')
    if png_path.exists() and not force and png_path.stat().st_size > 0:
        fresh = png_path.stat().st_mtime >= html_path.stat().st_mtime
        size_ok = True
        try:
            from PIL import Image
            with Image.open(png_path) as image:
                size_ok = image.size[0] >= int(width * 0.9) and image.size[1] >= int(height * 0.9)
        except Exception:
            size_ok = False
        if fresh and size_ok:
            return png_path
    try:
        fig = extract_figure_from_plotly_html(html_path)
        if fig is None:
            return None
        return write_preview_png_from_figure(
            fig, png_path, width=width, height=height, mutate=True,
        )
    except Exception as exc:
        print(f'Preview PNG failed for {html_path.name}: {exc}')
        return None


def hover_preview_spec_for_measurement(measurement):
    """Return PREVIEW_SPECS entry for a linearity measurement, or None."""
    for spec in PREVIEW_SPECS:
        if spec['file_token'] == measurement or spec['key'] == measurement:
            return spec
    return None

def _md_number(md):
    if md is None:
        return None
    text = str(md).strip().upper()
    if text.startswith('MD') and text[2:].isdigit():
        return int(text[2:])
    if text.isdigit():
        return int(text)
    return None


def _empty_preview_entry(spec):
    return {
        'key': spec['key'],
        'label': spec['label'],
        'stats_var': spec['stats_var'],
        'channel': None,
        'gain': spec['gain'],
        'score': None,
        'mean': None,
        'html': None,
        'png': None,
        'html_url': None,
        'png_url': None,
        'available': False,
        'has_html': False,
        'has_png': False,
        'can_generate': False,
    }


def _invalidate_slot_preview_memo(benchtest_id, serial_no, md_number):
    memo_key = (str(benchtest_id), str(serial_no), int(md_number))
    with _SLOT_PREVIEW_MEMO_LOCK:
        _SLOT_PREVIEW_MEMO.pop(memo_key, None)


def _store_slot_preview_memo(memo_key, fingerprint, payload):
    with _SLOT_PREVIEW_MEMO_LOCK:
        _SLOT_PREVIEW_MEMO[memo_key] = {
            'fp': fingerprint,
            'ts': time.time(),
            'payload': payload,
        }


def _run_png_jobs(png_jobs, *, drive_dir, force_png):
    if not png_jobs:
        return
    for entry, html_path in png_jobs:
        png_path = ensure_preview_png(html_path, force=force_png)
        if png_path is not None:
            entry['png'] = png_path.name
            entry['png_url'] = web_url_for(png_path, drive_dir=drive_dir)
            entry['has_png'] = True
            entry['can_generate'] = False
        else:
            entry['can_generate'] = bool(entry.get('has_html'))


def _previews_from_sidecar(sidecar, board_path, drive_dir, ensure_png, force_png):
    """Rebuild preview entries from sidecar JSON. Returns None if incomplete."""
    by_key = {
        entry.get('key'): entry
        for entry in (sidecar.get('previews') or [])
        if isinstance(entry, dict) and entry.get('key')
    }
    if not all(spec['key'] in by_key for spec in PREVIEW_SPECS):
        return None

    previews = []
    png_jobs = []
    for spec in PREVIEW_SPECS:
        raw = by_key[spec['key']]
        entry = _empty_preview_entry(spec)
        for field in ('channel', 'gain', 'html', 'png', 'score', 'mean', 'label', 'stats_var'):
            if raw.get(field) is not None:
                entry[field] = raw.get(field)
        _refresh_preview_flags(entry, board_path, drive_dir=drive_dir)
        if force_png and entry.get('has_html'):
            html_path = board_path / entry['html']
            if html_path.exists():
                png_jobs.append((entry, html_path))
        elif ensure_png and entry.get('has_html') and not entry.get('has_png'):
            html_path = board_path / entry['html']
            if html_path.exists():
                png_jobs.append((entry, html_path))
        previews.append(entry)
    return previews, png_jobs


def _previews_from_unique_files(board_path, serial_no, md_number, drive_dir, ensure_png, force_png):
    """
    Fast path when --worst left a single HTML/PNG per family for this MD.
    Returns None if any family is ambiguous (0 or 2+ files).
    """
    previews = []
    png_jobs = []
    for spec in PREVIEW_SPECS:
        html_path = _unique_family_html(
            board_path,
            serial_no,
            spec['file_token'],
            md_number,
            gain=spec['gain'],
        )
        if html_path is None:
            return None
        match = re.search(r'_CH(\d+)', html_path.name)
        entry = _empty_preview_entry(spec)
        entry['channel'] = int(match.group(1)) if match else None
        entry['html'] = html_path.name
        entry['html_url'] = web_url_for(html_path, drive_dir=drive_dir)
        entry['available'] = True
        entry['has_html'] = True
        png_path = html_path.with_suffix('.png')
        if png_path.exists() and png_path.stat().st_size > 0 and not force_png:
            entry['png'] = png_path.name
            entry['png_url'] = web_url_for(png_path, drive_dir=drive_dir)
            entry['has_png'] = True
        elif ensure_png:
            png_jobs.append((entry, html_path))
        else:
            entry['can_generate'] = True
        previews.append(entry)
    return previews, png_jobs


def _previews_from_statistics(
    board_path,
    serial_no,
    md_number,
    stats_doc,
    drive_dir,
    ensure_png,
    force_png,
):
    previews = []
    png_jobs = []
    for spec in PREVIEW_SPECS:
        pick = None
        if stats_doc is not None:
            pick = pick_worst_channel(stats_doc, spec['stats_var'], worse=spec['worse'])

        channel = pick['channel'] if pick else None
        html_path = find_existing_plot(
            board_path,
            serial_no,
            spec['file_token'],
            md_number,
            gain=spec['gain'],
            channel_index=channel,
        )
        if html_path is None:
            html_path = find_existing_plot(
                board_path,
                serial_no,
                spec['file_token'],
                md_number,
                gain=spec['gain'],
                channel_index=None,
            )
            if html_path is not None:
                match = re.search(r'_CH(\d+)', html_path.name)
                channel = int(match.group(1)) if match else channel

        entry = _empty_preview_entry(spec)
        entry['channel'] = channel
        entry['score'] = None if not pick else pick.get('score')
        entry['mean'] = None if not pick else pick.get('mean')
        if html_path is not None:
            entry['html'] = html_path.name
            entry['html_url'] = web_url_for(html_path, drive_dir=drive_dir)
            entry['available'] = True
            entry['has_html'] = True
            png_path = html_path.with_suffix('.png')
            if png_path.exists() and png_path.stat().st_size > 0 and not force_png:
                entry['png'] = png_path.name
                entry['png_url'] = web_url_for(png_path, drive_dir=drive_dir)
                entry['has_png'] = True
            elif ensure_png:
                png_jobs.append((entry, html_path))
            else:
                entry['can_generate'] = True
        previews.append(entry)
    return previews, png_jobs


def build_slot_previews(
    benchtest_id,
    serial_no,
    md,
    *,
    drive_dir=DRIVE_BENCHTESTS,
    ensure_png=False,
    force_png=False,
):
    """
    Resolve worst-channel preview entries for one MD brick.

    Fast path order (hover must stay cheap):
      1) in-process memo
      2) hover sidecar JSON (written by --worst / first resolve)
      3) unique PNG/HTML per family (after --worst pruning)
      4) Statistics.yaml (slow; last resort)

    By default only reports existing HTML/PNG on disk (no kaleido generation).
    Set ensure_png=True to create missing PNGs from HTML.
    """
    md_number = _md_number(md)
    if md_number is None:
        return {'success': False, 'error': 'Invalid md', 'previews': []}

    board_path = board_dir(benchtest_id, serial_no, drive_dir=drive_dir)
    if not board_path.is_dir():
        return {
            'success': False,
            'error': f'Board folder not found: {board_path.name}',
            'previews': [],
        }

    stats_path = statistics_yaml_path(board_path, serial_no)
    sidecar_path = hover_previews_sidecar_path(board_path, serial_no, md_number)
    memo_key = (str(benchtest_id), str(serial_no), int(md_number))
    fingerprint = _slot_memo_fingerprint(
        benchtest_id, serial_no, md_number, board_path, stats_path, sidecar_path,
    )

    if not ensure_png and not force_png:
        with _SLOT_PREVIEW_MEMO_LOCK:
            hit = _SLOT_PREVIEW_MEMO.get(memo_key)
            if (
                hit
                and hit.get('fp') == fingerprint
                and (time.time() - hit.get('ts', 0.0)) < _SLOT_PREVIEW_MEMO_TTL_S
            ):
                return hit['payload']

    previews = None
    png_jobs = []
    source = None
    write_sidecar = False

    sidecar = load_hover_previews_sidecar(board_path, serial_no, md_number)
    if sidecar is not None:
        loaded = _previews_from_sidecar(
            sidecar, board_path, drive_dir, ensure_png, force_png,
        )
        if loaded is not None:
            previews, png_jobs = loaded
            source = 'sidecar'
            raw_by_key = {
                raw.get('key'): raw
                for raw in (sidecar.get('previews') or [])
                if isinstance(raw, dict)
            }
            write_sidecar = any(
                (
                    entry.get('png') != (raw_by_key.get(entry['key']) or {}).get('png')
                    or entry.get('html') != (raw_by_key.get(entry['key']) or {}).get('html')
                )
                for entry in previews
            )

    if previews is None:
        loaded = _previews_from_unique_files(
            board_path, serial_no, md_number, drive_dir, ensure_png, force_png,
        )
        if loaded is not None:
            previews, png_jobs = loaded
            source = 'unique'
            write_sidecar = True

    if previews is None:
        stats_doc = load_statistics_yaml(stats_path)
        previews, png_jobs = _previews_from_statistics(
            board_path,
            serial_no,
            md_number,
            stats_doc,
            drive_dir,
            ensure_png,
            force_png,
        )
        source = 'statistics'
        write_sidecar = True

    _run_png_jobs(png_jobs, drive_dir=drive_dir, force_png=force_png)
    if png_jobs:
        write_sidecar = True
        _invalidate_slot_preview_memo(benchtest_id, serial_no, md_number)

    if write_sidecar:
        save_hover_previews_sidecar(board_path, serial_no, md_number, previews)
        fingerprint = _slot_memo_fingerprint(
            benchtest_id, serial_no, md_number, board_path, stats_path, sidecar_path,
        )

    payload = {
        'success': True,
        'benchtest_id': int(benchtest_id) if str(benchtest_id).isdigit() else benchtest_id,
        'serial_no': int(serial_no) if str(serial_no).isdigit() else serial_no,
        'md': f'MD{md_number}',
        'board_dir': str(board_path),
        'statistics_yaml': stats_path.name if stats_path.exists() else None,
        'preview_source': source,
        'previews': previews,
    }

    if not ensure_png and not force_png:
        _store_slot_preview_memo(memo_key, fingerprint, payload)

    return payload


def generate_slot_preview_png(
    benchtest_id,
    serial_no,
    md,
    *,
    key=None,
    drive_dir=DRIVE_BENCHTESTS,
    force=False,
):
    """
    Generate PNG thumbnail(s) for one MD brick's worst-channel previews.

    key: optional PREVIEW_SPECS key; if omitted, generate all missing for the slot.
    """
    payload = build_slot_previews(
        benchtest_id,
        serial_no,
        md,
        drive_dir=drive_dir,
        ensure_png=False,
        force_png=False,
    )
    if not payload.get('success'):
        return payload

    targets = []
    for entry in payload.get('previews') or []:
        if key and entry.get('key') != key:
            continue
        if not entry.get('has_html'):
            continue
        if entry.get('has_png') and not force:
            continue
        html_name = entry.get('html')
        if not html_name:
            continue
        html_path = Path(payload['board_dir']) / html_name
        if html_path.exists():
            targets.append((entry, html_path))

    if key and not targets:
        # Explicit key requested but nothing to do / no HTML.
        match = next(
            (e for e in (payload.get('previews') or []) if e.get('key') == key),
            None,
        )
        if match is None:
            return {'success': False, 'error': f'Unknown preview key: {key}', 'previews': payload.get('previews') or []}
        if not match.get('has_html'):
            return {
                'success': False,
                'error': 'Data not available (no HTML plot)',
                'previews': payload.get('previews') or [],
            }
        # Already has png
        return payload

    start_preview_kaleido_server()
    try:
        for entry, html_path in targets:
            png_path = ensure_preview_png(html_path, force=force)
            if png_path is not None:
                entry['png'] = png_path.name
                entry['png_url'] = web_url_for(png_path, drive_dir=drive_dir)
                entry['has_png'] = True
                entry['can_generate'] = False
            else:
                entry['can_generate'] = True
    finally:
        stop_preview_kaleido_server()

    md_number = _md_number(md)
    board_path = Path(payload['board_dir'])
    if md_number is not None:
        save_hover_previews_sidecar(
            board_path, serial_no, md_number, payload.get('previews') or [],
        )
        _invalidate_slot_preview_memo(benchtest_id, serial_no, md_number)

    # Refresh png flags for all entries from disk (picks up sidecar + memo).
    refreshed = build_slot_previews(
        benchtest_id,
        serial_no,
        md,
        drive_dir=drive_dir,
        ensure_png=False,
        force_png=False,
    )
    refreshed['generated_keys'] = [entry['key'] for entry, _html in targets]
    return refreshed
