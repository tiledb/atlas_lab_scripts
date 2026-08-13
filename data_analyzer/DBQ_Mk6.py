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

# Mathematics Packages
import numpy as np
import pandas as pd

# Plotting Packages (plotly)
import plotly.express as plotlyEX

# Server Packages
from ruamel.yaml import YAML

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



# Main
def DBQ_Mk6(regenerate_mode=None, specific_benchtest_ids=None, specific_daughterboard_id=None):

    timenow = datetime.now()
    print(f'Current Date/Time: {timenow}')
    
    ### ####### ###
    ### MariaDB ###
    ### ####### ###
    # We connect to MariaDB and read the relevant data from the daughterboard and benchtest tables
    try:
        ### Connect to MariaDB ###
        print("\n==================== MariaDB Tree ====================")
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

    except Error as e:
        print("\u274C MariaDB Connection Failed")



    ### ######## ###
    ### InfluxDB ###
    ### ######## ###

    ### Comments for InfluxDB
    ### The benchtest_proc dictionary is completely general, but the "benchtest_pass" parameter isn't clear
    ### Likewise, the use of the "benchtest_id" parameter is clear either. It's just a number, but if we're going to loop over it, it has to correspond to something (maybe a direcory name?)
    ### Add output flags for each benchtest_id that needs to be processed
    ### Likewise, add flags for which MDs are filled
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

        # Define Query Output Storage Dictionary
        queryResults = {}
        #print(f'queryResults = {queryResults}')

        # Define plot regeneration tracking
        plot_regenerate = {}
        #print(f'plot_regenerate = {plot_regenerate}')

        # Define Data Array
        dataDict = {}

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
            elif regenerate_mode == 'benchtest_id_results_log' or regenerate_mode == 'plots':
                # Skip writing benchtest_id.log if only regenerating results or plots
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

            # Set plot regeneration flag for this benchtest
            if regenerate_mode == 'benchtest_id_log' or regenerate_mode == 'benchtest_id_results_log':
                plot_regenerate[benchtest_id] = False
            elif regenerate_mode == 'plots' or regenerate_mode == 'all':
                plot_regenerate[benchtest_id] = True
            else:
                plot_regenerate[benchtest_id] = True

            # Table Loop
            for table in config.keys():
                print("----------------------------")
                print(f'Table: {table}')

                # InfluxDB Query Construction
                # Query used to download data from InfluxDB changes depending on which table is considered
                # Handling Variable based queries
                if table in VarTables:
                    print(f'{table} is in VarTables')

                    # Define DaughterBoards
                    querystr_channels = ''
                    my_channels = []

                    # Loop over present DaughterBoards
                    for MDi in range(0,4):
                        if benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi] != None:
                            print(f'Mini-Drawer {MDi+1} contains DaughterBoard with Serial Number: {benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}')
                            querystr_channels = querystr_channels + '"PprGTH MD' + str(MDi+1) + '", '
                            my_channels.append("PprGTH MD" + str(MDi+1))

                    querystr_channels = querystr_channels[:-2]
                    print(f'querystr_channels = {querystr_channels}')
                    print(f'my_channels = {my_channels}')

                    # Define Table
                    querystr_table = f'"{table}"'
                    print(f'querystr_table = {querystr_table}')

                    # Define Variables
                    querystr_variables = ''
                    my_variables = []

                    # Loop over chosen Variables
                    for ivar in config[table].keys():
                        querystr_variables = querystr_variables + '"' + ivar + '", '
                        my_variables.append(ivar)
                        dataDict[benchtest_id][ivar] = {}

                        for chan in my_channels:
                            if chan[7:10] not in dataDict[benchtest_id][ivar]:
                                dataDict[benchtest_id][ivar][chan[7:10]] = {}

                    #print(f'dataDict = {dataDict}')

                    querystr_variables = querystr_variables[:-2]
                    print(f'querystr_variables = {querystr_variables}')
                    print(f'my_variables = {my_variables}')

                    # Define Time Range
                    start_time = benchtest_proc[benchtest_id]["benchtest_timestamp"][0]
                    stop_time  = benchtest_proc[benchtest_id]["benchtest_timestamp"][1]
                    querystr_time_range = f'time >= \'{benchtest_proc[benchtest_id]["benchtest_timestamp"][0]}\' AND time <= \'{benchtest_proc[benchtest_id]["benchtest_timestamp"][1]}\''
                    print(f'querystr_time_range = {querystr_time_range}')

                    # Construct Query
                    my_query = f'SELECT {querystr_channels}, {querystr_variables} FROM {querystr_table} WHERE {querystr_time_range}'
                    print(f'my_query = {my_query}')

                    # Query database
                    queryResults[benchtest_id][table] = client.query(my_query)
                    
                    # Check if query returned any data
                    query_points = list(queryResults[benchtest_id][table].get_points())
                    if not query_points:
                        print(f'Warning: No data returned from InfluxDB for table {table} in benchtest {benchtest_id}')
                        # Initialize empty data structure for this table to prevent errors later
                        for ivar in my_variables:
                            for chan in my_channels:
                                if chan[7:10] not in dataDict[benchtest_id][ivar]:
                                    dataDict[benchtest_id][ivar][chan[7:10]] = {}
                        print(f'Querying Table: {table} - No data available\n')
                    else:
                        print(f'Querying Table: {table} - Success!\n')
                    
                    #print(f'queryResults = {queryResults}')
                    #print(f'queryResults[{benchtest_id}] = {queryResults[benchtest_id]}')
                    #print(f'queryResults[{benchtest_id}][{table}] = {queryResults[benchtest_id][table]}')

                    # Data Loop
                    for point in query_points:
                        #print(f'point = {point}')
                        #print(f'Time: {point['time']}')

                        for ppr in my_channels:
                            if point[ppr] != None:
                                #print(f'{ppr} : {point[ppr]}')
                                #print(f'PprGTH {ppr[7:10]} : {point[ppr]}')
                                #print(f'ppr = "{ppr}"')
                                #print(f'ppr[7:10] = "{ppr[7:10]}"')
                                #print(f'point = {point}')
                                #print(f'point[ppr] = {point[ppr]}')

                                for ivar in my_variables:
                                    #print(f'ivar = {ivar}')
                                    #print(f'point[ivar] = {point[ivar]}')

                                    if point[ppr] not in dataDict[benchtest_id][ivar][ppr[7:10]]:
                                        dataDict[benchtest_id][ivar][ppr[7:10]][point[ppr]] = {}

                                    if "x" not in dataDict[benchtest_id][ivar][ppr[7:10]][point[ppr]]:
                                        dataDict[benchtest_id][ivar][ppr[7:10]][point[ppr]]["x"] = []

                                    if "y" not in dataDict[benchtest_id][ivar][ppr[7:10]][point[ppr]]:
                                        dataDict[benchtest_id][ivar][ppr[7:10]][point[ppr]]["y"] = []

                                    #if (ivar == "hg_max_dev" or ivar == "lg_max_dev" or ivar == "hg_slope" or ivar == "lg_slope" or ivar == "hg_r2" or ivar == "lg_r2"):
                                        #print(f'{ivar}: {point[ivar]}')

                                    if point[ivar] != None:
                                        #Filtering zeroes from table CIS_Linearity variables hg_center and lg_center
                                        if table == "CIS" and point[ivar] == 0:
                                            print(f"  Warning: Variable {ivar} in Table {table} has value {point[ivar]} at {datetime.fromisoformat(point['time'])}. Filtering out.")
                                        else:
                                            dataDict[benchtest_id][ivar][ppr[7:10]][point[ppr]]["x"].append(datetime.fromisoformat(point['time']))
                                            dataDict[benchtest_id][ivar][ppr[7:10]][point[ppr]]["y"].append(point[ivar])
                                    else:
                                        print(f"  Warning: NULL value encountered for variable {ivar} in Table {table} at {datetime.fromisoformat(point['time'])}. Skipping this point.")

                # Handling Tag based queries
                elif table in TagTables:
                    print(f'{table} is in TagTables')

                    # Define Table
                    querystr_table = f'"{table}"'
                    print(f'querystr_table = {querystr_table}')

                    # Define Time Range
                    start_time = benchtest_proc[benchtest_id]["benchtest_timestamp"][0]
                    stop_time  = benchtest_proc[benchtest_id]["benchtest_timestamp"][1]
                    querystr_time_range = f'time >= \'{benchtest_proc[benchtest_id]["benchtest_timestamp"][0]}\' AND time <= \'{benchtest_proc[benchtest_id]["benchtest_timestamp"][1]}\''
                    print(f'querystr_time_range = {querystr_time_range}')

                    # Define Tags
                    querystr_tags = ''
                    my_tags = []

                    # Contruct Tags
                    for ivar in config[table].keys():
                        #print(f'ivar: {ivar}')
                        #print(f'dataDict[{benchtest_id}] = {dataDict[benchtest_id]}')
                        dataDict[benchtest_id][ivar] = {}

                        for MDi in range(0,4):
                            if benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi] != None:
                                #print(f'Mini-Drawer {MDi+1} contains DaughterBoard with Serial Number: {benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}')
                                #print(f'dataDict[{benchtest_id}][{ivar}] = {dataDict[benchtest_id][ivar]}')
                                dataDict[benchtest_id][ivar]["MD"+str(MDi+1)] = {}

                                for side in ['a', 'b']:
                                    #print(f'Side: {side}')
                                    #print(f'dataDict[{benchtest_id}][{ivar}][{MDi}] = {dataDict[benchtest_id][ivar][MDi]}')
                                    dataDict[benchtest_id][ivar]["MD"+str(MDi+1)]["db"+side] = {}
                                    dataDict[benchtest_id][ivar]["MD"+str(MDi+1)]["db"+side]["x"] = []
                                    dataDict[benchtest_id][ivar]["MD"+str(MDi+1)]["db"+side]["y"] = []

                                    querystr_tags = querystr_tags + '"entity_id" = \'db_tester_lbt_md' + str(MDi+1) + '_db' + side + '_' + ivar + '\' OR '

                    querystr_tags = '(' + querystr_tags[:-4] + ')'
                    print(f'querystr_tags = {querystr_tags}')

                    my_query = f'SELECT "entity_id", "value" FROM {querystr_table} WHERE {querystr_time_range} AND {querystr_tags}'
                    print(f'my_query = {my_query}')

                    # Query database
                    queryResults[benchtest_id][table] = client.query(my_query)
                    
                    # Check if query returned any data
                    query_points = list(queryResults[benchtest_id][table].get_points())
                    if not query_points:
                        print(f'Warning: No data returned from InfluxDB for table {table} in benchtest {benchtest_id}')
                        # Initialize empty data structure for this table to prevent errors later
                        for ivar in config[table].keys():
                            for MDi in range(0,4):
                                if benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi] != None:
                                    dataDict[benchtest_id][ivar]["MD"+str(MDi+1)] = {}
                                    for side in ['a', 'b']:
                                        dataDict[benchtest_id][ivar]["MD"+str(MDi+1)]["db"+side] = {}
                                        dataDict[benchtest_id][ivar]["MD"+str(MDi+1)]["db"+side]["x"] = []
                                        dataDict[benchtest_id][ivar]["MD"+str(MDi+1)]["db"+side]["y"] = []
                        print(f'Querying Table: {table} - No data available\n')
                    else:
                        print(f'Querying Table: {table} - Success!\n')
                    
                    #print(f'queryResults = {queryResults}')
                    #print(f'queryResults[{benchtest_id}] = {queryResults[benchtest_id]}')
                    #print(f'queryResults[{benchtest_id}][{table}] = {queryResults[benchtest_id][table]}')
                    
                    for point in query_points:
                        #print(f'point = {point}')

                        #print(f'MDString: {point["entity_id"][14:17].upper()}')
                        #print(f'DBSide:   {point["entity_id"][18:21]}')
                        #print(f'VarName:  {point["entity_id"][22:]}')
                        #print(f'Time:     {point["time"]}')
                        #print(f'Value:    {point["value"]}')

                        # Check for NULL values in the "value" field
                        if point["value"] != None:
                            dataDict[benchtest_id][point["entity_id"][22:]][point["entity_id"][14:17].upper()][point["entity_id"][18:21]]["x"].append(datetime.fromisoformat(point['time']))
                            dataDict[benchtest_id][point["entity_id"][22:]][point["entity_id"][14:17].upper()][point["entity_id"][18:21]]["y"].append(point["value"])
                        else:
                            print(f"  Warning: NULL value encountered for entity_id {point['entity_id']} in Table {table} at {datetime.fromisoformat(point['time'])}. Skipping this point.")
                        #point = {'time': '2026-04-16T17:53:06.240778Z', 'entity_id': 'db_tester_lbt_md2_dba_3v3', 'value': 3.329}

                    #for ivar in config[table].keys():
                        #print("ASS Check\n")
                        #print(f'dataDict[{benchtest_id}][{ivar}]: {dataDict[benchtest_id][ivar]}\n')

            print("----------------------------")
        print("============================\n")

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

    ### Statistical Tests for Data ###
    print("\nStatistical Tests")

    statDict = {}
    print(f'\nstatDict = {statDict}')

    for benchtest_id in benchtest_proc.keys():
        # statDict
        statDict[benchtest_id] = {}
        print(f'\n  statDict[{benchtest_id}] = {statDict[benchtest_id]}')
        
        # Recalculate btDIRName for this benchtest_id
        btDIRName = "benchtest_id_" + str(benchtest_id)

        with open(driveDIR + str(btDIRName) + "/" + "benchtest_id_" + str(benchtest_id) + ".log", "a") as logfile:
            logfile.write(f'  benchtest ID: {benchtest_id}\n')

            for MDi in range(0,4):

                if benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi] != None:
                    # Skip if specific daughterboard ID is provided and doesn't match
                    if specific_daughterboard_id is not None:
                        if benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi] != specific_daughterboard_id:
                            print(f'    Skipping DaughterBoard {benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]} (not the specified daughterboard)')
                            continue
                    
                    print(f'\n    DaughterBoard Serial Number: {benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}')
                    logfile.write(f'\n    DaughterBoard Serial Number: {benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}\n')
                    statDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]] = {}

                    # Make directory for each DaughterBoard undergoing benchtest
                    dbDIRName = "DB_" + str(benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi])
                    print(f'    Creating Directory: {driveDIR + btDIRName + "/" + dbDIRName}')
                    dbDIR_fullpath = Path(driveDIR + btDIRName + "/" + dbDIRName)
                    print(f'    dbDir_fullpath = {dbDIR_fullpath}')
                    dbDIR_fullpath.mkdir(parents=True, exist_ok=True)

                    for table in config.keys():
                        print(f'      Table: {table}')
                        logfile.write(f'      Table: {table}\n')

                        for ivar in config[table].keys():
                            print(f'        Variable:  {ivar}')
                            print(f'        config[{table}][{ivar}] = {config[table][ivar]}')
                            logfile.write(f'        Variable:  {ivar}\n')
                            logfile.write(f'        config[{table}][{ivar}] = {config[table][ivar]}\n')
                            statDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar] = {}

                            var_pointpass = []
                            var_npoints = 0

                            for channel in dataDict[benchtest_id][ivar]["MD"+str(MDi+1)]:
                                print(f'          Channel: {channel}')
                                #print(f'          dataDict[{benchtest_id}][{ivar}][{"MD"+str(MDi+1)}][{channel}][{"y"}]')
                                logfile.write(f'          Channel: {channel}\n')
                                #logfile.write(f'          dataDict[{benchtest_id}][{ivar}][{"MD"+str(MDi+1)}][{channel}][{"y"}]')

                                var_npoints += len(dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"])

                                if len(config[table][ivar]) == 1:

                                    for y in dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"]:
                                        #print(f'            y = {y}')

                                        if y == config[table][ivar][0]:
                                            #print("True")
                                            var_pointpass.append(1)
                                        else:
                                            #print("False")
                                            var_pointpass.append(0)

                                if len(config[table][ivar]) == 2:
                                    #This section is for variables that need to be between two values

                                    #np_yArray = np.array(dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"])
                                    #np_Filter = np.ones(np.size(np_yArray), dtype=bool)                                
                                    #np_yVarBound = np_yVarArray[(np_yVarArray > config[table][ivar][0]) & (np_yVarArray < config[table][ivar][1])]
                                    #
                                    #y_mu    = np.mean(np_yVarBound)
                                    #y_sigma = np.std(np_yVarbound)
                                    #
                                    #print(f'            mu    = {y_mu}')
                                    #print(f'            sigma = {y_sigma}')

                                    #for y in dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"]:
                                    for i, y in enumerate( dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"] ):

                                        datlen = len(dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"])

                                        #if ivar == "lg_r2":
                                        #    print(f'            i = {i}')
                                        #    print(f'            y = {y}')
                                        #    print(f'            datlen = {datlen}')

                                        np_RMArray = np.empty(0)
                                        roll_median = 0
                                        roll_MAD = 0

                                        if y >= config[table][ivar][0] and y <= config[table][ivar][1]:
                                            var_pointpass.append(1)

                                        elif y < config[table][ivar][0] or y > config[table][ivar][1]:

                                            # Skip spike/drop detection if there's only 1 data point
                                            if datlen == 1:
                                                print(f'              Warning: Only 1 data point available for {ivar} in {channel}. Cannot perform spike/drop detection. Marking as failed (out of bounds).')
                                                logfile.write(f'             Warning: Only 1 data point available for {ivar} in {channel}. Cannot perform spike/drop detection. Marking as failed (out of bounds).\n')
                                                var_pointpass.append(0)
                                            else:
                                                if i < 10:
                                                    print(f'              Case: i<10. [0, {i}, {i+1}, 21]')
                                                    np_RMArray = np.array( dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"][0:i] + dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"][i+1:21])
                                                elif i >= len(dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"]) - 10:
                                                    print(f'              Case: i>= len(dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"]) - 10. [datlen-21, i, i+1, datlen] = [{datlen-21}, {i}, {i+1}, {datlen}]')
                                                    np_RMArray = np.array( dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"][datlen-21:i] + dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"][i+1:datlen] )
                                                else:
                                                    print(f'              Case: else. [{i-10}, {i}, {i+1}, {i+11}]')
                                                    np_RMArray = np.array( dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"][i-10:i] + dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"][i+1:i+11])

                                                roll_median = np.median(np_RMArray)
                                                #roll_MAD = np.median(np.abs(np_RMArray - roll_median))
                                                roll_MAD = max(0.1, np.median(np.abs(np_RMArray - roll_median)))

                                                if i == 0:
                                                    print(f'              Case: i == 0')
                                                    if abs(dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"][i] - dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"][i+1]) < 3*roll_MAD:
                                                        var_pointpass.append(0)
                                                    else:
                                                        print(f'             Spike/Drop Detected @ [DBSN: {benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}, Table: {table}, Variable: {ivar}, Channel: {channel} Time: {dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["x"][i]}, Value: {dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"][i]}]')
                                                        logfile.write(f'             Spike/Drop Detected @ [DBSN: {benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}, Table: {table}, Variable: {ivar}, Channel: {channel} Time: {dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["x"][i]}, Value: {dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"][i]}]\n')
                                                elif i == datlen-1:
                                                    print(f'              Case: i == datlen-1')
                                                    if abs(dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"][i-1] - dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"][i]) < 3*roll_MAD:
                                                        var_pointpass.append(0)
                                                    else:
                                                        print(f'             Spike/Drop Detected @ [DBSN: {benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}, Table: {table}, Variable: {ivar}, Channel: {channel} Time: {dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["x"][i]}, Value: {dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"][i]}]')
                                                        logfile.write(f'             Spike/Drop Detected @ [DBSN: {benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}, Table: {table}, Variable: {ivar}, Channel: {channel} Time: {dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["x"][i]}, Value: {dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"][i]}]\n')
                                                else:
                                                    print(f'              Case: else.')                                            
                                                    if abs(dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"][i] - dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"][i-1]) < 3*roll_MAD or abs(dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"][i+1] - dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"][i]) < 3*roll_MAD:
                                                        var_pointpass.append(0)
                                                    else:
                                                        print(f'             Spike/Drop Detected @ [DBSN: {benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}, Table: {table}, Variable: {ivar}, Channel: {channel} Time: {dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["x"][i]}, Value: {dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"][i]}]')
                                                        logfile.write(f'             Spike/Drop Detected @ [DBSN: {benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}, Table: {table}, Variable: {ivar}, Channel: {channel} Time: {dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["x"][i]}, Value: {dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"][i]}]\n')

                            #if table == "V":
                            #    print(f'        var_pointpass = {var_pointpass}')
                            #    print(f'        len_pointpass = {len(var_pointpass)}')

                            # statDict will contain four diagnostic values:
                            # Total number of points per variable:
                            statDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar]["nPoints"] = var_npoints
                            # Total number of points after spikes/drops are filtered out
                            statDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar]["nConsidered"] = len(var_pointpass)
                            # Total number of points within the given bounds
                            statDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar]["nPass"] = sum(var_pointpass)
                            # Fraction of points within the given bounds
                            if len(var_pointpass) != 0:
                                statDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar]["fPass"] = sum(var_pointpass)/len(var_pointpass)
                            elif len(var_pointpass) == 0:
                                print(f'        Warning: Data Not Found for Variable {ivar} in Table {table}! Tentatively Ignoring Check and "Passing" Board, Please Consult Log.')
                                statDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar]["fPass"] = -1.0

    for btid, dbDict in statDict.items():
        print(f'\nFor benchtest with id: {btid}')

        # Reopen output directory
        btDIRName = "benchtest_id_" + str(btid)
        print(f'  Reopening directory: {driveDIR + str(btDIRName)}')

        # Handle backup and regeneration for benchtest_id.log
        log_path = driveDIR + str(btDIRName) + "/" + "benchtest_id_" + str(btid) + ".log"
        write_benchtest_log = True
        
        if regenerate_mode == 'benchtest_id_log' or regenerate_mode == 'all':
            backup_log_file(log_path)
        elif regenerate_mode == 'benchtest_id_results_log' or regenerate_mode == 'plots':
            # Skip writing benchtest_id.log if only regenerating results or plots
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
        elif regenerate_mode == 'benchtest_id_log' or regenerate_mode == 'plots':
            # Skip writing results if only regenerating main log or plots
            write_results_log = False
        else:
            # Default mode: backup if exists
            backup_log_file(results_path)

        # Handle plot regeneration
        write_plots = True
        if regenerate_mode == 'benchtest_id_log' or regenerate_mode == 'benchtest_id_results_log':
            # Skip plots if only regenerating logs
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

            # Update daughterboard table (skip if test_pass is -1)
            if benchtest_proc[btid]["benchtest_pass"] != -1:
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

    print(f'statDict = {statDict}')

    ### DataFrames ###
    # Defining DataFRame dictionary
    print(f'\nDataFrames')
    dfDict = {}

    for benchtest_id in benchtest_proc.keys():
        dfDict[benchtest_id] = {}
        print(f'\nbenchtest_id: {benchtest_id}')
        print(f'dfDict[{benchtest_id}]: {dfDict[benchtest_id]}')
        
        # Recalculate time range for this benchtest_id
        start_time = benchtest_proc[benchtest_id]["benchtest_timestamp"][0]
        stop_time = benchtest_proc[benchtest_id]["benchtest_timestamp"][1]

        for MDi in range(0,4):

            if benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi] != None:
                # Skip if specific daughterboard ID is provided and doesn't match
                if specific_daughterboard_id is not None:
                    if benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi] != specific_daughterboard_id:
                        print(f'  Skipping DaughterBoard {benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]} (not the specified daughterboard)')
                        continue
                
                print(f'\n  DaughterBoard Serial Number: {benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}')
                dfDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]] = {}
                print(f'  dfDict[{benchtest_id}][{benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}]: {dfDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]]}')

                for table in config.keys():
                    print(f'      Table: {table}')

                    for ivar in config[table].keys():
                        print(f'        Variable: {ivar}')
                        #print(f'    dataDict[{benchtest_id}][{ivar}][{"MD"+str(MDi+1)}] = {dataDict[benchtest_id][ivar]["MD"+str(MDi+1)]}')
                        #print(f'    len(dataDict[{benchtest_id}][{ivar}][{"MD"+str(MDi+1)}]) = {len(dataDict[benchtest_id][ivar]["MD"+str(MDi+1)])}')

                        print('Just a test statement')
                        dfDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar] = {}
                        #print(f'        dfDict[{benchtest_id}][{benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}][{ivar}]: {dfDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar]}')

                        #if len(dataDict[benchtest_id][ivar]["MD"+str(MDi+1)]) != 0:

                        dfCombo = []

                        for channel in dataDict[benchtest_id][ivar]["MD"+str(MDi+1)]:
                            print(f'          channel: {channel}')
                                    
                            dfDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar][channel] = pd.DataFrame( {'channel' : [channel]*len(dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["x"]), 'x' : dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["x"], 'y' : dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][channel]["y"] } )

                            dfCombo.append(dfDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar][channel])

                            #print(f'          dfDict[{benchtest_id}][{benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}][{ivar}][{channel}]:')
                            #print(f'\n{dfDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar][channel]}')

                        ### Adding the tolerances to the plots ###
                        if len(config[table][ivar]) == 1:
                            # The variable has a single value it needs to take
                            dfDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar]["TruthValue"] = pd.DataFrame( {'channel' : ["TruthValue", "TruthValue"], 'x' : [datetime.fromisoformat(start_time), datetime.fromisoformat(stop_time)], 'y' : [config[table][ivar][0], config[table][ivar][0]] } )

                            dfCombo.append(dfDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar]["TruthValue"])

                            #useful time range code
                            #start_time = benchtest_proc[benchtest_id]["benchtest_timestamp"][0]
                            #stop_time  = benchtest_proc[benchtest_id]["benchtest_timestamp"][1]

                        if len(config[table][ivar]) == 2:
                            # The variable has to between two different values
                            dfDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar]["LowerLimit"] = pd.DataFrame( {'channel' : ["LowerLimit", "LowerLimit"], 'x' : [datetime.fromisoformat(start_time), datetime.fromisoformat(stop_time)], 'y' : [config[table][ivar][0], config[table][ivar][0]] } )

                            dfCombo.append(dfDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar]["LowerLimit"])

                            dfDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar]["UpperLimit"] = pd.DataFrame( {'channel' : ["UpperLimit", "UpperLimit"], 'x' : [datetime.fromisoformat(start_time), datetime.fromisoformat(stop_time)], 'y' : [config[table][ivar][1], config[table][ivar][1]] } )

                            dfCombo.append(dfDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar]["UpperLimit"])

                        #DataFrame debugging stuff
                        #print(f'        dfCombo: {dfCombo}')
                        #for i, x in enumerate(dfCombo):
                        #    print(f"\n--- frame {i} ---")
                        #    print(x.shape)
                        #    print(x.dtypes)
                        #    print(x.isna().all())
                        #    
                        #for i, df in enumerate(dfCombo):
                        #    print(f"\n--- dfCombo[{i}] ---")
                        #    
                        #    print("shape:", df.shape)
                        #    print("empty:", df.empty)
                        #    
                        #    print("all-NA columns:")
                        #    print(df.columns[df.isna().all()])
                        #    
                        #    print(df.dtypes)

                        # We need to filter out empty DataFrames if there are database errors
                        dfCombo = [df for df in dfCombo if not df.empty]

                        dfDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar]["Full"] = pd.concat(dfCombo)

                        #print(f'        dfDict[{benchtest_id}][{benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}][{ppr}][{ivar}][{"Full"}]:')
                        #print(f'\n{dfDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar]["Full"]}')

    # plotly Plotting
    print(f'\n\n Plotly:')
    plotDict = {}

    for benchtest_id in benchtest_proc.keys():
        plotDict[benchtest_id] = {}
        print(f'\nbenchtest_id: {benchtest_id}')
        print(f'plotDict[{benchtest_id}]: {plotDict[benchtest_id]}')
        
        # Recalculate btDIRName for this benchtest_id
        btDIRName = "benchtest_id_" + str(benchtest_id)

        for MDi in range(0,4):

            if benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi] != None:
                # Skip if specific daughterboard ID is provided and doesn't match
                if specific_daughterboard_id is not None:
                    if benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi] != specific_daughterboard_id:
                        print(f'  Skipping DaughterBoard {benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]} (not the specified daughterboard)')
                        continue
                
                print(f'\n  DaughterBoard Serial Number: {benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}')
                plotDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]] = {}
                print(f'  plotDict[{benchtest_id}][{benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}]: {plotDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]]}')

                dbDIRName = "DB_" + str(benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi])
                
                # Create directory for each DaughterBoard if it doesn't exist
                dbDIR_fullpath = Path(driveDIR + btDIRName + "/" + dbDIRName)
                dbDIR_fullpath.mkdir(parents=True, exist_ok=True)

                for table in config.keys():
                    print(f'      Table: {table}')

                    for ivar in config[table].keys():
                        print(f'        Variable: {ivar}')
                        #print(f'        dataDict[{benchtest_id}][{ivar}][{"MD"+str(MDi+1)}] = {dataDict[benchtest_id][ivar]["MD"+str(MDi+1)]}')
                        print(f'        nChannels: {len(dataDict[benchtest_id][ivar]["MD"+str(MDi+1)])}')
                        #print(f'        len(dataDict[{benchtest_id}][{ivar}][{"MD"+str(MDi+1)}]) = {len(dataDict[benchtest_id][ivar]["MD"+str(MDi+1)])}')

                        plotDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar] = {}
                        #print(f'        plotDict[{benchtest_id}][{benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}][{ivar}]: {plotDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar]}')

                        testtime = datetime.now()
                        print(f'        Post Initialise-plotDict Date/Time: {testtime.strftime("%y/%m/%d - %H:%M:%S")}')

                        if len(dataDict[benchtest_id][ivar]["MD"+str(MDi+1)]) != 0:
                            plotDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar] = plotlyEX.line( dfDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar]["Full"], x="x", y="y", color = "channel", labels = {"x":"Time", "y":ivar, "channel":"Uplink Channel"} )

                            testtime = datetime.now()
                            print(f'          Post Define-plotDict Date/Time: {testtime.strftime("%y/%m/%d - %H:%M:%S")}')

                            plotDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar].update_layout(title = "DBSNo: "+str(benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi])+" - PPrGTH: "+ivar+" (Gen -> "+datetime.now().strftime("%Y-%m-%d %H:%M:%S")+")")

                            testtime = datetime.now()
                            print(f'          Post Update Layout-plotDict Date/Time: {testtime.strftime("%y/%m/%d - %H:%M:%S")}')

                            if len(config[table][ivar]) == 1:
                                print('            LENGTH = 1')
                                plotDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar].update_traces(selector={'name':'TruthValue'}, line={'color':'rgba(255, 0, 0, 1)'})
                                testtime = datetime.now()
                                print(f'            Post Update Truth-plotDict Date/Time: {testtime.strftime("%y/%m/%d - %H:%M:%S")}')

                            if len(config[table][ivar]) == 2:
                                print('            LENGTH = 2')
                                plotDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar].update_traces(selector={'name':'LowerLimit'}, line={'color':'rgba(255, 0, 0, 1)'})
                                plotDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar].update_traces(selector={'name':'UpperLimit'}, line={'color':'rgba(255, 0, 0, 1)'})
                                testtime = datetime.now()
                                print(f'            Post Update Limits-plotDict Date/Time: {testtime.strftime("%y/%m/%d - %H:%M:%S")}')

                            if plot_regenerate[benchtest_id]:
                                plot_path = driveDIR+btDIRName+"/"+dbDIRName + "/DBSNo_"+str(benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi])+"_PPrGTH_"+ivar+".html"
                                plotDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar].write_html(plot_path)
                                testtime = datetime.now()
                                print(f'          Post Final Save-plotDict Date/Time: {testtime.strftime("%y/%m/%d - %H:%M:%S")}')

    #print(f'ASS! {cursor.rowcount}')

