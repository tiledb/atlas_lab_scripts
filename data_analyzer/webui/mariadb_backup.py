"""Read MariaDB XLS/XLSX backups from /var/www/html/drive/mariadb_backup/."""

from __future__ import annotations

from datetime import datetime, timedelta, date as date_cls
from functools import lru_cache
from pathlib import Path
import fcntl
import re
import sqlite3
import zipfile
from xml.etree import ElementTree as ET

BACKUP_DIR = Path('/var/www/html/drive/mariadb_backup')
BACKUP_NAME_RE = re.compile(
    r'^data_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})\.(xlsx|xls)$'
)
SAFE_IDENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
EXCEL_EPOCH = datetime(1899, 12, 30)
BUILT_IN_DATE_FMT = {14, 15, 16, 17}
BUILT_IN_DATETIME_FMT = {22}


def is_safe_ident(name):
    return bool(name) and bool(SAFE_IDENT_RE.match(str(name)))


def list_backup_files():
    """Return backup xlsx files, newest first."""
    if not BACKUP_DIR.is_dir():
        return []
    files = []
    for path in BACKUP_DIR.iterdir():
        match = BACKUP_NAME_RE.match(path.name)
        if not match or not path.is_file():
            continue
        date_part, time_part, ext = match.groups()
        if ext.lower() != 'xlsx':
            continue
        try:
            stamp = datetime.strptime(f'{date_part} {time_part}', '%Y-%m-%d %H-%M-%S')
        except ValueError:
            continue
        files.append({
            'filename': path.name,
            'label': stamp.strftime('%Y-%m-%d %H:%M:%S'),
            'timestamp': stamp.strftime('%Y-%m-%dT%H:%M:%S'),
            'extension': ext,
        })
    files.sort(key=lambda item: item['timestamp'], reverse=True)
    for index, item in enumerate(files):
        item['latest'] = index == 0
        if item['latest']:
            item['label'] = f"{item['label']} (latest)"
    return files


def resolve_backup_path(filename):
    """Resolve a backup filename inside BACKUP_DIR, or None."""
    if not filename:
        return None
    name = Path(str(filename)).name
    if not BACKUP_NAME_RE.match(name):
        return None
    path = (BACKUP_DIR / name).resolve()
    try:
        path.relative_to(BACKUP_DIR.resolve())
    except ValueError:
        return None
    if path.is_file():
        return path
    return None


def list_backup_sheets(path):
    workbook = _load_workbook(path)
    return list(workbook['sheets'].keys())


def load_backup_sheet(path, sheet_name):
    workbook = _load_workbook(path)
    sheet = workbook['sheets'].get(sheet_name)
    if sheet is None:
        return None
    return {
        'columns': list(sheet['columns']),
        'rows': [dict(row) for row in sheet['rows']],
    }


def _load_workbook(path):
    path = Path(path)
    return _load_workbook_cached(str(path), path.stat().st_mtime)


@lru_cache(maxsize=8)
def _load_workbook_cached(path_str, _mtime):
    path = Path(path_str)
    if path.suffix.lower() != '.xlsx':
        raise ValueError(f'Unsupported backup format: {path.name}')
    return _read_xlsx(path)


def _local(tag):
    return tag.rsplit('}', 1)[-1] if tag else ''


def _read_xlsx(path):
    with zipfile.ZipFile(path) as archive:
        sheet_files = _sheet_targets(archive)
        shared_strings = _parse_shared_strings(archive)
        date_styles = _parse_date_styles(archive)
        sheets = {}
        for sheet_name, target in sheet_files:
            sheets[sheet_name] = _parse_sheet(
                archive,
                target,
                shared_strings,
                date_styles,
            )
        return {'sheets': sheets}


