from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from pathlib import Path
import mysql.connector
from mysql.connector import Error
from ruamel.yaml import YAML
import os
import subprocess
import re

os.environ['TZ'] = 'UTC'
app = Flask(__name__)
app.secret_key = '6#1-&75-?66'

# Function to read benchtest CSV and extract failed tests for a serial number
def get_failed_tests_for_serial(serial, benchtest_id, drive_dir="/var/www/html/drive/benchtests/"):
    """
    Read benchtest CSV file and extract failed tests for a specific serial number.
    Handles CSV files that may contain multiple boards in columns.
    
    Args:
        serial: Serial number of the board
        benchtest_id: Benchtest ID (integer)
        drive_dir: Directory containing benchtest folders
        
    Returns:
        list: List of failed test names, or None if file not found or no failures
    """
    benchtest_folder = f"benchtest_id_{benchtest_id}"
    csv_file = Path(drive_dir) / benchtest_folder / f"{benchtest_folder}_results.csv"
    
    if not csv_file.exists():
        return None, None
    
    try:
        with open(csv_file, 'r') as f:
            lines = f.readlines()
        
        # First line contains header with serial numbers
        # Format: "Measurement,9000001" or "Measurement,1101030,1101035"
        header = lines[0].strip().split(',')
        if len(header) < 2:
            return None, None
        
        # Find the column index for the requested serial number
        serial_str = str(serial)
        serial_index = None
        for i, col in enumerate(header[1:], start=1):  # Skip "Measurement" column
            if str(col) == serial_str:
                serial_index = i
                break
        
        if serial_index is None:
            # Serial not found in this CSV file
            return None, None
        
        # Parse measurements and find failed tests (value = 0) for this specific serial
        failed_tests = []
        board_pass_fail = None
        for line in lines[1:]:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            parts = line.split(',')
            if len(parts) > serial_index:
                measurement = parts[0]
                value = parts[serial_index].strip()
                
                # Check for Board PassFail
                if measurement == 'Board PassFail':
                    board_pass_fail = value
                
                # Value 0 indicates failure
                if value == '0':
                    # Filter out unwanted test names
                    if measurement not in ['burned', 'Board PassFail']:
                        failed_tests.append(measurement)
        
        return failed_tests if failed_tests else None, board_pass_fail
        
    except Exception as e:
        print(f"Error reading CSV file {csv_file}: {e}")
        return None, None

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
prod_database = 'tiledb'
dev_database = 'tiledbdev'

# Paths
SCRIPT_DIR = Path(__file__).parent.parent
VARS_YAML_PATH = SCRIPT_DIR / 'vars.yaml'
DBQ_SCRIPT_PATH = SCRIPT_DIR / 'DBQ_Mk6.py'
PRODUCTION_PLOTS_PATH = SCRIPT_DIR / 'production_plots_v1.py'

# Template names
login_template = "login.html"
dashboard_template = "dashboard.html"
run_script_template = "run_script.html"
edit_vars_template = "edit_vars.html"

