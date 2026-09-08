from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, Response, stream_with_context, has_request_context
from pathlib import Path
import mysql.connector
from mysql.connector import Error
from ruamel.yaml import YAML
import os
import subprocess
import re
import json
import argparse
import sys

from production_summary import build_production_summary
from production_statistics import build_production_statistics
from production_history import (
    build_history_snapshot,
    build_production_history,
    cache_milestone_snapshot,
    clear_history_cache_scope,
    iter_rebuild_history_cache,
    load_cached_snapshot,
    load_history_index,
    rebuild_history_cache,
)
from production_history_video import (
    estimate_video_selection,
    fetch_db_comments_for_video,
    iter_generate_history_slideshow,
    iter_generate_history_video,
    resolve_slideshow_path,
    resolve_video_path,
)
from burn_in import build_burn_in_overview, build_burn_in_plot_all_slots, build_burn_in_plot_for_slot
from benchtest_results import get_failed_tests_for_serial
from long_burn_in import build_long_burn_in_overview, build_long_burn_in_plot
from production_config import (
    SCHEDULE_CSV_PATH,
    backup_and_save_schedule,
    dashboard_tab_order_payload,
    load_production_config,
    save_burn_in_config,
    save_dashboard_tab_order,
    save_long_burn_in_config,
    save_production_config,
)
from production_schedule import load_calendar_grid, save_calendar_grid

os.environ['TZ'] = 'UTC'
app = Flask(__name__)
app.secret_key = '6#1-&75-?66'

# Function to read burned status from benchtest results log file
def get_burned_status(serial, benchtest_id, drive_dir="/var/www/html/drive/benchtests/"):
    """
    Read benchtest results log file and extract burned status for a specific serial number.
    
    Args:
        serial: Serial number of the board
        benchtest_id: Benchtest ID (integer)
        drive_dir: Directory containing benchtest folders
        
    Returns:
        str: "burned" if value is 1, "not burned" if value is 0 or -1, None if not found
    """
    benchtest_folder = f"benchtest_id_{benchtest_id}"
    log_file = Path(drive_dir) / benchtest_folder / f"{benchtest_folder}_results.log"
    
    if not log_file.exists():
        return None
    
    try:
        with open(log_file, 'r') as f:
            lines = f.readlines()
        
        # Look for the serial number in the log file
        serial_str = str(serial)
        found_serial = False
        burned_value = None
        
        for line in lines:
            line = line.strip()
            if f"DaughterBoard with Serial No: {serial_str}" in line:
                found_serial = True
            elif found_serial and line.startswith("burned:"):
                # Extract the burned value
                parts = line.split(':')
                if len(parts) >= 2:
                    burned_value = parts[1].strip()
                    break
        
        if burned_value:
            if burned_value == '1':
                return "not burned"
            elif burned_value in ['0', '-1']:
                return "burned"
        
        return None
        
    except Exception as e:
        print(f"Error reading log file {log_file}: {e}")
        return None

# Database configuration
host = 'piro-atlas-lab-vserver-01.fysik.su.se'
database = 'tiledb'
MAX_BRICK_WALL_BATCH = 13

# Paths
SCRIPT_DIR = Path(__file__).parent.parent
VARS_YAML_PATH = SCRIPT_DIR / 'vars.yaml'
SECRETS_YAML_PATH = SCRIPT_DIR.parent / 'secrets' / 'secrets.yaml'
DBQ_SCRIPT_PATH = SCRIPT_DIR / 'DBQ_Mk6.py'
PRODUCTION_PLOTS_PATH = SCRIPT_DIR / 'production_plots_v1.py'

# Template names
login_template = "login.html"
dashboard_template = "dashboard.html"
run_script_template = "run_script.html"
edit_vars_template = "edit_vars.html"
edit_production_template = "edit_production.html"
edit_burn_in_template = "edit_burn_in.html"
edit_long_burn_in_template = "edit_long_burn_in.html"
edit_history_cache_template = "edit_history_cache.html"
edit_tab_order_template = "edit_tab_order.html"
edit_dbq_plot_template = "edit_dbq_plot.html"

def load_secrets():
    """Load database credentials from secrets.yaml."""
    try:
        yaml_handler = YAML()
        with open(SECRETS_YAML_PATH, 'r') as f:
            return yaml_handler.load(f)
    except Exception as e:
        print(f"Error loading secrets.yaml: {e}")
        return {}


def is_guest_mode():
    return session.get('guest_mode', False)


def require_full_access():
    """Return a redirect response if the current session is guest-only."""
    if is_guest_mode():
        flash('This action is not available in guest mode.')
        return redirect(url_for('dashboard'))
    return None


def get_db_connection():
    """Create and return a database connection.

    Uses the logged-in Flask session when available; otherwise falls back to
    credentials in secrets.yaml (for CLI tools such as --rebuild-history-cache).
    """
    db_user = None
    db_pass = None
    db_name = database

    if has_request_context() and session.get('logged_in'):
        db_user = session.get('db_user')
        db_pass = session.get('db_pass')
        db_name = session.get('db_name') or database

    if not db_user or db_pass is None:
        secrets = load_secrets()
        mariadb = secrets.get('tiledb-mariadb', {}) if isinstance(secrets, dict) else {}
        db_user = mariadb.get('user')
        db_pass = mariadb.get('password')

    if not db_user or db_pass is None:
        print('Error while connecting to database: missing credentials')
        return None

    try:
        conn = mysql.connector.connect(
            host=host,
            user=db_user,
            password=db_pass,
            database=db_name,
        )
        conn.time_zone = '+00:00'
        return conn
    except Error as e:
        print("Error while connecting to database:", e)
        return None

def load_vars_yaml():
    """Load vars.yaml configuration preserving format."""
    try:
        yaml_handler = YAML()
        yaml_handler.preserve_quotes = True
        with open(VARS_YAML_PATH, 'r') as f:
            return yaml_handler.load(f)
    except Exception as e:
        print(f"Error loading vars.yaml: {e}")
        return {}


def load_vars_yaml_for_edit():
    """Normalized vars for the edit UI: thresholds/essential/caption/dimensions per variable."""
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    from vars_config import (
        format_thresholds_for_form,
        normalize_vars_config,
    )
    normalized = normalize_vars_config(load_vars_yaml())
    for table_vars in normalized.values():
        for var_name, entry in table_vars.items():
            entry['thresholds_text'] = format_thresholds_for_form(entry.get('thresholds'))
    return normalized


def save_vars_yaml(data):
    """Save configuration to vars.yaml in the thresholds/essential/caption/dimensions schema."""
    try:
        if str(SCRIPT_DIR) not in sys.path:
            sys.path.insert(0, str(SCRIPT_DIR))
        from vars_config import normalize_var_entry, parse_thresholds_text
        from ruamel.yaml.comments import CommentedMap, CommentedSeq

        out = CommentedMap()
        for table_name, table_vars in (data or {}).items():
            tmap = CommentedMap()
            for var_name, entry in (table_vars or {}).items():
                if isinstance(entry, dict):
                    thresholds = entry.get('thresholds')
                    if isinstance(thresholds, str):
                        thresholds = parse_thresholds_text(thresholds)
                    elif thresholds is None:
                        thresholds = []
                    elif not isinstance(thresholds, list):
                        thresholds = [thresholds]
                    raw = {
                        'thresholds': thresholds,
                        'essential': entry.get('essential', 0),
                        'caption': entry.get('caption', var_name),
                        'dimensions': entry.get('dimensions', ''),
                    }
                else:
                    raw = entry
                normalized = normalize_var_entry(raw, name=var_name)
                emap = CommentedMap()
                thr = CommentedSeq(normalized['thresholds'])
                thr.fa.set_flow_style()
                emap['thresholds'] = thr
                emap['essential'] = int(normalized['essential'])
                emap['caption'] = normalized['caption']
                emap['dimensions'] = normalized['dimensions']
                tmap[var_name] = emap
            out[table_name] = tmap

        yaml_handler = YAML()
        yaml_handler.preserve_quotes = True
        yaml_handler.default_flow_style = False
        yaml_handler.indent(mapping=2, sequence=4, offset=2)
        yaml_handler.width = 4096
        with open(VARS_YAML_PATH, 'w') as f:
            yaml_handler.dump(out, f)
        return True
    except Exception as e:
        print(f"Error saving vars.yaml: {e}")
        return False