def _sheet_targets(archive):
    workbook_xml = archive.read('xl/workbook.xml')
    rels_xml = archive.read('xl/_rels/workbook.xml.rels')
    rels_root = ET.fromstring(rels_xml)
    rel_map = {}
    for rel in rels_root:
        if _local(rel.tag) != 'Relationship':
            continue
        rel_id = rel.attrib.get('Id')
        target = rel.attrib.get('Target')
        if rel_id and target:
            target = target.replace('\\', '/').lstrip('/')
            if not target.startswith('xl/'):
                target = f'xl/{target}'
            rel_map[rel_id] = target

    root = ET.fromstring(workbook_xml)
    sheets = []
    for node in root.iter():
        if _local(node.tag) != 'sheet':
            continue
        name = node.attrib.get('name')
        rel_id = None
        for key, value in node.attrib.items():
            if _local(key) == 'id':
                rel_id = value
                break
        target = rel_map.get(rel_id)
        if name and target:
            sheets.append((name, target))
    return sheets


def _parse_shared_strings(archive):
    try:
        xml = archive.read('xl/sharedStrings.xml')
    except KeyError:
        return []
    root = ET.fromstring(xml)
    values = []
    for si in root:
        if _local(si.tag) != 'si':
            continue
        texts = []
        for node in si.iter():
            if _local(node.tag) == 't' and node.text:
                texts.append(node.text)
        values.append(''.join(texts))
    return values


def _parse_date_styles(archive):
    try:
        xml = archive.read('xl/styles.xml')
    except KeyError:
        return {}
    root = ET.fromstring(xml)
    num_fmts = {}
    cell_xfs = []
    for node in root.iter():
        local = _local(node.tag)
        if local == 'numFmt':
            try:
                num_id = int(node.attrib.get('numFmtId', '0'))
            except ValueError:
                continue
            num_fmts[num_id] = node.attrib.get('formatCode') or ''
        elif local == 'cellXfs':
            for xf in node:
                if _local(xf.tag) == 'xf':
                    try:
                        cell_xfs.append(int(xf.attrib.get('numFmtId', '0')))
                    except ValueError:
                        cell_xfs.append(0)
    styles = {}
    for index, num_fmt_id in enumerate(cell_xfs):
        styles[index] = _date_kind(num_fmt_id, num_fmts.get(num_fmt_id, ''))
    return styles


def _date_kind(num_fmt_id, format_code):
    if num_fmt_id in BUILT_IN_DATETIME_FMT:
        return 'datetime'
    if num_fmt_id in BUILT_IN_DATE_FMT:
        return 'date'
    code = (format_code or '').lower()
    if not code:
        return None
    has_time = ('h' in code) or ('s' in code)
    has_date = ('y' in code) or ('d' in code) or ('m' in code)
    if has_time:
        return 'datetime'
    if has_date:
        return 'date'
    return None


def _parse_sheet(archive, target, shared_strings, date_styles):
    root = ET.fromstring(archive.read(target))
    sheet_data = None
    for node in root:
        if _local(node.tag) == 'sheetData':
            sheet_data = node
            break
    if sheet_data is None:
        return {'columns': [], 'rows': []}

    raw_rows = []
    max_col = 0
    for row_node in sheet_data:
        if _local(row_node.tag) != 'row':
            continue
        cells = {}
        for cell in row_node:
            if _local(cell.tag) != 'c':
                continue
            ref = cell.attrib.get('r') or ''
            col_idx = _column_index(ref)
            if col_idx is None:
                continue
            max_col = max(max_col, col_idx + 1)
            cells[col_idx] = _cell_value(cell, shared_strings, date_styles)
        raw_rows.append(cells)

    if not raw_rows:
        return {'columns': [], 'rows': []}

    header_cells = raw_rows[0]
    columns = []
    used = set()
    for index in range(max_col):
        name = header_cells.get(index)
        name = str(name).strip() if name is not None else ''
        if not name:
            name = f'column_{index + 1}'
        original = name
        suffix = 2
        while name in used:
            name = f'{original}_{suffix}'
            suffix += 1
        used.add(name)
        columns.append(name)

    rows = []
    for cells in raw_rows[1:]:
        if not cells:
            continue
        row = {}
        empty = True
        for index, column in enumerate(columns):
            value = cells.get(index)
            row[column] = value
            if value is not None and value != '':
                empty = False
        if not empty:
            rows.append(row)
    return {'columns': columns, 'rows': rows}


