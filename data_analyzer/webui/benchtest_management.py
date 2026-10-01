"""Create and edit MariaDB benchtest rows from Advanced Tools."""

from datetime import datetime

from mysql.connector import Error

from production_config import utc_from_interpreted_db_datetime

PASS_OPTIONS = [
    {'value': 0, 'label': 'Pending / Failed'},
    {'value': 1, 'label': 'Passed'},
    {'value': 3, 'label': 'Unknown'},
    {'value': -1, 'label': 'Ignored'},
]

PASS_LABELS = {option['value']: option['label'] for option in PASS_OPTIONS}
DEFAULT_TEST_PASS = 0


def format_benchtest_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    text = str(value).strip()
    return text or None


def parse_benchtest_datetime(value):
    text = str(value or '').strip().replace('T', ' ')
    if not text:
        return None
    if len(text) == 16:
        text = f'{text}:00'
    try:
        return datetime.strptime(text[:19], '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return False


def parse_slot_serial(value):
    text = str(value if value is not None else '').strip()
    if not text:
        return None
    try:
        serial = int(text)
    except (TypeError, ValueError):
        return False
    if serial <= 0:
        return False
    return serial


def serialize_benchtest(row):
    test_pass = row.get('test_pass')
    return {
        'id': row.get('id'),
        'test_start': format_benchtest_datetime(row.get('test_start')),
        'test_stop': format_benchtest_datetime(row.get('test_stop')),
        'test_op': row.get('test_op') or '',
        'test_pass': test_pass,
        'test_pass_label': PASS_LABELS.get(test_pass, str(test_pass)),
        'db_slot1': row.get('db_slot1'),
        'db_slot2': row.get('db_slot2'),
        'db_slot3': row.get('db_slot3'),
        'db_slot4': row.get('db_slot4'),
    }


def list_daughterboard_serials(cursor):
    cursor.execute('SELECT serial_no FROM daughterboard ORDER BY serial_no')
    serials = []
    for row in cursor.fetchall():
        value = row.get('serial_no') if isinstance(row, dict) else row[0]
        if value is not None:
            serials.append(int(value))
    return serials


def list_benchtests(cursor):
    cursor.execute(
        """
        SELECT id, test_start, test_stop, test_op, test_pass,
               db_slot1, db_slot2, db_slot3, db_slot4
        FROM benchtest
        ORDER BY id DESC
        """
    )
    rows = [serialize_benchtest(row) for row in cursor.fetchall()]
    operators = sorted({
        row['test_op']
        for row in rows
        if row.get('test_op')
    }, key=str.lower)
    return {
        'success': True,
        'benchtests': rows,
        'pass_options': PASS_OPTIONS,
        'operators': operators,
        'serials': list_daughterboard_serials(cursor),
    }


def get_benchtest(cursor, benchtest_id):
    cursor.execute(
        """
        SELECT id, test_start, test_stop, test_op, test_pass,
               db_slot1, db_slot2, db_slot3, db_slot4
        FROM benchtest
        WHERE id = %s
        """,
        (benchtest_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return serialize_benchtest(row)


def _payload_error(data, require_id=False):
    if not isinstance(data, dict):
        return 'Invalid request body', None

    benchtest_id = data.get('id')
    if benchtest_id in ('', None):
        benchtest_id = None
    else:
        try:
            benchtest_id = int(benchtest_id)
        except (TypeError, ValueError):
            return 'Invalid benchtest ID', None
        if benchtest_id <= 0:
            return 'Invalid benchtest ID', None
    if require_id and benchtest_id is None:
        return 'Benchtest ID required', None

    start_dt = parse_benchtest_datetime(data.get('test_start'))
    if start_dt is False:
        return 'Invalid test start datetime', None
    stop_dt = parse_benchtest_datetime(data.get('test_stop'))
    if stop_dt is False:
        return 'Invalid test stop datetime', None
    if start_dt and stop_dt and stop_dt < start_dt:
        return 'Test stop must be on or after test start', None

    test_op = str(data.get('test_op') or '').strip()
    if len(test_op) > 255:
        return 'Operator name is too long', None

    slots = []
    seen = set()
    for field in ('db_slot1', 'db_slot2', 'db_slot3', 'db_slot4'):
        serial = parse_slot_serial(data.get(field))
        if serial is False:
            return f'Invalid serial for {field}', None
        if serial is not None:
            if serial in seen:
                return f'Serial {serial} is used in more than one slot', None
            seen.add(serial)
        slots.append(serial)

    return None, {
        'id': benchtest_id,
        'test_start': utc_from_interpreted_db_datetime(start_dt) if start_dt else None,
        'test_stop': utc_from_interpreted_db_datetime(stop_dt) if stop_dt else None,
        'test_op': test_op or None,
        'test_pass': DEFAULT_TEST_PASS,
        'db_slot1': slots[0],
        'db_slot2': slots[1],
        'db_slot3': slots[2],
        'db_slot4': slots[3],
    }


def _missing_serials(cursor, values):
    serials = [value for value in values if value is not None]
    if not serials:
        return []
    placeholders = ', '.join(['%s'] * len(serials))
    cursor.execute(
        f'SELECT serial_no FROM daughterboard WHERE serial_no IN ({placeholders})',
        serials,
    )
    found = {row['serial_no'] for row in cursor.fetchall()}
    return [serial for serial in serials if serial not in found]


def create_benchtest(cursor, data):
    error, payload = _payload_error(data, require_id=False)
    if error:
        return error, None
    missing = _missing_serials(cursor, [
        payload['db_slot1'], payload['db_slot2'],
        payload['db_slot3'], payload['db_slot4'],
    ])
    if missing:
        return f'Board not found: {", ".join(str(item) for item in missing)}', None

    if payload['id'] is None:
        cursor.execute(
            """
            INSERT INTO benchtest (
                test_start, test_stop, test_op, test_pass,
                db_slot1, db_slot2, db_slot3, db_slot4
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                payload['test_start'], payload['test_stop'], payload['test_op'],
                DEFAULT_TEST_PASS, payload['db_slot1'], payload['db_slot2'],
                payload['db_slot3'], payload['db_slot4'],
            ),
        )
        benchtest_id = cursor.lastrowid
    else:
        cursor.execute('SELECT id FROM benchtest WHERE id = %s', (payload['id'],))
        if cursor.fetchone():
            return f'Benchtest ID {payload["id"]} already exists', None
        cursor.execute(
            """
            INSERT INTO benchtest (
                id, test_start, test_stop, test_op, test_pass,
                db_slot1, db_slot2, db_slot3, db_slot4
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                payload['id'], payload['test_start'], payload['test_stop'],
                payload['test_op'], DEFAULT_TEST_PASS, payload['db_slot1'],
                payload['db_slot2'], payload['db_slot3'], payload['db_slot4'],
            ),
        )
        benchtest_id = payload['id']
    return None, get_benchtest(cursor, benchtest_id)


def update_benchtest(cursor, benchtest_id, data):
    data = dict(data or {})
    data['id'] = benchtest_id
    error, payload = _payload_error(data, require_id=True)
    if error:
        return error, None
    if payload['id'] != benchtest_id:
        return 'Benchtest ID cannot be changed', None

    cursor.execute('SELECT id FROM benchtest WHERE id = %s', (benchtest_id,))
    if not cursor.fetchone():
        return f'Benchtest {benchtest_id} not found', None

    missing = _missing_serials(cursor, [
        payload['db_slot1'], payload['db_slot2'],
        payload['db_slot3'], payload['db_slot4'],
    ])
    if missing:
        return f'Board not found: {", ".join(str(item) for item in missing)}', None

    # Result is set by DBQ_Mk6; never overwrite test_pass from the editor.
    cursor.execute(
        """
        UPDATE benchtest
        SET test_start = %s,
            test_stop = %s,
            test_op = %s,
            db_slot1 = %s,
            db_slot2 = %s,
            db_slot3 = %s,
            db_slot4 = %s
        WHERE id = %s
        """,
        (
            payload['test_start'], payload['test_stop'], payload['test_op'],
            payload['db_slot1'], payload['db_slot2'],
            payload['db_slot3'], payload['db_slot4'], benchtest_id,
        ),
    )
    return None, get_benchtest(cursor, benchtest_id)


def mark_benchtest_for_requalify(cursor, benchtest_id):
    """Reset test_pass to pending so DBQ_Mk6 will reprocess the row."""
    cursor.execute('SELECT id FROM benchtest WHERE id = %s', (benchtest_id,))
    if not cursor.fetchone():
        return f'Benchtest {benchtest_id} not found', None
    cursor.execute(
        'UPDATE benchtest SET test_pass = %s WHERE id = %s',
        (DEFAULT_TEST_PASS, benchtest_id),
    )
    return None, get_benchtest(cursor, benchtest_id)


def mysql_integrity_message(exc):
    if not isinstance(exc, Error):
        return str(exc)
    message = str(exc)
    if 'foreign key constraint' in message.lower():
        return 'One or more slot serials are not in the daughterboard table.'
    if 'duplicate' in message.lower():
        return 'A benchtest with that ID already exists.'
    return message