def decode_serial(serial):
    """Decode serial number to get tag, batch, and position.
    Format: TTBBDDD
      TT  = Tag
      BB  = Batch
      DDD = Position inside batch
    Example: 1102020
      11 -> tag
      02 -> batch
      020 -> position
    """
    serial = str(serial).zfill(7)
    return {
        "tag": int(serial[:2]),
        "batch": int(serial[2:4]),
        "position": int(serial[4:7])
    }

# Routes

@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        guest_mode = request.form.get('guest_mode') == 'guest'

        if guest_mode:
            secrets = load_secrets()
            mariadb = secrets.get('tiledb-mariadb', {})
            db_user = mariadb.get('user')
            db_pass = mariadb.get('password')
            if not db_user or not db_pass:
                flash('Guest mode is not configured. Missing database credentials.')
                return render_template(login_template)
            try:
                conn = mysql.connector.connect(
                    host=host,
                    user=db_user,
                    password=db_pass,
                    database=database,
                )
                if conn.is_connected():
                    session['logged_in'] = True
                    session['guest_mode'] = True
                    session['db_user'] = db_user
                    session['db_pass'] = db_pass
                    session['db_name'] = database
                    conn.close()
                    return redirect(url_for('dashboard'))
            except Error as e:
                flash("Error connecting to database in guest mode: " + str(e))
                return render_template(login_template)
        else:
            username = request.form['username']
            password = request.form['password']
            try:
                conn = mysql.connector.connect(
                    host=host,
                    user=username,
                    password=password,
                    database=database,
                )
                if conn.is_connected():
                    session['logged_in'] = True
                    session['guest_mode'] = False
                    session['db_user'] = username
                    session['db_pass'] = password
                    session['db_name'] = database
                    conn.close()
                    return redirect(url_for('dashboard'))
            except Error as e:
                flash("Error connecting to database: " + str(e))
                return render_template(login_template)
    return render_template(login_template)

@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    tab_payload = dashboard_tab_order_payload()
    return render_template(
        dashboard_template,
        dashboard_tab_order=tab_payload['order'],
    )

def parse_benchtest_id_spec(raw):
    """Parse '1,3-5,10' / '2-5' / '7' into a sorted unique list of ints."""
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []
    ids = []
    for part in text.split(','):
        token = part.strip()
        if not token:
            continue
        if '-' in token:
            ends = token.split('-', 1)
            try:
                start = int(ends[0].strip())
                end = int(ends[1].strip())
            except ValueError as exc:
                raise ValueError(f'Invalid benchtest range "{token}"') from exc
            if end < start:
                start, end = end, start
            ids.extend(range(start, end + 1))
        else:
            try:
                ids.append(int(token))
            except ValueError as exc:
                raise ValueError(f'Invalid benchtest id "{token}"') from exc
    # Preserve order while uniquifying
    seen = set()
    ordered = []
    for benchtest_id in ids:
        if benchtest_id not in seen:
            seen.add(benchtest_id)
            ordered.append(benchtest_id)
    return ordered


def fetch_all_benchtest_ids():
    """Return all benchtest IDs from the database, ascending."""
    conn = get_db_connection()
    if not conn:
        raise RuntimeError('Database connection failed while listing benchtests')
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM benchtest ORDER BY id')
        rows = cursor.fetchall()
        cursor.close()
        ids = []
        for row in rows:
            # Support both tuple and dict cursors
            value = row[0] if not isinstance(row, dict) else row.get('id')
            if value is not None:
                ids.append(int(value))
        return ids
    finally:
        conn.close()