def _column_index(cell_ref):
    letters = ''.join(ch for ch in (cell_ref or '') if ch.isalpha())
    if not letters:
        return None
    index = 0
    for ch in letters.upper():
        index = index * 26 + (ord(ch) - 64)
    return index - 1


def _cell_value(cell, shared_strings, date_styles):
    cell_type = cell.attrib.get('t')
    style_idx = cell.attrib.get('s')
    date_kind = None
    if style_idx is not None:
        try:
            date_kind = date_styles.get(int(style_idx))
        except ValueError:
            date_kind = None

    if cell_type == 'inlineStr':
        texts = []
        for node in cell.iter():
            if _local(node.tag) == 't' and node.text:
                texts.append(node.text)
        return ''.join(texts) if texts else None

    if cell_type == 's':
        raw = _cell_raw_number(cell)
        try:
            idx = int(raw)
            return shared_strings[idx]
        except (TypeError, ValueError, IndexError):
            return None

    if cell_type == 'b':
        raw = _cell_raw_text(cell)
        return raw in ('1', 'true', 'TRUE')

    raw = _cell_raw_text(cell)
    if raw is None:
        return None
    if cell_type in (None, 'n'):
        try:
            number = float(raw)
        except ValueError:
            return raw
        if date_kind:
            return _excel_serial_to_text(number, date_kind)
        if number.is_integer():
            return int(number)
        return number
    return raw


def _cell_raw_text(cell):
    for node in cell:
        if _local(node.tag) == 'v':
            return node.text
    return None


def _cell_raw_number(cell):
    text = _cell_raw_text(cell)
    return text


def _excel_serial_to_text(serial, date_kind):
    try:
        total_seconds = int(round(float(serial) * 86400))
    except (TypeError, ValueError):
        return None
    moment = EXCEL_EPOCH + timedelta(seconds=total_seconds)
    if date_kind == 'date':
        return moment.strftime('%Y-%m-%d')
    return moment.strftime('%Y-%m-%d %H:%M:%S')


