"""Compose Production History milestone PNGs into a 1920x1080 MP4."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from production_history import HISTORY_CACHE_DIR, load_history_index

VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
VIDEO_DIR_NAME = 'videos'
SLIDESHOW_DIR_NAME = 'slideshows'
MONTH_ABBR = (
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
)
SPEED_VALUES = (0.25, 0.5, 1, 2, 3, 4, 5, 8, 10)
DROP_N_VALUES = (1, 2, 3, 4, 5, 8, 10, 15, 20)


def video_output_dir():
    path = HISTORY_CACHE_DIR / VIDEO_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def slideshow_output_dir():
    path = HISTORY_CACHE_DIR / SLIDESHOW_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_video_filename(name):
    base = Path(str(name or '')).name
    if not re.fullmatch(r'history_\d{8}_\d{6}\.mp4', base):
        return None
    return base


def _safe_slideshow_filename(name):
    base = Path(str(name or '')).name
    if not re.fullmatch(r'history_(?:slide_)?\d{8}_\d{6}\.pdf', base):
        return None
    return base


def resolve_video_path(filename):
    safe = _safe_video_filename(filename)
    if not safe:
        return None
    path = video_output_dir() / safe
    if not path.is_file():
        return None
    return path


def resolve_slideshow_path(filename):
    safe = _safe_slideshow_filename(filename)
    if not safe:
        return None
    path = slideshow_output_dir() / safe
    if not path.is_file():
        return None
    return path


def _load_font(size, bold=False):
    candidates = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _parse_ymd(value):
    text = str(value or '').strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], '%Y-%m-%d')
    except ValueError:
        return None


def format_week_subtitle(milestone):
    """Return YYYY Week WW (Mon DD - Mon DD)."""
    start = _parse_ymd(milestone.get('week_start'))
    end = _parse_ymd(milestone.get('week_end'))
    week_key = str(milestone.get('week_key') or '')
    year = None
    week = None
    if '-W' in week_key:
        try:
            year_text, week_text = week_key.split('-W', 1)
            year = int(year_text)
            week = int(week_text)
        except ValueError:
            year = None
            week = None
    if year is None and start is not None:
        iso = start.isocalendar()
        year = iso.year
        week = iso.week
    if year is None:
        year = datetime.now().year
    if week is None:
        week = 0

    if start is not None and end is not None:
        start_text = f'{MONTH_ABBR[start.month - 1]} {start.day:02d}'
        end_text = f'{MONTH_ABBR[end.month - 1]} {end.day:02d}'
    else:
        start_text = '—'
        end_text = '—'
    return f'{year} Week {week:02d} ({start_text} - {end_text})'


def _event_date_key(value):
    text = str(value or '').strip()
    if not text:
        return None
    return text[:10]


def load_calendar_events_for_video():
    try:
        from production_config import SCHEDULE_CSV_PATH
        from production_schedule import load_schedule_calendar_events
        return load_schedule_calendar_events(SCHEDULE_CSV_PATH) or []
    except Exception as exc:
        print(f'Video calendar events unavailable: {exc}')
        return []


def fetch_db_comments_for_video(db_connection):
    """Return flat DB/board comments with timestamps for subtitle filtering."""
    if not db_connection:
        return []
    comments = []
    cursor = db_connection.cursor(dictionary=True)
    try:
        cursor.execute("SHOW TABLES LIKE 'comment'")
        if not cursor.fetchone():
            return []

        cursor.execute("""
            SELECT c.foreign_id, c.tstamp, c.op, c.note
            FROM comment c
            WHERE c.foreign_typ = 3
            ORDER BY c.tstamp
        """)
        for row in cursor.fetchall() or []:
            comments.append({
                'tstamp': str(row.get('tstamp') or ''),
                'op': row.get('op') or '',
                'note': row.get('note') or '',
                'serial': row.get('foreign_id'),
                'kind': 'board',
            })

        cursor.execute("""
            SELECT c.foreign_id, c.tstamp, c.op, c.note
            FROM comment c
            WHERE c.foreign_typ = 4
            ORDER BY c.tstamp
        """)
        benchtest_comments = cursor.fetchall() or []
        cursor.execute("""
            SELECT id, db_slot1, db_slot2, db_slot3, db_slot4
            FROM benchtest
        """)
        slots_by_id = {row['id']: row for row in (cursor.fetchall() or [])}
        for row in benchtest_comments:
            benchtest_id = row.get('foreign_id')
            slots = slots_by_id.get(benchtest_id) or {}
            serials = [
                slots.get(f'db_slot{slot}')
                for slot in range(1, 5)
                if slots.get(f'db_slot{slot}')
            ]
            comments.append({
                'tstamp': str(row.get('tstamp') or ''),
                'op': row.get('op') or '',
                'note': row.get('note') or '',
                'serial': serials[0] if serials else None,
                'serials': serials,
                'benchtest_id': benchtest_id,
                'kind': 'benchtest',
            })
    except Exception as exc:
        print(f'Video DB comments unavailable: {exc}')
        return []
    finally:
        try:
            cursor.close()
        except Exception:
            pass
    comments.sort(key=lambda item: item.get('tstamp') or '')
    return comments


def _in_week_range(date_value, week_start, week_end):
    key = _event_date_key(date_value)
    start_key = _event_date_key(week_start)
    end_key = _event_date_key(week_end)
    if not key or not start_key or not end_key:
        return False
    return start_key <= key <= end_key


def calendar_labels_for_week(milestone, calendar_events):
    week_start = milestone.get('week_start')
    week_end = milestone.get('week_end')
    labels = []
    for item in calendar_events or []:
        if _in_week_range(item.get('date'), week_start, week_end):
            label = str(item.get('label') or item.get('comment') or '').strip()
            if label:
                labels.append(label)
    return labels


def db_comments_for_week(milestone, db_comments):
    week_start = milestone.get('week_start')
    week_end = milestone.get('week_end')
    lines = []
    for item in db_comments or []:
        if not _in_week_range(item.get('tstamp'), week_start, week_end):
            continue
        note = str(item.get('note') or '').strip()
        if not note:
            continue
        day = _event_date_key(item.get('tstamp')) or ''
        op = str(item.get('op') or '').strip()
        if item.get('kind') == 'benchtest' and item.get('benchtest_id') is not None:
            prefix = f'{day} (bt{item["benchtest_id"]}'
            if op:
                prefix += f', {op}'
            prefix += ')'
        else:
            prefix = f'{day}'
            if op:
                prefix += f' ({op})'
        lines.append(f'{prefix}: {note}')
    return lines


def build_subtitle_lines(milestone, options=None, calendar_events=None, db_comments=None):
    options = normalize_video_options(options or {})
    lines = [format_week_subtitle(milestone)]
    if options.get('include_calendar_labels'):
        labels = calendar_labels_for_week(milestone, calendar_events)
        if labels:
            lines.append('Cal: ' + ' · '.join(labels[:6]))
            if len(labels) > 6:
                lines[-1] += f' · +{len(labels) - 6} more'
        else:
            lines.append('Cal: —')
    if options.get('include_comments'):
        notes = db_comments_for_week(milestone, db_comments)
        if notes:
            lines.append('Notes: ' + ' · '.join(notes[:4]))
            if len(notes) > 4:
                lines[-1] += f' · +{len(notes) - 4} more'
        else:
            lines.append('Notes: —')
    return lines


def _wrap_subtitle_line(draw, text, font, max_width):
    text = str(text or '')
    if not text:
        return ['']
    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return [text]
    words = text.split(' ')
    lines = []
    current = ''
    for word in words:
        candidate = word if not current else f'{current} {word}'
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    # Hard-cap wrapped lines so the subtitle bar stays readable.
    if len(lines) > 3:
        lines = lines[:3]
        if not lines[-1].endswith('…'):
            lines[-1] = lines[-1][: max(1, len(lines[-1]) - 1)] + '…'
    return lines or [text]


def _open_rgb(path):
    if not path or not Path(path).is_file():
        return None
    with Image.open(path) as image:
        return image.convert('RGB')


def _fit_into(image, box_w, box_h, background=(255, 255, 255)):
    canvas = Image.new('RGB', (box_w, box_h), background)
    if image is None:
        return canvas
    src_w, src_h = image.size
    if src_w <= 0 or src_h <= 0:
        return canvas
    scale = min(box_w / src_w, box_h / src_h)
    new_w = max(1, int(round(src_w * scale)))
    new_h = max(1, int(round(src_h * scale)))
    resized = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
    offset = ((box_w - new_w) // 2, (box_h - new_h) // 2)
    canvas.paste(resized, offset)
    return canvas


def _draw_panel(canvas, image, box, title=None, title_font=None):
    x, y, w, h = box
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((x, y, x + w - 1, y + h - 1), radius=10, fill=(255, 255, 255), outline=(220, 224, 230))
    title_h = 0
    if title:
        title_h = 28
        draw.text((x + 12, y + 6), title, fill=(70, 78, 90), font=title_font)
    inner = _fit_into(image, w - 16, h - 16 - title_h, background=(255, 255, 255))
    canvas.paste(inner, (x + 8, y + 8 + title_h))


def compose_history_frame(
    milestone,
    cache_dir=None,
    options=None,
    calendar_events=None,
    db_comments=None,
):
    """Lay out all milestone PNGs into one 1920x1080 RGB frame."""
    options = normalize_video_options(options or {})
    root = Path(cache_dir or HISTORY_CACHE_DIR)
    wall = _open_rgb(root / milestone['wall_png']) if milestone.get('wall_png') else None
    yield_pie = _open_rgb(root / milestone['yield_pie_png']) if milestone.get('yield_pie_png') else None
    burnin_pie = _open_rgb(root / milestone['burnin_pie_png']) if milestone.get('burnin_pie_png') else None
    produced_pie = _open_rgb(root / milestone['produced_pie_png']) if milestone.get('produced_pie_png') else None
    cumulative = _open_rgb(root / milestone['cumulative_png']) if milestone.get('cumulative_png') else None
    burnin = _open_rgb(root / milestone['burnin_png']) if milestone.get('burnin_png') else None

    canvas = Image.new('RGB', (VIDEO_WIDTH, VIDEO_HEIGHT), (245, 247, 250))
    title_font = _load_font(16, bold=True)
    subtitle_font = _load_font(28, bold=True)
    detail_font = _load_font(18, bold=False)

    pad = 18
    gap = 14
    subtitle_lines = build_subtitle_lines(
        milestone,
        options=options,
        calendar_events=calendar_events,
        db_comments=db_comments,
    )
    extra_lines = max(0, len(subtitle_lines) - 1)
    subtitle_h = 72 + (extra_lines * 28)
    subtitle_h = min(subtitle_h, 168)
    content_top = pad
    content_bottom = VIDEO_HEIGHT - pad - subtitle_h
    content_h = content_bottom - content_top
    content_w = VIDEO_WIDTH - (2 * pad)

    top_h = int(content_h * 0.58)
    bottom_h = content_h - top_h - gap
    wall_w = int(content_w * 0.62)
    pies_w = content_w - wall_w - gap
    pie_h = (top_h - (2 * gap)) // 3

    _draw_panel(
        canvas,
        wall,
        (pad, content_top, wall_w, top_h),
        title='Brick Wall',
        title_font=title_font,
    )
    pie_x = pad + wall_w + gap
    pies = (
        ('Yield', yield_pie),
        ('Burn-In Status', burnin_pie),
        ('Produced vs Expected', produced_pie),
    )
    for index, (title, image) in enumerate(pies):
        y = content_top + index * (pie_h + gap)
        _draw_panel(canvas, image, (pie_x, y, pies_w, pie_h), title=title, title_font=title_font)

    chart_y = content_top + top_h + gap
    chart_w = (content_w - gap) // 2
    _draw_panel(
        canvas,
        cumulative,
        (pad, chart_y, chart_w, bottom_h),
        title='Cumulative Board Count',
        title_font=title_font,
    )
    _draw_panel(
        canvas,
        burnin,
        (pad + chart_w + gap, chart_y, content_w - chart_w - gap, bottom_h),
        title='Burn-In Timeline',
        title_font=title_font,
    )

    # 80% transparent subtitle bar under the charts.
    overlay = Image.new('RGBA', (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    bar_top = VIDEO_HEIGHT - pad - subtitle_h
    overlay_draw.rectangle(
        (pad, bar_top, VIDEO_WIDTH - pad, VIDEO_HEIGHT - pad),
        fill=(24, 28, 36, 51),  # alpha 51 ≈ 20% opaque / 80% transparent
    )

    max_text_width = VIDEO_WIDTH - (2 * pad) - 40
    rendered_lines = []
    for index, line in enumerate(subtitle_lines):
        font = subtitle_font if index == 0 else detail_font
        rendered_lines.extend(
            (wrapped, font) for wrapped in _wrap_subtitle_line(overlay_draw, line, font, max_text_width)
        )

    line_gap = 4
    total_text_h = 0
    line_sizes = []
    for text, font in rendered_lines:
        bbox = overlay_draw.textbbox((0, 0), text, font=font)
        height = bbox[3] - bbox[1]
        line_sizes.append((text, font, height))
        total_text_h += height
    total_text_h += max(0, len(line_sizes) - 1) * line_gap
    text_y = bar_top + max(8, (subtitle_h - total_text_h) // 2)
    for text, font, height in line_sizes:
        bbox = overlay_draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_x = (VIDEO_WIDTH - text_w) // 2
        overlay_draw.text((text_x + 1, text_y + 1), text, fill=(0, 0, 0, 110), font=font)
        overlay_draw.text((text_x, text_y), text, fill=(255, 255, 255, 230), font=font)
        text_y += height + line_gap

    canvas = Image.alpha_composite(canvas.convert('RGBA'), overlay).convert('RGB')
    return canvas


def milestone_ready_for_video(milestone):
    keys = (
        'wall_png',
        'cumulative_png',
        'burnin_png',
        'yield_pie_png',
        'burnin_pie_png',
        'produced_pie_png',
    )
    if not all(milestone.get(key) for key in keys):
        return False
    root = HISTORY_CACHE_DIR
    return all((root / milestone[key]).is_file() for key in keys)


def normalize_video_options(raw):
    options = raw if isinstance(raw, dict) else {}
    unit = options.get('speed_unit') or options.get('unit') or 'milestones_per_second'
    if unit not in ('milestones_per_second', 'weeks_per_second'):
        unit = 'milestones_per_second'
    try:
        speed = float(options.get('speed_value') or options.get('speed') or 4)
    except (TypeError, ValueError):
        speed = 4.0
    if speed not in SPEED_VALUES:
        # allow nearby custom values but clamp
        speed = max(0.1, min(30.0, speed))
    try:
        drop_n = int(options.get('drop_n') or 1)
    except (TypeError, ValueError):
        drop_n = 1
    if drop_n not in DROP_N_VALUES:
        drop_n = 1
    milestone_index = options.get('milestone_index')
    if milestone_index is None:
        milestone_index = options.get('milestoneIndex')
    try:
        milestone_index = int(milestone_index) if milestone_index is not None else None
    except (TypeError, ValueError):
        milestone_index = None
    return {
        'speed_unit': unit,
        'speed_value': speed,
        'week_last_only': bool(options.get('week_last_only') or options.get('weekLastOnly')),
        'drop_milestones': bool(options.get('drop_milestones') or options.get('dropMilestones')),
        'drop_n': drop_n,
        'fade_transitions': bool(options.get('fade_transitions') or options.get('fadeTransitions')),
        'include_calendar_labels': bool(
            options.get('include_calendar_labels') or options.get('includeCalendarLabels')
        ),
        'include_comments': bool(
            options.get('include_comments') or options.get('includeComments')
        ),
        'milestone_index': milestone_index,
    }


def select_slideshow_milestone_indices(milestones, weeks, options):
    """Indices for slideshow/PDF export (optional single-milestone mode)."""
    options = normalize_video_options(options)
    milestone_index = options.get('milestone_index')
    if milestone_index is not None:
        if 0 <= milestone_index < len(milestones):
            return [milestone_index]
        return []
    return select_video_milestone_indices(milestones, weeks, options)


def select_video_milestone_indices(milestones, weeks, options):
    options = normalize_video_options(options)
    total = len(milestones or [])
    if total <= 0:
        return []

    if options['speed_unit'] == 'weeks_per_second' and options['week_last_only']:
        indices = []
        for week in weeks or []:
            week_indices = week.get('milestone_indices') or []
            if week_indices:
                indices.append(week_indices[-1])
        return [index for index in indices if 0 <= index < total]

    if options['speed_unit'] == 'milestones_per_second' and options['drop_milestones']:
        step = max(1, options['drop_n'] + 1)
        indices = list(range(0, total, step))
        if indices[-1] != total - 1:
            indices.append(total - 1)
        return indices

    return list(range(total))


def frame_duration_seconds(milestone, weeks, options):
    options = normalize_video_options(options)
    rate = max(0.05, float(options['speed_value']))
    if options['speed_unit'] == 'weeks_per_second':
        if options['week_last_only']:
            return 1.0 / rate
        week_key = milestone.get('week_key')
        week = next((item for item in (weeks or []) if item.get('week_key') == week_key), None)
        count = max(1, len((week or {}).get('milestone_indices') or []) or 1)
        return (1.0 / rate) / count
    return 1.0 / rate


def _write_concat_list(path, entries):
    lines = []
    for item in entries:
        frame_path = Path(item['path']).resolve()
        # ffmpeg concat demuxer needs escaped single quotes
        escaped = str(frame_path).replace("'", r"'\''")
        lines.append(f"file '{escaped}'")
        lines.append(f"duration {item['duration']:.6f}")
    # Repeat last file without duration so concat demuxer closes cleanly.
    if entries:
        escaped = str(Path(entries[-1]['path']).resolve()).replace("'", r"'\''")
        lines.append(f"file '{escaped}'")
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def _run_ffmpeg(concat_path, output_path):
    command = [
        'ffmpeg',
        '-y',
        '-f', 'concat',
        '-safe', '0',
        '-i', str(concat_path),
        '-vf', f'fps=30,format=yuv420p,scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:flags=lanczos',
        '-c:v', 'libx264',
        '-preset', 'veryfast',
        '-crf', '20',
        '-movflags', '+faststart',
        '-an',
        str(output_path),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-2000:] or result.stdout[-2000:] or 'ffmpeg failed')
    return result


def iter_generate_history_video(options=None, index_payload=None, db_comments=None):
    """Yield NDJSON-able progress events, then write an MP4 under history/videos/."""
    options = normalize_video_options(options or {})
    payload = index_payload or load_history_index() or {}
    milestones = payload.get('milestones') or []
    weeks = payload.get('weeks') or []
    if not milestones:
        yield {'type': 'error', 'error': 'No milestones available.'}
        return

    selected = select_video_milestone_indices(milestones, weeks, options)
    ready = []
    for index in selected:
        milestone = milestones[index]
        if milestone_ready_for_video(milestone):
            ready.append(milestone)
    if not ready:
        yield {'type': 'error', 'error': 'No cached milestone PNGs available for the selected playback options.'}
        return

    calendar_events = load_calendar_events_for_video() if options.get('include_calendar_labels') else []
    comment_rows = db_comments if options.get('include_comments') else []

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'history_{stamp}.mp4'
    output_path = video_output_dir() / filename
    work_dir = Path(tempfile.mkdtemp(prefix='history_video_', dir=str(video_output_dir())))

    try:
        yield {
            'type': 'start',
            'total': len(ready),
            'selected': len(selected),
            'options': options,
            'filename': filename,
        }
        entries = []
        prev_frame_path = None
        prev_image = None
        for offset, milestone in enumerate(ready):
            frame = compose_history_frame(
                milestone,
                options=options,
                calendar_events=calendar_events,
                db_comments=comment_rows,
            )
            frame_name = f'frame_{offset:05d}.jpg'
            frame_path = work_dir / frame_name
            frame.save(frame_path, format='JPEG', quality=90, optimize=True)
            duration = frame_duration_seconds(milestone, weeks, options)
            if options['fade_transitions'] and prev_image is not None and prev_frame_path is not None:
                blend = Image.blend(prev_image, frame, 0.5)
                blend_name = f'frame_{offset:05d}_fade.jpg'
                blend_path = work_dir / blend_name
                blend.save(blend_path, format='JPEG', quality=90, optimize=True)
                fade_duration = min(0.18, max(0.04, duration * 0.25))
                # Shorten the previous still so total pacing stays close to the requested rate.
                if entries:
                    entries[-1]['duration'] = max(0.04, entries[-1]['duration'] - (fade_duration / 2.0))
                entries.append({'path': str(blend_path), 'duration': fade_duration})
                duration = max(0.04, duration - (fade_duration / 2.0))
            entries.append({'path': str(frame_path), 'duration': duration})
            prev_frame_path = frame_path
            prev_image = frame
            yield {
                'type': 'progress',
                'phase': 'compose',
                'done': offset + 1,
                'total': len(ready),
                'percent': round(100.0 * (offset + 1) / len(ready), 1),
                'label': format_week_subtitle(milestone),
            }

        concat_path = work_dir / 'concat.txt'
        _write_concat_list(concat_path, entries)
        yield {
            'type': 'progress',
            'phase': 'encode',
            'done': len(ready),
            'total': len(ready),
            'percent': 100.0,
            'label': 'Encoding MP4…',
        }
        _run_ffmpeg(concat_path, output_path)
        total_duration = sum(item['duration'] for item in entries)
        yield {
            'type': 'done',
            'filename': filename,
            'path': str(output_path),
            'url': f'/api/production_history/video/download?file={filename}',
            'frames': len(ready),
            'duration_s': round(total_duration, 2),
            'width': VIDEO_WIDTH,
            'height': VIDEO_HEIGHT,
            'options': options,
        }
    except Exception as exc:
        yield {'type': 'error', 'error': str(exc)}
        if output_path.exists():
            try:
                output_path.unlink()
            except OSError:
                pass
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def estimate_video_selection(options=None, index_payload=None):
    options = normalize_video_options(options or {})
    payload = index_payload or load_history_index() or {}
    milestones = payload.get('milestones') or []
    weeks = payload.get('weeks') or []
    if options.get('milestone_index') is not None:
        selected = select_slideshow_milestone_indices(milestones, weeks, options)
    else:
        selected = select_video_milestone_indices(milestones, weeks, options)
    ready = [milestones[index] for index in selected if milestone_ready_for_video(milestones[index])]
    durations = [frame_duration_seconds(item, weeks, options) for item in ready]
    return {
        'success': True,
        'options': options,
        'selected': len(selected),
        'ready': len(ready),
        'missing': max(0, len(selected) - len(ready)),
        'duration_s': round(sum(durations), 2),
        'slides': len(ready),
        'width': VIDEO_WIDTH,
        'height': VIDEO_HEIGHT,
        'single_slide': options.get('milestone_index') is not None,
    }


def iter_generate_history_slideshow(options=None, index_payload=None, db_comments=None):
    """Yield progress events and write a one-slide-per-frame 1920x1080 PDF."""
    import img2pdf

    options = normalize_video_options(options or {})
    # Fade is meaningless for a static slideshow PDF.
    options['fade_transitions'] = False
    payload = index_payload or load_history_index() or {}
    milestones = payload.get('milestones') or []
    weeks = payload.get('weeks') or []
    if not milestones:
        yield {'type': 'error', 'error': 'No milestones available.'}
        return

    selected = select_slideshow_milestone_indices(milestones, weeks, options)
    if options.get('milestone_index') is not None and not selected:
        yield {
            'type': 'error',
            'error': f"Milestone index {options.get('milestone_index')} is out of range.",
        }
        return

    ready = []
    for index in selected:
        milestone = milestones[index]
        if milestone_ready_for_video(milestone):
            ready.append(milestone)
    if not ready:
        if options.get('milestone_index') is not None:
            yield {
                'type': 'error',
                'error': 'Current milestone is missing cached PNG frames. Rebuild history cache first.',
            }
        else:
            yield {
                'type': 'error',
                'error': 'No cached milestone PNGs available for the selected slideshow options.',
            }
        return

    calendar_events = load_calendar_events_for_video() if options.get('include_calendar_labels') else []
    comment_rows = db_comments if options.get('include_comments') else []

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    single = options.get('milestone_index') is not None
    filename = f"history_slide_{stamp}.pdf" if single else f'history_{stamp}.pdf'
    output_path = slideshow_output_dir() / filename
    work_dir = Path(tempfile.mkdtemp(prefix='history_slideshow_', dir=str(slideshow_output_dir())))

    try:
        yield {
            'type': 'start',
            'total': len(ready),
            'selected': len(selected),
            'options': options,
            'filename': filename,
            'format': 'pdf',
            'single_slide': single,
        }
        page_paths = []
        for offset, milestone in enumerate(ready):
            frame = compose_history_frame(
                milestone,
                options=options,
                calendar_events=calendar_events,
                db_comments=comment_rows,
            )
            page_name = f'slide_{offset:05d}.jpg'
            page_path = work_dir / page_name
            frame.save(page_path, format='JPEG', quality=92, optimize=True)
            page_paths.append(str(page_path))
            yield {
                'type': 'progress',
                'phase': 'compose',
                'done': offset + 1,
                'total': len(ready),
                'percent': round(100.0 * (offset + 1) / len(ready), 1),
                'label': format_week_subtitle(milestone),
            }

        yield {
            'type': 'progress',
            'phase': 'encode',
            'done': len(ready),
            'total': len(ready),
            'percent': 100.0,
            'label': 'Building PDF…',
        }
        with open(output_path, 'wb') as handle:
            handle.write(img2pdf.convert(page_paths))
        yield {
            'type': 'done',
            'filename': filename,
            'path': str(output_path),
            'url': f'/api/production_history/slideshow/download?file={filename}',
            'frames': len(ready),
            'slides': len(ready),
            'width': VIDEO_WIDTH,
            'height': VIDEO_HEIGHT,
            'format': 'pdf',
            'options': options,
            'single_slide': single,
        }
    except Exception as exc:
        yield {'type': 'error', 'error': str(exc)}
        if output_path.exists():
            try:
                output_path.unlink()
            except OSError:
                pass
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