def run_dbq_mk6_for_benchtest(benchtest_id, regenerate_mode=None, daughterboard_id=None, timeout=1800):
    """Run one DBQ_Mk6 process for a single benchtest ID."""
    cmd = ['python3', str(DBQ_SCRIPT_PATH)]
    if regenerate_mode and regenerate_mode != 'none':
        cmd.extend(['-r', str(regenerate_mode)])
    cmd.extend(['-b', str(benchtest_id)])
    if daughterboard_id:
        cmd.extend(['-d', str(daughterboard_id)])
    return subprocess.run(
        cmd,
        cwd=SCRIPT_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


@app.route('/run_script', methods=['GET', 'POST'])
def run_script():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    blocked = require_full_access()
    if blocked:
        return blocked
    
    message = ""
    error = None
    
    if request.method == 'POST':
        regenerate_mode = request.form.get('regenerate_mode') or 'none'
        specific_benchtest_ids = request.form.get('specific_benchtest_ids')
        specific_daughterboard_id = request.form.get('specific_daughterboard_id')
        
        try:
            scheduled_ids = parse_benchtest_id_spec(specific_benchtest_ids)
            run_sequential = (
                regenerate_mode == 'all'
                or len(scheduled_ids) > 1
            )

            if run_sequential:
                if not scheduled_ids:
                    scheduled_ids = fetch_all_benchtest_ids()
                if not scheduled_ids:
                    error = 'No benchtest IDs found to process.'
                else:
                    output_chunks = [
                        f'Running DBQ_Mk6 sequentially for {len(scheduled_ids)} benchtest(s): '
                        f'{", ".join(str(i) for i in scheduled_ids)}\n'
                        f'(one python process at a time to limit memory use)\n'
                    ]
                    failures = []
                    for benchtest_id in scheduled_ids:
                        output_chunks.append(f'\n===== Benchtest {benchtest_id} =====\n')
                        output_chunks.append(
                            f'$ python3 DBQ_Mk6.py'
                            f'{"" if regenerate_mode == "none" else f" -r {regenerate_mode}"}'
                            f' -b {benchtest_id}'
                            f'{"" if not specific_daughterboard_id else f" -d {specific_daughterboard_id}"}\n'
                        )
                        try:
                            result = run_dbq_mk6_for_benchtest(
                                benchtest_id,
                                regenerate_mode=regenerate_mode,
                                daughterboard_id=specific_daughterboard_id or None,
                            )
                        except subprocess.TimeoutExpired:
                            failures.append(benchtest_id)
                            output_chunks.append(
                                f'ERROR: benchtest {benchtest_id} timed out.\n'
                            )
                            continue

                        if result.stdout:
                            output_chunks.append(result.stdout)
                        if result.stderr:
                            output_chunks.append(result.stderr)
                        if result.returncode != 0:
                            failures.append(benchtest_id)
                            output_chunks.append(
                                f'ERROR: benchtest {benchtest_id} failed '
                                f'(exit {result.returncode}).\n'
                            )
                        else:
                            output_chunks.append(
                                f'OK: benchtest {benchtest_id} finished.\n'
                            )

                    if failures:
                        output_chunks.append(
                            f'\nFinished with failures on benchtests: '
                            f'{", ".join(str(i) for i in failures)}\n'
                        )
                    else:
                        output_chunks.append('\nAll scheduled benchtests finished successfully.\n')

                    # Refresh production plots once after the sequential batch
                    if len(failures) < len(scheduled_ids):
                        output_chunks.append('\n===== Production plots =====\n')
                        production_cmd = ['python3', str(PRODUCTION_PLOTS_PATH)]
                        production_result = subprocess.run(
                            production_cmd,
                            cwd=SCRIPT_DIR,
                            capture_output=True,
                            text=True,
                            timeout=1800,
                        )
                        if production_result.stdout:
                            output_chunks.append(production_result.stdout)
                        if production_result.stderr:
                            output_chunks.append(production_result.stderr)
                        if production_result.returncode == 0:
                            output_chunks.append('Production plots updated successfully.\n')
                        else:
                            output_chunks.append(
                                'Production plots update failed '
                                '(DBQ_Mk6 sequential runs completed).\n'
                            )

                    message = ''.join(output_chunks)
                    if failures and not message:
                        error = f'Failed benchtests: {", ".join(str(i) for i in failures)}'
            else:
                # Single benchtest (or non-all mode with no / one ID): one process
                cmd = ['python3', str(DBQ_SCRIPT_PATH)]
                if regenerate_mode and regenerate_mode != 'none':
                    cmd.extend(['-r', regenerate_mode])
                if scheduled_ids:
                    cmd.extend(['-b', str(scheduled_ids[0])])
                if specific_daughterboard_id:
                    cmd.extend(['-d', specific_daughterboard_id])

                result = subprocess.run(
                    cmd,
                    cwd=SCRIPT_DIR,
                    capture_output=True,
                    text=True,
                    timeout=1800,
                )

                if result.returncode == 0:
                    message = f"DBQ_Mk6 script executed successfully.\n{result.stdout}\n\n"
                    production_cmd = ['python3', str(PRODUCTION_PLOTS_PATH)]
                    production_result = subprocess.run(
                        production_cmd,
                        cwd=SCRIPT_DIR,
                        capture_output=True,
                        text=True,
                        timeout=1800,
                    )
                    if production_result.returncode == 0:
                        message += f"Production plots updated successfully.\n{production_result.stdout}"
                    else:
                        message += (
                            "Production plots update failed (but DBQ_Mk6 succeeded).\n"
                            f"Error: {production_result.stderr}"
                        )
                else:
                    error = f"DBQ_Mk6 script execution failed. Error:\n{result.stderr}"

        except subprocess.TimeoutExpired:
            error = "Script execution timed out."
        except Exception as e:
            error = f"Error running script: {str(e)}"
    
    return render_template(run_script_template, message=message, error=error)

@app.route('/edit_vars', methods=['GET', 'POST'])
def edit_vars():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    blocked = require_full_access()
    if blocked:
        return blocked
    
    message = ""
    error = None
    
    if request.method == 'POST':
        if str(SCRIPT_DIR) not in sys.path:
            sys.path.insert(0, str(SCRIPT_DIR))
        from vars_config import parse_thresholds_text

        yaml_data = {}
        table_names = request.form.getlist('table_name')
        
        for table_name in table_names:
            yaml_data[table_name] = {}
            var_names = request.form.getlist(f'{table_name}_var_name')
            
            for var_name in var_names:
                thresholds_str = request.form.get(f'{table_name}_{var_name}_thresholds', '')
                essential_str = request.form.get(f'{table_name}_{var_name}_essential', '0')
                caption_str = request.form.get(f'{table_name}_{var_name}_caption', var_name)
                dimensions_str = request.form.get(f'{table_name}_{var_name}_dimensions', '')
                try:
                    essential = 1 if str(essential_str).strip() in ('1', 'true', 'True', 'on') else 0
                    yaml_data[table_name][var_name] = {
                        'thresholds': parse_thresholds_text(thresholds_str),
                        'essential': essential,
                        'caption': (caption_str or var_name).strip() or var_name,
                        'dimensions': (dimensions_str or '').strip(),
                    }
                except Exception as e:
                    error = f"Error parsing value for {table_name}.{var_name}: {str(e)}"
                    return render_template(
                        edit_vars_template,
                        error=error,
                        vars_data=load_vars_yaml_for_edit(),
                    )
        
        if save_vars_yaml(yaml_data):
            message = "Configuration saved successfully!"
        else:
            error = "Failed to save configuration."
    
    vars_data = load_vars_yaml_for_edit()
    return render_template(edit_vars_template, message=message, error=error, vars_data=vars_data)

@app.route('/edit_production')
def edit_production():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    blocked = require_full_access()
    if blocked:
        return blocked

    return render_template(
        edit_production_template,
        config=load_production_config(),
    )

@app.route('/edit_burn_in')
def edit_burn_in():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    blocked = require_full_access()
    if blocked:
        return blocked

    from burn_in import _burn_in_config_payload
    return render_template(
        edit_burn_in_template,
        config=_burn_in_config_payload(load_production_config()),
    )

@app.route('/edit_long_burn_in')
def edit_long_burn_in():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    blocked = require_full_access()
    if blocked:
        return blocked

    from long_burn_in import _config_payload
    return render_template(
        edit_long_burn_in_template,
        config=_config_payload(load_production_config()),
    )


@app.route('/edit_history_cache')
def edit_history_cache():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    blocked = require_full_access()
    if blocked:
        return blocked

    return render_template(
        edit_history_cache_template,
        config=load_production_config(),
    )


@app.route('/edit_dbq_plot')
def edit_dbq_plot():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    blocked = require_full_access()
    if blocked:
        return blocked

    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    from dbq_plot_config import CONFIG_PATH, load_dbq_plot_config

    return render_template(
        edit_dbq_plot_template,
        config=load_dbq_plot_config(),
        config_path=str(CONFIG_PATH),
    )


@app.route('/api/dbq_plot/config', methods=['GET', 'POST'])
def dbq_plot_config_api():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401

    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    from dbq_plot_config import load_dbq_plot_config, save_dbq_plot_config

    if request.method == 'GET':
        return jsonify({'success': True, 'config': load_dbq_plot_config()})

    blocked = require_full_access()
    if blocked:
        return jsonify({'error': 'Not allowed in guest mode'}), 403

    try:
        data = request.get_json(silent=True) or {}
        saved = save_dbq_plot_config(data)
        return jsonify({'success': True, 'config': saved})
    except Exception as exc:
        print(f'Error saving DBQ plot config: {exc}')
        return jsonify({'error': str(exc)}), 500


@app.route('/api/dbq_plot/config/reset', methods=['POST'])
def dbq_plot_config_reset_api():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401

    blocked = require_full_access()
    if blocked:
        return jsonify({'error': 'Not allowed in guest mode'}), 403

    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    from dbq_plot_config import DEFAULT_DBQ_PLOT_CONFIG, save_dbq_plot_config

    try:
        saved = save_dbq_plot_config(DEFAULT_DBQ_PLOT_CONFIG)
        return jsonify({'success': True, 'config': saved})
    except Exception as exc:
        print(f'Error resetting DBQ plot config: {exc}')
        return jsonify({'error': str(exc)}), 500


@app.route('/edit_tab_order')
def edit_tab_order():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    blocked = require_full_access()
    if blocked:
        return blocked

    from production_config import DASHBOARD_TAB_LABELS, DEFAULT_DASHBOARD_TAB_ORDER
    payload = dashboard_tab_order_payload()
    return render_template(
        edit_tab_order_template,
        tab_order=payload['order'],
        default_order=list(DEFAULT_DASHBOARD_TAB_ORDER),
        labels=DASHBOARD_TAB_LABELS,
    )


@app.route('/api/dashboard_tab_order', methods=['GET', 'POST'])
def dashboard_tab_order_api():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401

    if request.method == 'GET':
        payload = dashboard_tab_order_payload()
        return jsonify({'success': True, **payload})

    blocked = require_full_access()
    if blocked:
        return jsonify({'error': 'Not allowed in guest mode'}), 403

    try:
        data = request.get_json() or {}
        saved = save_dashboard_tab_order(data.get('order') or [])
        payload = dashboard_tab_order_payload(saved)
        return jsonify({'success': True, **payload})
    except Exception as exc:
        print(f'Error saving dashboard tab order: {exc}')
        return jsonify({'error': str(exc)}), 500

@app.route('/api/brick_wall_data')
def brick_wall_data():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401

    from brick_wall_cache import load_brick_wall_cache, save_brick_wall_cache

    def _cache_fallback_response(reason):
        cached = load_brick_wall_cache()
        if not cached:
            return None
        return jsonify({
            'success': True,
            'boards_by_batch': cached.get('boards_by_batch') or {},
            'cached': True,
            'cached_at': cached.get('cached_at'),
            'plot_html': cached.get('plot_html') or 'production_brick_wall_latest.html',
            'cache_fallback': True,
            'cache_fallback_reason': reason,
        })
    
    try:
        conn = get_db_connection()
        if not conn:
            fallback = _cache_fallback_response('Database connection failed')
            if fallback:
                return fallback
            return jsonify({'error': 'Database connection failed'}), 500
        
        cursor = conn.cursor(dictionary=True)
        
        # Query all daughterboard data
        db_query = """
            SELECT d.serial_no, d.batch_id, d.db_status, d.burn_in,
                   d.burn_in_start, d.burn_in_stop,
                   d.kin_lot, d.pro_lot, d.gbt_lot,
                   d.ina_lot, d.ltm_lot, d.mos_lot, d.op4_lot, d.ok4_lot, d.ok1_lot,
                   d.mem_lot, d.sfp_lot, d.e_test, d.p_test, d.a0, d.a1, d.b0, d.b1
            FROM daughterboard d
            ORDER BY d.serial_no
        """
        cursor.execute(db_query)
        db_rows = cursor.fetchall()
        
        # Query benchtest information
        serial_to_benchtests = {}
        try:
            benchtest_query = """
                SELECT id, test_start, test_stop, test_op, test_pass,
                       db_slot1, db_slot2, db_slot3, db_slot4
                FROM benchtest
                ORDER BY id
            """
            cursor.execute(benchtest_query)
            benchtest_rows = cursor.fetchall()
            print(f"Benchtest rows: {len(benchtest_rows)}")
            if benchtest_rows:
                print(f"First benchtest row: {benchtest_rows[0]}")

            # Query comment information for bricks (foreign_typ = 3) and benchtests (foreign_typ = 4)
            serial_to_comments = {}
            try:
                # First, check if comment table exists
                cursor.execute("SHOW TABLES LIKE 'comment'")
                comment_table_exists = cursor.fetchone()
                print(f"Comment table exists: {comment_table_exists}")

                if comment_table_exists:
                    # Query brick comments (foreign_typ = 3)
                    comment_query = """
                        SELECT c.foreign_id, c.tstamp, c.op, c.note
                        FROM comment c
                        WHERE c.foreign_typ = 3
                        ORDER BY c.tstamp
                    """
                    cursor.execute(comment_query)
                    comment_rows = cursor.fetchall()
                    print(f"Brick comment rows: {len(comment_rows)}")

                    # Organize brick comments by daughterboard serial_no
                    for comment in comment_rows:
                        serial_no = comment['foreign_id']
                        if serial_no:
                            if serial_no not in serial_to_comments:
                                serial_to_comments[serial_no] = []
                            serial_to_comments[serial_no].append({
                                'tstamp': str(comment['tstamp']) if comment['tstamp'] else None,
                                'op': comment['op'],
                                'note': comment['note']
                            })

                    # Query benchtest comments (foreign_typ = 4)
                    benchtest_comment_query = """
                        SELECT c.foreign_id, c.tstamp, c.op, c.note
                        FROM comment c
                        WHERE c.foreign_typ = 4
                        ORDER BY c.tstamp
                    """
                    cursor.execute(benchtest_comment_query)
                    benchtest_comment_rows = cursor.fetchall()
                    print(f"Benchtest comment rows: {len(benchtest_comment_rows)}")

                    # Get benchtest data to map benchtest IDs to slot information
                    benchtest_slots_query = """
                        SELECT id, db_slot1, db_slot2, db_slot3, db_slot4
                        FROM benchtest
                    """
                    cursor.execute(benchtest_slots_query)
                    benchtest_slots_rows = cursor.fetchall()
                    print(f"Benchtest slots rows for comments: {len(benchtest_slots_rows)}")

                    # Create a mapping from benchtest ID to its slot data
                    benchtest_id_to_slots = {}
                    for bt in benchtest_slots_rows:
                        benchtest_id_to_slots[bt['id']] = {
                            'db_slot1': bt['db_slot1'],
                            'db_slot2': bt['db_slot2'],
                            'db_slot3': bt['db_slot3'],
                            'db_slot4': bt['db_slot4']
                        }

                    # Process benchtest comments and link them to bricks
                    for comment in benchtest_comment_rows:
                        benchtest_id = comment['foreign_id']
                        if benchtest_id and benchtest_id in benchtest_id_to_slots:
                            slots = benchtest_id_to_slots[benchtest_id]
                            # Check each slot for the brick serial number
                            for slot_num in range(1, 5):
                                slot_key = f'db_slot{slot_num}'
                                serial_no = slots[slot_key]
                                if serial_no:
                                    if serial_no not in serial_to_comments:
                                        serial_to_comments[serial_no] = []
                                    # Format: "tstamp (op, mdX@btY): note"
                                    formatted_note = f"{comment['note']}"
                                    serial_to_comments[serial_no].append({
                                        'tstamp': str(comment['tstamp']) if comment['tstamp'] else None,
                                        'op': comment['op'],
                                        'note': formatted_note,
                                        'md': slot_num,
                                        'bt': benchtest_id,
                                        'is_benchtest_comment': True
                                    })

                    # Sort comments chronologically for each serial number
                    for serial_no in serial_to_comments:
                        serial_to_comments[serial_no].sort(key=lambda x: x['tstamp'] or '')

                    print(f"Serial to comments mapping: {len(serial_to_comments)} boards with comments")
            except Exception as e:
                print(f"Error querying comment data: {e}")
                import traceback
                traceback.print_exc()
                serial_to_comments = {}

            # Initialize serial_to_has_post_burnin_test before the try block
            serial_to_has_post_burnin_test = {}

            if str(SCRIPT_DIR) not in sys.path:
                sys.path.insert(0, str(SCRIPT_DIR))
            try:
                from dbq_plot_config import format_test_length, test_length_seconds
            except Exception:
                def format_test_length(**_kwargs):
                    return None

                def test_length_seconds(**_kwargs):
                    return None

            # Organize benchtest data by serial
            for bt in benchtest_rows:
                # Each benchtest has up to 4 daughterboards (db_slot1, db_slot2, db_slot3, db_slot4)
                slots = [
                    ('MD1', bt['db_slot1']),
                    ('MD2', bt['db_slot2']),
                    ('MD3', bt['db_slot3']),
                    ('MD4', bt['db_slot4'])
                ]
                
                for slot_name, serial in slots:
                    if serial:  # Only if a daughterboard is present in this slot
                        # Convert serial to string for consistent matching
                        serial_str = str(serial)
                        if serial_str not in serial_to_benchtests:
                            serial_to_benchtests[serial_str] = []
                        
                        # Get failed tests and board pass fail for this benchtest
                        failed_tests, board_pass_fail = get_failed_tests_for_serial(serial_str, bt['id'])
                        
                        # Get burned status from log file
                        burned_status = get_burned_status(serial_str, bt['id'])
                        
                        # Use board_pass_fail from CSV if available, otherwise fall back to database test_pass
                        # Convert board_pass_fail to int since CSV returns strings
                        if board_pass_fail is not None:
                            try:
                                test_pass_value = int(board_pass_fail)
                            except (ValueError, TypeError):
                                test_pass_value = bt['test_pass']
                        else:
                            test_pass_value = bt['test_pass']

                        test_start = str(bt.get('test_start')) if bt.get('test_start') else None
                        test_stop = str(bt.get('test_stop')) if bt.get('test_stop') else None
                        length_seconds = test_length_seconds(start_time=test_start, stop_time=test_stop)
                        test_length = format_test_length(start_time=test_start, stop_time=test_stop)
                        if test_length == 'n/a':
                            test_length = None
                        
                        serial_to_benchtests[serial_str].append({
                            'benchtest_id': bt['id'],
                            'benchtest_slot': slot_name,
                            'test_pass': test_pass_value,
                            'test_start': test_start,
                            'test_stop': test_stop,
                            'test_length': test_length,
                            'test_length_seconds': length_seconds,
                            'test_op': bt.get('test_op'),
                            'failed_tests': failed_tests,
                            'burned': burned_status
                        })
            print(f"Serial to benchtests mapping: {len(serial_to_benchtests)} boards with benchtests")

            # Determine which boards have post-burn-in tests
            for serial_str in serial_to_benchtests:
                # Find the board's burn_in_stop from daughterboard data
                burn_in_stop = None
                for row in db_rows:
                    if str(row['serial_no']) == serial_str:
                        burn_in_stop = row['burn_in_stop']
                        break
                
                if burn_in_stop:
                    # Check if any benchtest for this serial has test_stop after burn_in_stop
                    has_post_burnin = False
                    for benchtest in serial_to_benchtests[serial_str]:
                        test_stop = benchtest.get('test_stop')
                        if test_stop:
                            try:
                                from datetime import datetime
                                test_stop_dt = datetime.strptime(test_stop, '%Y-%m-%d %H:%M:%S')
                                burn_in_stop_dt = datetime.strptime(str(burn_in_stop), '%Y-%m-%d %H:%M:%S')
                                if test_stop_dt > burn_in_stop_dt:
                                    has_post_burnin = True
                                    break
                            except (ValueError, TypeError):
                                pass
                    serial_to_has_post_burnin_test[serial_str] = has_post_burnin
                else:
                    serial_to_has_post_burnin_test[serial_str] = False
        except Exception as e:
            print(f"Error querying benchtest data: {e}")
            import traceback
            traceback.print_exc()
            serial_to_benchtests = {}
        
        # Decode serial numbers and organize by batch
        boards_by_batch = {}
        for row in db_rows:
            serial = row['serial_no']
            decoded = decode_serial(serial)
            
            # Filter out tag 90 (ignored boards)
            if decoded['tag'] == 90:
                continue

            batch = decoded['batch']
            if batch > MAX_BRICK_WALL_BATCH:
                continue
            
            if batch not in boards_by_batch:
                boards_by_batch[batch] = []
            
            # Check if this board has benchtests
            # Convert serial to string for lookup since benchtest dict uses string keys
            serial_str = str(serial)
            board_benchtests = serial_to_benchtests.get(serial_str, [])
            
            boards_by_batch[batch].append({
                'serial_no': serial,
                'tag': decoded['tag'],
                'batch': batch,
                'position': decoded['position'],
                'db_status': row['db_status'],
                'burn_in': row['burn_in'],
                'burn_in_start': str(row['burn_in_start']) if row['burn_in_start'] else None,
                'burn_in_stop': str(row['burn_in_stop']) if row['burn_in_stop'] else None,
                'kin_lot': row['kin_lot'],
                'pro_lot': row['pro_lot'],
                'gbt_lot': row['gbt_lot'],
                'ina_lot': row['ina_lot'],
                'ltm_lot': row['ltm_lot'],
                'mos_lot': row['mos_lot'],
                'op4_lot': row['op4_lot'],
                'ok4_lot': row['ok4_lot'],
                'ok1_lot': row['ok1_lot'],
                'mem_lot': row['mem_lot'],
                'sfp_lot': row['sfp_lot'],
                'e_test': row['e_test'],
                'p_test': row['p_test'],
                'a0': row['a0'],
                'a1': row['a1'],
                'b0': row['b0'],
                'b1': row['b1'],
                'benchtests': board_benchtests,
                'has_benchtest': len(board_benchtests) > 0,
                'has_post_burnin_test': serial_to_has_post_burnin_test.get(serial_str, False),
                'comments': serial_to_comments.get(serial, [])  # Use serial (int) instead of serial_str
            })
        
        # Sort boards within each batch by position
        for batch in boards_by_batch:
            boards_by_batch[batch].sort(key=lambda x: x['position'])
        
        cursor.close()
        conn.close()

        cache_info = save_brick_wall_cache(boards_by_batch)
        
        return jsonify({
            'success': True,
            'boards_by_batch': boards_by_batch,
            'cached': False,
            'cached_at': cache_info.get('cached_at'),
            'plot_html': cache_info.get('latest_html'),
        })
        
    except Exception as e:
        print(f"Error fetching brick wall data: {e}")
        from brick_wall_cache import load_brick_wall_cache
        cached = load_brick_wall_cache()
        if cached:
            return jsonify({
                'success': True,
                'boards_by_batch': cached.get('boards_by_batch') or {},
                'cached': True,
                'cached_at': cached.get('cached_at'),
                'plot_html': cached.get('plot_html') or 'production_brick_wall_latest.html',
                'cache_fallback': True,
                'cache_fallback_reason': str(e),
            })
        return jsonify({'error': str(e)}), 500


@app.route('/api/benchtest_list')
def benchtest_list():
    """Vertical benchtest list: each row has up to 4 MD bricks with pass/burn state."""
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401

    try:
        try:
            from dbq_plot_config import format_test_length, test_length_seconds
        except Exception:
            def format_test_length(**_kwargs):
                return 'n/a'

            def test_length_seconds(**_kwargs):
                return None

        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, test_start, test_stop, test_op, test_pass,
                   db_slot1, db_slot2, db_slot3, db_slot4
            FROM benchtest
            ORDER BY id DESC
            """
        )
        benchtest_rows = cursor.fetchall()

        cursor.execute(
            """
            SELECT serial_no, db_status, e_test, p_test, burn_in,
                   burn_in_start, burn_in_stop, sfp_lot, a0, a1, b0, b1
            FROM daughterboard
            """
        )
        db_rows = {str(row['serial_no']): row for row in cursor.fetchall()}
        cursor.close()
        conn.close()

        benchtests = []
        for bt in benchtest_rows:
            slots = []
            for md_index, slot_key in enumerate(
                ('db_slot1', 'db_slot2', 'db_slot3', 'db_slot4'),
                start=1,
            ):
                serial = bt.get(slot_key)
                md_name = f'MD{md_index}'
                if not serial:
                    slots.append({
                        'md': md_name,
                        'serial_no': None,
                        'empty': True,
                        'test_pass': None,
                        'burned': None,
                        'burn_in_stop': None,
                        'missing_sfp': False,
                        'tag': None,
                        'batch': None,
                        'position': None,
                    })
                    continue

                serial_str = str(serial)
                board = db_rows.get(serial_str) or {}
                try:
                    decoded = decode_serial(serial)
                except Exception:
                    decoded = {'tag': None, 'batch': None, 'position': None}
                _failed, board_pass_fail = get_failed_tests_for_serial(
                    serial_str, bt['id']
                )
                if board_pass_fail is not None:
                    try:
                        test_pass_value = int(board_pass_fail)
                    except (ValueError, TypeError):
                        test_pass_value = bt.get('test_pass')
                else:
                    # Per-board CSV missing: fall back only if this is a single-board
                    # result; otherwise leave unknown rather than copy whole-run flag.
                    occupied = sum(
                        1 for key in ('db_slot1', 'db_slot2', 'db_slot3', 'db_slot4')
                        if bt.get(key)
                    )
                    test_pass_value = bt.get('test_pass') if occupied == 1 else None

                burned_status = get_burned_status(serial_str, bt['id'])
                burn_in_stop = (
                    str(board['burn_in_stop']) if board.get('burn_in_stop') else None
                )
                missing_sfp = not any([
                    board.get('sfp_lot'),
                    board.get('a0'),
                    board.get('a1'),
                    board.get('b0'),
                    board.get('b1'),
                ])

                slots.append({
                    'md': md_name,
                    'serial_no': int(serial) if str(serial).isdigit() else serial,
                    'empty': False,
                    'test_pass': test_pass_value,
                    'burned': burned_status,
                    'burn_in': board.get('burn_in'),
                    'burn_in_stop': burn_in_stop,
                    'db_status': board.get('db_status'),
                    'e_test': board.get('e_test'),
                    'p_test': board.get('p_test'),
                    'missing_sfp': missing_sfp,
                    'tag': decoded.get('tag'),
                    'batch': decoded.get('batch'),
                    'position': decoded.get('position'),
                })

            test_start = str(bt['test_start']) if bt.get('test_start') else None
            test_stop = str(bt['test_stop']) if bt.get('test_stop') else None
            benchtests.append({
                'benchtest_id': bt['id'],
                'test_start': test_start,
                'test_stop': test_stop,
                'test_op': bt.get('test_op'),
                'test_length': format_test_length(
                    start_time=test_start,
                    stop_time=test_stop,
                ),
                'test_length_seconds': test_length_seconds(
                    start_time=test_start,
                    stop_time=test_stop,
                ),
                'slots': slots,
            })

        return jsonify({
            'success': True,
            'benchtests': benchtests,
            'count': len(benchtests),
        })
    except Exception as e:
        print(f'Error fetching benchtest list: {e}')
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/add_comment', methods=['POST'])
def add_comment():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401
    if is_guest_mode():
        return jsonify({'error': 'Not allowed in guest mode'}), 403

    try:
        data = request.get_json()
        foreign_typ = data.get('foreign_typ')
        foreign_id = data.get('foreign_id')
        op = data.get('op')
        note = data.get('note')

        if not foreign_typ or not foreign_id or not op or not note:
            return jsonify({'error': 'Missing required fields'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = conn.cursor(dictionary=True)

        # Insert the comment into the comment table
        insert_query = """
            INSERT INTO comment (foreign_typ, foreign_id, tstamp, op, note)
            VALUES (%s, %s, NOW(), %s, %s)
        """
        cursor.execute(insert_query, (foreign_typ, foreign_id, op, note))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'success': True})

    except Exception as e:
        print(f"Error adding comment: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/qualify_board', methods=['POST'])
def qualify_board():
    """Set db_status/e_test/p_test to 1 and insert a qualification comment."""
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401
    if is_guest_mode():
        return jsonify({'error': 'Not allowed in guest mode'}), 403

    try:
        data = request.get_json(silent=True) or {}
        serial_no = data.get('serial_no')
        op = (data.get('op') or '').strip()
        reason = (data.get('reason') or '').strip()

        if serial_no is None or str(serial_no).strip() == '':
            return jsonify({'error': 'Serial number required'}), 400
        if not op:
            return jsonify({'error': 'Operator name required'}), 400
        if not reason:
            return jsonify({'error': 'Reason required'}), 400

        try:
            serial_no = int(serial_no)
        except (TypeError, ValueError):
            return jsonify({'error': 'Invalid serial number'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            'SELECT serial_no FROM daughterboard WHERE serial_no = %s',
            (serial_no,),
        )
        row = cursor.fetchone()
        if not row:
            cursor.close()
            conn.close()
            return jsonify({'error': f'Board {serial_no} not found'}), 404

        cursor.execute(
            """
            UPDATE daughterboard
            SET db_status = 1, e_test = 1, p_test = 1
            WHERE serial_no = %s
            """,
            (serial_no,),
        )

        note = f'Qualified pass, reason: {reason}'
        cursor.execute(
            """
            INSERT INTO comment (foreign_typ, foreign_id, tstamp, op, note)
            VALUES (3, %s, NOW(), %s, %s)
            """,
            (serial_no, op, note),
        )

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            'success': True,
            'serial_no': serial_no,
            'db_status': 1,
            'e_test': 1,
            'p_test': 1,
            'comment': note,
        })

    except Exception as e:
        print(f"Error qualifying board: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/rerun_analysis', methods=['POST'])
def rerun_analysis():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401
    if is_guest_mode():
        return jsonify({'error': 'Not allowed in guest mode'}), 403
    
    try:
        data = request.get_json()
        serial_no = data.get('serial_no')
        
        if not serial_no:
            return jsonify({'error': 'Serial number required'}), 400
        
        def generate():
            import subprocess
            import sys
            
            # Run DBQ_Mk6.py for the specific board using -r all -d (board number)
            cmd = ['python3', str(DBQ_SCRIPT_PATH), '-r', 'all', '-d', str(serial_no)]
            
            process = subprocess.Popen(
                cmd,
                cwd=SCRIPT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            try:
                for line in process.stdout:
                    yield line
            except GeneratorExit:
                # Client disconnected, kill the process
                process.terminate()
                process.wait()
                yield "\n\nScript terminated by user.\n"
            
            process.wait()
            
            if process.returncode != 0:
                yield f"\nError: Script failed with return code {process.returncode}\n"
        
        from flask import Response
        return Response(generate(), mimetype='text/plain')
        
    except Exception as e:
        print(f"Error running analysis: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/production_summary')
def production_summary():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401

    from production_summary_cache import (
        load_production_summary_cache,
        save_production_summary_cache,
    )

    def _cache_fallback_response(reason):
        cached = load_production_summary_cache()
        if not cached:
            return None
        payload = dict(cached)
        payload['cached'] = True
        payload['cache_fallback'] = True
        payload['cache_fallback_reason'] = reason
        payload['plot_html'] = payload.get('plot_html') or 'production_summary_latest.html'
        return jsonify(payload)

    try:
        conn = get_db_connection()
        if not conn:
            fallback = _cache_fallback_response('Database connection failed')
            if fallback:
                return fallback
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = conn.cursor(dictionary=True)

        db_query = """
            SELECT d.serial_no, d.batch_id, d.db_status, d.burn_in,
                   d.burn_in_start, d.burn_in_stop,
                   d.kin_lot, d.pro_lot, d.gbt_lot,
                   d.ina_lot, d.ltm_lot, d.mos_lot, d.op4_lot, d.ok4_lot, d.ok1_lot,
                   d.mem_lot, d.sfp_lot, d.e_test, d.p_test, d.a0, d.a1, d.b0, d.b1
            FROM daughterboard d
            ORDER BY d.serial_no
        """
        cursor.execute(db_query)
        db_rows = cursor.fetchall()

        benchtest_query = """
            SELECT id, test_start, test_stop, test_op, test_pass,
                   db_slot1, db_slot2, db_slot3, db_slot4
            FROM benchtest
            ORDER BY id
        """
        cursor.execute(benchtest_query)
        benchtest_rows = cursor.fetchall()

        cursor.close()
        conn.close()

        summary = build_production_summary(db_rows, benchtest_rows)
        cache_info = save_production_summary_cache(summary)
        summary['cached'] = False
        summary['cached_at'] = cache_info.get('cached_at')
        summary['plot_html'] = cache_info.get('latest_html')
        return jsonify(summary)

    except Exception as e:
        print(f"Error fetching production summary: {e}")
        fallback = _cache_fallback_response(str(e))
        if fallback:
            return fallback
        return jsonify({'error': str(e)}), 500

@app.route('/api/production_statistics')
def production_statistics():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401

    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = conn.cursor(dictionary=True)

        db_query = """
            SELECT d.serial_no, d.batch_id, d.db_status, d.burn_in,
                   d.burn_in_start, d.burn_in_stop,
                   d.kin_lot, d.pro_lot, d.gbt_lot,
                   d.ina_lot, d.ltm_lot, d.mos_lot, d.op4_lot, d.ok4_lot, d.ok1_lot,
                   d.mem_lot, d.sfp_lot, d.e_test, d.p_test, d.a0, d.a1, d.b0, d.b1
            FROM daughterboard d
            ORDER BY d.serial_no
        """
        cursor.execute(db_query)
        db_rows = cursor.fetchall()

        benchtest_query = """
            SELECT id, test_start, test_stop, test_op, test_pass,
                   db_slot1, db_slot2, db_slot3, db_slot4
            FROM benchtest
            ORDER BY id
        """
        cursor.execute(benchtest_query)
        benchtest_rows = cursor.fetchall()

        cursor.close()
        conn.close()

        return jsonify(build_production_statistics(db_rows, benchtest_rows))

    except Exception as e:
        print(f"Error fetching production statistics: {e}")
        return jsonify({'error': str(e)}), 500

def _fetch_history_source_rows():
    conn = get_db_connection()
    if not conn:
        return None, None, 'Database connection failed'

    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT d.serial_no, d.batch_id, d.db_status, d.burn_in,
               d.burn_in_start, d.burn_in_stop,
               d.kin_lot, d.pro_lot, d.gbt_lot,
               d.ina_lot, d.ltm_lot, d.mos_lot, d.op4_lot, d.ok4_lot, d.ok1_lot,
               d.mem_lot, d.sfp_lot, d.e_test, d.p_test, d.a0, d.a1, d.b0, d.b1
        FROM daughterboard d
        ORDER BY d.serial_no
    """)
    db_rows = cursor.fetchall()
    cursor.execute("""
        SELECT id, test_start, test_stop, test_op, test_pass,
               db_slot1, db_slot2, db_slot3, db_slot4
        FROM benchtest
        ORDER BY id
    """)
    benchtest_rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return db_rows, benchtest_rows, None


