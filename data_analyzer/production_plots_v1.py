### ################################### ###
### Production Plots for DaughterBoard ###
### Version 1.0.0 ###
### ################################### ###

### ############### ###
### Package Imports ###
### ############### ###

# Basic Packages
from datetime import datetime, timedelta
import math
from pathlib import Path
import shutil

# Mathematics Packages
import numpy as np
import pandas as pd

# Server Packages
import yaml

# MySQL for MariaDB
import mysql.connector
from mysql.connector import Error

# InfluxDBClient for InfluxDB
from influxdb import InfluxDBClient

# Import plotting libraries
from production_overview_plots import create_production_overview_plot, save_production_overview_with_modal
from summary_dashboard_plots import create_summary_dashboard
from batch_distribution_plots import create_batch_distribution_dashboard

### ######### ###
### Functions ###
### ######### ###

# Load configuration data from .yaml file
def load_yaml_conf(filepath):
    with open(filepath, "r") as file:
        return yaml.safe_load(file)

# Function to print tree structure
def print_tree(level, name, is_last):
    prefix = "└── " if is_last else "├── "
    print(" " * (level * 4) + prefix + name)


# Function to backup existing plots to old subfolder with timestamp
def backup_old_plots(output_dir):
    output_path = Path(output_dir)
    old_dir = output_path / "old"
    old_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    # List of plot files to backup
    plot_files = [
        "production_overview.html",
        "lot_quality_analysis.html",
        "production_timeline.html",
        "summary_dashboard.html"
    ]
    
    for plot_file in plot_files:
        source_file = output_path / plot_file
        if source_file.exists():
            # Create backup filename with timestamp prefix
            backup_file = old_dir / f"{timestamp}_{plot_file}"
            shutil.copy2(source_file, backup_file)
            print(f"Backed up: {plot_file} -> {backup_file.name}")


# ---------------------------------------------------------
# Decode Serial Number
#
# Format: TTBBDDD
#   TT  = Tag
#   BB  = Batch
#   DDD = Position inside batch
#
# Example: 1102020
#   11 -> tag
#   02 -> batch
#   020 -> position
# ---------------------------------------------------------
def decode_serial(serial):
    serial = str(serial).zfill(7)
    return {
        "tag": int(serial[:2]),
        "batch": int(serial[2:4]),
        "position": int(serial[4:7])
    }


# Function to read benchtest CSV and extract failed tests for a serial number
def get_failed_tests_for_serial(serial, benchtest_id, drive_dir="/var/www/html/drive/benchtests/"):
    """
    Read benchtest CSV file and extract failed tests for a specific serial number.
    Handles CSV files that may contain multiple boards in columns.
    
    Args:
        serial: Serial number of the board
        benchtest_id: Benchtest ID in format "dbslotX@bt_Y" (e.g., "dbslot1@bt_9")
        drive_dir: Directory containing benchtest folders
        
    Returns:
        list: List of failed test names, or None if file not found or no failures
    """
    # Extract benchtest number from format "dbslotX@bt_Y"
    # Example: "dbslot1@bt_9" -> extract "9"
    import re
    match = re.search(r'bt_(\d+)', benchtest_id)
    if not match:
        return None
    
    bt_num = match.group(1)
    benchtest_folder = f"benchtest_id_{bt_num}"
    csv_file = Path(drive_dir) / benchtest_folder / f"{benchtest_folder}_results.csv"
    
    if not csv_file.exists():
        return None
    
    try:
        with open(csv_file, 'r') as f:
            lines = f.readlines()
        
        # First line contains header with serial numbers
        # Format: "Measurement,9000001" or "Measurement,1101030,1101035"
        header = lines[0].strip().split(',')
        if len(header) < 2:
            return None
        
        # Find the column index for the requested serial number
        serial_str = str(serial)
        serial_index = None
        for i, col in enumerate(header[1:], start=1):  # Skip "Measurement" column
            if str(col) == serial_str:
                serial_index = i
                break
        
        if serial_index is None:
            # Serial not found in this CSV file
            return None
        
        # Parse measurements and find failed tests (value = 0) for this specific serial
        failed_tests = []
        for line in lines[1:]:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            parts = line.split(',')
            if len(parts) > serial_index:
                measurement = parts[0]
                value = parts[serial_index].strip()
                
                # Value 0 indicates failure
                if value == '0':
                    # Filter out unwanted test names
                    if measurement not in ['burned', 'Board PassFail']:
                        failed_tests.append(measurement)
        
        return failed_tests if failed_tests else None
        
    except Exception as e:
        print(f"Error reading CSV file {csv_file}: {e}")
        return None