def get_db_connection():
    """Create and return a database connection using session credentials."""
    try:
        conn = mysql.connector.connect(
            host=host,
            user=session.get('db_user'),
            password=session.get('db_pass'),
            database=session['db_name']
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

def save_vars_yaml(data):
    """Save configuration to vars.yaml preserving original format."""
    try:
        # Load original data to get structure with formatting metadata
        yaml_handler = YAML()
        yaml_handler.preserve_quotes = True
        with open(VARS_YAML_PATH, 'r') as f:
            original_data = yaml_handler.load(f)
        
        # Recursively update values in original data while preserving structure
        def update_values(original, new):
            if isinstance(new, dict):
                for key, value in new.items():
                    if key in original:
                        original[key] = update_values(original[key], value)
                    else:
                        original[key] = value
            elif isinstance(new, list):
                # For lists, update element by element to preserve sequence style
                if isinstance(original, list):
                    for i in range(min(len(original), len(new))):
                        original[i] = new[i]
                    # If new list is longer, append remaining elements
                    for i in range(len(original), len(new)):
                        original.append(new[i])
                    # If new list is shorter, truncate
                    while len(original) > len(new):
                        original.pop()
                else:
                    return new
            else:
                return new
            return original
        
        update_values(original_data, data)
        
        # Save with ruamel.yaml to preserve formatting
        yaml_handler = YAML()
        yaml_handler.preserve_quotes = True
        yaml_handler.default_flow_style = False
        yaml_handler.indent(mapping=2, sequence=4, offset=2)
        yaml_handler.width = 4096
        with open(VARS_YAML_PATH, 'w') as f:
            yaml_handler.dump(original_data, f)
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
        username = request.form['username']
        password = request.form['password']
        development = request.form.get('development')
        if development is not None:
            database = dev_database
        else:
            database = prod_database
        try:
            conn = mysql.connector.connect(
                host=host,
                user=username,
                password=password,
            )
            if conn.is_connected():
                session['logged_in'] = True
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
    return render_template(dashboard_template)

@app.route('/run_script', methods=['GET', 'POST'])
def run_script():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    message = ""
    error = None
    
    if request.method == 'POST':
        regenerate_mode = request.form.get('regenerate_mode')
        specific_benchtest_ids = request.form.get('specific_benchtest_ids')
        specific_daughterboard_id = request.form.get('specific_daughterboard_id')
        
        # Build command
        cmd = ['python3', str(DBQ_SCRIPT_PATH)]
        
        if regenerate_mode and regenerate_mode != 'none':
            cmd.extend(['-r', regenerate_mode])
        
        if specific_benchtest_ids:
            cmd.extend(['-b', specific_benchtest_ids])
        
        if specific_daughterboard_id:
            cmd.extend(['-d', specific_daughterboard_id])
        
        try:
            # Run DBQ_Mk6 script
            result = subprocess.run(
                cmd,
                cwd=SCRIPT_DIR,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                # DBQ_Mk6 succeeded, now run production plots
                message = f"DBQ_Mk6 script executed successfully.\n{result.stdout}\n\n"
                
                # Run production plots
                production_cmd = ['python3', str(PRODUCTION_PLOTS_PATH)]
                production_result = subprocess.run(
                    production_cmd,
                    cwd=SCRIPT_DIR,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minute timeout
                )
                
                if production_result.returncode == 0:
                    message += f"Production plots updated successfully.\n{production_result.stdout}"
                else:
                    message += f"Production plots update failed (but DBQ_Mk6 succeeded).\nError: {production_result.stderr}"
            else:
                error = f"DBQ_Mk6 script execution failed. Error:\n{result.stderr}"
                
        except subprocess.TimeoutExpired:
            error = "Script execution timed out after 5 minutes."
        except Exception as e:
            error = f"Error running script: {str(e)}"
    
    return render_template(run_script_template, message=message, error=error)

@app.route('/edit_vars', methods=['GET', 'POST'])
def edit_vars():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    message = ""
    error = None
    
    if request.method == 'POST':
        # Parse the YAML form data
        yaml_data = {}
        
        # Get all table names from form
        table_names = request.form.getlist('table_name')
        
        for table_name in table_names:
            yaml_data[table_name] = {}
            
            # Get variables for this table
            var_names = request.form.getlist(f'{table_name}_var_name')
            
            for var_name in var_names:
                # Get the value for this variable
                value_str = request.form.get(f'{table_name}_{var_name}')
                
                # Parse the value (could be single value or list)
                if value_str:
                    try:
                        # Try to parse as list
                        if value_str.startswith('[') and value_str.endswith(']'):
                            # Parse list
                            values = value_str[1:-1].split(',')
                            parsed_values = []
                            for v in values:
                                v = v.strip()
                                # Try to convert to int or float
                                try:
                                    if '.' in v:
                                        parsed_values.append(float(v))
                                    else:
                                        parsed_values.append(int(v))
                                except ValueError:
                                    parsed_values.append(v)
                            yaml_data[table_name][var_name] = parsed_values
                        else:
                            # Single value
                            try:
                                if '.' in value_str:
                                    yaml_data[table_name][var_name] = float(value_str)
                                else:
                                    yaml_data[table_name][var_name] = int(value_str)
                            except ValueError:
                                yaml_data[table_name][var_name] = value_str
                    except Exception as e:
                        error = f"Error parsing value for {table_name}.{var_name}: {str(e)}"
                        return render_template(edit_vars_template, error=error, vars_data=load_vars_yaml())
        
        if save_vars_yaml(yaml_data):
            message = "Configuration saved successfully!"
        else:
            error = "Failed to save configuration."
    
    vars_data = load_vars_yaml()
    return render_template(edit_vars_template, message=message, error=error, vars_data=vars_data)

@app.route('/api/brick_wall_data')
def brick_wall_data():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        conn = get_db_connection()
        if not conn:
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
                        
                        serial_to_benchtests[serial_str].append({
                            'benchtest_id': bt['id'],
                            'benchtest_slot': slot_name,
                            'test_pass': test_pass_value,
                            'test_stop': str(bt.get('test_stop')) if bt.get('test_stop') else None,
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
        
        return jsonify({
            'success': True,
            'boards_by_batch': boards_by_batch
        })
        
    except Exception as e:
        print(f"Error fetching brick wall data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/add_comment', methods=['POST'])
def add_comment():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401

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

@app.route('/api/rerun_analysis', methods=['POST'])
def rerun_analysis():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401
    
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

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