@app.route('/api/production_history')
def production_history():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401

    try:
        force = request.args.get('recompute', '').lower() in ('1', 'true', 'yes')
        db_rows, benchtest_rows, error = _fetch_history_source_rows()
        if error:
            return jsonify({'error': error}), 500
        # Always return the full milestone list quickly; snapshots are cached lazily.
        return jsonify(build_production_history(
            db_rows,
            benchtest_rows,
            force_recompute=force,
        ))
    except Exception as e:
        print(f'Error fetching production history: {e}')
        import traceback
        traceback.print_exc()
        cached = load_history_index()
        if cached:
            cached = dict(cached)
            cached['cache_fallback'] = True
            cached['cache_fallback_reason'] = str(e)
            return jsonify(cached)
        return jsonify({'error': str(e)}), 500


@app.route('/api/production_history/snapshot')
def production_history_snapshot():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401

    as_of = request.args.get('as_of', '').strip()
    milestone_id = request.args.get('milestone_id', '').strip()
    index_raw = request.args.get('index', '').strip()
    force = request.args.get('recompute', '').lower() in ('1', 'true', 'yes')

    index = None
    if index_raw != '':
        try:
            index = int(index_raw)
        except ValueError:
            return jsonify({'error': 'Invalid index'}), 400

    if not force:
        cached = load_cached_snapshot(index=index, as_of=as_of or None, milestone_id=milestone_id or None)
        if cached:
            return jsonify(cached)

    try:
        db_rows, benchtest_rows, error = _fetch_history_source_rows()
        if error:
            return jsonify({'error': error}), 500

        history = build_production_history(db_rows, benchtest_rows, force_recompute=False)
        milestones = history.get('milestones') or []
        milestone = None
        if index is not None and 0 <= index < len(milestones):
            milestone = milestones[index]
        elif milestone_id:
            milestone = next((item for item in milestones if item.get('id') == milestone_id), None)
        elif as_of:
            milestone = next((item for item in milestones if item.get('timestamp') == as_of), None)

        if not milestone:
            if not as_of:
                return jsonify({'error': 'Milestone not found'}), 404
            milestone = {
                'id': f'asof-{as_of}',
                'index': index if index is not None else 0,
                'timestamp': as_of,
                'label': f'Snapshot @ {as_of}',
                'detail': None,
                'kind': 'snapshot',
            }

        if force:
            # Drop existing files for this milestone so it is rebuilt.
            from production_history import snapshot_paths
            paths = snapshot_paths(milestone.get('index', 0), milestone.get('timestamp'))
            for key in (
                'json', 'html', 'wall_png', 'cumulative_png', 'burnin_png',
                'yield_pie_png', 'burnin_pie_png', 'produced_pie_png',
            ):
                try:
                    path = paths[key]
                    if path.exists():
                        path.unlink()
                except OSError:
                    pass

        snapshot = cache_milestone_snapshot(
            db_rows,
            benchtest_rows,
            milestone,
            time_axis=history.get('time_axis'),
        )
        snapshot['cached'] = True
        snapshot['newly_cached'] = True
        return jsonify(snapshot)
    except Exception as e:
        print(f'Error fetching production history snapshot: {e}')
        import traceback
        traceback.print_exc()
        cached = load_cached_snapshot(index=index, as_of=as_of or None, milestone_id=milestone_id or None)
        if cached:
            cached = dict(cached)
            cached['cache_fallback'] = True
            cached['cache_fallback_reason'] = str(e)
            return jsonify(cached)
        return jsonify({'error': str(e)}), 500