def canonical_value(value):
    """Normalize a value for display and equality checks."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.hour == 0 and value.minute == 0 and value.second == 0 and value.microsecond == 0:
            # Keep time when the original was datetime-like; callers compare strings.
            return value.strftime('%Y-%m-%d %H:%M:%S')
        return value.strftime('%Y-%m-%d %H:%M:%S')
    if hasattr(value, 'year') and hasattr(value, 'month') and not hasattr(value, 'hour'):
        return value.strftime('%Y-%m-%d')
    if isinstance(value, bool):
        return '1' if value else '0'
    if isinstance(value, bytes):
        try:
            value = value.decode('utf-8')
        except UnicodeDecodeError:
            value = value.decode('utf-8', errors='replace')
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return format(value, 'g')
    if isinstance(value, int):
        return str(value)
    text = str(value).strip()
    if text.lower() in ('none', 'null', ''):
        return None
    text = text.replace('T', ' ')
    if '.' in text and re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+$', text):
        text = text.split('.', 1)[0]
    return text


def values_equal(left, right):
    a = canonical_value(left)
    b = canonical_value(right)
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if a == b:
        return True
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return False


def serialize_value(value):
    return canonical_value(value)


def coerce_for_mysql(value, column_type):
    """Coerce a backup value to something mysql-connector can send."""
    if value is None or value == '':
        return None
    type_str = (column_type or '').lower()
    text = canonical_value(value)
    if text is None:
        return None
    if 'datetime' in type_str or 'timestamp' in type_str:
        if re.match(r'^\d{4}-\d{2}-\d{2}$', text):
            return f'{text} 00:00:00'
        return text
    if type_str.startswith('date'):
        return text[:10]
    if 'int' in type_str:
        try:
            return int(float(text))
        except (TypeError, ValueError):
            return text
    if any(token in type_str for token in ('decimal', 'float', 'double', 'numeric', 'real')):
        try:
            return float(text)
        except (TypeError, ValueError):
            return text
    return text


def row_key_id(pk_columns, row):
    if not pk_columns:
        return None
    parts = []
    for column in pk_columns:
        value = canonical_value((row or {}).get(column))
        parts.append('' if value is None else value)
    return '|'.join(parts)


class BackupInProgress(RuntimeError):
    """Raised when a live backup is already running."""


def create_current_backup(connection):
    """Snapshot tiledb tables into XLSX and SQLite files in BACKUP_DIR."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = BACKUP_DIR / '.backup.lock'
    lock_fh = open(lock_path, 'a+', encoding='utf-8')
    try:
        try:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise BackupInProgress('A backup is already running.') from exc

        cursor = connection.cursor()
        cursor.execute('SHOW TABLES')
        tables = []
        for row in cursor.fetchall():
            name = row[0] if not isinstance(row, dict) else next(iter(row.values()))
            if is_safe_ident(name):
                tables.append(name)

        sheets = []
        for table in tables:
            cursor.execute(f'SHOW COLUMNS FROM `{table}`')
            columns = []
            for row in cursor.fetchall():
                col = row[0] if not isinstance(row, dict) else row.get('Field')
                if is_safe_ident(col):
                    columns.append(col)
            cursor.execute(f'SELECT * FROM `{table}`')
            raw_rows = cursor.fetchall()
            data_rows = []
            for raw in raw_rows:
                if isinstance(raw, dict):
                    data_rows.append({column: raw.get(column) for column in columns})
                else:
                    data_rows.append({
                        column: raw[index] if index < len(raw) else None
                        for index, column in enumerate(columns)
                    })
            sheets.append((table, columns, data_rows))
        cursor.close()

        stamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        xlsx_path = BACKUP_DIR / f'data_{stamp}.xlsx'
        sqlite_path = BACKUP_DIR / f'sqlite_{stamp}.sqlite'
        _write_xlsx(xlsx_path, sheets)
        _write_sqlite(sqlite_path, sheets)
        _load_workbook_cached.cache_clear()
        return {
            'filename': xlsx_path.name,
            'sqlite': sqlite_path.name,
            'timestamp': stamp,
            'label': datetime.strptime(stamp, '%Y-%m-%d_%H-%M-%S').strftime('%Y-%m-%d %H:%M:%S'),
            'table_count': len(sheets),
            'row_count': sum(len(rows) for _, _, rows in sheets),
        }
    finally:
        try:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        lock_fh.close()


def _col_letter(index):
    result = ''
    number = index + 1
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _xml_escape(value):
    return (
        str(value)
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
    )


def _excel_serial(moment):
    delta = moment - EXCEL_EPOCH
    return delta.total_seconds() / 86400.0


def _cell_xml(ref, value):
    if value is None:
        return ''
    if isinstance(value, datetime):
        serial = _excel_serial(value.replace(tzinfo=None) if value.tzinfo else value)
        return f'<c r="{ref}" s="2" t="n"><v>{serial}</v></c>'
    if isinstance(value, date_cls):
        midnight = datetime(value.year, value.month, value.day)
        serial = int(_excel_serial(midnight))
        return f'<c r="{ref}" s="1" t="n"><v>{serial}</v></c>'
    if isinstance(value, bool):
        return f'<c r="{ref}" t="n"><v>{"1" if value else "0"}</v></c>'
    if isinstance(value, int) and not isinstance(value, bool):
        return f'<c r="{ref}" t="n"><v>{value}</v></c>'
    if isinstance(value, float):
        if value != value:  # NaN
            return ''
        if value.is_integer():
            return f'<c r="{ref}" t="n"><v>{int(value)}</v></c>'
        return f'<c r="{ref}" t="n"><v>{value}</v></c>'
    text = str(value)
    if hasattr(value, 'as_tuple') and hasattr(value, 'quantize'):
        try:
            number = float(value)
            if number.is_integer():
                return f'<c r="{ref}" t="n"><v>{int(number)}</v></c>'
            return f'<c r="{ref}" t="n"><v>{number}</v></c>'
        except (TypeError, ValueError):
            pass
    return (
        f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">'
        f'{_xml_escape(text)}</t></is></c>'
    )


