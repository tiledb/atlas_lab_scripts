#!/usr/bin/env python3
"""Batch-generate PNG thumbnails for extra-plot HTML under the benchtests drive.

Walks /var/www/html/drive/benchtests/benchtest_id_*/DB_* and writes sibling
PNG previews used by the Benchtests MD-brick hover popup (and eye diagrams).

Modes:
  --worst (default): worst-channel hover plots
    ADC_Linearity_Samples (LG), CIS_Linearity_Samples (LG),
    CIS_Samples (LG), Integrator_Linearity_Samples
    — same selection as /api/benchtest_slot_previews in app.py
    plus all Link_Eye_Diagram_Samples HTML for those boards
  --all: every matching Samples / eye HTML (much slower / more disk)

Examples:
  myenv/bin/python generate_extra_plots_cache.py --worst
  myenv/bin/python generate_extra_plots_cache.py --worst -b 81
  myenv/bin/python generate_extra_plots_cache.py --all --force
  myenv/bin/python generate_extra_plots_cache.py --dry-run
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
WEBUI_DIR = SCRIPT_DIR / 'webui'
if str(WEBUI_DIR) not in sys.path:
    sys.path.insert(0, str(WEBUI_DIR))

from benchtest_plot_previews import (  # noqa: E402
    DRIVE_BENCHTESTS,
    PREVIEW_SPECS,
    build_slot_previews,
    ensure_preview_png,
    find_existing_plot,
    save_hover_previews_sidecar,
    start_preview_kaleido_server,
    stop_preview_kaleido_server,
)

_BT_DIR_RE = re.compile(r'^benchtest_id_(\d+)$')
_DB_DIR_RE = re.compile(r'^DB_(.+)$')
_MD_RE = re.compile(r'_MD(\d+)_', re.I)

# Channel/gain sample families (hover + --all).
SAMPLE_FILE_TOKENS = tuple(sorted({spec['file_token'] for spec in PREVIEW_SPECS}))
# Eye diagrams (no CH/gain; one HTML per uplink).
EYE_FILE_TOKEN = 'Link_Eye_Diagram_Samples'
ALL_FILE_TOKENS = SAMPLE_FILE_TOKENS + (EYE_FILE_TOKEN,)


def _iter_board_dirs(drive_dir: Path, benchtest_ids=None):
    roots = sorted(drive_dir.glob('benchtest_id_*'))
    for bt_dir in roots:
        match = _BT_DIR_RE.match(bt_dir.name)
        if not match or not bt_dir.is_dir():
            continue
        bt_id = int(match.group(1))
        if benchtest_ids is not None and bt_id not in benchtest_ids:
            continue
        for db_dir in sorted(bt_dir.glob('DB_*')):
            db_match = _DB_DIR_RE.match(db_dir.name)
            if not db_match or not db_dir.is_dir():
                continue
            serial = db_match.group(1)
            yield bt_id, serial, db_dir


def _discover_md_numbers(board_path: Path, serial_no: str):
    """Infer MD indexes from existing sample / eye HTML filenames."""
    found = set()
    for token in SAMPLE_FILE_TOKENS:
        for html in board_path.glob(f'DBSNo_{serial_no}_PPrGTH_{token}_MD*_CH*.html'):
            match = _MD_RE.search(html.name)
            if match:
                found.add(int(match.group(1)))
    for html in board_path.glob(
        f'DBSNo_{serial_no}_PPrGTH_{EYE_FILE_TOKEN}_MD*.html'
    ):
        match = _MD_RE.search(html.name)
        if match:
            found.add(int(match.group(1)))
    return sorted(found) or [1, 2, 3, 4]


def _collect_eye_html(board_path: Path, serial_no: str):
    """All Link_Eye_Diagram_Samples HTML for a board."""
    return sorted(
        board_path.glob(f'DBSNo_{serial_no}_PPrGTH_{EYE_FILE_TOKEN}_MD*.html')
    )


def _dedupe_paths(paths):
    seen = set()
    unique = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _collect_all_html(board_path: Path, serial_no: str):
    paths = []
    for token in SAMPLE_FILE_TOKENS:
        paths.extend(
            sorted(board_path.glob(f'DBSNo_{serial_no}_PPrGTH_{token}_MD*_CH*.html'))
        )
    paths.extend(_collect_eye_html(board_path, serial_no))
    return _dedupe_paths(paths)


def _collect_worst_html(benchtest_id, serial_no, board_path: Path, drive_dir: Path):
    """HTML files that hover would show (one per preview family per MD).

    Also includes all Link_Eye_Diagram_Samples HTML for the board, and
    writes/refreshes the hover sidecar JSON so the web UI never needs to
    re-parse Statistics.yaml on brick hover.
    """
    paths = []
    seen = set()
    for md_number in _discover_md_numbers(board_path, serial_no):
        payload = build_slot_previews(
            benchtest_id,
            serial_no,
            f'MD{md_number}',
            drive_dir=drive_dir,
            ensure_png=False,
            force_png=False,
        )
        # build_slot_previews already saves the sidecar on YAML/unique resolve;
        # re-save after we confirm disk paths so png names are current.
        save_hover_previews_sidecar(
            board_path, serial_no, md_number, payload.get('previews') or [],
        )
        for entry in payload.get('previews') or []:
            html_name = entry.get('html')
            if not html_name:
                continue
            html_path = board_path / html_name
            if not html_path.exists():
                # Rebuild path via finder if stats pointed at a missing file.
                html_path = find_existing_plot(
                    board_path,
                    serial_no,
                    entry.get('key') or '',
                    md_number,
                    gain=entry.get('gain'),
                    channel_index=entry.get('channel'),
                )
                # Prefer file_token from PREVIEW_SPECS when key is the family name.
                if html_path is None or not html_path.exists():
                    for spec in PREVIEW_SPECS:
                        if spec['key'] == entry.get('key'):
                            html_path = find_existing_plot(
                                board_path,
                                serial_no,
                                spec['file_token'],
                                md_number,
                                gain=entry.get('gain'),
                                channel_index=entry.get('channel'),
                            )
                            break
            if html_path is None or not html_path.exists():
                continue
            key = str(html_path)
            if key in seen:
                continue
            seen.add(key)
            paths.append(html_path)

    for html_path in _collect_eye_html(board_path, serial_no):
        key = str(html_path)
        if key in seen:
            continue
        seen.add(key)
        paths.append(html_path)
    return paths


def _needs_png(html_path: Path, force: bool) -> bool:
    from benchtest_plot_previews import _PNG_HEIGHT, _PNG_WIDTH

    png_path = html_path.with_suffix('.png')
    if force or not png_path.exists() or png_path.stat().st_size <= 0:
        return True
    if png_path.stat().st_mtime < html_path.stat().st_mtime:
        return True
    try:
        from PIL import Image
        with Image.open(png_path) as image:
            if image.size[0] < int(_PNG_WIDTH * 0.9) or image.size[1] < int(_PNG_HEIGHT * 0.9):
                return True
    except Exception:
        return True
    return False


def generate_cache(
    *,
    drive_dir: Path,
    benchtest_ids=None,
    mode: str = 'worst',
    force: bool = False,
    dry_run: bool = False,
):
    html_targets = []
    board_count = 0
    for bt_id, serial, board_path in _iter_board_dirs(drive_dir, benchtest_ids):
        board_count += 1
        if mode == 'all':
            html_targets.extend(_collect_all_html(board_path, serial))
        else:
            html_targets.extend(
                _collect_worst_html(bt_id, serial, board_path, drive_dir)
            )

    # Unique preserve order
    seen = set()
    unique_html = []
    for path in html_targets:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique_html.append(path)

    todo = [path for path in unique_html if _needs_png(path, force)]
    skipped = len(unique_html) - len(todo)

    print(
        f'Boards scanned: {board_count}  |  HTML matched: {len(unique_html)}  |  '
        f'to generate: {len(todo)}  |  already fresh: {skipped}  |  mode={mode}'
    )
    if dry_run:
        for path in todo[:50]:
            print(f'  [dry-run] would write {path.with_suffix(".png").name}')
        if len(todo) > 50:
            print(f'  ... and {len(todo) - 50} more')
        return {
            'boards': board_count,
            'matched': len(unique_html),
            'todo': len(todo),
            'written': 0,
            'failed': 0,
            'skipped': skipped,
        }

    written = 0
    failed = 0
    t0 = time.time()
    # One shared Chrome — avoids choreographer "unclean kill browser" from
    # parallel/oneshot kaleido sessions.
    start_preview_kaleido_server()
    try:
        total = len(todo)
        for index, html_path in enumerate(todo, start=1):
            rel = html_path
            try:
                rel = html_path.relative_to(drive_dir)
            except ValueError:
                pass
            print(
                f'  [{index}/{total}] generating {rel}',
                flush=True,
            )
            png_path = ensure_preview_png(html_path, force=force)
            if png_path is not None and png_path.exists():
                written += 1
                print(f'             wrote {png_path.name}', flush=True)
            else:
                failed += 1
                print(f'             FAILED {html_path.name}', flush=True)
    finally:
        stop_preview_kaleido_server()

    # Refresh hover sidecars so the web UI can serve without Statistics.yaml.
    if mode == 'worst':
        print('Refreshing hover preview sidecars…', flush=True)
        sidecar_count = 0
        for bt_id, serial, board_path in _iter_board_dirs(drive_dir, benchtest_ids):
            for md_number in _discover_md_numbers(board_path, serial):
                payload = build_slot_previews(
                    bt_id,
                    serial,
                    f'MD{md_number}',
                    drive_dir=drive_dir,
                    ensure_png=False,
                    force_png=False,
                )
                save_hover_previews_sidecar(
                    board_path, serial, md_number, payload.get('previews') or [],
                )
                sidecar_count += 1
        print(f'Wrote/refreshed {sidecar_count} hover sidecars', flush=True)

    elapsed = time.time() - t0
    print(
        f'Done in {elapsed:.1f}s: written={written} failed={failed} '
        f'skipped={skipped}'
    )
    return {
        'boards': board_count,
        'matched': len(unique_html),
        'todo': len(todo),
        'written': written,
        'failed': failed,
        'skipped': skipped,
        'elapsed_seconds': elapsed,
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Generate PNG thumbnails for extra-plot HTML under the benchtests drive.',
    )
    parser.add_argument(
        '--drive-dir',
        type=Path,
        default=DRIVE_BENCHTESTS,
        help=f'Benchtests root (default: {DRIVE_BENCHTESTS})',
    )
    parser.add_argument(
        '-b', '--benchtest-id',
        action='append',
        dest='benchtest_ids',
        help='Limit to one or more benchtest ids (repeatable)',
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        '--worst',
        action='store_const',
        const='worst',
        dest='mode',
        help=(
            'Worst-channel hover PNGs (default): ADC/CIS LG + Integrator, '
            'plus all Link_Eye_Diagram_Samples'
        ),
    )
    mode.add_argument(
        '--all',
        action='store_const',
        const='all',
        dest='mode',
        help=(
            'All ADC/CIS/Integrator sample HTML (every CH/gain) '
            'plus all Link_Eye_Diagram_Samples'
        ),
    )
    parser.set_defaults(mode='worst')
    parser.add_argument(
        '--force',
        action='store_true',
        help='Regenerate even if a newer PNG already exists',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='List work without writing PNGs',
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=1,
        help=argparse.SUPPRESS,  # kept for CLI compat; kaleido must stay serial
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    benchtest_ids = None
    if args.benchtest_ids:
        benchtest_ids = set()
        for raw in args.benchtest_ids:
            for part in str(raw).split(','):
                part = part.strip()
                if not part:
                    continue
                benchtest_ids.add(int(part))

    if not args.drive_dir.is_dir():
        print(f'Error: drive dir not found: {args.drive_dir}', file=sys.stderr)
        return 2

    if int(args.workers or 1) != 1:
        print(
            'Note: --workers ignored; kaleido PNG export runs sequentially '
            'on one Chrome to avoid unclean browser kills.'
        )

    generate_cache(
        drive_dir=args.drive_dir,
        benchtest_ids=benchtest_ids,
        mode=args.mode,
        force=bool(args.force),
        dry_run=bool(args.dry_run),
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