def _fetch_daughterboard_rows():
    conn = get_db_connection()
    if not conn:
        return None, 'Database connection failed'

    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT d.serial_no, d.batch_id, d.db_status, d.burn_in,
               d.burn_in_start, d.burn_in_stop,
               d.e_test, d.p_test
        FROM daughterboard d
        ORDER BY d.serial_no
    """)
    db_rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return db_rows, None


@app.route('/api/burn_in')
def burn_in_overview():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401

    try:
        db_rows, error = _fetch_daughterboard_rows()
        if error:
            return jsonify({'error': error}), 500
        return jsonify(build_burn_in_overview(db_rows))
    except Exception as e:
        print(f'Error fetching burn-in overview: {e}')
        return jsonify({'error': str(e)}), 500


def _request_wants_recompute():
    return request.args.get('recompute', '').lower() in ('1', 'true', 'yes')


@app.route('/api/burn_in/plot_all')
def burn_in_plot_all():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401

    try:
        db_rows, error = _fetch_daughterboard_rows()
        if error:
            return jsonify({'error': error}), 500
        return jsonify(build_burn_in_plot_all_slots(
            db_rows,
            force_recompute=_request_wants_recompute(),
        ))
    except Exception as e:
        print(f'Error fetching all burn-in plots: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/api/burn_in/plot/<slot_id>')
def burn_in_plot(slot_id):
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401

    try:
        db_rows, error = _fetch_daughterboard_rows()
        if error:
            return jsonify({'error': error}), 500
        return jsonify(build_burn_in_plot_for_slot(
            db_rows,
            slot_id,
            force_recompute=_request_wants_recompute(),
        ))
    except Exception as e:
        print(f'Error fetching burn-in plot for {slot_id}: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/api/burn_in/config', methods=['GET', 'POST'])
def burn_in_config_api():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401

    if request.method == 'GET':
        config = load_production_config()
        from burn_in import _burn_in_config_payload
        return jsonify({'success': True, 'config': _burn_in_config_payload(config)})

    blocked = require_full_access()
    if blocked:
        return jsonify({'error': 'Not allowed in guest mode'}), 403

    try:
        data = request.get_json() or {}
        saved = save_burn_in_config({
            'burnin_temperature_offset_c': data.get('temperature_offset_c', 0),
            'burnin_cache_dir': data.get('cache_dir', ''),
            'burnin_use_profiles': data.get('use_profiles', []),
            'burnin_activation_energies': data.get('activation_energies', []),
            'burnin_default_use_profile': data.get('default_use_profile'),
            'burnin_default_activation_energy_ev': data.get('default_activation_energy_ev'),
        })
        from burn_in import _burn_in_config_payload
        return jsonify({'success': True, 'config': _burn_in_config_payload(saved)})
    except Exception as e:
        print(f'Error saving burn-in config: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/api/burn_in/cache/clear', methods=['POST'])
def clear_burn_in_cache_api():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401

    blocked = require_full_access()
    if blocked:
        return jsonify({'error': 'Not allowed in guest mode'}), 403

    try:
        from burn_in import clear_burn_in_cache

        data = request.get_json(silent=True) or {}
        config = load_production_config()
        cache_dir = str(data.get('cache_dir', '')).strip()
        if cache_dir:
            config = {**config, 'burnin_cache_dir': cache_dir}
        result = clear_burn_in_cache(config)
        return jsonify({'success': True, **result})
    except Exception as e:
        print(f'Error clearing burn-in cache: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/api/long_burn_in')
def long_burn_in_overview():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401

    try:
        return jsonify(build_long_burn_in_overview())
    except Exception as e:
        print(f'Error fetching long burn-in overview: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/api/long_burn_in/plot')
def long_burn_in_plot():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401

    try:
        return jsonify(build_long_burn_in_plot(force_recompute=_request_wants_recompute()))
    except Exception as e:
        print(f'Error fetching long burn-in plot: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/api/long_burn_in/config', methods=['GET', 'POST'])
def long_burn_in_config_api():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401

    if request.method == 'GET':
        from long_burn_in import _config_payload
        return jsonify({'success': True, 'config': _config_payload(load_production_config())})

    blocked = require_full_access()
    if blocked:
        return jsonify({'error': 'Not allowed in guest mode'}), 403

    try:
        data = request.get_json() or {}
        saved = save_long_burn_in_config({
            'long_burnin_board_serial': data.get('board_serial', ''),
            'long_burnin_start': data.get('period_start', ''),
            'long_burnin_stop': data.get('period_stop', ''),
            'long_burnin_fpga_a_label': data.get('fpga_a_label', 'KU FPGA A'),
            'long_burnin_fpga_b_label': data.get('fpga_b_label', 'KU FPGA B'),
            'long_burnin_temperature_offset_c': data.get('temperature_offset_c', 0),
            'long_burnin_use_profiles': data.get('use_profiles', []),
            'long_burnin_activation_energies': data.get('activation_energies', []),
            'long_burnin_default_use_profile': data.get('default_use_profile'),
            'long_burnin_default_activation_energy_ev': data.get('default_activation_energy_ev'),
            'long_burnin_v_use_v': data.get('v_use_v'),
            'long_burnin_v_test_v': data.get('v_test_v'),
            'long_burnin_voltage_betas': data.get('voltage_betas'),
            'long_burnin_default_voltage_beta': data.get('default_voltage_beta'),
            'long_burnin_rh_use_options': data.get('rh_use_options'),
            'long_burnin_default_rh_use_pct': data.get('default_rh_use_pct'),
            'long_burnin_peck_exponents': data.get('peck_exponents'),
            'long_burnin_default_peck_exponent': data.get('default_peck_exponent'),
        })
        from long_burn_in import _config_payload
        return jsonify({'success': True, 'config': _config_payload(saved)})
    except Exception as e:
        print(f'Error saving long burn-in config: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/api/production_config', methods=['GET', 'POST'])
def production_config():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401

    if request.method == 'GET':
        return jsonify({'success': True, 'config': load_production_config()})

    blocked = require_full_access()
    if blocked:
        return jsonify({'error': 'Not allowed in guest mode'}), 403

    try:
        data = request.get_json() or {}
        updates = {}
        for key in (
            'pretest_offset_days',
            'post_test_offset_days',
            'burnin_offset_days',
            'production_plot_start_date',
            'production_plot_end_date',
            'production_plot_x_ticks',
            'production_plot_y_ticks',
            'history_plot_start_date',
            'history_plot_end_date',
            'history_plot_x_ticks',
            'history_plot_y_ticks',
        ):
            if key in data:
                updates[key] = data.get(key)
        if not updates:
            return jsonify({'error': 'No configuration fields provided'}), 400
        config = save_production_config(updates)
        return jsonify({'success': True, 'config': config})
    except Exception as e:
        print(f'Error saving production config: {e}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/production_schedule', methods=['GET', 'POST'])
def production_schedule_api():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401

    if request.method == 'GET':
        try:
            calendar = load_calendar_grid(SCHEDULE_CSV_PATH)
            return jsonify({'success': True, 'calendar': calendar})
        except Exception as e:
            print(f'Error loading production schedule: {e}')
            return jsonify({'error': str(e)}), 500

    blocked = require_full_access()
    if blocked:
        return jsonify({'error': 'Not allowed in guest mode'}), 403

    try:
        data = request.get_json() or {}
        calendar = data.get('calendar')
        if not calendar:
            return jsonify({'error': 'Missing calendar data'}), 400

        save_calendar_grid(calendar, SCHEDULE_CSV_PATH)
        return jsonify({'success': True})
    except Exception as e:
        print(f'Error saving production schedule: {e}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/production_schedule/upload', methods=['POST'])
def upload_production_schedule():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401

    blocked = require_full_access()
    if blocked:
        return jsonify({'error': 'Not allowed in guest mode'}), 403

    uploaded_file = request.files.get('schedule_file')
    if not uploaded_file or not uploaded_file.filename:
        return jsonify({'error': 'No file uploaded'}), 400
    if not uploaded_file.filename.lower().endswith('.csv'):
        return jsonify({'error': 'Uploaded file must be a CSV'}), 400

    try:
        filename = backup_and_save_schedule(uploaded_file)
        return jsonify({'success': True, 'filename': filename})
    except Exception as e:
        print(f'Error uploading production schedule: {e}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/production_history/rebuild')
def production_history_rebuild():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401
    if session.get('guest_mode'):
        return jsonify({'error': 'Not authorized'}), 403

    mode = (request.args.get('mode') or 'missing').strip().lower()
    if mode not in ('all', 'missing'):
        return jsonify({'error': 'mode must be "all" or "missing"'}), 400

    def generate():
        try:
            db_rows, benchtest_rows, error = _fetch_history_source_rows()
            if error:
                yield json.dumps({'event': 'error', 'error': error}) + '\n'
                return
            for event in iter_rebuild_history_cache(db_rows, benchtest_rows, mode=mode):
                yield json.dumps(event) + '\n'
        except Exception as exc:
            print(f'Error rebuilding production history cache: {exc}')
            import traceback
            traceback.print_exc()
            yield json.dumps({'event': 'error', 'error': str(exc)}) + '\n'

    return Response(
        stream_with_context(generate()),
        mimetype='application/x-ndjson',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        },
    )


@app.route('/api/production_history/video/estimate', methods=['POST'])
def production_history_video_estimate():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401
    try:
        options = request.get_json(silent=True) or {}
        return jsonify(estimate_video_selection(options=options))
    except Exception as exc:
        print(f'Error estimating history video: {exc}')
        return jsonify({'error': str(exc)}), 500


@app.route('/api/production_history/video/generate', methods=['POST'])
def production_history_video_generate():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401

    options = request.get_json(silent=True) or {}

    def generate():
        db_comments = []
        conn = None
        try:
            include_comments = bool(
                options.get('include_comments') or options.get('includeComments')
            )
            if include_comments:
                conn = get_db_connection()
                if conn:
                    db_comments = fetch_db_comments_for_video(conn)
            for event in iter_generate_history_video(options=options, db_comments=db_comments):
                # Pad lightly so proxies flush progress lines promptly.
                yield json.dumps(event) + '\n' + (' ' * 256) + '\n'
        except Exception as exc:
            print(f'Error generating history video: {exc}')
            import traceback
            traceback.print_exc()
            yield json.dumps({'type': 'error', 'error': str(exc)}) + '\n'
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    return Response(
        stream_with_context(generate()),
        mimetype='application/x-ndjson',
        headers={
            'Cache-Control': 'no-cache, no-store',
            'X-Accel-Buffering': 'no',
            'Content-Encoding': 'identity',
        },
    )


@app.route('/api/production_history/cache/clear', methods=['POST'])
def production_history_cache_clear():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401
    if session.get('guest_mode'):
        return jsonify({'error': 'Not authorized'}), 403

    payload = request.get_json(silent=True) or {}
    scope = (payload.get('scope') or request.args.get('scope') or 'all').strip().lower()
    try:
        result = clear_history_cache_scope(scope)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        print(f'Error clearing history cache: {exc}')
        return jsonify({'error': str(exc)}), 500


@app.route('/api/production_history/video/download')
def production_history_video_download():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401
    filename = (request.args.get('file') or '').strip()
    path = resolve_video_path(filename)
    if not path:
        return jsonify({'error': 'Video not found'}), 404
    from flask import send_file
    return send_file(
        path,
        mimetype='video/mp4',
        as_attachment=True,
        download_name=path.name,
    )


@app.route('/api/production_history/slideshow/estimate', methods=['POST'])
def production_history_slideshow_estimate():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401
    try:
        options = request.get_json(silent=True) or {}
        result = estimate_video_selection(options=options)
        result['format'] = 'pdf'
        return jsonify(result)
    except Exception as exc:
        print(f'Error estimating history slideshow: {exc}')
        return jsonify({'error': str(exc)}), 500


@app.route('/api/production_history/slideshow/generate', methods=['POST'])
def production_history_slideshow_generate():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401

    options = request.get_json(silent=True) or {}

    def generate():
        db_comments = []
        conn = None
        try:
            include_comments = bool(
                options.get('include_comments') or options.get('includeComments')
            )
            if include_comments:
                conn = get_db_connection()
                if conn:
                    db_comments = fetch_db_comments_for_video(conn)
            for event in iter_generate_history_slideshow(options=options, db_comments=db_comments):
                yield json.dumps(event) + '\n' + (' ' * 256) + '\n'
        except Exception as exc:
            print(f'Error generating history slideshow: {exc}')
            import traceback
            traceback.print_exc()
            yield json.dumps({'type': 'error', 'error': str(exc)}) + '\n'
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    return Response(
        stream_with_context(generate()),
        mimetype='application/x-ndjson',
        headers={
            'Cache-Control': 'no-cache, no-store',
            'X-Accel-Buffering': 'no',
            'Content-Encoding': 'identity',
        },
    )


@app.route('/api/production_history/slideshow/download')
def production_history_slideshow_download():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401
    filename = (request.args.get('file') or '').strip()
    path = resolve_slideshow_path(filename)
    if not path:
        return jsonify({'error': 'Slideshow not found'}), 404
    from flask import send_file
    return send_file(
        path,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=path.name,
    )


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


def _run_history_cache_cli(mode):
    """Rebuild production-history caches from the terminal and exit."""
    print(f'[history-cache] Starting rebuild (mode={mode})...')
    db_rows, benchtest_rows, error = _fetch_history_source_rows()
    if error:
        print(f'[history-cache] ERROR: {error}')
        return 1

    def on_progress(done, total, item):
        label = (item or {}).get('label') or (item or {}).get('timestamp') or '?'
        pct = (100.0 * done / total) if total else 100.0
        print(f'[history-cache] [{done}/{total}] {pct:5.1f}%  {label}')

    result = rebuild_history_cache(
        db_rows,
        benchtest_rows,
        mode=mode,
        progress_callback=on_progress,
    )
    print(
        f"[history-cache] Done. built={result.get('rebuild_built', 0)} "
        f"cached_count={result.get('cached_count', 0)} "
        f"milestones={result.get('rebuild_total_milestones', result.get('total', 0))}"
    )
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='TileQA web UI server, or rebuild Production History caches and exit.',
    )
    parser.add_argument(
        '--rebuild-history-cache',
        choices=('all', 'missing'),
        metavar='MODE',
        help=(
            'Rebuild Production History milestone caches and exit without starting the web server. '
            'MODE=all clears and rebuilds every milestone; MODE=missing only builds uncached ones.'
        ),
    )
    parser.add_argument('--host', default='0.0.0.0', help='Web server bind host (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=5001, help='Web server port (default: 5001)')
    parser.add_argument('--debug', action='store_true', help='Enable Flask debug mode')
    args = parser.parse_args()

    if args.rebuild_history_cache:
        sys.exit(_run_history_cache_cli(args.rebuild_history_cache))

    app.run(host=args.host, port=args.port, debug=args.debug)