def _sheet_xml(columns, rows):
    max_col = max(len(columns), 1)
    max_row = len(rows) + 1
    last = f'{_col_letter(max_col - 1)}{max_row}'
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        f'<dimension ref="A1:{last}"/>',
        '<sheetData>',
        '<row r="1">',
    ]
    for index, column in enumerate(columns):
        ref = f'{_col_letter(index)}1'
        parts.append(
            f'<c r="{ref}" t="inlineStr"><is><t>{_xml_escape(column)}</t></is></c>'
        )
    parts.append('</row>')
    for row_number, row in enumerate(rows, start=2):
        parts.append(f'<row r="{row_number}">')
        for index, column in enumerate(columns):
            ref = f'{_col_letter(index)}{row_number}'
            parts.append(_cell_xml(ref, row.get(column)))
        parts.append('</row>')
    parts.append('</sheetData></worksheet>')
    return ''.join(parts)


def _write_xlsx(path, sheets):
    content_types = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
    ]
    workbook_sheets = []
    rels = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
    ]
    for index, (name, _columns, _rows) in enumerate(sheets, start=1):
        content_types.append(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
        sheet_name = _xml_escape((name or f'sheet{index}')[:31])
        workbook_sheets.append(
            f'<sheet name="{sheet_name}" sheetId="{index}" r:id="rId{index}"/>'
        )
        rels.append(
            f'<Relationship Id="rId{index}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{index}.xml"/>'
        )
    rels.append(
        f'<Relationship Id="rId{len(sheets) + 1}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
    )
    rels.append('</Relationships>')
    content_types.append('</Types>')
    workbook = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets>' + ''.join(workbook_sheets) + '</sheets></workbook>'
    )
    styles = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<numFmts count="2">'
        '<numFmt numFmtId="165" formatCode="YYYY-MM-DD"/>'
        '<numFmt numFmtId="167" formatCode="YYYY-MM-DD HH:MM:SS"/>'
        '</numFmts>'
        '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="1"><fill><patternFill/></fill></fills>'
        '<borders count="1"><border/></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="3">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="167" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '</cellXfs></styleSheet>'
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>'
    )
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', ''.join(content_types))
        archive.writestr('_rels/.rels', root_rels)
        archive.writestr('xl/workbook.xml', workbook)
        archive.writestr('xl/_rels/workbook.xml.rels', ''.join(rels))
        archive.writestr('xl/styles.xml', styles)
        for index, (_name, columns, rows) in enumerate(sheets, start=1):
            archive.writestr(f'xl/worksheets/sheet{index}.xml', _sheet_xml(columns, rows))


def _write_sqlite(path, sheets):
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(str(path))
    cursor = conn.cursor()
    for table, columns, rows in sheets:
        if not columns:
            continue
        col_def = ', '.join(f'`{column}` TEXT' for column in columns)
        cursor.execute(f'DROP TABLE IF EXISTS `{table}`')
        cursor.execute(f'CREATE TABLE `{table}` ({col_def})')
        placeholders = ','.join(['?'] * len(columns))
        values = [
            [canonical_value(row.get(column)) for column in columns]
            for row in rows
        ]
        if values:
            cursor.executemany(
                f'INSERT INTO `{table}` VALUES ({placeholders})',
                values,
            )
    conn.commit()
    conn.close()

