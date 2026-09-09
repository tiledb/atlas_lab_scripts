### ################################### ###
### DaughterBoard Qualification Program ###
### Version 1.4.01
### ################################### ###

### ############### ###
### Package Imports ###
### ############### ###

# Basic Packages
from datetime import datetime
import math
from pathlib import Path
import argparse
import shutil
import csv
import gc
import os
import signal
import sys
import time
# Mathematics Packages
import numpy as np
import pandas as pd

# Plotting Packages (plotly)
import plotly.express as plotlyEX

# Server Packages
from ruamel.yaml import YAML

from vars_config import get_var_caption, get_var_dimensions, get_var_thresholds

# MySQL for MariaDB
import mysql.connector
from mysql.connector import Error

# InfluxDBClient for InfluxDB
from influxdb import InfluxDBClient

### ######### ###
### Functions ###
### ######### ###

# Load configuration data from .yaml file
def load_yaml_conf(filepath):
    yaml = YAML()
    with open(filepath, "r") as file:
        return yaml.load(file)

# Save configuration data to .yaml file while preserving exact formatting
def save_yaml_conf(filepath, data):
    # Load original data to get structure with formatting metadata
    yaml = YAML()
    yaml.preserve_quotes = True
    with open(filepath, "r") as file:
        original_data = yaml.load(file)
    
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
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.default_flow_style = False
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 4096
    
    with open(filepath, "w") as file:
        yaml.dump(original_data, file)

#def load_secrets(filepath="../secrets/secrets.yaml"):
#    with open(filepath, "r") as file:
#        return yaml.safe_load(file)

# Function to print tree structure
def print_tree(level, name, is_last):
    prefix = "└── " if is_last else "├── "
    print(" " * (level * 4) + prefix + name)

# Function to backup existing log files with timestamp
def backup_log_file(filepath):
    if Path(filepath).exists():
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_path = str(filepath).replace('.log', f'_backup_{timestamp}.log')
        shutil.copy2(filepath, backup_path)
        print(f'Backed up {filepath} to {backup_path}')
        return True
    return False


TIMING_CSV_FIELDS = [
    'md',
    'serial_no',
    'operation',
    'detail',
    'duration_seconds',
]

TIMING_LOG_DIRNAME = 'timing logs'


def timing_log_dir():
    """CSV timing logs live next to this script: <script_dir>/timing logs/."""
    return Path(__file__).resolve().parent / TIMING_LOG_DIRNAME


def timing_log_path(timestamp_str, benchtest_id=None):
    """Filename carries timestamp + benchtest_id (no run_id column/name)."""
    bt = '' if benchtest_id is None else str(benchtest_id).strip()
    if not bt:
        name = f'Timing_{timestamp_str}_session.csv'
    else:
        name = f'Timing_{timestamp_str}_BT{bt}.csv'
    return timing_log_dir() / name