### ######### ###
### Executing ###
### ######### ###

# Load Config
config  = load_yaml_conf("vars.yaml")
secrets = load_yaml_conf("../secrets/secrets.yaml")

# Setup argparse for regeneration options
parser = argparse.ArgumentParser(description='DaughterBoard Qualification Program')
parser.add_argument('-r', '--regenerate', type=str, choices=['benchtest_id_results_log', 'benchtest_id_log', 'plots', 'all'],
                    help='Force regeneration: benchtest_id_results_log, benchtest_id_log, plots, or all')
parser.add_argument('-b', '--benchtest_id', type=str,
                    help='Specific benchtest ID or range (e.g., "1" or "2-5") to regenerate (if not specified, processes all in regeneration mode)')
parser.add_argument('-d', '--daughterboard_id', type=str,
                    help='Specific daughterboard ID to analyze (if not specified, processes all daughterboards in the benchtest)')
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

            for k, val in enumerate(config[i][j]):
                print(f'      k = {k}')
                #print(f'      type(k) = {type(k)}')
                print(f'      config[{i}][{j}][{k}] = {val}')

    print("\n")

# Debug Code: Secrets Dictionary
DEBUG_SECRETS = True

if DEBUG_SECRETS:
    print(f"secrets: {secrets}")
    print(f"secrets.keys(): {secrets.keys()}")
    print(f"secrets.values(): {secrets.values()}")



# Execute main()
DBQ_Mk6(regenerate_mode=args.regenerate, specific_benchtest_ids=specific_benchtest_ids, specific_daughterboard_id=specific_daughterboard_id)