# Function to read burned status from benchtest results log file
def get_burned_status(serial, benchtest_id, drive_dir="/var/www/html/drive/benchtests/"):
    """
    Read benchtest results log file and extract burned status for a specific serial number.
    
    Args:
        serial: Serial number of the board
        benchtest_id: Benchtest ID in format "dbslotX@bt_Y" (e.g., "dbslot1@bt_9")
        drive_dir: Directory containing benchtest folders
        
    Returns:
        str: "burned" if value is 1, "not burned" if value is 0 or -1, None if not found
    """
    # Extract benchtest number from format "dbslotX@bt_Y"
    import re
    match = re.search(r'bt_(\d+)', benchtest_id)
    if not match:
        return None
    
    bt_num = match.group(1)
    benchtest_folder = f"benchtest_id_{bt_num}"
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
                return "burned"
            elif burned_value in ['0', '-1']:
                return "not burned"
        
        return None
        
    except Exception as e:
        print(f"Error reading log file {log_file}: {e}")
        return None


### ######### ###
### Main Function ###
### ######### ###

def production_plots():
    
    timenow = datetime.now()
    print(f'Current Date/Time: {timenow}')
    
    # Define output directory
    output_dir = "/var/www/html/drive/production_plots/"
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Backup existing plots before generating new ones
    print("\n==================== Backing Up Old Plots ====================")
    backup_old_plots(output_dir)
    
    ### ####### ###
    ### MariaDB ###
    ### ####### ###
    try:
        print("\n==================== MariaDB Connection ====================")
        print(f"🔗 Connecting to MariaDB at {secrets['tiledb-mariadb']['host']}...")
        connection = mysql.connector.connect(
            host=secrets["tiledb-mariadb"]["host"],
            user=secrets["tiledb-mariadb"]["user"],
            password=secrets["tiledb-mariadb"]["password"],
            autocommit=True
        )

        if connection.is_connected():
            print("✅ Connected to MariaDB!")
            cursor = connection.cursor()

        # Setting Timezone to UTC
        cursor.execute("SET time_zone = '+00:00'")

        # Select tiledb database
        cursor.execute("USE tiledb")
        
        # Query all daughterboard data with batch information
        print("\nFetching daughterboard data...")
        db_query = """
            SELECT d.serial_no, d.batch_id, d.db_status, d.burn_in,
                   d.burn_in_start, d.burn_in_stop,
                   d.kin_lot, d.pro_lot, d.gbt_lot,
                   d.ina_lot, d.ltm_lot, d.mos_lot, d.op4_lot, d.ok4_lot, d.ok1_lot,
                   d.mem_lot, d.sfp_lot, d.e_test, d.p_test, d.a0, d.a1, d.b0, d.b1
            FROM daughterboard d
            ORDER BY d.batch_id, d.serial_no
        """
        cursor.execute(db_query)
        db_rows = cursor.fetchall()
        db_columns = [desc[0] for desc in cursor.description]
        
        print(f"Retrieved {len(db_rows)} daughterboard records")
        
        # Convert to DataFrame
        df_daughterboards = pd.DataFrame(db_rows, columns=db_columns)
        print(f"Unique boards: {len(df_daughterboards)}")
        
        # Fetch benchtest information for each daughterboard
        print("Fetching benchtest information...")
        benchtest_query = """
            SELECT id, db_slot1, db_slot2, db_slot3, db_slot4,
                   test_stop, test_op, test_pass
            FROM benchtest
            WHERE (db_slot1 IS NOT NULL OR db_slot2 IS NOT NULL 
               OR db_slot3 IS NOT NULL OR db_slot4 IS NOT NULL)
               AND test_pass != -1
        """
        cursor.execute(benchtest_query)
        benchtest_rows = cursor.fetchall()
        benchtest_columns = [desc[0] for desc in cursor.description]
        df_benchtests = pd.DataFrame(benchtest_rows, columns=benchtest_columns)
        
        # Fetch ignored benchtests (test_pass = -1) separately
        print("Fetching ignored benchtest information...")
        ignored_benchtest_query = """
            SELECT id, db_slot1, db_slot2, db_slot3, db_slot4,
                   test_stop, test_op
            FROM benchtest
            WHERE (db_slot1 IS NOT NULL OR db_slot2 IS NOT NULL 
               OR db_slot3 IS NOT NULL OR db_slot4 IS NOT NULL)
               AND test_pass = -1
        """
        cursor.execute(ignored_benchtest_query)
        ignored_benchtest_rows = cursor.fetchall()
        ignored_benchtest_columns = [desc[0] for desc in cursor.description]
        df_ignored_benchtests = pd.DataFrame(ignored_benchtest_rows, columns=ignored_benchtest_columns)
        
        # Build mapping from serial_no to list of (dbslot@benchtest_id, test_stop, test_op)
        serial_to_benchtests = {}
        serial_to_benchtest_test_stop = {}  # Maps serial to dict of benchtest_id -> test_stop
        serial_to_benchtest_test_op = {}  # Maps serial to dict of benchtest_id -> test_op
        for _, row in df_benchtests.iterrows():
            bt_id = int(row['id'])
            test_stop = row['test_stop']
            test_op = row['test_op']
            for slot_num in range(1, 5):
                slot_col = f'db_slot{slot_num}'
                serial = row[slot_col]
                if pd.notna(serial):
                    if serial not in serial_to_benchtests:
                        serial_to_benchtests[serial] = []
                        serial_to_benchtest_test_stop[serial] = {}
                        serial_to_benchtest_test_op[serial] = {}
                    benchtest_slot = f'dbslot{slot_num}@bt_{bt_id}'
                    serial_to_benchtests[serial].append(benchtest_slot)
                    # Store test_stop timestamp for this specific benchtest
                    if pd.notna(test_stop):
                        serial_to_benchtest_test_stop[serial][benchtest_slot] = test_stop
                    # Store test_op for this specific benchtest
                    if pd.notna(test_op):
                        serial_to_benchtest_test_op[serial][benchtest_slot] = test_op
        
        # Build mapping for ignored benchtests (test_pass = -1)
        serial_to_ignored_benchtests = {}
        serial_to_ignored_benchtest_test_stop = {}
        serial_to_ignored_benchtest_test_op = {}
        for _, row in df_ignored_benchtests.iterrows():
            bt_id = int(row['id'])
            test_stop = row['test_stop']
            test_op = row['test_op']
            for slot_num in range(1, 5):
                slot_col = f'db_slot{slot_num}'
                serial = row[slot_col]
                if pd.notna(serial):
                    if serial not in serial_to_ignored_benchtests:
                        serial_to_ignored_benchtests[serial] = []
                        serial_to_ignored_benchtest_test_stop[serial] = {}
                        serial_to_ignored_benchtest_test_op[serial] = {}
                    benchtest_slot = f'dbslot{slot_num}@bt_{bt_id}'
                    serial_to_ignored_benchtests[serial].append(benchtest_slot)
                    if pd.notna(test_stop):
                        serial_to_ignored_benchtest_test_stop[serial][benchtest_slot] = test_stop
                    if pd.notna(test_op):
                        serial_to_ignored_benchtest_test_op[serial][benchtest_slot] = test_op
        
        # Sort benchtest slots chronologically by test_stop for each serial
        for serial in serial_to_benchtests:
            if serial in serial_to_benchtest_test_stop:
                # Sort by test_stop timestamp, using benchtest ID as tiebreaker
                serial_to_benchtests[serial].sort(key=lambda x: (
                    serial_to_benchtest_test_stop[serial].get(x, pd.Timestamp.min),
                    x  # Use benchtest slot string as tiebreaker
                ))
        
        # Sort ignored benchtest slots chronologically by test_stop for each serial
        for serial in serial_to_ignored_benchtests:
            if serial in serial_to_ignored_benchtest_test_stop:
                serial_to_ignored_benchtests[serial].sort(key=lambda x: (
                    serial_to_ignored_benchtest_test_stop[serial].get(x, pd.Timestamp.min),
                    x
                ))
        
        print(f"Found benchtest info for {len(serial_to_benchtests)} boards")
        print(f"Found ignored benchtest info for {len(serial_to_ignored_benchtests)} boards")
        
        # Determine which boards have post-burn-in tests
        serial_to_has_post_burnin_test = {}
        for serial in serial_to_benchtests:
            if serial in df_daughterboards.set_index('serial_no')['burn_in_stop'].index:
                burn_in_stop = df_daughterboards.set_index('serial_no').loc[serial, 'burn_in_stop']
                if pd.notna(burn_in_stop):
                    # Check if any benchtest for this serial has test_stop after burn_in_stop
                    has_post_burnin = False
                    if serial in serial_to_benchtest_test_stop:
                        for benchtest_slot, test_stop in serial_to_benchtest_test_stop[serial].items():
                            if pd.notna(test_stop) and test_stop > burn_in_stop:
                                has_post_burnin = True
                                break
                    serial_to_has_post_burnin_test[serial] = has_post_burnin
                else:
                    serial_to_has_post_burnin_test[serial] = False
            else:
                serial_to_has_post_burnin_test[serial] = False
        
        # Decode serial numbers to get tag, batch, and position
        decoded = df_daughterboards['serial_no'].apply(decode_serial)
        df_daughterboards['tag'] = decoded.apply(lambda x: x['tag'])
        df_daughterboards['decoded_batch'] = decoded.apply(lambda x: x['batch'])
        df_daughterboards['position_in_batch'] = decoded.apply(lambda x: x['position'])
        
        # Add test_stop timestamp from benchtest data (use the latest test_stop for each serial)
        serial_to_latest_test_stop = {}
        for serial, test_stops in serial_to_benchtest_test_stop.items():
            if test_stops:
                # Get the latest test_stop timestamp
                latest_test_stop = max(test_stops.values())
                serial_to_latest_test_stop[serial] = latest_test_stop
        df_daughterboards['test_stop'] = df_daughterboards['serial_no'].map(serial_to_latest_test_stop)
        
        # Filter out tags to ignore (currently only tag 90)
        tags_to_ignore = [90]
        df_daughterboards = df_daughterboards[~df_daughterboards['tag'].isin(tags_to_ignore)]
        print(f"After filtering tags {tags_to_ignore}: {len(df_daughterboards)} boards")
        
        # Sort by decoded batch and position
        df_daughterboards = df_daughterboards.sort_values(['decoded_batch', 'position_in_batch']).reset_index(drop=True)
        
        # Get batch information
        batch_query = """
            SELECT batch_id, COUNT(*) as board_count,
                   SUM(CASE WHEN db_status = 1 THEN 1 ELSE 0 END) as passed_count,
                   SUM(CASE WHEN db_status = 0 THEN 1 ELSE 0 END) as failed_count
            FROM daughterboard
            GROUP BY batch_id
            ORDER BY batch_id
        """
        cursor.execute(batch_query)
        batch_rows = cursor.fetchall()
        batch_columns = [desc[0] for desc in cursor.description]
        df_batches = pd.DataFrame(batch_rows, columns=batch_columns)
        
        # Convert numeric columns to proper types
        df_batches['board_count'] = pd.to_numeric(df_batches['board_count'])
        df_batches['passed_count'] = pd.to_numeric(df_batches['passed_count'])
        df_batches['failed_count'] = pd.to_numeric(df_batches['failed_count'])
        
        print(f"Found {len(df_batches)} batches")
        print(df_batches)
        
    except Error as e:
        print(f"❌ MariaDB Connection Failed: {e}")
        return

    ### ######## ###
    ### InfluxDB ###
    ### ######## ###
    
    influx_data = {}
    try:
        print("\n==================== InfluxDB Connection ====================")
        print(f"🔗 Connecting to InfluxDB at {secrets['tiledb-influxdb']['host']}:{secrets['tiledb-influxdb']['port']}...")
        client = InfluxDBClient(
            host=secrets["tiledb-influxdb"]["host"],
            port=secrets["tiledb-influxdb"]["port"],
            username=secrets["tiledb-influxdb"]["username"],
            password=secrets["tiledb-influxdb"]["password"]
        )
        client.ping()
        print("✅ Connected to InfluxDB!")
        
        client.switch_database("tiledb")
        
        # Define InfluxDB Tables
        VarTables = ["Link Status", "xADC", "ADC_Linearity", "CIS_Linearity", "CIS", "Integrator_Linearity"]
        TagTables = ["V"]
        
    except Exception as e:
        print(f"❌ InfluxDB Connection Failed: {e}")
        return

    ### ################# ###
    ### Production Plots ###
    ### ################# ###
    
    print("\n==================== Generating Production Plots ====================")
    
    # 1. Production Overview Plot (Individual Boards)
    print("Generating production overview plot...")
    fig_production_overview = create_production_overview_plot(
        df_daughterboards, 
        serial_to_benchtests, 
        timenow, 
        get_failed_tests_func=get_failed_tests_for_serial,
        serial_to_benchtest_test_stop=serial_to_benchtest_test_stop,
        serial_to_benchtest_test_op=serial_to_benchtest_test_op,
        serial_to_has_post_burnin_test=serial_to_has_post_burnin_test,
        serial_to_ignored_benchtests=serial_to_ignored_benchtests,
        serial_to_ignored_benchtest_test_stop=serial_to_ignored_benchtest_test_stop,
        serial_to_ignored_benchtest_test_op=serial_to_ignored_benchtest_test_op
    )
    save_production_overview_with_modal(fig_production_overview, output_dir)
    print("✅ Production overview plot saved with click-to-modal feature")
    
    # 2. Summary Dashboard
    print("Generating summary dashboard...")
    fig_summary = create_summary_dashboard(df_daughterboards, timenow, serial_to_benchtests=serial_to_benchtests)
    fig_summary.write_html(output_dir + "summary_dashboard.html")
    print("✅ Summary dashboard saved")
    
    # 3. Batch Distribution Dashboard
    print("Generating batch distribution dashboard...")
    fig_batch_dist = create_batch_distribution_dashboard(df_daughterboards, timenow)
    fig_batch_dist.write_html(output_dir + "batch_distribution.html")
    print("✅ Batch distribution dashboard saved")
    
    # Close connections
    cursor.close()
    connection.close()
    client.close()
    
    print(f"\n==================== Production Plots Complete ====================")
    print(f"All plots saved to: {output_dir}")
    print(f"Generated plots:")
    print(f"  - production_overview.html")
    print(f"  - summary_dashboard.html")
    print(f"  - batch_distribution.html")


### ######### ###
### Executing ###
### ######### ###

# Load Config
config = load_yaml_conf("vars.yaml")
secrets = load_yaml_conf("../secrets/secrets.yaml")

# Execute main()
if __name__ == "__main__":
    production_plots()