def open_timing_log(path):
    """Open a timing CSV for append; write header if the file is new/empty."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = (not path.exists()) or path.stat().st_size == 0
    fh = open(path, 'a', newline='', buffering=1)
    writer = csv.DictWriter(fh, fieldnames=TIMING_CSV_FIELDS)
    if write_header:
        writer.writeheader()
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass
    return fh, writer


def flush_timing_log(fh):
    if fh is None:
        return
    try:
        fh.flush()
        os.fsync(fh.fileno())
    except OSError:
        pass


class TimingLogSession:
    """One CSV per benchtest under timing logs/; session rows use *_session.csv."""

    def __init__(self, timestamp_str):
        self.timestamp_str = timestamp_str
        self._files = {}  # key '' or str(btid) -> (fh, writer, path)
        self._closed = False

    def writer_for(self, benchtest_id=''):
        if self._closed:
            return None, None
        key = '' if benchtest_id is None else str(benchtest_id).strip()
        if key not in self._files:
            path = timing_log_path(self.timestamp_str, key or None)
            fh, writer = open_timing_log(path)
            self._files[key] = (fh, writer, path)
            print(f'Timing: writing CSV log to {path}')
        fh, writer, _path = self._files[key]
        return writer, fh

    def paths(self):
        return [path for (_fh, _writer, path) in self._files.values()]

    def close(self):
        if self._closed:
            return
        for fh, _writer, _path in self._files.values():
            close_timing_log(fh)
        self._files.clear()
        self._closed = True


def write_timing_row(session, operation, duration_seconds,
                     benchtest_id='', md='', serial_no='', detail='',
                     progress=None):
    """Append one CSV timing row and force it to disk immediately."""
    if session is None:
        return
    writer, fh = session.writer_for(benchtest_id)
    if writer is None:
        return
    writer.writerow({
        'md': '' if md is None else md,
        'serial_no': '' if serial_no is None else serial_no,
        'operation': operation,
        'detail': '' if detail is None else detail,
        'duration_seconds': f'{float(duration_seconds):.6f}',
    })
    flush_timing_log(fh)
    if progress is not None:
        progress['last_operation'] = operation
        progress['last_detail'] = detail
        progress['last_benchtest_id'] = benchtest_id
        progress['last_md'] = md
        progress['last_serial_no'] = serial_no
        progress['active_operation'] = ''
        progress['active_detail'] = ''
        progress['active_t0'] = None


def timing_mark(progress, operation, benchtest_id='', md='', serial_no='', detail=''):
    """Record the operation about to start (used if Ctrl+C interrupts mid-step)."""
    if progress is None:
        return
    progress['active_operation'] = operation
    progress['active_detail'] = detail
    progress['active_benchtest_id'] = benchtest_id
    progress['active_md'] = md
    progress['active_serial_no'] = serial_no
    progress['active_t0'] = time.perf_counter()


def write_timing_break(session, progress=None, reason='KeyboardInterrupt'):
    """Append a break row for an interrupted run and force the log to disk."""
    if session is None:
        return
    benchtest_id = ''
    md = ''
    serial_no = ''
    detail = reason
    duration = 0.0
    if progress:
        if progress.get('active_operation'):
            benchtest_id = progress.get('active_benchtest_id', '')
            md = progress.get('active_md', '')
            serial_no = progress.get('active_serial_no', '')
            active = progress['active_operation']
            active_detail = progress.get('active_detail') or ''
            detail = f'{reason} during {active}'
            if active_detail:
                detail += f' ({active_detail})'
            if progress.get('active_t0') is not None:
                duration = max(0.0, time.perf_counter() - progress['active_t0'])
        elif progress.get('last_operation'):
            benchtest_id = progress.get('last_benchtest_id', '')
            md = progress.get('last_md', '')
            serial_no = progress.get('last_serial_no', '')
            last = progress['last_operation']
            last_detail = progress.get('last_detail') or ''
            detail = f'{reason} after {last}'
            if last_detail:
                detail += f' ({last_detail})'
    write_timing_row(
        session, 'break', duration,
        benchtest_id=benchtest_id, md=md, serial_no=serial_no, detail=detail,
        progress=progress,
    )


def close_timing_log(fh):
    if fh is None:
        return
    flush_timing_log(fh)
    try:
        fh.close()
    except Exception:
        pass


# Main
def DBQ_Mk6(regenerate_mode=None, specific_benchtest_ids=None, specific_daughterboard_id=None,
            enable_timing=False, skip_db_status_update=False):

    timenow = datetime.now()
    print(f'Current Date/Time: {timenow}')
    timing_stamp = timenow.strftime('%Y%m%dT%H%M%S')
    timing_session = None
    timing_progress = {
        'active_operation': '',
        'active_detail': '',
        'active_benchtest_id': '',
        'active_md': '',
        'active_serial_no': '',
        'active_t0': None,
        'last_operation': '',
        'last_detail': '',
        'last_benchtest_id': '',
        'last_md': '',
        'last_serial_no': '',
    }
    driveDIR = "/var/www/html/drive/benchtests/"
    _prev_sigint = None
    _timing_closed = False

    def _close_timing_once():
        nonlocal timing_session, _timing_closed
        if _timing_closed:
            return
        if timing_session is not None:
            timing_session.close()
        timing_session = None
        _timing_closed = True

    def _sigint_handler(signum, frame):
        print('\nTiming: Ctrl+C received — writing break row to timing log')
        write_timing_break(
            timing_session,
            progress=timing_progress, reason='KeyboardInterrupt',
        )
        _close_timing_once()
        raise KeyboardInterrupt

    if enable_timing:
        timing_session = TimingLogSession(timing_stamp)
        print(
            f'Timing: CSV logs under {timing_log_dir()} '
            f'(filename stamp={timing_stamp})'
        )
        write_timing_row(
            timing_session,
            'run_start', 0.0, detail='begin', progress=timing_progress,
            )
        try:
            _prev_sigint = signal.signal(signal.SIGINT, _sigint_handler)
        except Exception:
            _prev_sigint = None

    try:
        _dbq_mk6_run(
            regenerate_mode=regenerate_mode,
            specific_benchtest_ids=specific_benchtest_ids,
            specific_daughterboard_id=specific_daughterboard_id,
            enable_timing=enable_timing,
            timing_session=timing_session,
            timing_progress=timing_progress,
            driveDIR=driveDIR,
            skip_db_status_update=skip_db_status_update,
        )
    except KeyboardInterrupt:
        print('\nTiming: interrupted by Ctrl+C — ensuring break row is in timing log')
        write_timing_break(
            timing_session,
            progress=timing_progress, reason='KeyboardInterrupt',
        )
        raise
    finally:
        if _prev_sigint is not None:
            try:
                signal.signal(signal.SIGINT, _prev_sigint)
            except Exception:
                pass
        if enable_timing and not _timing_closed:
            paths = timing_session.paths() if timing_session else []
            _close_timing_once()
            if paths:
                print('Timing: closed ' + ', '.join(str(p) for p in paths))
            else:
                print(f'Timing: closed (stamp={timing_stamp})')


def _dbq_mk6_run(regenerate_mode=None, specific_benchtest_ids=None, specific_daughterboard_id=None,
                 enable_timing=False, timing_session=None,
                 timing_progress=None, driveDIR="/var/www/html/drive/benchtests/",
                 skip_db_status_update=False):
    mariadb_read_seconds = None

    ### ####### ###
    ### MariaDB ###
    ### ####### ###
    # We connect to MariaDB and read the relevant data from the daughterboard and benchtest tables
    try:
        ### Connect to MariaDB ###
        print("\n==================== MariaDB Tree ====================")
        timing_mark(timing_progress, 'mariadb_read', detail='benchtest_table')
        _t_mariadb = time.perf_counter()
        print(f"🔗 Connecting to MariaDB at {secrets['tiledb-mariadb']['host']}...")
        connection = mysql.connector.connect(
            host=secrets["tiledb-mariadb"]["host"],
            user=secrets["tiledb-mariadb"]["user"],
            password=secrets["tiledb-mariadb"]["password"],
            autocommit=True
        )

        # Confirm MariaDB Connection
        if connection.is_connected():
            print("✅ Connected to MariaDB!")
            cursor = connection.cursor()

        # Setting Timezone to UTC
        cursor.execute("SET time_zone = '+00:00'")

        # List all databases
        cursor.execute("SHOW DATABASES;")
        databases = [db[0] for db in cursor.fetchall()]

        if not databases:
            print("⚠ No databases found in MariaDB.")
            return

        print("📂 MariaDB Databases:")
        for i, db in enumerate(databases):
            print_tree(0, db, i == len(databases) - 1)

        # Select "tiledb" database
        cursor.execute(f"USE tiledb")

        # List all tables in the selected database
        cursor.execute("SHOW TABLES;")
        tables = [tbl[0] for tbl in cursor.fetchall()]

        if not tables:
            print("⚠ No tables found in selected database.")
            return

        print("\nTables in tiledb:")
        for i, table in enumerate(tables):
            print_tree(1, table, i == len(tables) - 1)

        # Query benchtest table
        cursor.execute("SELECT * FROM benchtest")

        # Queried data takes the form of an array called "rows", each element of which is a special "row" object that contains the data from one entry in the benchtest table
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] # This "columns" array contains the names of each of the variables stored in the table
        print(f"columns = {columns}")
        print(f"rows    = {rows}")

        # Each benchtest that requires its data to be processed has it's data stored in this dictionary
        # The format is: { id : { benchtest_pass      : test_pass,
        #                         benchtest_timestamp : [start_time, stop_time],
        #                         benchtest_serialnos : [md1_dbserialno, md2_dbserialno, md3_dbserialno, md4_dbserialno] } }
        benchtest_proc = {}

        if rows:
            print("\nData from MariaDB benchtest")
            print(" | ".join(columns))
            for row in rows:
                # row structure
                #row[0] = benchtest id
                #row[1] = benchtest start time
                #row[2] = benchtest stop time
                #row[3] = benchtest user
                #row[4] = benchtest processing/passed flag: 0,1,2 or 3
                #row[5] = MD1 DB Serial No
                #row[6] = MD2 DB Serial No
                #row[7] = MD3 DB Serial No
                #row[8] = MD4 DB Serial No
                #print(row)

		# If the benchtest is flagged for reprocessing, then store them in a dictionary
                # In regeneration mode, process all benchtests (or specific ones if specified)
                if regenerate_mode is not None:
                    if specific_benchtest_ids is not None:
                        if row[0] in specific_benchtest_ids:
                            # Check if specific daughterboard ID is provided and if it's in this benchtest
                            if specific_daughterboard_id is not None:
                                if specific_daughterboard_id in [row[5], row[6], row[7], row[8]]:
                                    if row[1] is not None and row[2] is not None:
                                        benchtest_proc[row[0]] = dict([("benchtest_pass", row[4]),
                                                                       ("benchtest_timestamp", [row[1].strftime("%Y-%m-%dT%H:%M:%SZ"), row[2].strftime("%Y-%m-%dT%H:%M:%SZ")]),
                                                                       ("benchtest_serialnos", [row[5], row[6], row[7], row[8]] )])
                                    else:
                                        print(f'  Skipping benchtest {row[0]} due to missing timestamp data')
                                else:
                                    print(f'  Skipping benchtest {row[0]} as it does not contain daughterboard {specific_daughterboard_id}')
                            else:
                                if row[1] is not None and row[2] is not None:
                                    benchtest_proc[row[0]] = dict([("benchtest_pass", row[4]),
                                                                   ("benchtest_timestamp", [row[1].strftime("%Y-%m-%dT%H:%M:%SZ"), row[2].strftime("%Y-%m-%dT%H:%M:%SZ")]),
                                                                   ("benchtest_serialnos", [row[5], row[6], row[7], row[8]] )])
                                else:
                                    print(f'  Skipping benchtest {row[0]} due to missing timestamp data')
                    else:
                        # Process all benchtests in regeneration mode
                        # Check if specific daughterboard ID is provided
                        if specific_daughterboard_id is not None:
                            if specific_daughterboard_id in [row[5], row[6], row[7], row[8]]:
                                if row[1] is not None and row[2] is not None:
                                    benchtest_proc[row[0]] = dict([("benchtest_pass", row[4]),
                                                                   ("benchtest_timestamp", [row[1].strftime("%Y-%m-%dT%H:%M:%SZ"), row[2].strftime("%Y-%m-%dT%H:%M:%SZ")]),
                                                                   ("benchtest_serialnos", [row[5], row[6], row[7], row[8]] )])
                                else:
                                    print(f'  Skipping benchtest {row[0]} due to missing timestamp data')
                            else:
                                print(f'  Skipping benchtest {row[0]} as it does not contain daughterboard {specific_daughterboard_id}')
                        else:
                            if row[1] is not None and row[2] is not None:
                                benchtest_proc[row[0]] = dict([("benchtest_pass", row[4]),
                                                               ("benchtest_timestamp", [row[1].strftime("%Y-%m-%dT%H:%M:%SZ"), row[2].strftime("%Y-%m-%dT%H:%M:%SZ")]),
                                                               ("benchtest_serialnos", [row[5], row[6], row[7], row[8]] )])
                            else:
                                print(f'  Skipping benchtest {row[0]} due to missing timestamp data')
                elif row[4] == 2:
                    # Check if specific daughterboard ID is provided
                    if specific_daughterboard_id is not None:
                        if specific_daughterboard_id in [row[5], row[6], row[7], row[8]]:
                            if row[1] is not None and row[2] is not None:
                                benchtest_proc[row[0]] = dict([("benchtest_pass", row[4]),
                                                               ("benchtest_timestamp", [row[1].strftime("%Y-%m-%dT%H:%M:%SZ"), row[2].strftime("%Y-%m-%dT%H:%M:%SZ")]),
                                                               ("benchtest_serialnos", [row[5], row[6], row[7], row[8]] )])
                            else:
                                print(f'  Skipping benchtest {row[0]} due to missing timestamp data')
                        else:
                            print(f'  Skipping benchtest {row[0]} as it does not contain daughterboard {specific_daughterboard_id}')
                    else:
                        if row[1] is not None and row[2] is not None:
                            benchtest_proc[row[0]] = dict([("benchtest_pass", row[4]),
                                                           ("benchtest_timestamp", [row[1].strftime("%Y-%m-%dT%H:%M:%SZ"), row[2].strftime("%Y-%m-%dT%H:%M:%SZ")]),
                                                           ("benchtest_serialnos", [row[5], row[6], row[7], row[8]] )])
                        else:
                            print(f'  Skipping benchtest {row[0]} due to missing timestamp data')

        else:
            print("⚠ No data found in selected table.")

        # Printing Dictionary
        print(benchtest_proc)

        #for key, value in benchtest_proc.items():
        #    print(f"{key} : {value}")

        mariadb_read_seconds = time.perf_counter() - _t_mariadb
        if enable_timing:
            print(f'Timing: MariaDB read took {mariadb_read_seconds:.3f} s')
            write_timing_row(
                timing_session,
                'mariadb_read', mariadb_read_seconds,
                detail='benchtest_table', progress=timing_progress,
                )

    except Error as e:
        print("\u274C MariaDB Connection Failed")
        if enable_timing and '_t_mariadb' in locals():
            mariadb_read_seconds = time.perf_counter() - _t_mariadb



    ### ######## ###
    ### InfluxDB ###
    ### ######## ###

    ### Comments for InfluxDB
    ### The benchtest_proc dictionary is completely general, but the "benchtest_pass" parameter isn't clear
    ### Likewise, the use of the "benchtest_id" parameter is clear either. It's just a number, but if we're going to loop over it, it has to correspond to something (maybe a direcory name?)
    ### Add output flags for each benchtest_id that needs to be processed
    ### Likewise, add flags for which MDs are filled
    # Accumulated pass/fail stats (small); series data is held per-MD only inside the Influx loop.
    statDict = {}
    try:
        ### Connect to influxDB ###
        print("\n==================== InfluxDB Tree ====================")
        print(f"🔗 Connecting to InfluxDB at {secrets['tiledb-influxdb']['host']}:{secrets['tiledb-influxdb']['port']}...")
        client = InfluxDBClient(
            host=secrets["tiledb-influxdb"]["host"],
            port=secrets["tiledb-influxdb"]["port"],
            username=secrets["tiledb-influxdb"]["username"],
            password=secrets["tiledb-influxdb"]["password"]
        )
        client.ping()
        print("✅ Connected to InfluxDB!")

        # Get Databases
        databases = client.get_list_database()
        if not databases:
            print("?? No databases found in InfluxDB.")
            return

        # List Databases
        print("📂 InfluxDB Databases:")
        print(databases)

        # List Table
        print("============================")
        for i, db in enumerate(databases):
            db_name = db["name"]
            print_tree(0, db_name, i == len(databases) - 1)

            client.switch_database(db_name)
            result = client.query("SHOW MEASUREMENTS")
            measurements = [m["name"] for m in result.get_points()]

            print("============================")
            print(measurements)
            print("============================")
            if not measurements:
                print_tree(1, "(No Measurements)", True)
            else:
                for j, measurement in enumerate(measurements):
                    print_tree(1, measurement, j == len(measurements) - 1)



        # Access InfluxDB Table: 'tiledb'
        client.switch_database("tiledb")


        ### Analysing benchtest Data ###
        # Define output directroy
        driveDIR = "/var/www/html/drive/benchtests/"

        # Define Query Output Storage Dictionary (transient; cleared after parse)
        queryResults = {}
        #print(f'queryResults = {queryResults}')

        # Define plot / statistics regeneration tracking
        plot_regenerate = {}
        stats_regenerate = {}
        #print(f'plot_regenerate = {plot_regenerate}')

        # Define Data Array (series held for one MD at a time)
        dataDict = {}
        dfDict = {}
        plotDict = {}

        # Define InfluxDB Tables
        VarTables = ["Link Status", "xADC", "ADC_Linearity", "CIS_Linearity", "CIS", "Integrator_Linearity"]
        TagTables = ["V"]

        # benchtest Loop
        for benchtest_id in benchtest_proc.keys():

            # Make output directory
            btDIRName = "benchtest_id_" + str(benchtest_id)
            print(f'  Creating directory: {driveDIR + str(btDIRName)}')
            btDIR_fullpath = Path(driveDIR + str(btDIRName))
            print(f'  btDIR_fullpath = {btDIR_fullpath}')
            btDIR_fullpath.mkdir(parents=True, exist_ok=True)

            print("============================")
            print(f'benchtest id: {benchtest_id}')
            print(f'benchtest start time: {benchtest_proc[benchtest_id]["benchtest_timestamp"][0]}')
            print(f'benchtest stop time:  {benchtest_proc[benchtest_id]["benchtest_timestamp"][1]}')
            print(f'benchtest MD1 DB Serial Number: {benchtest_proc[benchtest_id]["benchtest_serialnos"][0]}')
            print(f'benchtest MD2 DB Serial Number: {benchtest_proc[benchtest_id]["benchtest_serialnos"][1]}')
            print(f'benchtest MD3 DB Serial Number: {benchtest_proc[benchtest_id]["benchtest_serialnos"][2]}')
            print(f'benchtest MD4 DB Serial Number: {benchtest_proc[benchtest_id]["benchtest_serialnos"][3]}')

            # Handle backup and regeneration for benchtest_id.log
            log_path = driveDIR + str(btDIRName) + "/" + "benchtest_id_" + str(benchtest_id) + ".log"
            write_benchtest_log = True
            
            if regenerate_mode == 'benchtest_id_log' or regenerate_mode == 'all':
                backup_log_file(log_path)
            elif regenerate_mode in ('benchtest_id_results_log', 'plots', 'statistics'):
                # Skip writing benchtest_id.log if only regenerating results, plots, or statistics
                write_benchtest_log = False
            else:
                # Default mode: backup if exists
                backup_log_file(log_path)

            if write_benchtest_log:
                with open(log_path, "w") as logfile:
                    logfile.write(f'benchtest id: {benchtest_id}\n')
                    logfile.write(f'benchtest start time: {benchtest_proc[benchtest_id]["benchtest_timestamp"][0]}\n')
                    logfile.write(f'benchtest stop time:  {benchtest_proc[benchtest_id]["benchtest_timestamp"][1]}\n')
                    logfile.write(f'benchtest MD1 DB Serial Number: {benchtest_proc[benchtest_id]["benchtest_serialnos"][0]}\n')
                    logfile.write(f'benchtest MD2 DB Serial Number: {benchtest_proc[benchtest_id]["benchtest_serialnos"][1]}\n')
                    logfile.write(f'benchtest MD3 DB Serial Number: {benchtest_proc[benchtest_id]["benchtest_serialnos"][2]}\n')
                    logfile.write(f'benchtest MD4 DB Serial Number: {benchtest_proc[benchtest_id]["benchtest_serialnos"][3]}\n')

                    # Verifying Kintex IDs
                    for MDi in range(0,4):
                        if benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi] != None:
                            print(f'  For DaughterBoard with Serial No# {benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}:')
                            logfile.write(f'  For DaughterBoard with Serial No# {benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}:\n')

                            # Querying Kintex IDs
                            tiledb_kintexid_query = f"SELECT kintex_a_id, kintex_b_id FROM daughterboard WHERE serial_no = '{benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}'"

                            #print(f'tiledb_kintexid_query = {tiledb_kintexid_query}')

                            cursor.execute(tiledb_kintexid_query)

                            rows = cursor.fetchall()
                            columns = [desc[0] for desc in cursor.description] # This "columns" array contains the names of each of the variables stored in the table
                            #print(f"columns = {columns}")
                            #print(f"rows    = {rows}")

                            KintexID_A = rows[0][0]
                            KintexID_B = rows[0][1]

                            print(f'  A-Side Kintex ID: {KintexID_A}')
                            print(f'  B-Side Kintex ID: {KintexID_B}')
                            logfile.write(f'  A-Side Kintex ID: {KintexID_A}\n')
                            logfile.write(f'  B-Side Kintex ID: {KintexID_B}\n')

                            if KintexID_A == None:
                                print(f'    WARNING! Kintex A-Side ID isn\'t set!')
                                logfile.write(f'    WARNING! Kintex A-Side ID isn\'t set!\n')

                            if KintexID_B == None:
                                print(f'    WARNING! Kintex B-Side ID isn\'t set!')
                                logfile.write(f'    WARNING! Kintex B-Side ID isn\'t set!\n')

                            if KintexID_A == KintexID_B and KintexID_A != None and KintexID_B != None:
                                print(f'    WARNING! Kintex IDs match for both sides!')
                                logfile.write(f'    WARNING! Kintex IDs match for both sides!\n')

            # Allocate result dictionary space
            queryResults[benchtest_id] = {}
            #print(f'queryResults = {queryResults}')
            #print(f'queryResults[{benchtest_id}] = {queryResults[benchtest_id]}')

            # Allocate data dictionary space
            dataDict[benchtest_id] = {}

            # Set plot / statistics regeneration flags for this benchtest
            if regenerate_mode == 'benchtest_id_log' or regenerate_mode == 'benchtest_id_results_log':
                plot_regenerate[benchtest_id] = False
                stats_regenerate[benchtest_id] = False
            elif regenerate_mode == 'statistics':
                plot_regenerate[benchtest_id] = False
                stats_regenerate[benchtest_id] = True
            elif regenerate_mode == 'plots' or regenerate_mode == 'all':
                plot_regenerate[benchtest_id] = True
                stats_regenerate[benchtest_id] = True
            else:
                # Default / first-pass processing: generate both
                plot_regenerate[benchtest_id] = True
                stats_regenerate[benchtest_id] = True

            # Per-MD processing: query -> stats -> (DF/plots if needed) -> free.
            # Peak RAM should be ~1 daughterboard of series data, not all 4.
            print(f'\nStatistical Tests / per-MD ingest for benchtest {benchtest_id}')
            statDict[benchtest_id] = {}
            dfDict[benchtest_id] = {}
            plotDict[benchtest_id] = {}

            bt_log_path = driveDIR + str(btDIRName) + "/" + "benchtest_id_" + str(benchtest_id) + ".log"
            with open(bt_log_path, "a") as logfile:
                logfile.write(f'  benchtest ID: {benchtest_id}\n')

            _t_benchtest = time.perf_counter()
            for MDi in range(0, 4):
                if benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi] is None:
                    continue

                # Skip if specific daughterboard ID is provided and doesn't match
                if specific_daughterboard_id is not None:
                    if benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi] != specific_daughterboard_id:
                        print(f'    Skipping DaughterBoard {benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]} (not the specified daughterboard)')
                        continue

                board_serial = benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]
                md_key = "MD" + str(MDi + 1)
                print("----------------------------")
                print(f'Processing Mini-Drawer {MDi+1} (serial={board_serial}) for benchtest {benchtest_id}')

                # Hold series data for this MD only
                dataDict[benchtest_id] = {}
                _t_md = time.perf_counter()

                # Table Loop (query Influx for this MD only)
                _t_influx = time.perf_counter()
                for table in config.keys():
                    print("----------------------------")
                    print(f'Table: {table} (MD{MDi+1} only)')
                    timing_mark(
                        timing_progress, 'influx_read',
                        benchtest_id=benchtest_id, md=md_key, serial_no=board_serial, detail=str(table),
                    )
                    _t_influx_table = time.perf_counter()

                    # InfluxDB Query Construction
                    # Handling Variable based queries
                    if table in VarTables:
                        print(f'{table} is in VarTables')

                        querystr_channels = '"PprGTH MD' + str(MDi+1) + '"'
                        my_channels = ["PprGTH MD" + str(MDi+1)]
                        print(f'Mini-Drawer {MDi+1} contains DaughterBoard with Serial Number: {board_serial}')
                        print(f'querystr_channels = {querystr_channels}')
                        print(f'my_channels = {my_channels}')

                        querystr_table = f'"{table}"'
                        print(f'querystr_table = {querystr_table}')

                        querystr_variables = ''
                        my_variables = []

                        for ivar in config[table].keys():
                            querystr_variables = querystr_variables + '"' + ivar + '", '
                            my_variables.append(ivar)
                            if ivar not in dataDict[benchtest_id]:
                                dataDict[benchtest_id][ivar] = {}
                            if md_key not in dataDict[benchtest_id][ivar]:
                                dataDict[benchtest_id][ivar][md_key] = {}

                        querystr_variables = querystr_variables[:-2]
                        print(f'querystr_variables = {querystr_variables}')
                        print(f'my_variables = {my_variables}')

                        start_time = benchtest_proc[benchtest_id]["benchtest_timestamp"][0]
                        stop_time  = benchtest_proc[benchtest_id]["benchtest_timestamp"][1]
                        querystr_time_range = f'time >= \'{benchtest_proc[benchtest_id]["benchtest_timestamp"][0]}\' AND time <= \'{benchtest_proc[benchtest_id]["benchtest_timestamp"][1]}\''
                        print(f'querystr_time_range = {querystr_time_range}')

                        my_query = f'SELECT {querystr_channels}, {querystr_variables} FROM {querystr_table} WHERE {querystr_time_range}'
                        print(f'my_query = {my_query}')

                        query_result = client.query(my_query)
                        query_points = list(query_result.get_points())
                        del query_result
                        if not query_points:
                            print(f'Warning: No data returned from InfluxDB for table {table} in benchtest {benchtest_id} ({md_key})')
                            for ivar in my_variables:
                                if ivar not in dataDict[benchtest_id]:
                                    dataDict[benchtest_id][ivar] = {}
                                if md_key not in dataDict[benchtest_id][ivar]:
                                    dataDict[benchtest_id][ivar][md_key] = {}
                            print(f'Querying Table: {table} - No data available\n')
                        else:
                            print(f'Querying Table: {table} - Success!\n')

                        for point in query_points:
                            for ppr in my_channels:
                                if point[ppr] != None:
                                    for ivar in my_variables:
                                        if point[ppr] not in dataDict[benchtest_id][ivar][ppr[7:10]]:
                                            dataDict[benchtest_id][ivar][ppr[7:10]][point[ppr]] = {}

                                        if "x" not in dataDict[benchtest_id][ivar][ppr[7:10]][point[ppr]]:
                                            dataDict[benchtest_id][ivar][ppr[7:10]][point[ppr]]["x"] = []

                                        if "y" not in dataDict[benchtest_id][ivar][ppr[7:10]][point[ppr]]:
                                            dataDict[benchtest_id][ivar][ppr[7:10]][point[ppr]]["y"] = []

                                        if point[ivar] != None:
                                            # Filtering zeroes from table CIS variables
                                            if table == "CIS" and point[ivar] == 0:
                                                print(f"  Warning: Variable {ivar} in Table {table} has value {point[ivar]} at {datetime.fromisoformat(point['time'])}. Filtering out.")
                                            else:
                                                dataDict[benchtest_id][ivar][ppr[7:10]][point[ppr]]["x"].append(datetime.fromisoformat(point['time']))
                                                dataDict[benchtest_id][ivar][ppr[7:10]][point[ppr]]["y"].append(point[ivar])
                                        else:
                                            print(f"  Warning: NULL value encountered for variable {ivar} in Table {table} at {datetime.fromisoformat(point['time'])}. Skipping this point.")
                        del query_points

                    elif table in TagTables:
                        print(f'{table} is in TagTables')

                        querystr_table = f'"{table}"'
                        print(f'querystr_table = {querystr_table}')

                        start_time = benchtest_proc[benchtest_id]["benchtest_timestamp"][0]
                        stop_time  = benchtest_proc[benchtest_id]["benchtest_timestamp"][1]
                        querystr_time_range = f'time >= \'{benchtest_proc[benchtest_id]["benchtest_timestamp"][0]}\' AND time <= \'{benchtest_proc[benchtest_id]["benchtest_timestamp"][1]}\''
                        print(f'querystr_time_range = {querystr_time_range}')

                        querystr_tags = ''

                        for ivar in config[table].keys():
                            if ivar not in dataDict[benchtest_id]:
                                dataDict[benchtest_id][ivar] = {}
                            dataDict[benchtest_id][ivar][md_key] = {}

                            for side in ['a', 'b']:
                                dataDict[benchtest_id][ivar][md_key]["db"+side] = {}
                                dataDict[benchtest_id][ivar][md_key]["db"+side]["x"] = []
                                dataDict[benchtest_id][ivar][md_key]["db"+side]["y"] = []

                                querystr_tags = querystr_tags + '"entity_id" = \'db_tester_lbt_md' + str(MDi+1) + '_db' + side + '_' + ivar + '\' OR '

                        querystr_tags = '(' + querystr_tags[:-4] + ')'
                        print(f'querystr_tags = {querystr_tags}')

                        my_query = f'SELECT "entity_id", "value" FROM {querystr_table} WHERE {querystr_time_range} AND {querystr_tags}'
                        print(f'my_query = {my_query}')

                        query_result = client.query(my_query)
                        query_points = list(query_result.get_points())
                        del query_result
                        if not query_points:
                            print(f'Warning: No data returned from InfluxDB for table {table} in benchtest {benchtest_id} ({md_key})')
                            for ivar in config[table].keys():
                                if ivar not in dataDict[benchtest_id]:
                                    dataDict[benchtest_id][ivar] = {}
                                dataDict[benchtest_id][ivar][md_key] = {}
                                for side in ['a', 'b']:
                                    dataDict[benchtest_id][ivar][md_key]["db"+side] = {}
                                    dataDict[benchtest_id][ivar][md_key]["db"+side]["x"] = []
                                    dataDict[benchtest_id][ivar][md_key]["db"+side]["y"] = []
                            print(f'Querying Table: {table} - No data available\n')
                        else:
                            print(f'Querying Table: {table} - Success!\n')

                        for point in query_points:
                            if point["value"] != None:
                                dataDict[benchtest_id][point["entity_id"][22:]][point["entity_id"][14:17].upper()][point["entity_id"][18:21]]["x"].append(datetime.fromisoformat(point['time']))
                                dataDict[benchtest_id][point["entity_id"][22:]][point["entity_id"][14:17].upper()][point["entity_id"][18:21]]["y"].append(point["value"])
                            else:
                                print(f"  Warning: NULL value encountered for entity_id {point['entity_id']} in Table {table} at {datetime.fromisoformat(point['time'])}. Skipping this point.")

                        del query_points

                    write_timing_row(
                        timing_session,
                        'influx_read', time.perf_counter() - _t_influx_table,
                        benchtest_id=benchtest_id, md=md_key, serial_no=board_serial,
                        detail=str(table), progress=timing_progress,
                        )

                write_timing_row(
                    timing_session,
                    'influx_read', time.perf_counter() - _t_influx,
                    benchtest_id=benchtest_id, md=md_key, serial_no=board_serial,
                    detail='all_tables', progress=timing_progress,
                    )

                # --- Statistical tests for this MD only ---
                timing_mark(
                    timing_progress, 'analysis',
                    benchtest_id=benchtest_id, md=md_key, serial_no=board_serial, detail='statistical_tests',
                )
                _t_analysis = time.perf_counter()
                with open(bt_log_path, "a") as logfile:
                    print(f'\n    DaughterBoard Serial Number: {board_serial}')
                    logfile.write(f'\n    DaughterBoard Serial Number: {board_serial}\n')
                    statDict[benchtest_id][board_serial] = {}

                    dbDIRName = "DB_" + str(board_serial)
                    print(f'    Creating Directory: {driveDIR + btDIRName + "/" + dbDIRName}')
                    dbDIR_fullpath = Path(driveDIR + btDIRName + "/" + dbDIRName)
                    print(f'    dbDir_fullpath = {dbDIR_fullpath}')
                    dbDIR_fullpath.mkdir(parents=True, exist_ok=True)

                    for table in config.keys():
                        print(f'      Table: {table}')
                        logfile.write(f'      Table: {table}\n')

                        for ivar in config[table].keys():
                            timing_mark(
                                timing_progress, 'analysis_test',
                                benchtest_id=benchtest_id, md=md_key, serial_no=board_serial,
                                detail=f'{table}/{ivar}',
                            )
                            _t_analysis_test = time.perf_counter()
                            print(f'        Variable:  {ivar}')
                            print(f'        config[{table}][{ivar}] = {config[table][ivar]}')
                            logfile.write(f'        Variable:  {ivar}\n')
                            logfile.write(f'        config[{table}][{ivar}] = {config[table][ivar]}\n')
                            statDict[benchtest_id][board_serial][ivar] = {}

                            var_pointpass = []
                            var_npoints = 0

                            # Empty-query handling may leave MD bucket missing; treat as no channels.
                            md_channels = dataDict[benchtest_id].get(ivar, {}).get(md_key, {})

                            for channel in md_channels:
                                print(f'          Channel: {channel}')
                                logfile.write(f'          Channel: {channel}\n')

                                var_npoints += len(dataDict[benchtest_id][ivar][md_key][channel]["y"])

                                var_thresholds = get_var_thresholds(config[table][ivar])
                                if len(var_thresholds) == 1:

                                    for y in dataDict[benchtest_id][ivar][md_key][channel]["y"]:
                                        if y == var_thresholds[0]:
                                            var_pointpass.append(1)
                                        else:
                                            var_pointpass.append(0)

                                if len(var_thresholds) == 2:
                                    for i, y in enumerate( dataDict[benchtest_id][ivar][md_key][channel]["y"] ):

                                        datlen = len(dataDict[benchtest_id][ivar][md_key][channel]["y"])

                                        np_RMArray = np.empty(0)
                                        roll_median = 0
                                        roll_MAD = 0

                                        if y >= var_thresholds[0] and y <= var_thresholds[1]:
                                            var_pointpass.append(1)

                                        elif y < var_thresholds[0] or y > var_thresholds[1]:

                                            if datlen == 1:
                                                print(f'              Warning: Only 1 data point available for {ivar} in {channel}. Cannot perform spike/drop detection. Marking as failed (out of bounds).')
                                                logfile.write(f'             Warning: Only 1 data point available for {ivar} in {channel}. Cannot perform spike/drop detection. Marking as failed (out of bounds).\n')
                                                var_pointpass.append(0)
                                            else:
                                                if i < 10:
                                                    print(f'              Case: i<10. [0, {i}, {i+1}, 21]')
                                                    np_RMArray = np.array( dataDict[benchtest_id][ivar][md_key][channel]["y"][0:i] + dataDict[benchtest_id][ivar][md_key][channel]["y"][i+1:21])
                                                elif i >= len(dataDict[benchtest_id][ivar][md_key][channel]["y"]) - 10:
                                                    print(f'              Case: i>= len(dataDict[benchtest_id][ivar][md_key][channel]["y"]) - 10. [datlen-21, i, i+1, datlen] = [{datlen-21}, {i}, {i+1}, {datlen}]')
                                                    np_RMArray = np.array( dataDict[benchtest_id][ivar][md_key][channel]["y"][datlen-21:i] + dataDict[benchtest_id][ivar][md_key][channel]["y"][i+1:datlen] )
                                                else:
                                                    print(f'              Case: else. [{i-10}, {i}, {i+1}, {i+11}]')
                                                    np_RMArray = np.array( dataDict[benchtest_id][ivar][md_key][channel]["y"][i-10:i] + dataDict[benchtest_id][ivar][md_key][channel]["y"][i+1:i+11])

                                                roll_median = np.median(np_RMArray)
                                                roll_MAD = max(0.1, np.median(np.abs(np_RMArray - roll_median)))

                                                if i == 0:
                                                    print(f'              Case: i == 0')
                                                    if abs(dataDict[benchtest_id][ivar][md_key][channel]["y"][i] - dataDict[benchtest_id][ivar][md_key][channel]["y"][i+1]) < 3*roll_MAD:
                                                        var_pointpass.append(0)
                                                    else:
                                                        print(f'             Spike/Drop Detected @ [DBSN: {board_serial}, Table: {table}, Variable: {ivar}, Channel: {channel} Time: {dataDict[benchtest_id][ivar][md_key][channel]["x"][i]}, Value: {dataDict[benchtest_id][ivar][md_key][channel]["y"][i]}]')
                                                        logfile.write(f'             Spike/Drop Detected @ [DBSN: {board_serial}, Table: {table}, Variable: {ivar}, Channel: {channel} Time: {dataDict[benchtest_id][ivar][md_key][channel]["x"][i]}, Value: {dataDict[benchtest_id][ivar][md_key][channel]["y"][i]}]\n')
                                                elif i == datlen-1:
                                                    print(f'              Case: i == datlen-1')
                                                    if abs(dataDict[benchtest_id][ivar][md_key][channel]["y"][i-1] - dataDict[benchtest_id][ivar][md_key][channel]["y"][i]) < 3*roll_MAD:
                                                        var_pointpass.append(0)
                                                    else:
                                                        print(f'             Spike/Drop Detected @ [DBSN: {board_serial}, Table: {table}, Variable: {ivar}, Channel: {channel} Time: {dataDict[benchtest_id][ivar][md_key][channel]["x"][i]}, Value: {dataDict[benchtest_id][ivar][md_key][channel]["y"][i]}]')
                                                        logfile.write(f'             Spike/Drop Detected @ [DBSN: {board_serial}, Table: {table}, Variable: {ivar}, Channel: {channel} Time: {dataDict[benchtest_id][ivar][md_key][channel]["x"][i]}, Value: {dataDict[benchtest_id][ivar][md_key][channel]["y"][i]}]\n')
                                                else:
                                                    print(f'              Case: else.')
                                                    if abs(dataDict[benchtest_id][ivar][md_key][channel]["y"][i] - dataDict[benchtest_id][ivar][md_key][channel]["y"][i-1]) < 3*roll_MAD or abs(dataDict[benchtest_id][ivar][md_key][channel]["y"][i+1] - dataDict[benchtest_id][ivar][md_key][channel]["y"][i]) < 3*roll_MAD:
                                                        var_pointpass.append(0)
                                                    else:
                                                        print(f'             Spike/Drop Detected @ [DBSN: {board_serial}, Table: {table}, Variable: {ivar}, Channel: {channel} Time: {dataDict[benchtest_id][ivar][md_key][channel]["x"][i]}, Value: {dataDict[benchtest_id][ivar][md_key][channel]["y"][i]}]')
                                                        logfile.write(f'             Spike/Drop Detected @ [DBSN: {board_serial}, Table: {table}, Variable: {ivar}, Channel: {channel} Time: {dataDict[benchtest_id][ivar][md_key][channel]["x"][i]}, Value: {dataDict[benchtest_id][ivar][md_key][channel]["y"][i]}]\n')

                            statDict[benchtest_id][board_serial][ivar]["nPoints"] = var_npoints
                            statDict[benchtest_id][board_serial][ivar]["nConsidered"] = len(var_pointpass)
                            statDict[benchtest_id][board_serial][ivar]["nPass"] = sum(var_pointpass)
                            if len(var_pointpass) != 0:
                                statDict[benchtest_id][board_serial][ivar]["fPass"] = sum(var_pointpass)/len(var_pointpass)
                            elif len(var_pointpass) == 0:
                                print(f'        Warning: Data Not Found for Variable {ivar} in Table {table}! Tentatively Ignoring Check and "Passing" Board, Please Consult Log.')
                                statDict[benchtest_id][board_serial][ivar]["fPass"] = -1.0

                            write_timing_row(
                                timing_session,
                                'analysis_test', time.perf_counter() - _t_analysis_test,
                                benchtest_id=benchtest_id, md=md_key, serial_no=board_serial,
                                detail=f'{table}/{ivar}', progress=timing_progress,
                                )

                write_timing_row(
                    timing_session,
                    'analysis', time.perf_counter() - _t_analysis,
                    benchtest_id=benchtest_id, md=md_key, serial_no=board_serial,
                    detail='statistical_tests', progress=timing_progress,
                    )

                # --- DataFrames + plots / statistics YAML for this MD only (if needed) ---
                # Isolate failures so remaining MDs still get query/stats into statDict.
                need_plots_or_stats = plot_regenerate.get(benchtest_id) or stats_regenerate.get(benchtest_id)
                timing_mark(
                    timing_progress, 'plots_and_ops',
                    benchtest_id=benchtest_id, md=md_key, serial_no=board_serial,
                    detail='dataframes_plots_extra' if need_plots_or_stats else 'skipped',
                )
                _t_ops = time.perf_counter()
                if need_plots_or_stats:
                    try:
                        print(f'\nDataFrames / Plotly for serial={board_serial}')
                        start_time = benchtest_proc[benchtest_id]["benchtest_timestamp"][0]
                        stop_time = benchtest_proc[benchtest_id]["benchtest_timestamp"][1]

                        # Build DataFrames only when figures will be written (stats YAML uses dataDict).
                        if plot_regenerate.get(benchtest_id):
                            dfDict[benchtest_id][board_serial] = {}
                            for table in config.keys():
                                print(f'      Table: {table}')
                                for ivar in config[table].keys():
                                    timing_mark(
                                        timing_progress, 'dataframe_test',
                                        benchtest_id=benchtest_id, md=md_key, serial_no=board_serial,
                                        detail=f'{table}/{ivar}',
                                    )
                                    _t_df_test = time.perf_counter()
                                    print(f'        Variable: {ivar}')
                                    dfDict[benchtest_id][board_serial][ivar] = {}
                                    dfCombo = []
                                    md_channels = dataDict[benchtest_id].get(ivar, {}).get(md_key, {})
                                    for channel in md_channels:
                                        print(f'          channel: {channel}')
                                        dfDict[benchtest_id][board_serial][ivar][channel] = pd.DataFrame( {'channel' : [channel]*len(dataDict[benchtest_id][ivar][md_key][channel]["x"]), 'x' : dataDict[benchtest_id][ivar][md_key][channel]["x"], 'y' : dataDict[benchtest_id][ivar][md_key][channel]["y"] } )
                                        dfCombo.append(dfDict[benchtest_id][board_serial][ivar][channel])

                                    _refs = (dbq_plot_style or {}).get('reference_traces') or {}
                                    truth_name = _refs.get('truth_name') or 'TruthValue'
                                    lower_name = _refs.get('lower_name') or 'LowerLimit'
                                    upper_name = _refs.get('upper_name') or 'UpperLimit'
                                    var_thresholds = get_var_thresholds(config[table][ivar])
                                    if len(var_thresholds) == 1:
                                        dfDict[benchtest_id][board_serial][ivar][truth_name] = pd.DataFrame( {'channel' : [truth_name, truth_name], 'x' : [datetime.fromisoformat(start_time), datetime.fromisoformat(stop_time)], 'y' : [var_thresholds[0], var_thresholds[0]] } )
                                        dfCombo.append(dfDict[benchtest_id][board_serial][ivar][truth_name])
                                    if len(var_thresholds) == 2:
                                        dfDict[benchtest_id][board_serial][ivar][lower_name] = pd.DataFrame( {'channel' : [lower_name, lower_name], 'x' : [datetime.fromisoformat(start_time), datetime.fromisoformat(stop_time)], 'y' : [var_thresholds[0], var_thresholds[0]] } )
                                        dfCombo.append(dfDict[benchtest_id][board_serial][ivar][lower_name])
                                        dfDict[benchtest_id][board_serial][ivar][upper_name] = pd.DataFrame( {'channel' : [upper_name, upper_name], 'x' : [datetime.fromisoformat(start_time), datetime.fromisoformat(stop_time)], 'y' : [var_thresholds[1], var_thresholds[1]] } )
                                        dfCombo.append(dfDict[benchtest_id][board_serial][ivar][upper_name])

                                    dfCombo = [df for df in dfCombo if not df.empty]
                                    full_df = pd.concat(dfCombo) if dfCombo else pd.DataFrame(columns=['channel', 'x', 'y'])
                                    dfDict[benchtest_id][board_serial][ivar] = {"Full": full_df}
                                    del dfCombo, full_df
                                    write_timing_row(
                                        timing_session,
                                        'dataframe_test', time.perf_counter() - _t_df_test,
                                        benchtest_id=benchtest_id, md=md_key, serial_no=board_serial,
                                        detail=f'{table}/{ivar}', progress=timing_progress,
                                        )

                        # plotly Plotting / statistics YAML for this MD
                        print(f'\n  Plotly: serial={board_serial}')
                        plotDict[benchtest_id][board_serial] = {}
                        dbDIRName = "DB_" + str(board_serial)
                        dbDIR_fullpath = Path(driveDIR + btDIRName + "/" + dbDIRName)
                        dbDIR_fullpath.mkdir(parents=True, exist_ok=True)
                        board_stats_variables = {}

                        for table in config.keys():
                            print(f'      Table: {table}')
                            for ivar in config[table].keys():
                                timing_mark(
                                    timing_progress, 'plot_test',
                                    benchtest_id=benchtest_id, md=md_key, serial_no=board_serial,
                                    detail=f'{table}/{ivar}',
                                )
                                _t_plot_test = time.perf_counter()
                                print(f'        Variable: {ivar}')
                                md_channels = dataDict[benchtest_id].get(ivar, {}).get(md_key, {})
                                print(f'        nChannels: {len(md_channels)}')
                                plotDict[benchtest_id][board_serial][ivar] = {}

                                testtime = datetime.now()
                                print(f'        Post Initialise-plotDict Date/Time: {testtime.strftime("%y/%m/%d - %H:%M:%S")}')

                                if len(md_channels) != 0:
                                    plot_caption = get_var_caption(config[table][ivar], default_name=ivar)
                                    plot_dimensions = get_var_dimensions(config[table][ivar])
                                    _refs = (dbq_plot_style or {}).get('reference_traces') or {}
                                    truth_name = _refs.get('truth_name') or 'TruthValue'
                                    lower_name = _refs.get('lower_name') or 'LowerLimit'
                                    upper_name = _refs.get('upper_name') or 'UpperLimit'
                                    var_thresholds = get_var_thresholds(config[table][ivar])

                                    channel_y_data = {}
                                    channel_stats = {}
                                    for channel, series in md_channels.items():
                                        if channel in (truth_name, lower_name, upper_name):
                                            continue
                                        y_values = series.get('y') or []
                                        channel_y_data[channel] = y_values
                                        stats = compute_y_stats(y_values)
                                        if stats:
                                            channel_stats[channel] = stats

                                    if stats_regenerate.get(benchtest_id):
                                        board_stats_variables[ivar] = build_variable_stats_payload(
                                            ivar,
                                            plot_caption,
                                            var_thresholds,
                                            channel_y_data,
                                            table=table,
                                            dimensions=plot_dimensions,
                                        )

                                    if not plot_regenerate.get(benchtest_id):
                                        write_timing_row(
                                            timing_session,
                                            'plot_test', time.perf_counter() - _t_plot_test,
                                            benchtest_id=benchtest_id, md=md_key, serial_no=board_serial,
                                            detail=f'{table}/{ivar}', progress=timing_progress,
                                            )
                                        continue

                                    plotDict[benchtest_id][board_serial][ivar] = plotlyEX.line(
                                        dfDict[benchtest_id][board_serial][ivar]["Full"],
                                        x="x",
                                        y="y",
                                        color="channel",
                                        labels=px_line_labels(
                                            dbq_plot_style,
                                            plot_caption,
                                            dimensions=plot_dimensions,
                                        ),
                                    )

                                    testtime = datetime.now()
                                    print(f'          Post Define-plotDict Date/Time: {testtime.strftime("%y/%m/%d - %H:%M:%S")}')

                                    threshold_mode = None
                                    truth_value = None
                                    lower_value = None
                                    upper_value = None
                                    if len(var_thresholds) == 1:
                                        print('            LENGTH = 1')
                                        threshold_mode = 'truth'
                                        truth_value = var_thresholds[0]
                                    elif len(var_thresholds) == 2:
                                        print('            LENGTH = 2')
                                        threshold_mode = 'limits'
                                        lower_value = var_thresholds[0]
                                        upper_value = var_thresholds[1]

                                    style_dbq_figure(
                                        plotDict[benchtest_id][board_serial][ivar],
                                        dbq_plot_style,
                                        serial=board_serial,
                                        ivar=plot_caption,
                                        dimensions=plot_dimensions,
                                        threshold_mode=threshold_mode,
                                        start_time=start_time,
                                        stop_time=stop_time,
                                        benchtest_id=benchtest_id,
                                    )
                                    apply_plot_legend_stats(
                                        plotDict[benchtest_id][board_serial][ivar],
                                        channel_stats,
                                        truth_name=truth_name,
                                        lower_name=lower_name,
                                        upper_name=upper_name,
                                        truth_value=truth_value,
                                        lower_value=lower_value,
                                        upper_value=upper_value,
                                    )
                                    testtime = datetime.now()
                                    print(f'          Post Style-plotDict Date/Time: {testtime.strftime("%y/%m/%d - %H:%M:%S")}')

                                    plot_path = driveDIR+btDIRName+"/"+dbDIRName + "/DBSNo_"+str(board_serial)+"_PPrGTH_"+ivar+".html"
                                    plotDict[benchtest_id][board_serial][ivar].write_html(
                                        plot_path,
                                        **write_html_options(dbq_plot_style),
                                    )
                                    plotDict[benchtest_id][board_serial].pop(ivar, None)
                                    if (
                                        benchtest_id in dfDict
                                        and board_serial in dfDict[benchtest_id]
                                        and ivar in dfDict[benchtest_id][board_serial]
                                    ):
                                        del dfDict[benchtest_id][board_serial][ivar]
                                    testtime = datetime.now()
                                    print(f'          Post Final Save-plotDict Date/Time: {testtime.strftime("%y/%m/%d - %H:%M:%S")}')

                                write_timing_row(
                                    timing_session,
                                    'plot_test', time.perf_counter() - _t_plot_test,
                                    benchtest_id=benchtest_id, md=md_key, serial_no=board_serial,
                                    detail=f'{table}/{ivar}', progress=timing_progress,
                                    )

                        if stats_regenerate.get(benchtest_id) and board_stats_variables:
                            stats_path = (
                                driveDIR + btDIRName + "/" + dbDIRName
                                + "/DBSNo_" + str(board_serial) + "_PPrGTH_Statistics.yaml"
                            )
                            write_board_statistics_yaml(
                                stats_path,
                                serial=board_serial,
                                benchtest_id=benchtest_id,
                                variables_payload=board_stats_variables,
                                start_time=start_time,
                                stop_time=stop_time,
                            )
                            print(f'  Wrote statistics YAML: {stats_path}')

                        if plot_regenerate.get(benchtest_id):
                            try:
                                from piro_extra_test_plots import generate_extra_plots_for_board
                                extra_plots = ['ADC_Linearity_Samples',
                                'CIS_Samples',
                                'Link_Eye_Diagram_Samples',
                                'Integrator_Linearity_Samples',
                                'CIS_Linearity_Samples']

                                for extra_plot in extra_plots:
                                    timing_mark(
                                        timing_progress, 'extra_plot',
                                        benchtest_id=benchtest_id, md=md_key, serial_no=board_serial,
                                        detail=extra_plot,
                                    )
                                    _t_extra = time.perf_counter()
                                    generate_extra_plots_for_board(
                                        client,
                                        benchtest_id=benchtest_id,
                                        board_serial=board_serial,
                                        md_index=MDi,
                                        start_time=start_time,
                                        stop_time=stop_time,
                                        out_dir=str(dbDIR_fullpath),
                                        dbq_plot_style=dbq_plot_style,
                                        plots=[extra_plot],
                                    )
                                    write_timing_row(
                                        timing_session,
                                        'extra_plot', time.perf_counter() - _t_extra,
                                        benchtest_id=benchtest_id, md=md_key, serial_no=board_serial,
                                        detail=extra_plot, progress=timing_progress,
                                        )
                            except Exception as extra_exc:
                                print(f'  Warning: piro_extra_test_plots failed: {extra_exc}')
                    except Exception as plot_exc:
                        print(f'  Warning: DF/plot/stats-YAML pipeline failed for serial={board_serial}: {plot_exc}')

                write_timing_row(
                    timing_session,
                    'plots_and_ops', time.perf_counter() - _t_ops,
                    benchtest_id=benchtest_id, md=md_key, serial_no=board_serial,
                    detail='dataframes_plots_extra' if need_plots_or_stats else 'skipped',
                    progress=timing_progress,
                    )
                write_timing_row(
                    timing_session,
                    'md_total', time.perf_counter() - _t_md,
                    benchtest_id=benchtest_id, md=md_key, serial_no=board_serial,
                    progress=timing_progress,
                    )

                # Free per-board / per-MD series data before next MD
                if benchtest_id in dataDict:
                    dataDict[benchtest_id].clear()
                if benchtest_id in dfDict:
                    dfDict[benchtest_id].pop(board_serial, None)
                if benchtest_id in plotDict:
                    plotDict[benchtest_id].pop(board_serial, None)
                gc.collect()
                print(
                    f'  Freed in-memory data for serial={board_serial} '
                    f'{md_key} (benchtest {benchtest_id})'
                )

            write_timing_row(
                timing_session,
                'benchtest_total', time.perf_counter() - _t_benchtest,
                benchtest_id=benchtest_id, progress=timing_progress,
                )

            # Free remaining per-benchtest containers after all MDs.
            dataDict.pop(benchtest_id, None)
            dfDict.pop(benchtest_id, None)
            plotDict.pop(benchtest_id, None)
            gc.collect()

            print("----------------------------")
        print("============================\n")
        # Influx ResultSets / point lists are already released per table.
        queryResults.clear()
        gc.collect()

    except Exception as e:
        print(f"\u274C InfluxDB Connection Failed: {e}")

    # Some debugging code
    #for btid in dataDict:
    #    print(f'btid = {btid}')
    #
    #    for variable in dataDict[btid]:
    #        print(f'  variable = {variable}')
    #
    #        for MD in dataDict[btid][variable]:
    #            print(f'    MD = {MD}')
    #
    #            for channel in dataDict[btid][variable][MD]:
    #                print(f'        channel = {channel}')
    #                print(f'        dataDict[{btid}][{variable}][{MD}][{channel}]')
    #                print(f'        dataDict[{btid}][{variable}][{MD}][{channel}] = {dataDict[btid][variable][MD][channel]}')
    #
    #                for dim in dataDict[btid][variable][MD][channel]:
    #                    #if variable == "hg_max_dev":
    #                    #    print(f'          dim = {dim}')
    #                    #    print(f'          dataDict[{btid}][{variable}][{MD}][{channel}][{dim}] = {dataDict[btid][variable][MD][channel][dim]}')
    #
    #                    #for i in range(0, len(dataDict[btid][variable][MD][channel]["x"])):
    #                    #    print(f'          [{dataDict[btid][variable][MD][channel]["x"][i]}, {dataDict[btid][variable][MD][channel]["y"][i]}]')


    for btid, dbDict in statDict.items():
        print(f'\nFor benchtest with id: {btid}')
        timing_mark(
            timing_progress, 'results_output',
            benchtest_id=btid, detail='logs_csv_mariadb_updates',
        )
        _t_results = time.perf_counter()

        # Reopen output directory
        btDIRName = "benchtest_id_" + str(btid)
        print(f'  Reopening directory: {driveDIR + str(btDIRName)}')

        # Handle backup and regeneration for benchtest_id.log
        log_path = driveDIR + str(btDIRName) + "/" + "benchtest_id_" + str(btid) + ".log"
        write_benchtest_log = True
        
        if regenerate_mode == 'benchtest_id_log' or regenerate_mode == 'all':
            backup_log_file(log_path)
        elif regenerate_mode in ('benchtest_id_results_log', 'plots', 'statistics'):
            # Skip writing benchtest_id.log if only regenerating results, plots, or statistics
            write_benchtest_log = False
        else:
            # Default mode: backup if exists
            backup_log_file(log_path)

        # Handle backup and regeneration for benchtest_id_results.log
        results_path = driveDIR + str(btDIRName) + "/" + "benchtest_id_" + str(btid) + "_results.log"
        csv_path = driveDIR + str(btDIRName) + "/" + "benchtest_id_" + str(btid) + "_results.csv"
        write_results_log = True
        
        if regenerate_mode == 'benchtest_id_results_log' or regenerate_mode == 'all':
            backup_log_file(results_path)
        elif regenerate_mode in ('benchtest_id_log', 'plots', 'statistics'):
            # Skip writing results if only regenerating main log, plots, or statistics
            write_results_log = False
        else:
            # Default mode: backup if exists
            backup_log_file(results_path)

        # Handle plot regeneration
        write_plots = True
        if regenerate_mode in ('benchtest_id_log', 'benchtest_id_results_log', 'statistics'):
            # Skip plots if only regenerating logs or statistics
            write_plots = False
        elif regenerate_mode == 'plots' or regenerate_mode == 'all':
            # Regenerate plots
            write_plots = True
        else:
            # Default mode: generate plots
            write_plots = True

        # Open files based on regeneration mode
        logfile = None
        resultsfile = None
        csvfile = None
        
        if write_benchtest_log:
            logfile = open(log_path, "a")
            logfile.write(f'In benchtest with id: {btid}\n')
        
        if write_results_log:
            # Check if we need to preserve existing data (when using -d)
            if specific_daughterboard_id is not None and Path(results_path).exists():
                # Read existing log file to preserve other daughterboards' data
                with open(results_path, "r") as existing_log:
                    existing_log_lines = existing_log.readlines()
                resultsfile = open(results_path, "w")
                # Write back existing content except for the specific daughterboard section
                skip_section = False
                for line in existing_log_lines:
                    # Check if this line starts a daughterboard section
                    if f'DaughterBoard with Serial No: {specific_daughterboard_id}' in line:
                        skip_section = True
                        continue
                    # Check if we should stop skipping (next daughterboard section or end of file)
                    if skip_section and line.startswith('DaughterBoard with Serial No:'):
                        skip_section = False
                    if not skip_section:
                        resultsfile.write(line)
            else:
                resultsfile = open(results_path, "w")
            
            # Handle CSV file similarly
            if specific_daughterboard_id is not None and Path(csv_path).exists():
                # Read existing CSV to preserve other daughterboards' data
                existing_csv_data = {}
                with open(csv_path, "r") as existing_csv:
                    csv_reader = csv.reader(existing_csv)
                    header = next(csv_reader)
                    for row in csv_reader:
                        if row:
                            measurement = row[0]
                            existing_csv_data[measurement] = row[1:]
                csvfile = open(csv_path, "w")
            else:
                csvfile = open(csv_path, "w")
                existing_csv_data = None
            
            # Collect all measurement names for CSV header
            all_measurements = []
            for table in config.keys():
                for var in config[table].keys():
                    all_measurements.append(var)
            all_measurements.append("burned")
            all_measurements.append("Board PassFail")
            
            # Write CSV header with DaughterBoard IDs and measurement names
            # Use all daughterboard serial numbers from the benchtest, not just processed ones
            all_db_serials = [str(sn) for sn in benchtest_proc[btid]["benchtest_serialnos"] if sn is not None]
            csv_header = ["Measurement"] + all_db_serials
            csvfile.write(",".join(csv_header) + "\n")
            
            # Initialize dictionary to store results for CSV
            csv_results = {var: {} for var in all_measurements}
            for var in all_measurements:
                for db_serial in all_db_serials:
                    csv_results[var][db_serial] = None

        for DBSN, varDict in dbDict.items():
            # Skip if specific daughterboard ID is provided and doesn't match
            if specific_daughterboard_id is not None:
                if DBSN != specific_daughterboard_id:
                    print(f'  Skipping DaughterBoard {DBSN} (not the specified daughterboard)')
                    continue
            
            print(f'\n  For DaughterBoard with Serial No: {DBSN}')
            if logfile:
                logfile.write(f'  DaughterBoard with Serial No: {DBSN}\n')
            if resultsfile:
                resultsfile.write(f'DaughterBoard with Serial No: {DBSN}\n')

            cond_LinkStat = True
            cond_V        = True
            cond_xADC     = True
            cond_other    = True
            burned        = 0

            #\u2705 - Check
            #\u274C - Cross

            for var in config["Link Status"].keys():
                print(f'    Variable {var} has {varDict[var]["nPoints"]} points in total.')
                print(f'    Variable {var} has {varDict[var]["nConsidered"]} points considered for the test.')
                print(f'    Variable {var} has {varDict[var]["nPoints"] - varDict[var]["nConsidered"]} points which correspond to spikes/drops and are therefore not considered for pass rate calculations.')
                print(f'    Variable {var} has {varDict[var]["nPass"]} points within the tolerance boundaries.')

                if logfile:
                    logfile.write(f'    Variable {var} has {varDict[var]["nPoints"]} points in total.\n')
                    logfile.write(f'    Variable {var} has {varDict[var]["nConsidered"]} points considered for the test.\n')
                    logfile.write(f'    Variable {var} has {varDict[var]["nPoints"] - varDict[var]["nConsidered"]} points which correspond to spikes/drops and are therefore not considered for pass rate calculations.\n')
                    logfile.write(f'    Variable {var} has {varDict[var]["nPass"]} points within the tolerance boundaries.\n')

                if varDict[var]["fPass"] == 1.0:
                    print(f'    Link Status variable check passed! {var} has {varDict[var]["fPass"]*100}% of points within the tolerance boundaries.')
                    if logfile:
                        logfile.write(f'    Link Status variable check passed! {var} has {varDict[var]["fPass"]*100}% of points within the tolerance boundaries.\n')
                    if resultsfile:
                        resultsfile.write(f'{var}: 1\n')
                    if csvfile:
                        csv_results[var][str(DBSN)] = 1
                elif varDict[var]["fPass"] < 1.0 and varDict[var]["fPass"] >= 0.0:
                    print(f'    Link Status variable check failed! {var} has {(1-varDict[var]["fPass"])*100}% of points outside of tolerance boundaries.')
                    if logfile:
                        logfile.write(f'    Link Status variable check failed! {var} has {(1-varDict[var]["fPass"])*100}% of points outside of tolerance boundaries.\n')
                    if resultsfile:
                        resultsfile.write(f'{var}: 0\n')
                    if csvfile:
                        csv_results[var][str(DBSN)] = 0
                    cond_LinkStat = False
                elif varDict[var]["fPass"] == -1.0:
                    print(f'    Warning: Data Not Found for Variable {var} in Table Link Status! Tentatively Ignoring Check and "Passing" Board, Please Consult Log.')
                    if logfile:
                        logfile.write(f'    Warning: Data Not Found for Variable {var} in Table Link Status! Tentatively Ignoring Check and "Passing" Board, Please Consult Log.')
                    if resultsfile:
                        resultsfile.write(f'{var}: -1\n')
                    if csvfile:
                        csv_results[var][str(DBSN)] = -1

            for var in config["V"].keys():
                print(f'    Variable {var} has {varDict[var]["nPoints"]} points in total.')
                print(f'    Variable {var} has {varDict[var]["nConsidered"]} points considered for the test.')
                print(f'    Variable {var} has {varDict[var]["nPoints"] - varDict[var]["nConsidered"]} points which correspond to spikes/drops and are therefore not considered for pass rate calculations.')
                print(f'    Variable {var} has {varDict[var]["nPass"]} points within the tolerance boundaries.')

                if logfile:
                    logfile.write(f'    Variable {var} has {varDict[var]["nPoints"]} points in total.\n')
                    logfile.write(f'    Variable {var} has {varDict[var]["nConsidered"]} points considered for the test.\n')
                    logfile.write(f'    Variable {var} has {varDict[var]["nPoints"] - varDict[var]["nConsidered"]} points which correspond to spikes/drops and are therefore not considered for pass rate calculations.\n')
                    logfile.write(f'    Variable {var} has {varDict[var]["nPass"]} points within the tolerance boundaries.\n')

                if varDict[var]["fPass"] == 1.0:
                    print(f'    V variable check passed! {var} has {varDict[var]["fPass"]*100}% of points within the tolerance boundaries.')
                    if logfile:
                        logfile.write(f'    V variable check passed! {var} has {varDict[var]["fPass"]*100}% of points within the tolerance boundaries.\n')
                    if resultsfile:
                        resultsfile.write(f'{var}: 1\n')
                    if csvfile:
                        csv_results[var][str(DBSN)] = 1
                elif varDict[var]["fPass"] < 1.0 and varDict[var]["fPass"] >= 0.0:
                    print(f'    V variable check failed! {var} has {(1-varDict[var]["fPass"])*100}% of points outside of tolerance boundaries.')
                    if logfile:
                        logfile.write(f'    V variable check failed! {var} has {(1-varDict[var]["fPass"])*100}% of points outside of tolerance boundaries.\n')
                    if resultsfile:
                        resultsfile.write(f'{var}: 0\n')
                    if csvfile:
                        csv_results[var][str(DBSN)] = 0
                    cond_V = False
                elif varDict[var]["fPass"] == -1.0:
                    print(f'    Warning: Data Not Found for Variable {var} in Table V! Tentatively Ignoring Check and "Passing" Board, Please Consult Log.')
                    if logfile:
                        logfile.write(f'    Warning: Data Not Found for Variable {var} in Table V! Tentatively Ignoring Check and "Passing" Board, Please Consult Log.')
                    if resultsfile:
                        resultsfile.write(f'{var}: -1\n')
                    if csvfile:
                        csv_results[var][str(DBSN)] = -1

            for var in config["xADC"].keys():
                print(f'    Variable {var} has {varDict[var]["nPoints"]} points in total.')
                print(f'    Variable {var} has {varDict[var]["nConsidered"]} points considered for the test.')
                print(f'    Variable {var} has {varDict[var]["nPoints"] - varDict[var]["nConsidered"]} points which correspond to spikes/drops and are therefore not considered for pass rate calculations.')
                print(f'    Variable {var} has {varDict[var]["nPass"]} points within the tolerance boundaries.')

                if logfile:
                    logfile.write(f'    Variable {var} has {varDict[var]["nPoints"]} points in total.\n')
                    logfile.write(f'    Variable {var} has {varDict[var]["nConsidered"]} points considered for the test.\n')
                    logfile.write(f'    Variable {var} has {varDict[var]["nPoints"] - varDict[var]["nConsidered"]} points which correspond to spikes/drops and are therefore not considered for pass rate calculations.\n')
                    logfile.write(f'    Variable {var} has {varDict[var]["nPass"]} points within the tolerance boundaries.\n')

                if varDict[var]["fPass"] >= 0.95:
                    print(f'    xADC variable check passed! {var} has {varDict[var]["fPass"]*100}% of points within the tolerance boundaries.')
                    if logfile:
                        logfile.write(f'    xADC variable check passed! {var} has {varDict[var]["fPass"]*100}% of points within the tolerance boundaries.\n')
                    if resultsfile:
                        resultsfile.write(f'{var}: 1\n')
                    if csvfile:
                        csv_results[var][str(DBSN)] = 1
                elif varDict[var]["fPass"] < 0.95 and varDict[var]["fPass"] >= 0.0:
                    print(f'    xADC variable check failed! {var} has {(1-varDict[var]["fPass"])*100}% of points outside of tolerance boundaries.')
                    if logfile:
                        logfile.write(f'    xADC variable check failed! {var} has {(1-varDict[var]["fPass"])*100}% of points outside of tolerance boundaries.\n')
                    if resultsfile:
                        resultsfile.write(f'{var}: 0\n')
                    if csvfile:
                        csv_results[var][str(DBSN)] = 0
                    cond_xADC = False
                elif varDict[var]["fPass"] == -1.0:
                    print(f'    Warning: Data Not Found for Variable {var} in Table xADC! Tentatively Ignoring Check and "Passing" Board, Please Consult Log.')
                    if logfile:
                        logfile.write(f'    Warning: Data Not Found for Variable {var} in Table xADC! Tentatively Ignoring Check and "Passing" Board, Please Consult Log.')
                    if resultsfile:
                        resultsfile.write(f'{var}: -1\n')
                    if csvfile:
                        csv_results[var][str(DBSN)] = -1

            rem_tables = [x for x in config.keys() if x not in ["Link Status", "V", "xADC"]]
            print(f'  Remaining Tables: {rem_tables}')

            for table in rem_tables:
                print(f'    Table: {table}')

                for var in config[table].keys():
                    print(f'    Variable {var} has {varDict[var]["nPoints"]} points in total.')
                    print(f'    Variable {var} has {varDict[var]["nConsidered"]} points considered for the test.')
                    print(f'    Variable {var} has {varDict[var]["nPoints"] - varDict[var]["nConsidered"]} points which correspond to spikes/drops and are therefore not considered for pass rate calculations.')
                    print(f'    Variable {var} has {varDict[var]["nPass"]} points within the tolerance boundaries.')

                    if logfile:
                        logfile.write(f'    Variable {var} has {varDict[var]["nPoints"]} points in total.\n')
                        logfile.write(f'    Variable {var} has {varDict[var]["nConsidered"]} points considered for the test.\n')
                        logfile.write(f'    Variable {var} has {varDict[var]["nPoints"] - varDict[var]["nConsidered"]} points which correspond to spikes/drops and are therefore not considered for pass rate calculations.\n')
                        logfile.write(f'    Variable {var} has {varDict[var]["nPass"]} points within the tolerance boundaries.\n')

                    if varDict[var]["fPass"] >= 0.98:
                        print(f'    Variable check passed! {var} has {varDict[var]["fPass"]*100}% of points within the tolerance boundaries.')
                        if logfile:
                            logfile.write(f'    Variable check passed! {var} has {varDict[var]["fPass"]*100}% of points within the tolerance boundaries.\n')
                        if resultsfile:
                            resultsfile.write(f'{var}: 1\n')
                        if csvfile:
                            csv_results[var][str(DBSN)] = 1
                    elif varDict[var]["fPass"] < 0.98 and varDict[var]["fPass"] >= 0.0:
                        print(f'    Variable check failed! {var} has {(1-varDict[var]["fPass"])*100}% of points outside of tolerance boundaries.')
                        if logfile:
                            logfile.write(f'    Variable check failed! {var} has {(1-varDict[var]["fPass"])*100}% of points outside of tolerance boundaries.\n')
                        if resultsfile:
                            resultsfile.write(f'{var}: 0\n')
                        if csvfile:
                            csv_results[var][str(DBSN)] = 0
                        cond_other = False
                    elif varDict[var]["fPass"] == -1.0:
                        print(f'    Warning: Data Not Found for Variable {var} in Table {table}! Tentatively Ignoring Check and "Passing" Board, Please Consult Log.')
                        if logfile:
                            logfile.write(f'    Warning: Data Not Found for Variable {var} in Table {table}! Tentatively Ignoring Check and "Passing" Board, Please Consult Log.')
                        if resultsfile:
                            resultsfile.write(f'{var}: -1\n')
                        if csvfile:
                            csv_results[var][str(DBSN)] = -1

            # Burn-in test: Check if daughterboard burn_in_stop is after benchtest test_stop
            print(f'    Checking burn-in status for DaughterBoard {DBSN}')
            if logfile:
                logfile.write(f'    Checking burn-in status for DaughterBoard {DBSN}\n')
            
            # Query daughterboard table for burn_in_stop
            tiledb_burnin_query = f"SELECT burn_in_stop FROM daughterboard WHERE serial_no = {DBSN}"
            cursor.execute(tiledb_burnin_query)
            burnin_result = cursor.fetchone()
            
            if burnin_result and burnin_result[0] is not None:
                burn_in_stop = burnin_result[0]
                # Get benchtest stop time from benchtest_proc
                test_stop = datetime.strptime(benchtest_proc[btid]["benchtest_timestamp"][1], "%Y-%m-%dT%H:%M:%SZ")
                
                print(f'    burn_in_stop: {burn_in_stop}')
                print(f'    test_stop: {test_stop}')
                
                if logfile:
                    logfile.write(f'    burn_in_stop: {burn_in_stop}\n')
                    logfile.write(f'    test_stop: {test_stop}\n')
                
                # Compare timestamps
                if burn_in_stop > test_stop:
                    burned = 1
                    print(f'    Burn-in check passed: DaughterBoard has been burned-in (burn_in_stop > test_stop)')
                    if logfile:
                        logfile.write(f'    Burn-in check passed: DaughterBoard has been burned-in (burn_in_stop > test_stop)\n')
                    if resultsfile:
                        resultsfile.write(f'burned: 1\n')
                    if csvfile:
                        csv_results["burned"][str(DBSN)] = 1
                else:
                    burned = 0
                    print(f'    Burn-in check failed: DaughterBoard has not been burned-in (burn_in_stop <= test_stop)')
                    if logfile:
                        logfile.write(f'    Burn-in check failed: DaughterBoard has not been burned-in (burn_in_stop <= test_stop)\n')
                    if resultsfile:
                        resultsfile.write(f'burned: 0\n')
                    if csvfile:
                        csv_results["burned"][str(DBSN)] = 0
            else:
                burned = -1
                print(f'    Warning: burn_in_stop data not found for DaughterBoard {DBSN}')
                if logfile:
                    logfile.write(f'    Warning: burn_in_stop data not found for DaughterBoard {DBSN}\n')
                if resultsfile:
                    resultsfile.write(f'burned: -1\n')
                if csvfile:
                    csv_results["burned"][str(DBSN)] = -1

            if cond_LinkStat and cond_V and cond_xADC and cond_other:
                statDict[btid][DBSN]["Board PassFail"] = 1
                print(f'  Final Verdict: DaughterBoard with Serial No# {DBSN} has PASSED the benchtest.\n\n')
                if logfile:
                    logfile.write(f'  Final Verdict: DaughterBoard with Serial No# {DBSN} has PASSED the benchtest.\n\n')
                if resultsfile:
                    resultsfile.write(f'Board PassFail: 1\n')
                if csvfile:
                    csv_results["Board PassFail"][str(DBSN)] = 1
            else:
                statDict[btid][DBSN]["Board PassFail"] = 0
                print(f'  Final Verdict: DaughterBoard with Serial No# {DBSN} has FAILED the benchtest.\n\n')
                if logfile:
                    logfile.write(f'  Final Verdict: DaughterBoard with Serial No# {DBSN} has FAILED the benchtest.\n\n')
                if resultsfile:
                    resultsfile.write(f'Board PassFail: 0\n')
                if csvfile:
                    csv_results["Board PassFail"][str(DBSN)] = 0

            # Update daughterboard table (skip if test_pass is -1, or plots-only recreate)
            if skip_db_status_update:
                print(
                    f'  Skipping db_status update for DaughterBoard {DBSN} '
                    f'(--recreate-plots-only / skip_db_status_update)'
                )
            elif benchtest_proc[btid]["benchtest_pass"] != -1:
                tiledb_dbupdatequery = "UPDATE daughterboard SET db_status = '" + str(statDict[btid][DBSN]["Board PassFail"]) + "' WHERE serial_no = " + str(DBSN)
                print(f'daughterboard update query: {tiledb_dbupdatequery}')
                cursor.execute(tiledb_dbupdatequery)
            else:
                print(f'  Skipping db_status update for benchtest {btid} due to test_pass = -1')

        # Close files if they were opened
        if logfile:
            logfile.close()
        if resultsfile:
            resultsfile.close()
        if csvfile:
            # Write CSV data rows
            for var in all_measurements:
                if specific_daughterboard_id is not None and existing_csv_data is not None:
                    # Preserve existing data for other daughterboards, only update specific one
                    if var in existing_csv_data:
                        existing_row = existing_csv_data[var]
                        # Rebuild row to match current all_db_serials structure
                        row = [var]
                        for db_serial in all_db_serials:
                            if db_serial == str(specific_daughterboard_id):
                                # Update the specific daughterboard's value
                                row.append(str(csv_results[var][db_serial]) if csv_results[var][db_serial] is not None else "")
                            elif len(existing_row) > all_db_serials.index(db_serial):
                                # Preserve existing value if available
                                row.append(existing_row[all_db_serials.index(db_serial)])
                            else:
                                # Fill with empty string if no existing data
                                row.append("")
                    else:
                        # New measurement, write new row
                        row = [var] + [str(csv_results[var][db_serial]) if csv_results[var][db_serial] is not None else "" for db_serial in all_db_serials]
                else:
                    # Normal write all data
                    row = [var] + [str(csv_results[var][db_serial]) if csv_results[var][db_serial] is not None else "" for db_serial in all_db_serials]
                csvfile.write(",".join(row) + "\n")
            csvfile.close()

        write_timing_row(
            timing_session,
            'results_output', time.perf_counter() - _t_results,
            benchtest_id=btid, detail='logs_csv_mariadb_updates', progress=timing_progress,
            )

    print(f'statDict = {statDict}')

### ######### ###
### Executing ###
### ######### ###

# Load Config
config  = load_yaml_conf("vars.yaml")
secrets = load_yaml_conf("../secrets/secrets.yaml")
try:
    from dbq_plot_config import (
        load_dbq_plot_config,
        px_line_labels,
        style_dbq_figure,
        write_html_options,
    )
    dbq_plot_style = load_dbq_plot_config()
except Exception as exc:
    print(f'Warning: DBQ plot style config unavailable ({exc}); using built-in defaults.')
    dbq_plot_style = None

    def px_line_labels(_style, ivar, dimensions=None):
        from vars_config import format_y_axis_label
        return {"x": "Time", "y": format_y_axis_label(ivar, dimensions), "channel": "Uplink Channel"}

    def style_dbq_figure(fig, _style=None, **_kwargs):
        return fig

    def write_html_options(_style=None):
        return {}

try:
    from dbq_measurement_stats import (
        apply_plot_legend_stats,
        build_variable_stats_payload,
        compute_y_stats,
        write_board_statistics_yaml,
    )
except Exception as exc:
    print(f'Warning: DBQ measurement stats unavailable ({exc}); legend/stats YAML disabled.')

    def apply_plot_legend_stats(fig, *_args, **_kwargs):
        return fig

    def build_variable_stats_payload(*_args, **_kwargs):
        return {}

    def compute_y_stats(_y):
        return None

    def write_board_statistics_yaml(*_args, **_kwargs):
        return None

# Setup argparse for regeneration options
parser = argparse.ArgumentParser(description='DaughterBoard Qualification Program')
parser.add_argument('-r', '--regenerate', type=str, choices=['benchtest_id_results_log', 'benchtest_id_log', 'plots', 'statistics', 'all'],
                    help='Force regeneration: benchtest_id_results_log, benchtest_id_log, plots, statistics, or all')
parser.add_argument('-b', '--benchtest_id', type=str,
                    help='Specific benchtest ID or range (e.g., "1" or "2-5") to regenerate (if not specified, processes all in regeneration mode)')
parser.add_argument('-d', '--daughterboard_id', type=str,
                    help='Specific daughterboard ID to analyze (if not specified, processes all daughterboards in the benchtest)')
parser.add_argument('--timing', action='store_true',
                    help='Write per-step CSV timing logs under "<script>/timing logs/" '
                         '(filename Timing_<timestamp>_BT<id>.csv)')
parser.add_argument(
    '--recreate-plots-only',
    action='store_true',
    help=(
        'Regenerate plots (same as -r plots) but do not update daughterboard '
        'db_status in MariaDB'
    ),
)
args = parser.parse_args()

# Parse benchtest_id parameter
specific_benchtest_ids = None
if args.benchtest_id:
    if '-' in args.benchtest_id:
        # Range format: x-y
        try:
            start, end = map(int, args.benchtest_id.split('-'))
            specific_benchtest_ids = list(range(start, end + 1))
        except ValueError:
            print(f'Error: Invalid range format "{args.benchtest_id}". Use format "x-y" (e.g., "2-5")')
            exit(1)
    else:
        # Single ID
        try:
            specific_benchtest_ids = [int(args.benchtest_id)]
        except ValueError:
            print(f'Error: Invalid benchtest ID "{args.benchtest_id}". Must be a number or range (e.g., "1" or "2-5")')
            exit(1)

# Parse daughterboard_id parameter
specific_daughterboard_id = None
if args.daughterboard_id:
    try:
        specific_daughterboard_id = int(args.daughterboard_id)
    except ValueError:
        print(f'Error: Invalid daughterboard ID "{args.daughterboard_id}". Must be a number.')
        exit(1)

# Debug Code: Config Dictionary
DEBUG_CONFIG = True

if DEBUG_CONFIG:
    print(f"config: {config}")
    #print(type(config))
    print(f"config.keys(): {config.keys()}")
    print(f"config.values(): {config.values()}\n")
    print(config.items())
    for i in config.keys():
        print(f'  i = {i}')
        #print(f'  type(i) = {type(i)}')
        print(f"  config[{i}] = {config[i]}")

        for j in config[i].keys():
            print(f'    j = {j}')
            #print(f'    type(j) = {type(j)}')
            print(f'    config[{i}][{j}] = {config[i][j]}')

            thresholds = get_var_thresholds(config[i][j])
            for k, val in enumerate(thresholds):
                print(f'      k = {k}')
                #print(f'      type(k) = {type(k)}')
                print(f'      thresholds[{k}] = {val}')
            print(f'      caption = {get_var_caption(config[i][j], default_name=j)}')
            print(f'      dimensions = {get_var_dimensions(config[i][j])}')

    print("\n")

# Debug Code: Secrets Dictionary
DEBUG_SECRETS = True

if DEBUG_SECRETS:
    print(f"secrets: {secrets}")
    print(f"secrets.keys(): {secrets.keys()}")
    print(f"secrets.values(): {secrets.values()}")



# Execute main()
regenerate_mode = args.regenerate
skip_db_status_update = bool(args.recreate_plots_only)
if args.recreate_plots_only:
    # Plots recreate without touching daughterboard db_status.
    if regenerate_mode is None:
        regenerate_mode = 'plots'
    elif regenerate_mode != 'plots':
        print(
            f'Note: --recreate-plots-only forces plot regeneration; '
            f'overriding -r/--regenerate={regenerate_mode!r} → plots'
        )
        regenerate_mode = 'plots'
    print('Mode: --recreate-plots-only (plots on, db_status updates off)')

try:
    DBQ_Mk6(
        regenerate_mode=regenerate_mode,
        specific_benchtest_ids=specific_benchtest_ids,
        specific_daughterboard_id=specific_daughterboard_id,
        enable_timing=bool(args.timing),
        skip_db_status_update=skip_db_status_update,
    )
except KeyboardInterrupt:
    print('Interrupted (Ctrl+C). Timing log has been updated with a break row if --timing was set.')
    sys.exit(130)
