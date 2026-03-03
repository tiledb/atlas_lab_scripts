### ################################### ###
### DaughterBoard Qualification Program ###
### Version 0.6
### ################################### ###

### ############### ###
### Package Imports ###
### ############### ###

# Basic Packages
from datetime import datetime
import math

# Mathematics Packages
import numpy as np
import pandas as pd

# Plotting Packages (plotly)
import plotly.express as plotlyEX

# Server Packages
import yaml

# MySQL for MariaDB
import mysql.connector
from mysql.connector import Error

# InfluxDBClient for InfluxDB
from influxdb import InfluxDBClient

### ######### ###
### Functions ###
### ######### ###

# Load configuration data from .yaml file
def load_secrets(filepath="../secrets/secrets.yaml"):
    with open(filepath, "r") as file:
        return yaml.safe_load(file)

# Function to print tree structure
def print_tree(level, name, is_last):
    prefix = "\u2514\u2500\u2500 " if is_last else "\u251C\u2500\u2500 "
    print(" " * (level * 4) + prefix + name)

# Main
def db_qual():

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
            password=secrets["tiledb-mariadb"]["password"]
        )

        # Confirm MariaDB Connection
        if connection.is_connected():
            print("✅ Connected to MariaDB!")
            cursor = connection.cursor()

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
        # The format is: {benchtest_id : [benchtest_pass, [start_time, stop_time], [db1_serialno, db2_serialno, db3_serialno, db4_serialno] ] }
        benchtest_proc = {}

        if rows:
            print("\nData from MariaDB benchtest")
            print(" | ".join(columns))
            for row in rows:
                # If the benchtest is flagged for reprocessing, then redownload the 
                if row[4] == 0:
                    benchtest_id    = row[0]
                    benchtest_start = row[1].strftime("%Y-%m-%dT%H:%M:%SZ")
                    benchtest_stop  = row[2].strftime("%Y-%m-%dT%H:%M:%SZ")
                    benchtest_pass  = row[4]

                    benchtest_proc[row[0]] = [row[4], [row[1].strftime("%Y-%m-%dT%H:%M:%SZ"), row[2].strftime("%Y-%m-%dT%H:%M:%SZ")], [row[5], row[6], row[7], row[8]]]
                    print(" | ".join(map(str, row)))
        else:
            print("⚠ No data found in selected table.")

        ## Readout: Static:
        #print(f"benchtest id: {benchtest_id}")
        #print(f"Converted start time: {benchtest_start}")
        #print(f"Converted stop time:  {benchtest_stop}")
        #print(f"benchtest pass: {benchtest_pass}")

        ## Readout: Dynamic:
        #print(f"benchtest_proc: {benchtest_proc}")
        #print(f"benchtest_proc[1] = {benchtest_proc[1]}")
        #print(f"benchtest_proc[1][0] = {benchtest_proc[1][1]}")
        #print(f"benchtest_proc[1][1] = {benchtest_proc[1][1]}")
        #print(f"benchtest_proc[1][1][0] = {benchtest_proc[1][1][0]}")
        #print(f"benchtest_proc[1][1][1] = {benchtest_proc[1][1][1]}")
        #print(f"benchtest_proc[1][2] = {benchtest_proc[1][1]}")
        #print(f"benchtest_proc[1][2][0] = {benchtest_proc[1][1][0]}")
        #print(f"benchtest_proc[1][2][1] = {benchtest_proc[1][1][1]}")
        #print(f"benchtest_proc[1][2][2] = {benchtest_proc[1][1][0]}")
        #print(f"benchtest_proc[1][2][3] = {benchtest_proc[1][1][1]}")

    except Error as e:
        print("❌ MariaDB Connection Failed")



    ### ######## ###
    ### InfluxDB ###
    ### ######## ###
    try:
        ### Connect to InfluxDB ###
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

        # List Tables
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



        # Access TileDB
        client.switch_database("tiledb")

        # Access timestamp
        #Historic Date: 3rd of September, 2024, from 23:06:10 to 23:08:00
        #start_time= "2024-09-03T17:40:00Z"
        #stop_time= "2024-09-03T17:50:00Z"
 
        #Historic Date: 9th of July, 2025, from 17:00:00 to 17:05:00
        #The day in Early July where (I think) Christophe, Nikola and I were in Eduardo's office (with him on Zoom call)
        #It was then where we replaced the old DaughterBoard on the test Main Board with a new one. Specifically, around 16:00
        #start_time= "2025-07-09T17:00:00Z"
        #stop_time= "2025-07-10T17:05:00Z"

        #Historic Date: 10th of July, 2025, from 14:15:00 to 14:45:00
        #Default testing timestamp
        #start_time = "2025-07-10T14:15:00Z"
        #stop_time  = "2025-07-10T14:45:00Z"

        # Using timestamps from MariaDB
        # Single
        #start_time = benchtest_start
        #stop_time  = benchtest_stop
        # Dynamic
        start_time = benchtest_proc[1][1][0]
        stop_time  = benchtest_proc[1][1][1]

        # Define formal time stamp
        my_time_range = f'time >= \'{start_time}\' AND time <= \'{stop_time}\''
        print(f'my_time_range = {my_time_range}')
        print("----------------------------")

        # Access Link_Status Table
        my_measurement = '"Link Status"' #Table for Link Status Data
        print(f'my_measurement = {my_measurement}')

        # Access Channels
        my_channels = '"PPrEmu MD1", "PPrEmu MD2", "PPrEmu MD3", "PPrEmu MD4", "PprGTH MD1", "PprGTH MD2", "PprGTH MD3", "PprGTH MD4"'
        print(f'my_channels = {my_channels}')

        # Access Variables
        my_variables = '"gbtrx_rdy", "crc", "ber", "latency"'
        print(f'my_variables = {my_variables}')

        # Define formal SQL Query
        # Basic Query
        my_query = f'SELECT "PPrEmu MD1", "gbtrx_rdy" FROM "{my_measurement}" {my_time_range}'
        # Multivariable Query
        my_query = f'SELECT {my_channels}, {my_variables} FROM {my_measurement} WHERE {my_time_range}'
        print(f'my_query = {my_query}')
        print("----------------------------")

        # Storing data from Query in "result" object
        result_LinkStat = client.query(my_query)
        print('Link Status Results Obtained!')

        ###################################
        ### Link_Status Data Processing ###
        ###################################

        # Number of Events
        nevents = 0

        ### Flags for Filtering Data ###
        # Mini-Drawer
        selectMD1 = 0
        selectMD2 = 0
        selectMD3 = 0
        selectMD4 = 0

        # Emu/PPr
        selectEmu = 0
        selectPpr = 0

        # Uplink Channel
        selectA0 = 0
        selectA1 = 0
        selectB0 = 0
        selectB1 = 0

        ### Arrays ###
        # gbtrx_rdy
        MD1_Emu_A0_gbtrxrdy_x = []
        MD1_Emu_A0_gbtrxrdy_y = []
        MD1_Emu_A1_gbtrxrdy_x = []
        MD1_Emu_A1_gbtrxrdy_y = []
        MD1_Emu_B0_gbtrxrdy_x = []
        MD1_Emu_B0_gbtrxrdy_y = []
        MD1_Emu_B1_gbtrxrdy_x = []
        MD1_Emu_B1_gbtrxrdy_y = []

        MD2_Emu_A0_gbtrxrdy_x = []
        MD2_Emu_A0_gbtrxrdy_y = []
        MD2_Emu_A1_gbtrxrdy_x = []
        MD2_Emu_A1_gbtrxrdy_y = []
        MD2_Emu_B0_gbtrxrdy_x = []
        MD2_Emu_B0_gbtrxrdy_y = []
        MD2_Emu_B1_gbtrxrdy_x = []
        MD2_Emu_B1_gbtrxrdy_y = []

        MD3_Emu_A0_gbtrxrdy_x = []
        MD3_Emu_A0_gbtrxrdy_y = []
        MD3_Emu_A1_gbtrxrdy_x = []
        MD3_Emu_A1_gbtrxrdy_y = []
        MD3_Emu_B0_gbtrxrdy_x = []
        MD3_Emu_B0_gbtrxrdy_y = []
        MD3_Emu_B1_gbtrxrdy_x = []
        MD3_Emu_B1_gbtrxrdy_y = []

        MD4_Emu_A0_gbtrxrdy_x = []
        MD4_Emu_A0_gbtrxrdy_y = []
        MD4_Emu_A1_gbtrxrdy_x = []
        MD4_Emu_A1_gbtrxrdy_y = []
        MD4_Emu_B0_gbtrxrdy_x = []
        MD4_Emu_B0_gbtrxrdy_y = []
        MD4_Emu_B1_gbtrxrdy_x = []
        MD4_Emu_B1_gbtrxrdy_y = []

        MD1_Ppr_A0_gbtrxrdy_x = []
        MD1_Ppr_A0_gbtrxrdy_y = []
        MD1_Ppr_A1_gbtrxrdy_x = []
        MD1_Ppr_A1_gbtrxrdy_y = []
        MD1_Ppr_B0_gbtrxrdy_x = []
        MD1_Ppr_B0_gbtrxrdy_y = []
        MD1_Ppr_B1_gbtrxrdy_x = []
        MD1_Ppr_B1_gbtrxrdy_y = []

        MD2_Ppr_A0_gbtrxrdy_x = []
        MD2_Ppr_A0_gbtrxrdy_y = []
        MD2_Ppr_A1_gbtrxrdy_x = []
        MD2_Ppr_A1_gbtrxrdy_y = []
        MD2_Ppr_B0_gbtrxrdy_x = []
        MD2_Ppr_B0_gbtrxrdy_y = []
        MD2_Ppr_B1_gbtrxrdy_x = []
        MD2_Ppr_B1_gbtrxrdy_y = []

        MD3_Ppr_A0_gbtrxrdy_x = []
        MD3_Ppr_A0_gbtrxrdy_y = []
        MD3_Ppr_A1_gbtrxrdy_x = []
        MD3_Ppr_A1_gbtrxrdy_y = []
        MD3_Ppr_B0_gbtrxrdy_x = []
        MD3_Ppr_B0_gbtrxrdy_y = []
        MD3_Ppr_B1_gbtrxrdy_x = []
        MD3_Ppr_B1_gbtrxrdy_y = []

        MD4_Ppr_A0_gbtrxrdy_x = []
        MD4_Ppr_A0_gbtrxrdy_y = []
        MD4_Ppr_A1_gbtrxrdy_x = []
        MD4_Ppr_A1_gbtrxrdy_y = []
        MD4_Ppr_B0_gbtrxrdy_x = []
        MD4_Ppr_B0_gbtrxrdy_y = []
        MD4_Ppr_B1_gbtrxrdy_x = []
        MD4_Ppr_B1_gbtrxrdy_y = []

        # crc
        MD1_Emu_A0_crc_x = []
        MD1_Emu_A0_crc_y = []
        MD1_Emu_A1_crc_x = []
        MD1_Emu_A1_crc_y = []
        MD1_Emu_B0_crc_x = []
        MD1_Emu_B0_crc_y = []
        MD1_Emu_B1_crc_x = []
        MD1_Emu_B1_crc_y = []

        MD2_Emu_A0_crc_x = []
        MD2_Emu_A0_crc_y = []
        MD2_Emu_A1_crc_x = []
        MD2_Emu_A1_crc_y = []
        MD2_Emu_B0_crc_x = []
        MD2_Emu_B0_crc_y = []
        MD2_Emu_B1_crc_x = []
        MD2_Emu_B1_crc_y = []

        MD3_Emu_A0_crc_x = []
        MD3_Emu_A0_crc_y = []
        MD3_Emu_A1_crc_x = []
        MD3_Emu_A1_crc_y = []
        MD3_Emu_B0_crc_x = []
        MD3_Emu_B0_crc_y = []
        MD3_Emu_B1_crc_x = []
        MD3_Emu_B1_crc_y = []

        MD4_Emu_A0_crc_x = []
        MD4_Emu_A0_crc_y = []
        MD4_Emu_A1_crc_x = []
        MD4_Emu_A1_crc_y = []
        MD4_Emu_B0_crc_x = []
        MD4_Emu_B0_crc_y = []
        MD4_Emu_B1_crc_x = []
        MD4_Emu_B1_crc_y = []

        MD1_Ppr_A0_crc_x = []
        MD1_Ppr_A0_crc_y = []
        MD1_Ppr_A1_crc_x = []
        MD1_Ppr_A1_crc_y = []
        MD1_Ppr_B0_crc_x = []
        MD1_Ppr_B0_crc_y = []
        MD1_Ppr_B1_crc_x = []
        MD1_Ppr_B1_crc_y = []

        MD2_Ppr_A0_crc_x = []
        MD2_Ppr_A0_crc_y = []
        MD2_Ppr_A1_crc_x = []
        MD2_Ppr_A1_crc_y = []
        MD2_Ppr_B0_crc_x = []
        MD2_Ppr_B0_crc_y = []
        MD2_Ppr_B1_crc_x = []
        MD2_Ppr_B1_crc_y = []

        MD3_Ppr_A0_crc_x = []
        MD3_Ppr_A0_crc_y = []
        MD3_Ppr_A1_crc_x = []
        MD3_Ppr_A1_crc_y = []
        MD3_Ppr_B0_crc_x = []
        MD3_Ppr_B0_crc_y = []
        MD3_Ppr_B1_crc_x = []
        MD3_Ppr_B1_crc_y = []

        MD4_Ppr_A0_crc_x = []
        MD4_Ppr_A0_crc_y = []
        MD4_Ppr_A1_crc_x = []
        MD4_Ppr_A1_crc_y = []
        MD4_Ppr_B0_crc_x = []
        MD4_Ppr_B0_crc_y = []
        MD4_Ppr_B1_crc_x = []
        MD4_Ppr_B1_crc_y = []

        # ber
        MD1_Emu_A0_ber_x = []
        MD1_Emu_A0_ber_y = []
        MD1_Emu_A1_ber_x = []
        MD1_Emu_A1_ber_y = []
        MD1_Emu_B0_ber_x = []
        MD1_Emu_B0_ber_y = []
        MD1_Emu_B1_ber_x = []
        MD1_Emu_B1_ber_y = []

        MD2_Emu_A0_ber_x = []
        MD2_Emu_A0_ber_y = []
        MD2_Emu_A1_ber_x = []
        MD2_Emu_A1_ber_y = []
        MD2_Emu_B0_ber_x = []
        MD2_Emu_B0_ber_y = []
        MD2_Emu_B1_ber_x = []
        MD2_Emu_B1_ber_y = []

        MD3_Emu_A0_ber_x = []
        MD3_Emu_A0_ber_y = []
        MD3_Emu_A1_ber_x = []
        MD3_Emu_A1_ber_y = []
        MD3_Emu_B0_ber_x = []
        MD3_Emu_B0_ber_y = []
        MD3_Emu_B1_ber_x = []
        MD3_Emu_B1_ber_y = []

        MD4_Emu_A0_ber_x = []
        MD4_Emu_A0_ber_y = []
        MD4_Emu_A1_ber_x = []
        MD4_Emu_A1_ber_y = []
        MD4_Emu_B0_ber_x = []
        MD4_Emu_B0_ber_y = []
        MD4_Emu_B1_ber_x = []
        MD4_Emu_B1_ber_y = []

        MD1_Ppr_A0_ber_x = []
        MD1_Ppr_A0_ber_y = []
        MD1_Ppr_A1_ber_x = []
        MD1_Ppr_A1_ber_y = []
        MD1_Ppr_B0_ber_x = []
        MD1_Ppr_B0_ber_y = []
        MD1_Ppr_B1_ber_x = []
        MD1_Ppr_B1_ber_y = []

        MD2_Ppr_A0_ber_x = []
        MD2_Ppr_A0_ber_y = []
        MD2_Ppr_A1_ber_x = []
        MD2_Ppr_A1_ber_y = []
        MD2_Ppr_B0_ber_x = []
        MD2_Ppr_B0_ber_y = []
        MD2_Ppr_B1_ber_x = []
        MD2_Ppr_B1_ber_y = []

        MD3_Ppr_A0_ber_x = []
        MD3_Ppr_A0_ber_y = []
        MD3_Ppr_A1_ber_x = []
        MD3_Ppr_A1_ber_y = []
        MD3_Ppr_B0_ber_x = []
        MD3_Ppr_B0_ber_y = []
        MD3_Ppr_B1_ber_x = []
        MD3_Ppr_B1_ber_y = []

        MD4_Ppr_A0_ber_x = []
        MD4_Ppr_A0_ber_y = []
        MD4_Ppr_A1_ber_x = []
        MD4_Ppr_A1_ber_y = []
        MD4_Ppr_B0_ber_x = []
        MD4_Ppr_B0_ber_y = []
        MD4_Ppr_B1_ber_x = []
        MD4_Ppr_B1_ber_y = []

        # latency
        MD1_Emu_A0_latency_x = []
        MD1_Emu_A0_latency_y = []
        MD1_Emu_A1_latency_x = []
        MD1_Emu_A1_latency_y = []
        MD1_Emu_B0_latency_x = []
        MD1_Emu_B0_latency_y = []
        MD1_Emu_B1_latency_x = []
        MD1_Emu_B1_latency_y = []

        MD2_Emu_A0_latency_x = []
        MD2_Emu_A0_latency_y = []
        MD2_Emu_A1_latency_x = []
        MD2_Emu_A1_latency_y = []
        MD2_Emu_B0_latency_x = []
        MD2_Emu_B0_latency_y = []
        MD2_Emu_B1_latency_x = []
        MD2_Emu_B1_latency_y = []

        MD3_Emu_A0_latency_x = []
        MD3_Emu_A0_latency_y = []
        MD3_Emu_A1_latency_x = []
        MD3_Emu_A1_latency_y = []
        MD3_Emu_B0_latency_x = []
        MD3_Emu_B0_latency_y = []
        MD3_Emu_B1_latency_x = []
        MD3_Emu_B1_latency_y = []

        MD4_Emu_A0_latency_x = []
        MD4_Emu_A0_latency_y = []
        MD4_Emu_A1_latency_x = []
        MD4_Emu_A1_latency_y = []
        MD4_Emu_B0_latency_x = []
        MD4_Emu_B0_latency_y = []
        MD4_Emu_B1_latency_x = []
        MD4_Emu_B1_latency_y = []

        MD1_Ppr_A0_latency_x = []
        MD1_Ppr_A0_latency_y = []
        MD1_Ppr_A1_latency_x = []
        MD1_Ppr_A1_latency_y = []
        MD1_Ppr_B0_latency_x = []
        MD1_Ppr_B0_latency_y = []
        MD1_Ppr_B1_latency_x = []
        MD1_Ppr_B1_latency_y = []

        MD2_Ppr_A0_latency_x = []
        MD2_Ppr_A0_latency_y = []
        MD2_Ppr_A1_latency_x = []
        MD2_Ppr_A1_latency_y = []
        MD2_Ppr_B0_latency_x = []
        MD2_Ppr_B0_latency_y = []
        MD2_Ppr_B1_latency_x = []
        MD2_Ppr_B1_latency_y = []

        MD3_Ppr_A0_latency_x = []
        MD3_Ppr_A0_latency_y = []
        MD3_Ppr_A1_latency_x = []
        MD3_Ppr_A1_latency_y = []
        MD3_Ppr_B0_latency_x = []
        MD3_Ppr_B0_latency_y = []
        MD3_Ppr_B1_latency_x = []
        MD3_Ppr_B1_latency_y = []

        MD4_Ppr_A0_latency_x = []
        MD4_Ppr_A0_latency_y = []
        MD4_Ppr_A1_latency_x = []
        MD4_Ppr_A1_latency_y = []
        MD4_Ppr_B0_latency_x = []
        MD4_Ppr_B0_latency_y = []
        MD4_Ppr_B1_latency_x = []
        MD4_Ppr_B1_latency_y = []

        # Retrieving, Printing, Filtering and Storing data from result object
        print("---------------- Reading Data: ----------------")

        for point in result_LinkStat.get_points():
            # Printing timestamp for each measurement
            print(f"Time: {point['time']}")

            # Incrementing Event Count
            nevents = nevents+1

            for key,value in point.items():
                if key != 'time':
                    print(f'{key} : {value}')

                # Defining Filters
                if (key == 'PPrEmu MD1') and (value == 'uplink A0'):
                    selectMD1 = 1
                    selectEmu = 1
                    selectA0  = 1
                elif (key == 'PPrEmu MD1') and (value == 'uplink A1'):
                    selectMD1 = 1
                    selectEmu = 1
                    selectA1  = 1
                elif (key == 'PPrEmu MD1') and (value == 'uplink B0'):
                    selectMD1 = 1
                    selectEmu = 1
                    selectB0  = 1
                elif (key == 'PPrEmu MD1') and (value == 'uplink B1'):
                    selectMD1 = 1
                    selectEmu = 1
                    selectB1  = 1
                elif (key == 'PPrEmu MD2') and (value == 'uplink A0'):
                    selectMD2 = 1
                    selectEmu = 1
                    selectA0  = 1
                elif (key == 'PPrEmu MD2') and (value == 'uplink A1'):
                    selectMD2 = 1
                    selectEmu = 1
                    selectA1  = 1
                elif (key == 'PPrEmu MD2') and (value == 'uplink B0'):
                    selectMD2 = 1
                    selectEmu = 1
                    selectB0  = 1
                elif (key == 'PPrEmu MD2') and (value == 'uplink B1'):
                    selectMD2 = 1
                    selectEmu = 1
                    selectB1  = 1
                elif (key == 'PPrEmu MD3') and (value == 'uplink A0'):
                    selectMD3 = 1
                    selectEmu = 1
                    selectA0  = 1
                elif (key == 'PPrEmu MD3') and (value == 'uplink A1'):
                    selectMD3 = 1
                    selectEmu = 1
                    selectA1  = 1
                elif (key == 'PPrEmu MD3') and (value == 'uplink B0'):
                    selectMD3 = 1
                    selectEmu = 1
                    selectB0  = 1
                elif (key == 'PPrEmu MD3') and (value == 'uplink B1'):
                    selectMD3 = 1
                    selectEmu = 1
                    selectB1  = 1
                elif (key == 'PPrEmu MD4') and (value == 'uplink A0'):
                    selectMD4 = 1
                    selectEmu = 1
                    selectA0  = 1
                elif (key == 'PPrEmu MD4') and (value == 'uplink A1'):
                    selectMD4 = 1
                    selectEmu = 1
                    selectA1  = 1
                elif (key == 'PPrEmu MD4') and (value == 'uplink B0'):
                    selectMD4 = 1
                    selectEmu = 1
                    selectB0  = 1
                elif (key == 'PPrEmu MD4') and (value == 'uplink B1'):
                    selectMD4 = 1
                    selectEmu = 1
                    selectB1  = 1
                elif (key == 'PprGTH MD1') and (value == 'uplink A0'):
                    selectMD1 = 1
                    selectPpr = 1
                    selectA0  = 1
                elif (key == 'PprGTH MD1') and (value == 'uplink A1'):
                    selectMD1 = 1
                    selectPpr = 1
                    selectA1  = 1
                elif (key == 'PprGTH MD1') and (value == 'uplink B0'):
                    selectMD1 = 1
                    selectPpr = 1
                    selectB0  = 1
                elif (key == 'PprGTH MD1') and (value == 'uplink B1'):
                    selectMD1 = 1
                    selectPpr = 1
                    selectB1  = 1
                elif (key == 'PprGTH MD2') and (value == 'uplink A0'):
                    selectMD2 = 1
                    selectPpr = 1
                    selectA0  = 1
                elif (key == 'PprGTH MD2') and (value == 'uplink A1'):
                    selectMD2 = 1
                    selectPpr = 1
                    selectA1  = 1
                elif (key == 'PprGTH MD2') and (value == 'uplink B0'):
                    selectMD2 = 1
                    selectPpr = 1
                    selectB0  = 1
                elif (key == 'PprGTH MD2') and (value == 'uplink B1'):
                    selectMD2 = 1
                    selectPpr = 1
                    selectB1  = 1
                elif (key == 'PprGTH MD3') and (value == 'uplink A0'):
                    selectMD3 = 1
                    selectPpr = 1
                    selectA0  = 1
                elif (key == 'PprGTH MD3') and (value == 'uplink A1'):
                    selectMD3 = 1
                    selectPpr = 1
                    selectA1  = 1
                elif (key == 'PprGTH MD3') and (value == 'uplink B0'):
                    selectMD3 = 1
                    selectPpr = 1
                    selectB0  = 1
                elif (key == 'PprGTH MD3') and (value == 'uplink B1'):
                    selectMD3 = 1
                    selectPpr = 1
                    selectB1  = 1
                elif (key == 'PprGTH MD4') and (value == 'uplink A0'):
                    selectMD4 = 1
                    selectPpr = 1
                    selectA0  = 1
                elif (key == 'PprGTH MD4') and (value == 'uplink A1'):
                    selectMD4 = 1
                    selectPpr = 1
                    selectA1  = 1
                elif (key == 'PprGTH MD4') and (value == 'uplink B0'):
                    selectMD4 = 1
                    selectPpr = 1
                    selectB0  = 1
                elif (key == 'PprGTH MD4') and (value == 'uplink B1'):
                    selectMD4 = 1
                    selectPpr = 1
                    selectB1  = 1

                # Storing Data
                if key == 'gbtrx_rdy':
                    if selectMD1 and selectEmu and selectA0:
                        MD1_Emu_A0_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A0_gbtrxrdy_y.append(value)
                    elif selectMD1 and selectEmu and selectA1:
                        MD1_Emu_A1_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A1_gbtrxrdy_y.append(value)
                    elif selectMD1 and selectEmu and selectB0:
                        MD1_Emu_B0_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B0_gbtrxrdy_y.append(value)
                    elif selectMD1 and selectEmu and selectB1:
                        MD1_Emu_B1_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B1_gbtrxrdy_y.append(value)
                    elif selectMD2 and selectEmu and selectA0:
                        MD2_Emu_A0_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A0_gbtrxrdy_y.append(value)
                    elif selectMD2 and selectEmu and selectA1:
                        MD2_Emu_A1_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A1_gbtrxrdy_y.append(value)
                    elif selectMD2 and selectEmu and selectB0:
                        MD2_Emu_B0_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B0_gbtrxrdy_y.append(value)
                    elif selectMD2 and selectEmu and selectB1:
                        MD2_Emu_B1_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B1_gbtrxrdy_y.append(value)
                    elif selectMD3 and selectEmu and selectA0:
                        MD3_Emu_A0_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A0_gbtrxrdy_y.append(value)
                    elif selectMD3 and selectEmu and selectA1:
                        MD3_Emu_A1_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A1_gbtrxrdy_y.append(value)
                    elif selectMD3 and selectEmu and selectB0:
                        MD3_Emu_B0_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B0_gbtrxrdy_y.append(value)
                    elif selectMD3 and selectEmu and selectB1:
                        MD3_Emu_B1_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B1_gbtrxrdy_y.append(value)
                    elif selectMD4 and selectEmu and selectA0:
                        MD4_Emu_A0_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A0_gbtrxrdy_y.append(value)
                    elif selectMD4 and selectEmu and selectA1:
                        MD4_Emu_A1_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A1_gbtrxrdy_y.append(value)
                    elif selectMD4 and selectEmu and selectB0:
                        MD4_Emu_B0_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B0_gbtrxrdy_y.append(value)
                    elif selectMD4 and selectEmu and selectB1:
                        MD4_Emu_B1_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B1_gbtrxrdy_y.append(value)
                    elif selectMD1 and selectPpr and selectA0:
                        MD1_Ppr_A0_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A0_gbtrxrdy_y.append(value)
                    elif selectMD1 and selectPpr and selectA1:
                        MD1_Ppr_A1_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A1_gbtrxrdy_y.append(value)
                    elif selectMD1 and selectPpr and selectB0:
                        MD1_Ppr_B0_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B0_gbtrxrdy_y.append(value)
                    elif selectMD1 and selectPpr and selectB1:
                        MD1_Ppr_B1_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B1_gbtrxrdy_y.append(value)
                    elif selectMD2 and selectPpr and selectA0:
                        MD2_Ppr_A0_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A0_gbtrxrdy_y.append(value)
                    elif selectMD2 and selectPpr and selectA1:
                        MD2_Ppr_A1_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A1_gbtrxrdy_y.append(value)
                    elif selectMD2 and selectPpr and selectB0:
                        MD2_Ppr_B0_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B0_gbtrxrdy_y.append(value)
                    elif selectMD2 and selectPpr and selectB1:
                        MD2_Ppr_B1_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B1_gbtrxrdy_y.append(value)
                    elif selectMD3 and selectPpr and selectA0:
                        MD3_Ppr_A0_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A0_gbtrxrdy_y.append(value)
                    elif selectMD3 and selectPpr and selectA1:
                        MD3_Ppr_A1_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A1_gbtrxrdy_y.append(value)
                    elif selectMD3 and selectPpr and selectB0:
                        MD3_Ppr_B0_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B0_gbtrxrdy_y.append(value)
                    elif selectMD3 and selectPpr and selectB1:
                        MD3_Ppr_B1_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B1_gbtrxrdy_y.append(value)
                    elif selectMD4 and selectPpr and selectA0:
                        MD4_Ppr_A0_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A0_gbtrxrdy_y.append(value)
                    elif selectMD4 and selectPpr and selectA1:
                        MD4_Ppr_A1_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A1_gbtrxrdy_y.append(value)
                    elif selectMD4 and selectPpr and selectB0:
                        MD4_Ppr_B0_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B0_gbtrxrdy_y.append(value)
                    elif selectMD4 and selectPpr and selectB1:
                        MD4_Ppr_B1_gbtrxrdy_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B1_gbtrxrdy_y.append(value)

                if key == 'crc':
                    if selectMD1 and selectEmu and selectA0:
                        MD1_Emu_A0_crc_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A0_crc_y.append(value)
                    elif selectMD1 and selectEmu and selectA1:
                        MD1_Emu_A1_crc_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A1_crc_y.append(value)
                    elif selectMD1 and selectEmu and selectB0:
                        MD1_Emu_B0_crc_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B0_crc_y.append(value)
                    elif selectMD1 and selectEmu and selectB1:
                        MD1_Emu_B1_crc_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B1_crc_y.append(value)
                    elif selectMD2 and selectEmu and selectA0:
                        MD2_Emu_A0_crc_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A0_crc_y.append(value)
                    elif selectMD2 and selectEmu and selectA1:
                        MD2_Emu_A1_crc_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A1_crc_y.append(value)
                    elif selectMD2 and selectEmu and selectB0:
                        MD2_Emu_B0_crc_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B0_crc_y.append(value)
                    elif selectMD2 and selectEmu and selectB1:
                        MD2_Emu_B1_crc_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B1_crc_y.append(value)
                    elif selectMD3 and selectEmu and selectA0:
                        MD3_Emu_A0_crc_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A0_crc_y.append(value)
                    elif selectMD3 and selectEmu and selectA1:
                        MD3_Emu_A1_crc_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A1_crc_y.append(value)
                    elif selectMD3 and selectEmu and selectB0:
                        MD3_Emu_B0_crc_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B0_crc_y.append(value)
                    elif selectMD3 and selectEmu and selectB1:
                        MD3_Emu_B1_crc_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B1_crc_y.append(value)
                    elif selectMD4 and selectEmu and selectA0:
                        MD4_Emu_A0_crc_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A0_crc_y.append(value)
                    elif selectMD4 and selectEmu and selectA1:
                        MD4_Emu_A1_crc_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A1_crc_y.append(value)
                    elif selectMD4 and selectEmu and selectB0:
                        MD4_Emu_B0_crc_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B0_crc_y.append(value)
                    elif selectMD4 and selectEmu and selectB1:
                        MD4_Emu_B1_crc_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B1_crc_y.append(value)
                    elif selectMD1 and selectPpr and selectA0:
                        MD1_Ppr_A0_crc_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A0_crc_y.append(value)
                    elif selectMD1 and selectPpr and selectA1:
                        MD1_Ppr_A1_crc_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A1_crc_y.append(value)
                    elif selectMD1 and selectPpr and selectB0:
                        MD1_Ppr_B0_crc_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B0_crc_y.append(value)
                    elif selectMD1 and selectPpr and selectB1:
                        MD1_Ppr_B1_crc_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B1_crc_y.append(value)
                    elif selectMD2 and selectPpr and selectA0:
                        MD2_Ppr_A0_crc_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A0_crc_y.append(value)
                    elif selectMD2 and selectPpr and selectA1:
                        MD2_Ppr_A1_crc_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A1_crc_y.append(value)
                    elif selectMD2 and selectPpr and selectB0:
                        MD2_Ppr_B0_crc_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B0_crc_y.append(value)
                    elif selectMD2 and selectPpr and selectB1:
                        MD2_Ppr_B1_crc_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B1_crc_y.append(value)
                    elif selectMD3 and selectPpr and selectA0:
                        MD3_Ppr_A0_crc_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A0_crc_y.append(value)
                    elif selectMD3 and selectPpr and selectA1:
                        MD3_Ppr_A1_crc_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A1_crc_y.append(value)
                    elif selectMD3 and selectPpr and selectB0:
                        MD3_Ppr_B0_crc_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B0_crc_y.append(value)
                    elif selectMD3 and selectPpr and selectB1:
                        MD3_Ppr_B1_crc_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B1_crc_y.append(value)
                    elif selectMD4 and selectPpr and selectA0:
                        MD4_Ppr_A0_crc_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A0_crc_y.append(value)
                    elif selectMD4 and selectPpr and selectA1:
                        MD4_Ppr_A1_crc_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A1_crc_y.append(value)
                    elif selectMD4 and selectPpr and selectB0:
                        MD4_Ppr_B0_crc_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B0_crc_y.append(value)
                    elif selectMD4 and selectPpr and selectB1:
                        MD4_Ppr_B1_crc_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B1_crc_y.append(value)

                if key == 'ber':
                    if selectMD1 and selectEmu and selectA0:
                        MD1_Emu_A0_ber_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A0_ber_y.append(value)
                    elif selectMD1 and selectEmu and selectA1:
                        MD1_Emu_A1_ber_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A1_ber_y.append(value)
                    elif selectMD1 and selectEmu and selectB0:
                        MD1_Emu_B0_ber_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B0_ber_y.append(value)
                    elif selectMD1 and selectEmu and selectB1:
                        MD1_Emu_B1_ber_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B1_ber_y.append(value)
                    elif selectMD2 and selectEmu and selectA0:
                        MD2_Emu_A0_ber_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A0_ber_y.append(value)
                    elif selectMD2 and selectEmu and selectA1:
                        MD2_Emu_A1_ber_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A1_ber_y.append(value)
                    elif selectMD2 and selectEmu and selectB0:
                        MD2_Emu_B0_ber_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B0_ber_y.append(value)
                    elif selectMD2 and selectEmu and selectB1:
                        MD2_Emu_B1_ber_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B1_ber_y.append(value)
                    elif selectMD3 and selectEmu and selectA0:
                        MD3_Emu_A0_ber_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A0_ber_y.append(value)
                    elif selectMD3 and selectEmu and selectA1:
                        MD3_Emu_A1_ber_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A1_ber_y.append(value)
                    elif selectMD3 and selectEmu and selectB0:
                        MD3_Emu_B0_ber_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B0_ber_y.append(value)
                    elif selectMD3 and selectEmu and selectB1:
                        MD3_Emu_B1_ber_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B1_ber_y.append(value)
                    elif selectMD4 and selectEmu and selectA0:
                        MD4_Emu_A0_ber_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A0_ber_y.append(value)
                    elif selectMD4 and selectEmu and selectA1:
                        MD4_Emu_A1_ber_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A1_ber_y.append(value)
                    elif selectMD4 and selectEmu and selectB0:
                        MD4_Emu_B0_ber_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B0_ber_y.append(value)
                    elif selectMD4 and selectEmu and selectB1:
                        MD4_Emu_B1_ber_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B1_ber_y.append(value)
                    elif selectMD1 and selectPpr and selectA0:
                        MD1_Ppr_A0_ber_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A0_ber_y.append(value)
                    elif selectMD1 and selectPpr and selectA1:
                        MD1_Ppr_A1_ber_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A1_ber_y.append(value)
                    elif selectMD1 and selectPpr and selectB0:
                        MD1_Ppr_B0_ber_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B0_ber_y.append(value)
                    elif selectMD1 and selectPpr and selectB1:
                        MD1_Ppr_B1_ber_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B1_ber_y.append(value)
                    elif selectMD2 and selectPpr and selectA0:
                        MD2_Ppr_A0_ber_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A0_ber_y.append(value)
                    elif selectMD2 and selectPpr and selectA1:
                        MD2_Ppr_A1_ber_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A1_ber_y.append(value)
                    elif selectMD2 and selectPpr and selectB0:
                        MD2_Ppr_B0_ber_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B0_ber_y.append(value)
                    elif selectMD2 and selectPpr and selectB1:
                        MD2_Ppr_B1_ber_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B1_ber_y.append(value)
                    elif selectMD3 and selectPpr and selectA0:
                        MD3_Ppr_A0_ber_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A0_ber_y.append(value)
                    elif selectMD3 and selectPpr and selectA1:
                        MD3_Ppr_A1_ber_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A1_ber_y.append(value)
                    elif selectMD3 and selectPpr and selectB0:
                        MD3_Ppr_B0_ber_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B0_ber_y.append(value)
                    elif selectMD3 and selectPpr and selectB1:
                        MD3_Ppr_B1_ber_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B1_ber_y.append(value)
                    elif selectMD4 and selectPpr and selectA0:
                        MD4_Ppr_A0_ber_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A0_ber_y.append(value)
                    elif selectMD4 and selectPpr and selectA1:
                        MD4_Ppr_A1_ber_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A1_ber_y.append(value)
                    elif selectMD4 and selectPpr and selectB0:
                        MD4_Ppr_B0_ber_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B0_ber_y.append(value)
                    elif selectMD4 and selectPpr and selectB1:
                        MD4_Ppr_B1_ber_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B1_ber_y.append(value)

                if key == 'latency':
                    if selectMD1 and selectEmu and selectA0:
                        MD1_Emu_A0_latency_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A0_latency_y.append(value)
                    elif selectMD1 and selectEmu and selectA1:
                        MD1_Emu_A1_latency_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A1_latency_y.append(value)
                    elif selectMD1 and selectEmu and selectB0:
                        MD1_Emu_B0_latency_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B0_latency_y.append(value)
                    elif selectMD1 and selectEmu and selectB1:
                        MD1_Emu_B1_latency_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B1_latency_y.append(value)
                    elif selectMD2 and selectEmu and selectA0:
                        MD2_Emu_A0_latency_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A0_latency_y.append(value)
                    elif selectMD2 and selectEmu and selectA1:
                        MD2_Emu_A1_latency_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A1_latency_y.append(value)
                    elif selectMD2 and selectEmu and selectB0:
                        MD2_Emu_B0_latency_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B0_latency_y.append(value)
                    elif selectMD2 and selectEmu and selectB1:
                        MD2_Emu_B1_latency_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B1_latency_y.append(value)
                    elif selectMD3 and selectEmu and selectA0:
                        MD3_Emu_A0_latency_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A0_latency_y.append(value)
                    elif selectMD3 and selectEmu and selectA1:
                        MD3_Emu_A1_latency_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A1_latency_y.append(value)
                    elif selectMD3 and selectEmu and selectB0:
                        MD3_Emu_B0_latency_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B0_latency_y.append(value)
                    elif selectMD3 and selectEmu and selectB1:
                        MD3_Emu_B1_latency_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B1_latency_y.append(value)
                    elif selectMD4 and selectEmu and selectA0:
                        MD4_Emu_A0_latency_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A0_latency_y.append(value)
                    elif selectMD4 and selectEmu and selectA1:
                        MD4_Emu_A1_latency_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A1_latency_y.append(value)
                    elif selectMD4 and selectEmu and selectB0:
                        MD4_Emu_B0_latency_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B0_latency_y.append(value)
                    elif selectMD4 and selectEmu and selectB1:
                        MD4_Emu_B1_latency_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B1_latency_y.append(value)
                    elif selectMD1 and selectPpr and selectA0:
                        MD1_Ppr_A0_latency_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A0_latency_y.append(value)
                    elif selectMD1 and selectPpr and selectA1:
                        MD1_Ppr_A1_latency_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A1_latency_y.append(value)
                    elif selectMD1 and selectPpr and selectB0:
                        MD1_Ppr_B0_latency_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B0_latency_y.append(value)
                    elif selectMD1 and selectPpr and selectB1:
                        MD1_Ppr_B1_latency_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B1_latency_y.append(value)
                    elif selectMD2 and selectPpr and selectA0:
                        MD2_Ppr_A0_latency_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A0_latency_y.append(value)
                    elif selectMD2 and selectPpr and selectA1:
                        MD2_Ppr_A1_latency_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A1_latency_y.append(value)
                    elif selectMD2 and selectPpr and selectB0:
                        MD2_Ppr_B0_latency_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B0_latency_y.append(value)
                    elif selectMD2 and selectPpr and selectB1:
                        MD2_Ppr_B1_latency_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B1_latency_y.append(value)
                    elif selectMD3 and selectPpr and selectA0:
                        MD3_Ppr_A0_latency_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A0_latency_y.append(value)
                    elif selectMD3 and selectPpr and selectA1:
                        MD3_Ppr_A1_latency_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A1_latency_y.append(value)
                    elif selectMD3 and selectPpr and selectB0:
                        MD3_Ppr_B0_latency_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B0_latency_y.append(value)
                    elif selectMD3 and selectPpr and selectB1:
                        MD3_Ppr_B1_latency_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B1_latency_y.append(value)
                    elif selectMD4 and selectPpr and selectA0:
                        MD4_Ppr_A0_latency_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A0_latency_y.append(value)
                    elif selectMD4 and selectPpr and selectA1:
                        MD4_Ppr_A1_latency_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A1_latency_y.append(value)
                    elif selectMD4 and selectPpr and selectB0:
                        MD4_Ppr_B0_latency_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B0_latency_y.append(value)
                    elif selectMD4 and selectPpr and selectB1:
                        MD4_Ppr_B1_latency_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B1_latency_y.append(value)

            # Reset Selection
            selectMD1 = 0
            selectMD2 = 0
            selectMD3 = 0
            selectMD4 = 0
            selectEmu = 0
            selectPpr = 0
            selectA0 = 0
            selectA1 = 0
            selectB0 = 0
            selectB1 = 0

        print(f'Number of Events: {nevents}')

        ### DataFrames ###
        # gbtrx_rdy
        # MD1 - Emu
        df_gbtrxrdy_MD1EmuA0 = pd.DataFrame( {'name': ['9000001 - Emu - Uplink A0']*len(MD1_Emu_A0_gbtrxrdy_x), #Fix Naming Nomenclature
                                              'x'   : MD1_Emu_A0_gbtrxrdy_x,
                                              'y'   : MD1_Emu_A0_gbtrxrdy_y} )
        df_gbtrxrdy_MD1EmuA1 = pd.DataFrame( {'name': ['9000001 - Emu - Uplink A1']*len(MD1_Emu_A1_gbtrxrdy_x),
                                              'x'   : MD1_Emu_A1_gbtrxrdy_x,
                                              'y'   : MD1_Emu_A1_gbtrxrdy_y} )
        df_gbtrxrdy_MD1EmuB0 = pd.DataFrame( {'name': ['9000001 - Emu - Uplink B0']*len(MD1_Emu_B0_gbtrxrdy_x),
                                              'x'   : MD1_Emu_B0_gbtrxrdy_x,
                                              'y'   : MD1_Emu_B0_gbtrxrdy_y} )
        df_gbtrxrdy_MD1EmuB1 = pd.DataFrame( {'name': ['9000001 - Emu - Uplink B1']*len(MD1_Emu_B1_gbtrxrdy_x),
                                              'x'   : MD1_Emu_B1_gbtrxrdy_x,
                                              'y'   : MD1_Emu_B1_gbtrxrdy_y} )

        df_gbtrxrdy_MD1Emu = pd.concat( [df_gbtrxrdy_MD1EmuA0, df_gbtrxrdy_MD1EmuA1, df_gbtrxrdy_MD1EmuB0, df_gbtrxrdy_MD1EmuB1] )

        # MD2 - Emu
        df_gbtrxrdy_MD2EmuA0 = pd.DataFrame( {'name': [' - Emu - Uplink A0']*len(MD2_Emu_A0_gbtrxrdy_x),
                                              'x'   : MD2_Emu_A0_gbtrxrdy_x,
                                              'y'   : MD2_Emu_A0_gbtrxrdy_y} )
        df_gbtrxrdy_MD2EmuA1 = pd.DataFrame( {'name': [' - Emu - Uplink A1']*len(MD2_Emu_A1_gbtrxrdy_x),
                                              'x'   : MD2_Emu_A1_gbtrxrdy_x,
                                              'y'   : MD2_Emu_A1_gbtrxrdy_y} )
        df_gbtrxrdy_MD2EmuB0 = pd.DataFrame( {'name': [' - Emu - Uplink B0']*len(MD2_Emu_B0_gbtrxrdy_x),
                                              'x'   : MD2_Emu_B0_gbtrxrdy_x,
                                              'y'   : MD2_Emu_B0_gbtrxrdy_y} )
        df_gbtrxrdy_MD2EmuB1 = pd.DataFrame( {'name': [' - Emu - Uplink B1']*len(MD2_Emu_B1_gbtrxrdy_x),
                                              'x'   : MD2_Emu_B1_gbtrxrdy_x,
                                              'y'   : MD2_Emu_B1_gbtrxrdy_y} )

        df_gbtrxrdy_MD2Emu = pd.concat( [df_gbtrxrdy_MD2EmuA0, df_gbtrxrdy_MD2EmuA1, df_gbtrxrdy_MD2EmuB0, df_gbtrxrdy_MD2EmuB1] )

        # MD3 - Emu
        df_gbtrxrdy_MD3EmuA0 = pd.DataFrame( {'name': [' - Emu - Uplink A0']*len(MD3_Emu_A0_gbtrxrdy_x),
                                              'x'   : MD3_Emu_A0_gbtrxrdy_x,
                                              'y'   : MD3_Emu_A0_gbtrxrdy_y} )
        df_gbtrxrdy_MD3EmuA1 = pd.DataFrame( {'name': [' - Emu - Uplink A1']*len(MD3_Emu_A1_gbtrxrdy_x),
                                              'x'   : MD3_Emu_A1_gbtrxrdy_x,
                                              'y'   : MD3_Emu_A1_gbtrxrdy_y} )
        df_gbtrxrdy_MD3EmuB0 = pd.DataFrame( {'name': [' - Emu - Uplink B0']*len(MD3_Emu_B0_gbtrxrdy_x),
                                              'x'   : MD3_Emu_B0_gbtrxrdy_x,
                                              'y'   : MD3_Emu_B0_gbtrxrdy_y} )
        df_gbtrxrdy_MD3EmuB1 = pd.DataFrame( {'name': [' - Emu - Uplink B1']*len(MD3_Emu_B1_gbtrxrdy_x),
                                              'x'   : MD3_Emu_B1_gbtrxrdy_x,
                                              'y'   : MD3_Emu_B1_gbtrxrdy_y} )

        df_gbtrxrdy_MD3Emu = pd.concat( [df_gbtrxrdy_MD3EmuA0, df_gbtrxrdy_MD3EmuA1, df_gbtrxrdy_MD3EmuB0, df_gbtrxrdy_MD3EmuB1] )

        # MD4 - Emu
        df_gbtrxrdy_MD4EmuA0 = pd.DataFrame( {'name': [' - Emu - Uplink A0']*len(MD4_Emu_A0_gbtrxrdy_x),
                                              'x'   : MD4_Emu_A0_gbtrxrdy_x,
                                              'y'   : MD4_Emu_A0_gbtrxrdy_y} )
        df_gbtrxrdy_MD4EmuA1 = pd.DataFrame( {'name': [' - Emu - Uplink A1']*len(MD4_Emu_A1_gbtrxrdy_x),
                                              'x'   : MD4_Emu_A1_gbtrxrdy_x,
                                              'y'   : MD4_Emu_A1_gbtrxrdy_y} )
        df_gbtrxrdy_MD4EmuB0 = pd.DataFrame( {'name': [' - Emu - Uplink B0']*len(MD4_Emu_B0_gbtrxrdy_x),
                                              'x'   : MD4_Emu_B0_gbtrxrdy_x,
                                              'y'   : MD4_Emu_B0_gbtrxrdy_y} )
        df_gbtrxrdy_MD4EmuB1 = pd.DataFrame( {'name': [' - Emu - Uplink B1']*len(MD4_Emu_B1_gbtrxrdy_x),
                                              'x'   : MD4_Emu_B1_gbtrxrdy_x,
                                              'y'   : MD4_Emu_B1_gbtrxrdy_y} )

        df_gbtrxrdy_MD4Emu = pd.concat( [df_gbtrxrdy_MD4EmuA0, df_gbtrxrdy_MD4EmuA1, df_gbtrxrdy_MD4EmuB0, df_gbtrxrdy_MD4EmuB1] )

        # MD1 - Ppr
        df_gbtrxrdy_MD1PprA0 = pd.DataFrame( {'name': ['9000001 - Ppr - Uplink A0']*len(MD1_Ppr_A0_gbtrxrdy_x),
                                              'x'   : MD1_Ppr_A0_gbtrxrdy_x,
                                              'y'   : MD1_Ppr_A0_gbtrxrdy_y} )
        df_gbtrxrdy_MD1PprA1 = pd.DataFrame( {'name': ['9000001 - Ppr - Uplink A1']*len(MD1_Ppr_A1_gbtrxrdy_x),
                                              'x'   : MD1_Ppr_A1_gbtrxrdy_x,
                                              'y'   : MD1_Ppr_A1_gbtrxrdy_y} )
        df_gbtrxrdy_MD1PprB0 = pd.DataFrame( {'name': ['9000001 - Ppr - Uplink B0']*len(MD1_Ppr_B0_gbtrxrdy_x),
                                              'x'   : MD1_Ppr_B0_gbtrxrdy_x,
                                              'y'   : MD1_Ppr_B0_gbtrxrdy_y} )
        df_gbtrxrdy_MD1PprB1 = pd.DataFrame( {'name': ['9000001 - Ppr - Uplink B1']*len(MD1_Ppr_B1_gbtrxrdy_x),
                                              'x'   : MD1_Ppr_B1_gbtrxrdy_x,
                                              'y'   : MD1_Ppr_B1_gbtrxrdy_y} )

        df_gbtrxrdy_MD1Ppr = pd.concat( [df_gbtrxrdy_MD1PprA0, df_gbtrxrdy_MD1PprA1, df_gbtrxrdy_MD1PprB0, df_gbtrxrdy_MD1PprB1] )

        # MD2 - Ppr
        df_gbtrxrdy_MD2PprA0 = pd.DataFrame( {'name': [' - Ppr - Uplink A0']*len(MD2_Ppr_A0_gbtrxrdy_x),
                                              'x'   : MD2_Ppr_A0_gbtrxrdy_x,
                                              'y'   : MD2_Ppr_A0_gbtrxrdy_y} )
        df_gbtrxrdy_MD2PprA1 = pd.DataFrame( {'name': [' - Ppr - Uplink A1']*len(MD2_Ppr_A1_gbtrxrdy_x),
                                              'x'   : MD2_Ppr_A1_gbtrxrdy_x,
                                              'y'   : MD2_Ppr_A1_gbtrxrdy_y} )
        df_gbtrxrdy_MD2PprB0 = pd.DataFrame( {'name': [' - Ppr - Uplink B0']*len(MD2_Ppr_B0_gbtrxrdy_x),
                                              'x'   : MD2_Ppr_B0_gbtrxrdy_x,
                                              'y'   : MD2_Ppr_B0_gbtrxrdy_y} )
        df_gbtrxrdy_MD2PprB1 = pd.DataFrame( {'name': [' - Ppr - Uplink B1']*len(MD2_Ppr_B1_gbtrxrdy_x),
                                              'x'   : MD2_Ppr_B1_gbtrxrdy_x,
                                              'y'   : MD2_Ppr_B1_gbtrxrdy_y} )

        df_gbtrxrdy_MD2Ppr = pd.concat( [df_gbtrxrdy_MD2PprA0, df_gbtrxrdy_MD2PprA1, df_gbtrxrdy_MD2PprB0, df_gbtrxrdy_MD2PprB1] )

        # MD3 - Ppr
        df_gbtrxrdy_MD3PprA0 = pd.DataFrame( {'name': [' - Ppr - Uplink A0']*len(MD3_Ppr_A0_gbtrxrdy_x),
                                              'x'   : MD3_Ppr_A0_gbtrxrdy_x,
                                              'y'   : MD3_Ppr_A0_gbtrxrdy_y} )
        df_gbtrxrdy_MD3PprA1 = pd.DataFrame( {'name': [' - Ppr - Uplink A1']*len(MD3_Ppr_A1_gbtrxrdy_x),
                                              'x'   : MD3_Ppr_A1_gbtrxrdy_x,
                                              'y'   : MD3_Ppr_A1_gbtrxrdy_y} )
        df_gbtrxrdy_MD3PprB0 = pd.DataFrame( {'name': [' - Ppr - Uplink B0']*len(MD3_Ppr_B0_gbtrxrdy_x),
                                              'x'   : MD3_Ppr_B0_gbtrxrdy_x,
                                              'y'   : MD3_Ppr_B0_gbtrxrdy_y} )
        df_gbtrxrdy_MD3PprB1 = pd.DataFrame( {'name': [' - Ppr - Uplink B1']*len(MD3_Ppr_B1_gbtrxrdy_x),
                                              'x'   : MD3_Ppr_B1_gbtrxrdy_x,
                                              'y'   : MD3_Ppr_B1_gbtrxrdy_y} )

        df_gbtrxrdy_MD3Ppr = pd.concat( [df_gbtrxrdy_MD3PprA0, df_gbtrxrdy_MD3PprA1, df_gbtrxrdy_MD3PprB0, df_gbtrxrdy_MD3PprB1] )

        # MD4 - Ppr
        df_gbtrxrdy_MD4PprA0 = pd.DataFrame( {'name': [' - Ppr - Uplink A0']*len(MD4_Ppr_A0_gbtrxrdy_x),
                                              'x'   : MD4_Ppr_A0_gbtrxrdy_x,
                                              'y'   : MD4_Ppr_A0_gbtrxrdy_y} )
        df_gbtrxrdy_MD4PprA1 = pd.DataFrame( {'name': [' - Ppr - Uplink A1']*len(MD4_Ppr_A1_gbtrxrdy_x),
                                              'x'   : MD4_Ppr_A1_gbtrxrdy_x,
                                              'y'   : MD4_Ppr_A1_gbtrxrdy_y} )
        df_gbtrxrdy_MD4PprB0 = pd.DataFrame( {'name': [' - Ppr - Uplink B0']*len(MD4_Ppr_B0_gbtrxrdy_x),
                                              'x'   : MD4_Ppr_B0_gbtrxrdy_x,
                                              'y'   : MD4_Ppr_B0_gbtrxrdy_y} )
        df_gbtrxrdy_MD4PprB1 = pd.DataFrame( {'name': [' - Ppr - Uplink B1']*len(MD4_Ppr_B1_gbtrxrdy_x),
                                              'x'   : MD4_Ppr_B1_gbtrxrdy_x,
                                              'y'   : MD4_Ppr_B1_gbtrxrdy_y} )

        df_gbtrxrdy_MD4Ppr = pd.concat( [df_gbtrxrdy_MD4PprA0, df_gbtrxrdy_MD4PprA1, df_gbtrxrdy_MD4PprB0, df_gbtrxrdy_MD4PprB1] )



        # crc
        # MD1 - Emu
        df_crc_MD1EmuA0 = pd.DataFrame( {'name': ['9000001 - Emu - Uplink A0']*len(MD1_Emu_A0_crc_x), #Fix Naming Nomenclature
                                         'x'   : MD1_Emu_A0_crc_x,
                                         'y'   : MD1_Emu_A0_crc_y} )
        df_crc_MD1EmuA1 = pd.DataFrame( {'name': ['9000001 - Emu - Uplink A1']*len(MD1_Emu_A1_crc_x),
                                         'x'   : MD1_Emu_A1_crc_x,
                                         'y'   : MD1_Emu_A1_crc_y} )
        df_crc_MD1EmuB0 = pd.DataFrame( {'name': ['9000001 - Emu - Uplink B0']*len(MD1_Emu_B0_crc_x),
                                         'x'   : MD1_Emu_B0_crc_x,
                                         'y'   : MD1_Emu_B0_crc_y} )
        df_crc_MD1EmuB1 = pd.DataFrame( {'name': ['9000001 - Emu - Uplink B1']*len(MD1_Emu_B1_crc_x),
                                         'x'   : MD1_Emu_B1_crc_x,
                                         'y'   : MD1_Emu_B1_crc_y} )

        df_crc_MD1Emu = pd.concat( [df_crc_MD1EmuA0, df_crc_MD1EmuA1, df_crc_MD1EmuB0, df_crc_MD1EmuB1] )

        # MD2 - Emu
        df_crc_MD2EmuA0 = pd.DataFrame( {'name': [' - Emu - Uplink A0']*len(MD2_Emu_A0_crc_x),
                                         'x'   : MD2_Emu_A0_crc_x,
                                         'y'   : MD2_Emu_A0_crc_y} )
        df_crc_MD2EmuA1 = pd.DataFrame( {'name': [' - Emu - Uplink A1']*len(MD2_Emu_A1_crc_x),
                                         'x'   : MD2_Emu_A1_crc_x,
                                         'y'   : MD2_Emu_A1_crc_y} )
        df_crc_MD2EmuB0 = pd.DataFrame( {'name': [' - Emu - Uplink B0']*len(MD2_Emu_B0_crc_x),
                                         'x'   : MD2_Emu_B0_crc_x,
                                         'y'   : MD2_Emu_B0_crc_y} )
        df_crc_MD2EmuB1 = pd.DataFrame( {'name': [' - Emu - Uplink B1']*len(MD2_Emu_B1_crc_x),
                                         'x'   : MD2_Emu_B1_crc_x,
                                         'y'   : MD2_Emu_B1_crc_y} )

        df_crc_MD2Emu = pd.concat( [df_crc_MD2EmuA0, df_crc_MD2EmuA1, df_crc_MD2EmuB0, df_crc_MD2EmuB1] )

        # MD3 - Emu
        df_crc_MD3EmuA0 = pd.DataFrame( {'name': [' - Emu - Uplink A0']*len(MD3_Emu_A0_crc_x),
                                         'x'   : MD3_Emu_A0_crc_x,
                                         'y'   : MD3_Emu_A0_crc_y} )
        df_crc_MD3EmuA1 = pd.DataFrame( {'name': [' - Emu - Uplink A1']*len(MD3_Emu_A1_crc_x),
                                         'x'   : MD3_Emu_A1_crc_x,
                                         'y'   : MD3_Emu_A1_crc_y} )
        df_crc_MD3EmuB0 = pd.DataFrame( {'name': [' - Emu - Uplink B0']*len(MD3_Emu_B0_crc_x),
                                         'x'   : MD3_Emu_B0_crc_x,
                                         'y'   : MD3_Emu_B0_crc_y} )
        df_crc_MD3EmuB1 = pd.DataFrame( {'name': [' - Emu - Uplink B1']*len(MD3_Emu_B1_crc_x),
                                         'x'   : MD3_Emu_B1_crc_x,
                                         'y'   : MD3_Emu_B1_crc_y} )

        df_crc_MD3Emu = pd.concat( [df_crc_MD3EmuA0, df_crc_MD3EmuA1, df_crc_MD3EmuB0, df_crc_MD3EmuB1] )

        # MD4 - Emu
        df_crc_MD4EmuA0 = pd.DataFrame( {'name': [' - Emu - Uplink A0']*len(MD4_Emu_A0_crc_x),
                                         'x'   : MD4_Emu_A0_crc_x,
                                         'y'   : MD4_Emu_A0_crc_y} )
        df_crc_MD4EmuA1 = pd.DataFrame( {'name': [' - Emu - Uplink A1']*len(MD4_Emu_A1_crc_x),
                                         'x'   : MD4_Emu_A1_crc_x,
                                         'y'   : MD4_Emu_A1_crc_y} )
        df_crc_MD4EmuB0 = pd.DataFrame( {'name': [' - Emu - Uplink B0']*len(MD4_Emu_B0_crc_x),
                                         'x'   : MD4_Emu_B0_crc_x,
                                         'y'   : MD4_Emu_B0_crc_y} )
        df_crc_MD4EmuB1 = pd.DataFrame( {'name': [' - Emu - Uplink B1']*len(MD4_Emu_B1_crc_x),
                                         'x'   : MD4_Emu_B1_crc_x,
                                         'y'   : MD4_Emu_B1_crc_y} )

        df_crc_MD4Emu = pd.concat( [df_crc_MD4EmuA0, df_crc_MD4EmuA1, df_crc_MD4EmuB0, df_crc_MD4EmuB1] )

        # MD1 - Ppr
        df_crc_MD1PprA0 = pd.DataFrame( {'name': ['9000001 - Ppr - Uplink A0']*len(MD1_Ppr_A0_crc_x),
                                         'x'   : MD1_Ppr_A0_crc_x,
                                         'y'   : MD1_Ppr_A0_crc_y} )
        df_crc_MD1PprA1 = pd.DataFrame( {'name': ['9000001 - Ppr - Uplink A1']*len(MD1_Ppr_A1_crc_x),
                                         'x'   : MD1_Ppr_A1_crc_x,
                                         'y'   : MD1_Ppr_A1_crc_y} )
        df_crc_MD1PprB0 = pd.DataFrame( {'name': ['9000001 - Ppr - Uplink B0']*len(MD1_Ppr_B0_crc_x),
                                         'x'   : MD1_Ppr_B0_crc_x,
                                         'y'   : MD1_Ppr_B0_crc_y} )
        df_crc_MD1PprB1 = pd.DataFrame( {'name': ['9000001 - Ppr - Uplink B1']*len(MD1_Ppr_B1_crc_x),
                                         'x'   : MD1_Ppr_B1_crc_x,
                                         'y'   : MD1_Ppr_B1_crc_y} )

        df_crc_MD1Ppr = pd.concat( [df_crc_MD1PprA0, df_crc_MD1PprA1, df_crc_MD1PprB0, df_crc_MD1PprB1] )

        # MD2 - Ppr
        df_crc_MD2PprA0 = pd.DataFrame( {'name': [' - Ppr - Uplink A0']*len(MD2_Ppr_A0_crc_x),
                                         'x'   : MD2_Ppr_A0_crc_x,
                                         'y'   : MD2_Ppr_A0_crc_y} )
        df_crc_MD2PprA1 = pd.DataFrame( {'name': [' - Ppr - Uplink A1']*len(MD2_Ppr_A1_crc_x),
                                         'x'   : MD2_Ppr_A1_crc_x,
                                         'y'   : MD2_Ppr_A1_crc_y} )
        df_crc_MD2PprB0 = pd.DataFrame( {'name': [' - Ppr - Uplink B0']*len(MD2_Ppr_B0_crc_x),
                                         'x'   : MD2_Ppr_B0_crc_x,
                                         'y'   : MD2_Ppr_B0_crc_y} )
        df_crc_MD2PprB1 = pd.DataFrame( {'name': [' - Ppr - Uplink B1']*len(MD2_Ppr_B1_crc_x),
                                         'x'   : MD2_Ppr_B1_crc_x,
                                         'y'   : MD2_Ppr_B1_crc_y} )

        df_crc_MD2Ppr = pd.concat( [df_crc_MD2PprA0, df_crc_MD2PprA1, df_crc_MD2PprB0, df_crc_MD2PprB1] )

        # MD3 - Ppr
        df_crc_MD3PprA0 = pd.DataFrame( {'name': [' - Ppr - Uplink A0']*len(MD3_Ppr_A0_crc_x),
                                         'x'   : MD3_Ppr_A0_crc_x,
                                         'y'   : MD3_Ppr_A0_crc_y} )
        df_crc_MD3PprA1 = pd.DataFrame( {'name': [' - Ppr - Uplink A1']*len(MD3_Ppr_A1_crc_x),
                                         'x'   : MD3_Ppr_A1_crc_x,
                                         'y'   : MD3_Ppr_A1_crc_y} )
        df_crc_MD3PprB0 = pd.DataFrame( {'name': [' - Ppr - Uplink B0']*len(MD3_Ppr_B0_crc_x),
                                         'x'   : MD3_Ppr_B0_crc_x,
                                         'y'   : MD3_Ppr_B0_crc_y} )
        df_crc_MD3PprB1 = pd.DataFrame( {'name': [' - Ppr - Uplink B1']*len(MD3_Ppr_B1_crc_x),
                                         'x'   : MD3_Ppr_B1_crc_x,
                                         'y'   : MD3_Ppr_B1_crc_y} )

        df_crc_MD3Ppr = pd.concat( [df_crc_MD3PprA0, df_crc_MD3PprA1, df_crc_MD3PprB0, df_crc_MD3PprB1] )

        # MD4 - Ppr
        df_crc_MD4PprA0 = pd.DataFrame( {'name': [' - Ppr - Uplink A0']*len(MD4_Ppr_A0_crc_x),
                                         'x'   : MD4_Ppr_A0_crc_x,
                                         'y'   : MD4_Ppr_A0_crc_y} )
        df_crc_MD4PprA1 = pd.DataFrame( {'name': [' - Ppr - Uplink A1']*len(MD4_Ppr_A1_crc_x),
                                         'x'   : MD4_Ppr_A1_crc_x,
                                         'y'   : MD4_Ppr_A1_crc_y} )
        df_crc_MD4PprB0 = pd.DataFrame( {'name': [' - Ppr - Uplink B0']*len(MD4_Ppr_B0_crc_x),
                                         'x'   : MD4_Ppr_B0_crc_x,
                                         'y'   : MD4_Ppr_B0_crc_y} )
        df_crc_MD4PprB1 = pd.DataFrame( {'name': [' - Ppr - Uplink B1']*len(MD4_Ppr_B1_crc_x),
                                         'x'   : MD4_Ppr_B1_crc_x,
                                         'y'   : MD4_Ppr_B1_crc_y} )

        df_crc_MD4Ppr = pd.concat( [df_crc_MD4PprA0, df_crc_MD4PprA1, df_crc_MD4PprB0, df_crc_MD4PprB1] )



        # ber
        # MD1 - Emu
        df_ber_MD1EmuA0 = pd.DataFrame( {'name': ['9000001 - Emu - Uplink A0']*len(MD1_Emu_A0_ber_x), #Fix Naming Nomenclature
                                         'x'   : MD1_Emu_A0_ber_x,
                                         'y'   : MD1_Emu_A0_ber_y} )
        df_ber_MD1EmuA1 = pd.DataFrame( {'name': ['9000001 - Emu - Uplink A1']*len(MD1_Emu_A1_ber_x),
                                         'x'   : MD1_Emu_A1_ber_x,
                                         'y'   : MD1_Emu_A1_ber_y} )
        df_ber_MD1EmuB0 = pd.DataFrame( {'name': ['9000001 - Emu - Uplink B0']*len(MD1_Emu_B0_ber_x),
                                         'x'   : MD1_Emu_B0_ber_x,
                                         'y'   : MD1_Emu_B0_ber_y} )
        df_ber_MD1EmuB1 = pd.DataFrame( {'name': ['9000001 - Emu - Uplink B1']*len(MD1_Emu_B1_ber_x),
                                         'x'   : MD1_Emu_B1_ber_x,
                                         'y'   : MD1_Emu_B1_ber_y} )

        df_ber_MD1Emu = pd.concat( [df_ber_MD1EmuA0, df_ber_MD1EmuA1, df_ber_MD1EmuB0, df_ber_MD1EmuB1] )

        # MD2 - Emu
        df_ber_MD2EmuA0 = pd.DataFrame( {'name': [' - Emu - Uplink A0']*len(MD2_Emu_A0_ber_x),
                                         'x'   : MD2_Emu_A0_ber_x,
                                         'y'   : MD2_Emu_A0_ber_y} )
        df_ber_MD2EmuA1 = pd.DataFrame( {'name': [' - Emu - Uplink A1']*len(MD2_Emu_A1_ber_x),
                                         'x'   : MD2_Emu_A1_ber_x,
                                         'y'   : MD2_Emu_A1_ber_y} )
        df_ber_MD2EmuB0 = pd.DataFrame( {'name': [' - Emu - Uplink B0']*len(MD2_Emu_B0_ber_x),
                                         'x'   : MD2_Emu_B0_ber_x,
                                         'y'   : MD2_Emu_B0_ber_y} )
        df_ber_MD2EmuB1 = pd.DataFrame( {'name': [' - Emu - Uplink B1']*len(MD2_Emu_B1_ber_x),
                                         'x'   : MD2_Emu_B1_ber_x,
                                         'y'   : MD2_Emu_B1_ber_y} )

        df_ber_MD2Emu = pd.concat( [df_ber_MD2EmuA0, df_ber_MD2EmuA1, df_ber_MD2EmuB0, df_ber_MD2EmuB1] )

        # MD3 - Emu
        df_ber_MD3EmuA0 = pd.DataFrame( {'name': [' - Emu - Uplink A0']*len(MD3_Emu_A0_ber_x),
                                         'x'   : MD3_Emu_A0_ber_x,
                                         'y'   : MD3_Emu_A0_ber_y} )
        df_ber_MD3EmuA1 = pd.DataFrame( {'name': [' - Emu - Uplink A1']*len(MD3_Emu_A1_ber_x),
                                         'x'   : MD3_Emu_A1_ber_x,
                                         'y'   : MD3_Emu_A1_ber_y} )
        df_ber_MD3EmuB0 = pd.DataFrame( {'name': [' - Emu - Uplink B0']*len(MD3_Emu_B0_ber_x),
                                         'x'   : MD3_Emu_B0_ber_x,
                                         'y'   : MD3_Emu_B0_ber_y} )
        df_ber_MD3EmuB1 = pd.DataFrame( {'name': [' - Emu - Uplink B1']*len(MD3_Emu_B1_ber_x),
                                         'x'   : MD3_Emu_B1_ber_x,
                                         'y'   : MD3_Emu_B1_ber_y} )

        df_ber_MD3Emu = pd.concat( [df_ber_MD3EmuA0, df_ber_MD3EmuA1, df_ber_MD3EmuB0, df_ber_MD3EmuB1] )

        # MD4 - Emu
        df_ber_MD4EmuA0 = pd.DataFrame( {'name': [' - Emu - Uplink A0']*len(MD4_Emu_A0_ber_x),
                                         'x'   : MD4_Emu_A0_ber_x,
                                         'y'   : MD4_Emu_A0_ber_y} )
        df_ber_MD4EmuA1 = pd.DataFrame( {'name': [' - Emu - Uplink A1']*len(MD4_Emu_A1_ber_x),
                                         'x'   : MD4_Emu_A1_ber_x,
                                         'y'   : MD4_Emu_A1_ber_y} )
        df_ber_MD4EmuB0 = pd.DataFrame( {'name': [' - Emu - Uplink B0']*len(MD4_Emu_B0_ber_x),
                                         'x'   : MD4_Emu_B0_ber_x,
                                         'y'   : MD4_Emu_B0_ber_y} )
        df_ber_MD4EmuB1 = pd.DataFrame( {'name': [' - Emu - Uplink B1']*len(MD4_Emu_B1_ber_x),
                                         'x'   : MD4_Emu_B1_ber_x,
                                         'y'   : MD4_Emu_B1_ber_y} )

        df_ber_MD4Emu = pd.concat( [df_ber_MD4EmuA0, df_ber_MD4EmuA1, df_ber_MD4EmuB0, df_ber_MD4EmuB1] )

        # MD1 - Ppr
        df_ber_MD1PprA0 = pd.DataFrame( {'name': ['9000001 - Ppr - Uplink A0']*len(MD1_Ppr_A0_ber_x),
                                         'x'   : MD1_Ppr_A0_ber_x,
                                         'y'   : MD1_Ppr_A0_ber_y} )
        df_ber_MD1PprA1 = pd.DataFrame( {'name': ['9000001 - Ppr - Uplink A1']*len(MD1_Ppr_A1_ber_x),
                                         'x'   : MD1_Ppr_A1_ber_x,
                                         'y'   : MD1_Ppr_A1_ber_y} )
        df_ber_MD1PprB0 = pd.DataFrame( {'name': ['9000001 - Ppr - Uplink B0']*len(MD1_Ppr_B0_ber_x),
                                         'x'   : MD1_Ppr_B0_ber_x,
                                         'y'   : MD1_Ppr_B0_ber_y} )
        df_ber_MD1PprB1 = pd.DataFrame( {'name': ['9000001 - Ppr - Uplink B1']*len(MD1_Ppr_B1_ber_x),
                                         'x'   : MD1_Ppr_B1_ber_x,
                                         'y'   : MD1_Ppr_B1_ber_y} )

        df_ber_MD1Ppr = pd.concat( [df_ber_MD1PprA0, df_ber_MD1PprA1, df_ber_MD1PprB0, df_ber_MD1PprB1] )

        # MD2 - Ppr
        df_ber_MD2PprA0 = pd.DataFrame( {'name': [' - Ppr - Uplink A0']*len(MD2_Ppr_A0_ber_x),
                                         'x'   : MD2_Ppr_A0_ber_x,
                                         'y'   : MD2_Ppr_A0_ber_y} )
        df_ber_MD2PprA1 = pd.DataFrame( {'name': [' - Ppr - Uplink A1']*len(MD2_Ppr_A1_ber_x),
                                         'x'   : MD2_Ppr_A1_ber_x,
                                         'y'   : MD2_Ppr_A1_ber_y} )
        df_ber_MD2PprB0 = pd.DataFrame( {'name': [' - Ppr - Uplink B0']*len(MD2_Ppr_B0_ber_x),
                                         'x'   : MD2_Ppr_B0_ber_x,
                                         'y'   : MD2_Ppr_B0_ber_y} )
        df_ber_MD2PprB1 = pd.DataFrame( {'name': [' - Ppr - Uplink B1']*len(MD2_Ppr_B1_ber_x),
                                         'x'   : MD2_Ppr_B1_ber_x,
                                         'y'   : MD2_Ppr_B1_ber_y} )

        df_ber_MD2Ppr = pd.concat( [df_ber_MD2PprA0, df_ber_MD2PprA1, df_ber_MD2PprB0, df_ber_MD2PprB1] )

        # MD3 - Ppr
        df_ber_MD3PprA0 = pd.DataFrame( {'name': [' - Ppr - Uplink A0']*len(MD3_Ppr_A0_ber_x),
                                         'x'   : MD3_Ppr_A0_ber_x,
                                         'y'   : MD3_Ppr_A0_ber_y} )
        df_ber_MD3PprA1 = pd.DataFrame( {'name': [' - Ppr - Uplink A1']*len(MD3_Ppr_A1_ber_x),
                                         'x'   : MD3_Ppr_A1_ber_x,
                                         'y'   : MD3_Ppr_A1_ber_y} )
        df_ber_MD3PprB0 = pd.DataFrame( {'name': [' - Ppr - Uplink B0']*len(MD3_Ppr_B0_ber_x),
                                         'x'   : MD3_Ppr_B0_ber_x,
                                         'y'   : MD3_Ppr_B0_ber_y} )
        df_ber_MD3PprB1 = pd.DataFrame( {'name': [' - Ppr - Uplink B1']*len(MD3_Ppr_B1_ber_x),
                                         'x'   : MD3_Ppr_B1_ber_x,
                                         'y'   : MD3_Ppr_B1_ber_y} )

        df_ber_MD3Ppr = pd.concat( [df_ber_MD3PprA0, df_ber_MD3PprA1, df_ber_MD3PprB0, df_ber_MD3PprB1] )

        # MD4 - Ppr
        df_ber_MD4PprA0 = pd.DataFrame( {'name': [' - Ppr - Uplink A0']*len(MD4_Ppr_A0_ber_x),
                                         'x'   : MD4_Ppr_A0_ber_x,
                                         'y'   : MD4_Ppr_A0_ber_y} )
        df_ber_MD4PprA1 = pd.DataFrame( {'name': [' - Ppr - Uplink A1']*len(MD4_Ppr_A1_ber_x),
                                         'x'   : MD4_Ppr_A1_ber_x,
                                         'y'   : MD4_Ppr_A1_ber_y} )
        df_ber_MD4PprB0 = pd.DataFrame( {'name': [' - Ppr - Uplink B0']*len(MD4_Ppr_B0_ber_x),
                                         'x'   : MD4_Ppr_B0_ber_x,
                                         'y'   : MD4_Ppr_B0_ber_y} )
        df_ber_MD4PprB1 = pd.DataFrame( {'name': [' - Ppr - Uplink B1']*len(MD4_Ppr_B1_ber_x),
                                         'x'   : MD4_Ppr_B1_ber_x,
                                         'y'   : MD4_Ppr_B1_ber_y} )

        df_ber_MD4Ppr = pd.concat( [df_ber_MD4PprA0, df_ber_MD4PprA1, df_ber_MD4PprB0, df_ber_MD4PprB1] )



        # latency
        # MD1 - Emu
        df_latency_MD1EmuA0 = pd.DataFrame( {'name': ['9000001 - Emu - Uplink A0']*len(MD1_Emu_A0_latency_x), #Fix Naming Nomenclature
                                             'x'   : MD1_Emu_A0_latency_x,
                                             'y'   : MD1_Emu_A0_latency_y} )
        df_latency_MD1EmuA1 = pd.DataFrame( {'name': ['9000001 - Emu - Uplink A1']*len(MD1_Emu_A1_latency_x),
                                             'x'   : MD1_Emu_A1_latency_x,
                                             'y'   : MD1_Emu_A1_latency_y} )
        df_latency_MD1EmuB0 = pd.DataFrame( {'name': ['9000001 - Emu - Uplink B0']*len(MD1_Emu_B0_latency_x),
                                             'x'   : MD1_Emu_B0_latency_x,
                                             'y'   : MD1_Emu_B0_latency_y} )
        df_latency_MD1EmuB1 = pd.DataFrame( {'name': ['9000001 - Emu - Uplink B1']*len(MD1_Emu_B1_latency_x),
                                             'x'   : MD1_Emu_B1_latency_x,
                                             'y'   : MD1_Emu_B1_latency_y} )

        df_latency_MD1Emu = pd.concat( [df_latency_MD1EmuA0, df_latency_MD1EmuA1, df_latency_MD1EmuB0, df_latency_MD1EmuB1] )

        # MD2 - Emu
        df_latency_MD2EmuA0 = pd.DataFrame( {'name': [' - Emu - Uplink A0']*len(MD2_Emu_A0_latency_x),
                                             'x'   : MD2_Emu_A0_latency_x,
                                             'y'   : MD2_Emu_A0_latency_y} )
        df_latency_MD2EmuA1 = pd.DataFrame( {'name': [' - Emu - Uplink A1']*len(MD2_Emu_A1_latency_x),
                                             'x'   : MD2_Emu_A1_latency_x,
                                             'y'   : MD2_Emu_A1_latency_y} )
        df_latency_MD2EmuB0 = pd.DataFrame( {'name': [' - Emu - Uplink B0']*len(MD2_Emu_B0_latency_x),
                                             'x'   : MD2_Emu_B0_latency_x,
                                             'y'   : MD2_Emu_B0_latency_y} )
        df_latency_MD2EmuB1 = pd.DataFrame( {'name': [' - Emu - Uplink B1']*len(MD2_Emu_B1_latency_x),
                                             'x'   : MD2_Emu_B1_latency_x,
                                             'y'   : MD2_Emu_B1_latency_y} )

        df_latency_MD2Emu = pd.concat( [df_latency_MD2EmuA0, df_latency_MD2EmuA1, df_latency_MD2EmuB0, df_latency_MD2EmuB1] )

        # MD3 - Emu
        df_latency_MD3EmuA0 = pd.DataFrame( {'name': [' - Emu - Uplink A0']*len(MD3_Emu_A0_latency_x),
                                             'x'   : MD3_Emu_A0_latency_x,
                                             'y'   : MD3_Emu_A0_latency_y} )
        df_latency_MD3EmuA1 = pd.DataFrame( {'name': [' - Emu - Uplink A1']*len(MD3_Emu_A1_latency_x),
                                             'x'   : MD3_Emu_A1_latency_x,
                                             'y'   : MD3_Emu_A1_latency_y} )
        df_latency_MD3EmuB0 = pd.DataFrame( {'name': [' - Emu - Uplink B0']*len(MD3_Emu_B0_latency_x),
                                             'x'   : MD3_Emu_B0_latency_x,
                                             'y'   : MD3_Emu_B0_latency_y} )
        df_latency_MD3EmuB1 = pd.DataFrame( {'name': [' - Emu - Uplink B1']*len(MD3_Emu_B1_latency_x),
                                             'x'   : MD3_Emu_B1_latency_x,
                                             'y'   : MD3_Emu_B1_latency_y} )

        df_latency_MD3Emu = pd.concat( [df_latency_MD3EmuA0, df_latency_MD3EmuA1, df_latency_MD3EmuB0, df_latency_MD3EmuB1] )

        # MD4 - Emu
        df_latency_MD4EmuA0 = pd.DataFrame( {'name': [' - Emu - Uplink A0']*len(MD4_Emu_A0_latency_x),
                                             'x'   : MD4_Emu_A0_latency_x,
                                             'y'   : MD4_Emu_A0_latency_y} )
        df_latency_MD4EmuA1 = pd.DataFrame( {'name': [' - Emu - Uplink A1']*len(MD4_Emu_A1_latency_x),
                                             'x'   : MD4_Emu_A1_latency_x,
                                             'y'   : MD4_Emu_A1_latency_y} )
        df_latency_MD4EmuB0 = pd.DataFrame( {'name': [' - Emu - Uplink B0']*len(MD4_Emu_B0_latency_x),
                                             'x'   : MD4_Emu_B0_latency_x,
                                             'y'   : MD4_Emu_B0_latency_y} )
        df_latency_MD4EmuB1 = pd.DataFrame( {'name': [' - Emu - Uplink B1']*len(MD4_Emu_B1_latency_x),
                                             'x'   : MD4_Emu_B1_latency_x,
                                             'y'   : MD4_Emu_B1_latency_y} )

        df_latency_MD4Emu = pd.concat( [df_latency_MD4EmuA0, df_latency_MD4EmuA1, df_latency_MD4EmuB0, df_latency_MD4EmuB1] )

        # MD1 - Ppr
        df_latency_MD1PprA0 = pd.DataFrame( {'name': ['9000001 - Ppr - Uplink A0']*len(MD1_Ppr_A0_latency_x),
                                             'x'   : MD1_Ppr_A0_latency_x,
                                             'y'   : MD1_Ppr_A0_latency_y} )
        df_latency_MD1PprA1 = pd.DataFrame( {'name': ['9000001 - Ppr - Uplink A1']*len(MD1_Ppr_A1_latency_x),
                                             'x'   : MD1_Ppr_A1_latency_x,
                                             'y'   : MD1_Ppr_A1_latency_y} )
        df_latency_MD1PprB0 = pd.DataFrame( {'name': ['9000001 - Ppr - Uplink B0']*len(MD1_Ppr_B0_latency_x),
                                             'x'   : MD1_Ppr_B0_latency_x,
                                             'y'   : MD1_Ppr_B0_latency_y} )
        df_latency_MD1PprB1 = pd.DataFrame( {'name': ['9000001 - Ppr - Uplink B1']*len(MD1_Ppr_B1_latency_x),
                                             'x'   : MD1_Ppr_B1_latency_x,
                                             'y'   : MD1_Ppr_B1_latency_y} )

        df_latency_MD1Ppr = pd.concat( [df_latency_MD1PprA0, df_latency_MD1PprA1, df_latency_MD1PprB0, df_latency_MD1PprB1] )

        # MD2 - Ppr
        df_latency_MD2PprA0 = pd.DataFrame( {'name': [' - Ppr - Uplink A0']*len(MD2_Ppr_A0_latency_x),
                                             'x'   : MD2_Ppr_A0_latency_x,
                                             'y'   : MD2_Ppr_A0_latency_y} )
        df_latency_MD2PprA1 = pd.DataFrame( {'name': [' - Ppr - Uplink A1']*len(MD2_Ppr_A1_latency_x),
                                             'x'   : MD2_Ppr_A1_latency_x,
                                             'y'   : MD2_Ppr_A1_latency_y} )
        df_latency_MD2PprB0 = pd.DataFrame( {'name': [' - Ppr - Uplink B0']*len(MD2_Ppr_B0_latency_x),
                                             'x'   : MD2_Ppr_B0_latency_x,
                                             'y'   : MD2_Ppr_B0_latency_y} )
        df_latency_MD2PprB1 = pd.DataFrame( {'name': [' - Ppr - Uplink B1']*len(MD2_Ppr_B1_latency_x),
                                             'x'   : MD2_Ppr_B1_latency_x,
                                             'y'   : MD2_Ppr_B1_latency_y} )

        df_latency_MD2Ppr = pd.concat( [df_latency_MD2PprA0, df_latency_MD2PprA1, df_latency_MD2PprB0, df_latency_MD2PprB1] )

        # MD3 - Ppr
        df_latency_MD3PprA0 = pd.DataFrame( {'name': [' - Ppr - Uplink A0']*len(MD3_Ppr_A0_latency_x),
                                             'x'   : MD3_Ppr_A0_latency_x,
                                             'y'   : MD3_Ppr_A0_latency_y} )
        df_latency_MD3PprA1 = pd.DataFrame( {'name': [' - Ppr - Uplink A1']*len(MD3_Ppr_A1_latency_x),
                                             'x'   : MD3_Ppr_A1_latency_x,
                                             'y'   : MD3_Ppr_A1_latency_y} )
        df_latency_MD3PprB0 = pd.DataFrame( {'name': [' - Ppr - Uplink B0']*len(MD3_Ppr_B0_latency_x),
                                             'x'   : MD3_Ppr_B0_latency_x,
                                             'y'   : MD3_Ppr_B0_latency_y} )
        df_latency_MD3PprB1 = pd.DataFrame( {'name': [' - Ppr - Uplink B1']*len(MD3_Ppr_B1_latency_x),
                                             'x'   : MD3_Ppr_B1_latency_x,
                                             'y'   : MD3_Ppr_B1_latency_y} )

        df_latency_MD3Ppr = pd.concat( [df_latency_MD3PprA0, df_latency_MD3PprA1, df_latency_MD3PprB0, df_latency_MD3PprB1] )

        # MD4 - Ppr
        df_latency_MD4PprA0 = pd.DataFrame( {'name': [' - Ppr - Uplink A0']*len(MD4_Ppr_A0_latency_x),
                                             'x'   : MD4_Ppr_A0_latency_x,
                                             'y'   : MD4_Ppr_A0_latency_y} )
        df_latency_MD4PprA1 = pd.DataFrame( {'name': [' - Ppr - Uplink A1']*len(MD4_Ppr_A1_latency_x),
                                             'x'   : MD4_Ppr_A1_latency_x,
                                             'y'   : MD4_Ppr_A1_latency_y} )
        df_latency_MD4PprB0 = pd.DataFrame( {'name': [' - Ppr - Uplink B0']*len(MD4_Ppr_B0_latency_x),
                                             'x'   : MD4_Ppr_B0_latency_x,
                                             'y'   : MD4_Ppr_B0_latency_y} )
        df_latency_MD4PprB1 = pd.DataFrame( {'name': [' - Ppr - Uplink B1']*len(MD4_Ppr_B1_latency_x),
                                             'x'   : MD4_Ppr_B1_latency_x,
                                             'y'   : MD4_Ppr_B1_latency_y} )

        df_latency_MD4Ppr = pd.concat( [df_latency_MD4PprA0, df_latency_MD4PprA1, df_latency_MD4PprB0, df_latency_MD4PprB1] )

        

        ### Plotting ###
        # gbtrx_rdy
        fig_gbtrxrdy_MD1Emu = plotlyEX.line( df_gbtrxrdy_MD1Emu, x="x", y="y", color='name', labels={"x":"Time", "y":"gbtrx_rdy", "name":"Uplink Channel"})
        fig_gbtrxrdy_MD1Emu.update_layout(title='PPrEmu MD1: GBTRX_RDY')
        fig_gbtrxrdy_MD1Emu.write_html("plotly_MD1EmuGBTRXRDY_combined.html")

        fig_gbtrxrdy_MD2Emu = plotlyEX.line( df_gbtrxrdy_MD2Emu, x="x", y="y", color='name', labels={"x":"Time", "y":"gbtrx_rdy", "name":"Uplink Channel"})
        fig_gbtrxrdy_MD2Emu.update_layout(title='PPrEmu MD2: GBTRX_RDY')
        fig_gbtrxrdy_MD2Emu.write_html("plotly_MD2EmuGBTRXRDY_combined.html")

        fig_gbtrxrdy_MD3Emu = plotlyEX.line( df_gbtrxrdy_MD3Emu, x="x", y="y", color='name', labels={"x":"Time", "y":"gbtrx_rdy", "name":"Uplink Channel"})
        fig_gbtrxrdy_MD3Emu.update_layout(title='PPrEmu MD3: GBTRX_RDY')
        fig_gbtrxrdy_MD3Emu.write_html("plotly_MD3EmuGBTRXRDY_combined.html")

        fig_gbtrxrdy_MD4Emu = plotlyEX.line( df_gbtrxrdy_MD4Emu, x="x", y="y", color='name', labels={"x":"Time", "y":"gbtrx_rdy", "name":"Uplink Channel"})
        fig_gbtrxrdy_MD4Emu.update_layout(title='PPrEmu MD4: GBTRX_RDY')
        fig_gbtrxrdy_MD4Emu.write_html("plotly_MD4EmuGBTRXRDY_combined.html")

        fig_gbtrxrdy_MD1Ppr = plotlyEX.line( df_gbtrxrdy_MD1Ppr, x="x", y="y", color='name', labels={"x":"Time", "y":"gbtrx_rdy", "name":"Uplink Channel"})
        fig_gbtrxrdy_MD1Ppr.update_layout(title='PprGTH MD1: GBTRX_RDY')
        fig_gbtrxrdy_MD1Ppr.write_html("plotly_MD1PprGBTRXRDY_combined.html")

        fig_gbtrxrdy_MD2Ppr = plotlyEX.line( df_gbtrxrdy_MD2Ppr, x="x", y="y", color='name', labels={"x":"Time", "y":"gbtrx_rdy", "name":"Uplink Channel"})
        fig_gbtrxrdy_MD2Ppr.update_layout(title='PprGTH MD2: GBTRX_RDY')
        fig_gbtrxrdy_MD2Ppr.write_html("plotly_MD2PprGBTRXRDY_combined.html")

        fig_gbtrxrdy_MD3Ppr = plotlyEX.line( df_gbtrxrdy_MD3Ppr, x="x", y="y", color='name', labels={"x":"Time", "y":"gbtrx_rdy", "name":"Uplink Channel"})
        fig_gbtrxrdy_MD3Ppr.update_layout(title='PprGTH MD3: GBTRX_RDY')
        fig_gbtrxrdy_MD3Ppr.write_html("plotly_MD3PprGBTRXRDY_combined.html")

        fig_gbtrxrdy_MD4Ppr = plotlyEX.line( df_gbtrxrdy_MD4Ppr, x="x", y="y", color='name', labels={"x":"Time", "y":"gbtrx_rdy", "name":"Uplink Channel"})
        fig_gbtrxrdy_MD4Ppr.update_layout(title='PprGTH MD4: GBTRX_RDY')
        fig_gbtrxrdy_MD4Ppr.write_html("plotly_MD4PprGBTRXRDY_combined.html")

        # crc
        fig_crc_MD1Emu = plotlyEX.line( df_crc_MD1Emu, x="x", y="y", color='name', labels={"x":"Time", "y":"crc", "name":"Uplink Channel"})
        fig_crc_MD1Emu.update_layout(title='PPrEmu MD1: CRC')
        fig_crc_MD1Emu.write_html("plotly_MD1EmuCRC_combined.html")

        fig_crc_MD2Emu = plotlyEX.line( df_crc_MD2Emu, x="x", y="y", color='name', labels={"x":"Time", "y":"crc", "name":"Uplink Channel"})
        fig_crc_MD2Emu.update_layout(title='PPrEmu MD2: CRC')
        fig_crc_MD2Emu.write_html("plotly_MD2EmuCRC_combined.html")

        fig_crc_MD3Emu = plotlyEX.line( df_crc_MD3Emu, x="x", y="y", color='name', labels={"x":"Time", "y":"crc", "name":"Uplink Channel"})
        fig_crc_MD3Emu.update_layout(title='PPrEmu MD3: CRC')
        fig_crc_MD3Emu.write_html("plotly_MD3EmuCRC_combined.html")

        fig_crc_MD4Emu = plotlyEX.line( df_crc_MD4Emu, x="x", y="y", color='name', labels={"x":"Time", "y":"crc", "name":"Uplink Channel"})
        fig_crc_MD4Emu.update_layout(title='PPrEmu MD4: CRC')
        fig_crc_MD4Emu.write_html("plotly_MD4EmuCRC_combined.html")

        fig_crc_MD1Ppr = plotlyEX.line( df_crc_MD1Ppr, x="x", y="y", color='name', labels={"x":"Time", "y":"crc", "name":"Uplink Channel"})
        fig_crc_MD1Ppr.update_layout(title='PprGTH MD1: CRC')
        fig_crc_MD1Ppr.write_html("plotly_MD1PprCRC_combined.html")

        fig_crc_MD2Ppr = plotlyEX.line( df_crc_MD2Ppr, x="x", y="y", color='name', labels={"x":"Time", "y":"crc", "name":"Uplink Channel"})
        fig_crc_MD2Ppr.update_layout(title='PprGTH MD2: CRC')
        fig_crc_MD2Ppr.write_html("plotly_MD2PprCRC_combined.html")

        fig_crc_MD3Ppr = plotlyEX.line( df_crc_MD3Ppr, x="x", y="y", color='name', labels={"x":"Time", "y":"crc", "name":"Uplink Channel"})
        fig_crc_MD3Ppr.update_layout(title='PprGTH MD3: CRC')
        fig_crc_MD3Ppr.write_html("plotly_MD3PprCRC_combined.html")

        fig_crc_MD4Ppr = plotlyEX.line( df_crc_MD4Ppr, x="x", y="y", color='name', labels={"x":"Time", "y":"crc", "name":"Uplink Channel"})
        fig_crc_MD4Ppr.update_layout(title='PprGTH MD4: CRC')
        fig_crc_MD4Ppr.write_html("plotly_MD4PprCRC_combined.html")

        # ber
        fig_ber_MD1Emu = plotlyEX.line( df_ber_MD1Emu, x="x", y="y", color='name', labels={"x":"Time", "y":"ber", "name":"Uplink Channel"})
        fig_ber_MD1Emu.update_layout(title='PPrEmu MD1: BER')
        fig_ber_MD1Emu.write_html("plotly_MD1EmuBER_combined.html")

        fig_ber_MD2Emu = plotlyEX.line( df_ber_MD2Emu, x="x", y="y", color='name', labels={"x":"Time", "y":"ber", "name":"Uplink Channel"})
        fig_ber_MD2Emu.update_layout(title='PPrEmu MD2: BER')
        fig_ber_MD2Emu.write_html("plotly_MD2EmuBER_combined.html")

        fig_ber_MD3Emu = plotlyEX.line( df_ber_MD3Emu, x="x", y="y", color='name', labels={"x":"Time", "y":"ber", "name":"Uplink Channel"})
        fig_ber_MD3Emu.update_layout(title='PPrEmu MD3: BER')
        fig_ber_MD3Emu.write_html("plotly_MD3EmuBER_combined.html")

        fig_ber_MD4Emu = plotlyEX.line( df_ber_MD4Emu, x="x", y="y", color='name', labels={"x":"Time", "y":"ber", "name":"Uplink Channel"})
        fig_ber_MD4Emu.update_layout(title='PPrEmu MD4: BER')
        fig_ber_MD4Emu.write_html("plotly_MD4EmuBER_combined.html")

        fig_ber_MD1Ppr = plotlyEX.line( df_ber_MD1Ppr, x="x", y="y", color='name', labels={"x":"Time", "y":"ber", "name":"Uplink Channel"})
        fig_ber_MD1Ppr.update_layout(title='PprGTH MD1: BER')
        fig_ber_MD1Ppr.write_html("plotly_MD1PprBER_combined.html")

        fig_ber_MD2Ppr = plotlyEX.line( df_ber_MD2Ppr, x="x", y="y", color='name', labels={"x":"Time", "y":"ber", "name":"Uplink Channel"})
        fig_ber_MD2Ppr.update_layout(title='PprGTH MD2: BER')
        fig_ber_MD2Ppr.write_html("plotly_MD2PprBER_combined.html")

        fig_ber_MD3Ppr = plotlyEX.line( df_ber_MD3Ppr, x="x", y="y", color='name', labels={"x":"Time", "y":"ber", "name":"Uplink Channel"})
        fig_ber_MD3Ppr.update_layout(title='PprGTH MD3: BER')
        fig_ber_MD3Ppr.write_html("plotly_MD3PprBER_combined.html")

        fig_ber_MD4Ppr = plotlyEX.line( df_ber_MD4Ppr, x="x", y="y", color='name', labels={"x":"Time", "y":"ber", "name":"Uplink Channel"})
        fig_ber_MD4Ppr.update_layout(title='PprGTH MD4: BER')
        fig_ber_MD4Ppr.write_html("plotly_MD4PprBER_combined.html")

        # latency
        fig_latency_MD1Emu = plotlyEX.line( df_latency_MD1Emu, x="x", y="y", color='name', labels={"x":"Time", "y":"latency", "name":"Uplink Channel"})
        fig_latency_MD1Emu.update_layout(title='PPrEmu MD1: LATENCY')
        fig_latency_MD1Emu.write_html("plotly_MD1EmuLATENCY_combined.html")

        fig_latency_MD2Emu = plotlyEX.line( df_latency_MD2Emu, x="x", y="y", color='name', labels={"x":"Time", "y":"latency", "name":"Uplink Channel"})
        fig_latency_MD2Emu.update_layout(title='PPrEmu MD2: LATENCY')
        fig_latency_MD2Emu.write_html("plotly_MD2EmuLATENCY_combined.html")

        fig_latency_MD3Emu = plotlyEX.line( df_latency_MD3Emu, x="x", y="y", color='name', labels={"x":"Time", "y":"latency", "name":"Uplink Channel"})
        fig_latency_MD3Emu.update_layout(title='PPrEmu MD3: LATENCY')
        fig_latency_MD3Emu.write_html("plotly_MD3EmuLATENCY_combined.html")

        fig_latency_MD4Emu = plotlyEX.line( df_latency_MD4Emu, x="x", y="y", color='name', labels={"x":"Time", "y":"latency", "name":"Uplink Channel"})
        fig_latency_MD4Emu.update_layout(title='PPrEmu MD4: LATENCY')
        fig_latency_MD4Emu.write_html("plotly_MD4EmuLATENCY_combined.html")

        fig_latency_MD1Ppr = plotlyEX.line( df_latency_MD1Ppr, x="x", y="y", color='name', labels={"x":"Time", "y":"latency", "name":"Uplink Channel"})
        fig_latency_MD1Ppr.update_layout(title='PprGTH MD1: LATENCY')
        fig_latency_MD1Ppr.write_html("plotly_MD1PprLATENCY_combined.html")

        fig_latency_MD2Ppr = plotlyEX.line( df_latency_MD2Ppr, x="x", y="y", color='name', labels={"x":"Time", "y":"latency", "name":"Uplink Channel"})
        fig_latency_MD2Ppr.update_layout(title='PprGTH MD2: LATENCY')
        fig_latency_MD2Ppr.write_html("plotly_MD2PprLATENCY_combined.html")

        fig_latency_MD3Ppr = plotlyEX.line( df_latency_MD3Ppr, x="x", y="y", color='name', labels={"x":"Time", "y":"latency", "name":"Uplink Channel"})
        fig_latency_MD3Ppr.update_layout(title='PprGTH MD3: LATENCY')
        fig_latency_MD3Ppr.write_html("plotly_MD3PprLATENCY_combined.html")

        fig_latency_MD4Ppr = plotlyEX.line( df_latency_MD4Ppr, x="x", y="y", color='name', labels={"x":"Time", "y":"latency", "name":"Uplink Channel"})
        fig_latency_MD4Ppr.update_layout(title='PprGTH MD4: LATENCY')
        fig_latency_MD4Ppr.write_html("plotly_MD4PprLATENCY_combined.html")



        # Access xADC Table
        my_measurement = '"xADC"' #Table for xADC  Data
        print(f'my_measurement = {my_measurement}')

        # Access Channels
        my_channels = '"PPrEmu MD1", "PPrEmu MD2", "PPrEmu MD3", "PPrEmu MD4", "PprGTH MD1", "PprGTH MD2", "PprGTH MD3", "PprGTH MD4"'
        print(f'my_channels = {my_channels}')

        # Access Variables
        my_variables = '"db_mon_0.95v(vaux0)", "db_mon_1.0v(vaux5)", "db_mon_1.2v(vaux9)", "db_mon_1.5v(vaux3)", "db_mon_1.8v(vaux8)", "db_mon_2.5v(vaux1)", "db_mon_3.3v(vaux11)", "mb_mon_+5v(vaux10)", "mb_mon_-5v(vaux7)", "mb_mon_1.2v(vaux14)", "mb_mon_1.8v(vaux12)", "mb_mon_2.5v(vaux15)", "max_temp", "max_vccint", "min_vccint", "max_vccout", "min_vccout", "max_vram", "min_vram", "pgood_db_0v95", "pgood_db_1v0", "pgood_db_1v2", "pgood_db_1v5", "pgood_db_1v8", "pgood_db_2v5", "pgood_db_3v3", "pgood_mb_5v0", "pgood_mb_5v0_n", "pgood_mb_1v2", "pgood_mb_1v8", "pgood_mb_2v5"'
        print(f'my_variables = {my_variables}')

        # Defining formal SQL Query
        # Basic Query
        my_query = f'SELECT "PPrEmu MD1", "db_mon_0.95v(vaux0)" FROM "{my_measurement}" {my_time_range}'
        # Multivariable Query
        my_query = f'SELECT {my_channels}, {my_variables} FROM {my_measurement} WHERE {my_time_range}'
        print(f'my_query = {my_query}')
        print("----------------------------")

        result_xADC = client.query(my_query)
        print('xADC Results Obtained!')

        ############################
        ### xADC Data Processing ###
        ############################

        # Number of Events
        nevents = 0

        ### Flags for Filtering Data ###
        # Mini-Drawer
        selectMD1 = 0
        selectMD2 = 0
        selectMD3 = 0
        selectMD4 = 0

        # Emu/PPr
        selectEmu = 0
        selectPpr = 0

        # FPGA Side
        selectA = 0
        selectB = 0

        ### Arrays ###
        # DaughterBoard Currents
        #db_mon_0.95v(vaux0)
        MD1_Emu_A_DBC0v95_x = []
        MD1_Emu_A_DBC0v95_y = []
        MD1_Emu_B_DBC0v95_x = []
        MD1_Emu_B_DBC0v95_y = []

        MD2_Emu_A_DBC0v95_x = []
        MD2_Emu_A_DBC0v95_y = []
        MD2_Emu_B_DBC0v95_x = []
        MD2_Emu_B_DBC0v95_y = []

        MD3_Emu_A_DBC0v95_x = []
        MD3_Emu_A_DBC0v95_y = []
        MD3_Emu_B_DBC0v95_x = []
        MD3_Emu_B_DBC0v95_y = []

        MD4_Emu_A_DBC0v95_x = []
        MD4_Emu_A_DBC0v95_y = []
        MD4_Emu_B_DBC0v95_x = []
        MD4_Emu_B_DBC0v95_y = []

        MD1_Ppr_A_DBC0v95_x = []
        MD1_Ppr_A_DBC0v95_y = []
        MD1_Ppr_B_DBC0v95_x = []
        MD1_Ppr_B_DBC0v95_y = []

        MD2_Ppr_A_DBC0v95_x = []
        MD2_Ppr_A_DBC0v95_y = []
        MD2_Ppr_B_DBC0v95_x = []
        MD2_Ppr_B_DBC0v95_y = []

        MD3_Ppr_A_DBC0v95_x = []
        MD3_Ppr_A_DBC0v95_y = []
        MD3_Ppr_B_DBC0v95_x = []
        MD3_Ppr_B_DBC0v95_y = []

        MD4_Ppr_A_DBC0v95_x = []
        MD4_Ppr_A_DBC0v95_y = []
        MD4_Ppr_B_DBC0v95_x = []
        MD4_Ppr_B_DBC0v95_y = []

        #db_mon_1.0v(vaux5)
        MD1_Emu_A_DBC1v0_x = []
        MD1_Emu_A_DBC1v0_y = []
        MD1_Emu_B_DBC1v0_x = []
        MD1_Emu_B_DBC1v0_y = []

        MD2_Emu_A_DBC1v0_x = []
        MD2_Emu_A_DBC1v0_y = []
        MD2_Emu_B_DBC1v0_x = []
        MD2_Emu_B_DBC1v0_y = []

        MD3_Emu_A_DBC1v0_x = []
        MD3_Emu_A_DBC1v0_y = []
        MD3_Emu_B_DBC1v0_x = []
        MD3_Emu_B_DBC1v0_y = []

        MD4_Emu_A_DBC1v0_x = []
        MD4_Emu_A_DBC1v0_y = []
        MD4_Emu_B_DBC1v0_x = []
        MD4_Emu_B_DBC1v0_y = []

        MD1_Ppr_A_DBC1v0_x = []
        MD1_Ppr_A_DBC1v0_y = []
        MD1_Ppr_B_DBC1v0_x = []
        MD1_Ppr_B_DBC1v0_y = []

        MD2_Ppr_A_DBC1v0_x = []
        MD2_Ppr_A_DBC1v0_y = []
        MD2_Ppr_B_DBC1v0_x = []
        MD2_Ppr_B_DBC1v0_y = []

        MD3_Ppr_A_DBC1v0_x = []
        MD3_Ppr_A_DBC1v0_y = []
        MD3_Ppr_B_DBC1v0_x = []
        MD3_Ppr_B_DBC1v0_y = []

        MD4_Ppr_A_DBC1v0_x = []
        MD4_Ppr_A_DBC1v0_y = []
        MD4_Ppr_B_DBC1v0_x = []
        MD4_Ppr_B_DBC1v0_y = []

        #db_mon_1.2v(vaux9)
        MD1_Emu_A_DBC1v2_x = []
        MD1_Emu_A_DBC1v2_y = []
        MD1_Emu_B_DBC1v2_x = []
        MD1_Emu_B_DBC1v2_y = []

        MD2_Emu_A_DBC1v2_x = []
        MD2_Emu_A_DBC1v2_y = []
        MD2_Emu_B_DBC1v2_x = []
        MD2_Emu_B_DBC1v2_y = []

        MD3_Emu_A_DBC1v2_x = []
        MD3_Emu_A_DBC1v2_y = []
        MD3_Emu_B_DBC1v2_x = []
        MD3_Emu_B_DBC1v2_y = []

        MD4_Emu_A_DBC1v2_x = []
        MD4_Emu_A_DBC1v2_y = []
        MD4_Emu_B_DBC1v2_x = []
        MD4_Emu_B_DBC1v2_y = []

        MD1_Ppr_A_DBC1v2_x = []
        MD1_Ppr_A_DBC1v2_y = []
        MD1_Ppr_B_DBC1v2_x = []
        MD1_Ppr_B_DBC1v2_y = []

        MD2_Ppr_A_DBC1v2_x = []
        MD2_Ppr_A_DBC1v2_y = []
        MD2_Ppr_B_DBC1v2_x = []
        MD2_Ppr_B_DBC1v2_y = []

        MD3_Ppr_A_DBC1v2_x = []
        MD3_Ppr_A_DBC1v2_y = []
        MD3_Ppr_B_DBC1v2_x = []
        MD3_Ppr_B_DBC1v2_y = []

        MD4_Ppr_A_DBC1v2_x = []
        MD4_Ppr_A_DBC1v2_y = []
        MD4_Ppr_B_DBC1v2_x = []
        MD4_Ppr_B_DBC1v2_y = []

        #db_mon_1.5v(vaux3)
        MD1_Emu_A_DBC1v5_x = []
        MD1_Emu_A_DBC1v5_y = []
        MD1_Emu_B_DBC1v5_x = []
        MD1_Emu_B_DBC1v5_y = []

        MD2_Emu_A_DBC1v5_x = []
        MD2_Emu_A_DBC1v5_y = []
        MD2_Emu_B_DBC1v5_x = []
        MD2_Emu_B_DBC1v5_y = []

        MD3_Emu_A_DBC1v5_x = []
        MD3_Emu_A_DBC1v5_y = []
        MD3_Emu_B_DBC1v5_x = []
        MD3_Emu_B_DBC1v5_y = []

        MD4_Emu_A_DBC1v5_x = []
        MD4_Emu_A_DBC1v5_y = []
        MD4_Emu_B_DBC1v5_x = []
        MD4_Emu_B_DBC1v5_y = []

        MD1_Ppr_A_DBC1v5_x = []
        MD1_Ppr_A_DBC1v5_y = []
        MD1_Ppr_B_DBC1v5_x = []
        MD1_Ppr_B_DBC1v5_y = []

        MD2_Ppr_A_DBC1v5_x = []
        MD2_Ppr_A_DBC1v5_y = []
        MD2_Ppr_B_DBC1v5_x = []
        MD2_Ppr_B_DBC1v5_y = []

        MD3_Ppr_A_DBC1v5_x = []
        MD3_Ppr_A_DBC1v5_y = []
        MD3_Ppr_B_DBC1v5_x = []
        MD3_Ppr_B_DBC1v5_y = []

        MD4_Ppr_A_DBC1v5_x = []
        MD4_Ppr_A_DBC1v5_y = []
        MD4_Ppr_B_DBC1v5_x = []
        MD4_Ppr_B_DBC1v5_y = []

        #db_mon_1.8v(vaux8)
        MD1_Emu_A_DBC1v8_x = []
        MD1_Emu_A_DBC1v8_y = []
        MD1_Emu_B_DBC1v8_x = []
        MD1_Emu_B_DBC1v8_y = []

        MD2_Emu_A_DBC1v8_x = []
        MD2_Emu_A_DBC1v8_y = []
        MD2_Emu_B_DBC1v8_x = []
        MD2_Emu_B_DBC1v8_y = []

        MD3_Emu_A_DBC1v8_x = []
        MD3_Emu_A_DBC1v8_y = []
        MD3_Emu_B_DBC1v8_x = []
        MD3_Emu_B_DBC1v8_y = []

        MD4_Emu_A_DBC1v8_x = []
        MD4_Emu_A_DBC1v8_y = []
        MD4_Emu_B_DBC1v8_x = []
        MD4_Emu_B_DBC1v8_y = []

        MD1_Ppr_A_DBC1v8_x = []
        MD1_Ppr_A_DBC1v8_y = []
        MD1_Ppr_B_DBC1v8_x = []
        MD1_Ppr_B_DBC1v8_y = []

        MD2_Ppr_A_DBC1v8_x = []
        MD2_Ppr_A_DBC1v8_y = []
        MD2_Ppr_B_DBC1v8_x = []
        MD2_Ppr_B_DBC1v8_y = []

        MD3_Ppr_A_DBC1v8_x = []
        MD3_Ppr_A_DBC1v8_y = []
        MD3_Ppr_B_DBC1v8_x = []
        MD3_Ppr_B_DBC1v8_y = []

        MD4_Ppr_A_DBC1v8_x = []
        MD4_Ppr_A_DBC1v8_y = []
        MD4_Ppr_B_DBC1v8_x = []
        MD4_Ppr_B_DBC1v8_y = []

        #db_mon_2.5v(vaux1)
        MD1_Emu_A_DBC2v5_x = []
        MD1_Emu_A_DBC2v5_y = []
        MD1_Emu_B_DBC2v5_x = []
        MD1_Emu_B_DBC2v5_y = []

        MD2_Emu_A_DBC2v5_x = []
        MD2_Emu_A_DBC2v5_y = []
        MD2_Emu_B_DBC2v5_x = []
        MD2_Emu_B_DBC2v5_y = []

        MD3_Emu_A_DBC2v5_x = []
        MD3_Emu_A_DBC2v5_y = []
        MD3_Emu_B_DBC2v5_x = []
        MD3_Emu_B_DBC2v5_y = []

        MD4_Emu_A_DBC2v5_x = []
        MD4_Emu_A_DBC2v5_y = []
        MD4_Emu_B_DBC2v5_x = []
        MD4_Emu_B_DBC2v5_y = []

        MD1_Ppr_A_DBC2v5_x = []
        MD1_Ppr_A_DBC2v5_y = []
        MD1_Ppr_B_DBC2v5_x = []
        MD1_Ppr_B_DBC2v5_y = []

        MD2_Ppr_A_DBC2v5_x = []
        MD2_Ppr_A_DBC2v5_y = []
        MD2_Ppr_B_DBC2v5_x = []
        MD2_Ppr_B_DBC2v5_y = []

        MD3_Ppr_A_DBC2v5_x = []
        MD3_Ppr_A_DBC2v5_y = []
        MD3_Ppr_B_DBC2v5_x = []
        MD3_Ppr_B_DBC2v5_y = []

        MD4_Ppr_A_DBC2v5_x = []
        MD4_Ppr_A_DBC2v5_y = []
        MD4_Ppr_B_DBC2v5_x = []
        MD4_Ppr_B_DBC2v5_y = []

        #db_mon_3.3v(vaux11)
        MD1_Emu_A_DBC3v3_x = []
        MD1_Emu_A_DBC3v3_y = []
        MD1_Emu_B_DBC3v3_x = []
        MD1_Emu_B_DBC3v3_y = []

        MD2_Emu_A_DBC3v3_x = []
        MD2_Emu_A_DBC3v3_y = []
        MD2_Emu_B_DBC3v3_x = []
        MD2_Emu_B_DBC3v3_y = []

        MD3_Emu_A_DBC3v3_x = []
        MD3_Emu_A_DBC3v3_y = []
        MD3_Emu_B_DBC3v3_x = []
        MD3_Emu_B_DBC3v3_y = []

        MD4_Emu_A_DBC3v3_x = []
        MD4_Emu_A_DBC3v3_y = []
        MD4_Emu_B_DBC3v3_x = []
        MD4_Emu_B_DBC3v3_y = []

        MD1_Ppr_A_DBC3v3_x = []
        MD1_Ppr_A_DBC3v3_y = []
        MD1_Ppr_B_DBC3v3_x = []
        MD1_Ppr_B_DBC3v3_y = []

        MD2_Ppr_A_DBC3v3_x = []
        MD2_Ppr_A_DBC3v3_y = []
        MD2_Ppr_B_DBC3v3_x = []
        MD2_Ppr_B_DBC3v3_y = []

        MD3_Ppr_A_DBC3v3_x = []
        MD3_Ppr_A_DBC3v3_y = []
        MD3_Ppr_B_DBC3v3_x = []
        MD3_Ppr_B_DBC3v3_y = []

        MD4_Ppr_A_DBC3v3_x = []
        MD4_Ppr_A_DBC3v3_y = []
        MD4_Ppr_B_DBC3v3_x = []
        MD4_Ppr_B_DBC3v3_y = []

        # MainBoard Currents
        #mb_mon_+5v(vaux10)
        MD1_Emu_A_MBCP5v_x = []
        MD1_Emu_A_MBCP5v_y = []
        MD1_Emu_B_MBCP5v_x = []
        MD1_Emu_B_MBCP5v_y = []

        MD2_Emu_A_MBCP5v_x = []
        MD2_Emu_A_MBCP5v_y = []
        MD2_Emu_B_MBCP5v_x = []
        MD2_Emu_B_MBCP5v_y = []

        MD3_Emu_A_MBCP5v_x = []
        MD3_Emu_A_MBCP5v_y = []
        MD3_Emu_B_MBCP5v_x = []
        MD3_Emu_B_MBCP5v_y = []

        MD4_Emu_A_MBCP5v_x = []
        MD4_Emu_A_MBCP5v_y = []
        MD4_Emu_B_MBCP5v_x = []
        MD4_Emu_B_MBCP5v_y = []

        MD1_Ppr_A_MBCP5v_x = []
        MD1_Ppr_A_MBCP5v_y = []
        MD1_Ppr_B_MBCP5v_x = []
        MD1_Ppr_B_MBCP5v_y = []

        MD2_Ppr_A_MBCP5v_x = []
        MD2_Ppr_A_MBCP5v_y = []
        MD2_Ppr_B_MBCP5v_x = []
        MD2_Ppr_B_MBCP5v_y = []

        MD3_Ppr_A_MBCP5v_x = []
        MD3_Ppr_A_MBCP5v_y = []
        MD3_Ppr_B_MBCP5v_x = []
        MD3_Ppr_B_MBCP5v_y = []

        MD4_Ppr_A_MBCP5v_x = []
        MD4_Ppr_A_MBCP5v_y = []
        MD4_Ppr_B_MBCP5v_x = []
        MD4_Ppr_B_MBCP5v_y = []

        #mb_mon_-5v(vaux7)
        MD1_Emu_A_MBCN5v_x = []
        MD1_Emu_A_MBCN5v_y = []
        MD1_Emu_B_MBCN5v_x = []
        MD1_Emu_B_MBCN5v_y = []

        MD2_Emu_A_MBCN5v_x = []
        MD2_Emu_A_MBCN5v_y = []
        MD2_Emu_B_MBCN5v_x = []
        MD2_Emu_B_MBCN5v_y = []

        MD3_Emu_A_MBCN5v_x = []
        MD3_Emu_A_MBCN5v_y = []
        MD3_Emu_B_MBCN5v_x = []
        MD3_Emu_B_MBCN5v_y = []

        MD4_Emu_A_MBCN5v_x = []
        MD4_Emu_A_MBCN5v_y = []
        MD4_Emu_B_MBCN5v_x = []
        MD4_Emu_B_MBCN5v_y = []

        MD1_Ppr_A_MBCN5v_x = []
        MD1_Ppr_A_MBCN5v_y = []
        MD1_Ppr_B_MBCN5v_x = []
        MD1_Ppr_B_MBCN5v_y = []

        MD2_Ppr_A_MBCN5v_x = []
        MD2_Ppr_A_MBCN5v_y = []
        MD2_Ppr_B_MBCN5v_x = []
        MD2_Ppr_B_MBCN5v_y = []

        MD3_Ppr_A_MBCN5v_x = []
        MD3_Ppr_A_MBCN5v_y = []
        MD3_Ppr_B_MBCN5v_x = []
        MD3_Ppr_B_MBCN5v_y = []

        MD4_Ppr_A_MBCN5v_x = []
        MD4_Ppr_A_MBCN5v_y = []
        MD4_Ppr_B_MBCN5v_x = []
        MD4_Ppr_B_MBCN5v_y = []

        #mb_mon_1.2v(vaux14)
        MD1_Emu_A_MBC1v2_x = []
        MD1_Emu_A_MBC1v2_y = []
        MD1_Emu_B_MBC1v2_x = []
        MD1_Emu_B_MBC1v2_y = []

        MD2_Emu_A_MBC1v2_x = []
        MD2_Emu_A_MBC1v2_y = []
        MD2_Emu_B_MBC1v2_x = []
        MD2_Emu_B_MBC1v2_y = []

        MD3_Emu_A_MBC1v2_x = []
        MD3_Emu_A_MBC1v2_y = []
        MD3_Emu_B_MBC1v2_x = []
        MD3_Emu_B_MBC1v2_y = []

        MD4_Emu_A_MBC1v2_x = []
        MD4_Emu_A_MBC1v2_y = []
        MD4_Emu_B_MBC1v2_x = []
        MD4_Emu_B_MBC1v2_y = []

        MD1_Ppr_A_MBC1v2_x = []
        MD1_Ppr_A_MBC1v2_y = []
        MD1_Ppr_B_MBC1v2_x = []
        MD1_Ppr_B_MBC1v2_y = []

        MD2_Ppr_A_MBC1v2_x = []
        MD2_Ppr_A_MBC1v2_y = []
        MD2_Ppr_B_MBC1v2_x = []
        MD2_Ppr_B_MBC1v2_y = []

        MD3_Ppr_A_MBC1v2_x = []
        MD3_Ppr_A_MBC1v2_y = []
        MD3_Ppr_B_MBC1v2_x = []
        MD3_Ppr_B_MBC1v2_y = []

        MD4_Ppr_A_MBC1v2_x = []
        MD4_Ppr_A_MBC1v2_y = []
        MD4_Ppr_B_MBC1v2_x = []
        MD4_Ppr_B_MBC1v2_y = []

        #mb_mon_1.8v(vaux12)
        MD1_Emu_A_MBC1v8_x = []
        MD1_Emu_A_MBC1v8_y = []
        MD1_Emu_B_MBC1v8_x = []
        MD1_Emu_B_MBC1v8_y = []

        MD2_Emu_A_MBC1v8_x = []
        MD2_Emu_A_MBC1v8_y = []
        MD2_Emu_B_MBC1v8_x = []
        MD2_Emu_B_MBC1v8_y = []

        MD3_Emu_A_MBC1v8_x = []
        MD3_Emu_A_MBC1v8_y = []
        MD3_Emu_B_MBC1v8_x = []
        MD3_Emu_B_MBC1v8_y = []

        MD4_Emu_A_MBC1v8_x = []
        MD4_Emu_A_MBC1v8_y = []
        MD4_Emu_B_MBC1v8_x = []
        MD4_Emu_B_MBC1v8_y = []

        MD1_Ppr_A_MBC1v8_x = []
        MD1_Ppr_A_MBC1v8_y = []
        MD1_Ppr_B_MBC1v8_x = []
        MD1_Ppr_B_MBC1v8_y = []

        MD2_Ppr_A_MBC1v8_x = []
        MD2_Ppr_A_MBC1v8_y = []
        MD2_Ppr_B_MBC1v8_x = []
        MD2_Ppr_B_MBC1v8_y = []

        MD3_Ppr_A_MBC1v8_x = []
        MD3_Ppr_A_MBC1v8_y = []
        MD3_Ppr_B_MBC1v8_x = []
        MD3_Ppr_B_MBC1v8_y = []

        MD4_Ppr_A_MBC1v8_x = []
        MD4_Ppr_A_MBC1v8_y = []
        MD4_Ppr_B_MBC1v8_x = []
        MD4_Ppr_B_MBC1v8_y = []

        #mb_mon_2.5v(vaux15)
        MD1_Emu_A_MBC2v5_x = []
        MD1_Emu_A_MBC2v5_y = []
        MD1_Emu_B_MBC2v5_x = []
        MD1_Emu_B_MBC2v5_y = []

        MD2_Emu_A_MBC2v5_x = []
        MD2_Emu_A_MBC2v5_y = []
        MD2_Emu_B_MBC2v5_x = []
        MD2_Emu_B_MBC2v5_y = []

        MD3_Emu_A_MBC2v5_x = []
        MD3_Emu_A_MBC2v5_y = []
        MD3_Emu_B_MBC2v5_x = []
        MD3_Emu_B_MBC2v5_y = []

        MD4_Emu_A_MBC2v5_x = []
        MD4_Emu_A_MBC2v5_y = []
        MD4_Emu_B_MBC2v5_x = []
        MD4_Emu_B_MBC2v5_y = []

        MD1_Ppr_A_MBC2v5_x = []
        MD1_Ppr_A_MBC2v5_y = []
        MD1_Ppr_B_MBC2v5_x = []
        MD1_Ppr_B_MBC2v5_y = []

        MD2_Ppr_A_MBC2v5_x = []
        MD2_Ppr_A_MBC2v5_y = []
        MD2_Ppr_B_MBC2v5_x = []
        MD2_Ppr_B_MBC2v5_y = []

        MD3_Ppr_A_MBC2v5_x = []
        MD3_Ppr_A_MBC2v5_y = []
        MD3_Ppr_B_MBC2v5_x = []
        MD3_Ppr_B_MBC2v5_y = []

        MD4_Ppr_A_MBC2v5_x = []
        MD4_Ppr_A_MBC2v5_y = []
        MD4_Ppr_B_MBC2v5_x = []
        MD4_Ppr_B_MBC2v5_y = []

        #max_temp
        MD1_Emu_A_MAXTEMP_x = []
        MD1_Emu_A_MAXTEMP_y = []
        MD1_Emu_B_MAXTEMP_x = []
        MD1_Emu_B_MAXTEMP_y = []

        MD2_Emu_A_MAXTEMP_x = []
        MD2_Emu_A_MAXTEMP_y = []
        MD2_Emu_B_MAXTEMP_x = []
        MD2_Emu_B_MAXTEMP_y = []

        MD3_Emu_A_MAXTEMP_x = []
        MD3_Emu_A_MAXTEMP_y = []
        MD3_Emu_B_MAXTEMP_x = []
        MD3_Emu_B_MAXTEMP_y = []

        MD4_Emu_A_MAXTEMP_x = []
        MD4_Emu_A_MAXTEMP_y = []
        MD4_Emu_B_MAXTEMP_x = []
        MD4_Emu_B_MAXTEMP_y = []

        MD1_Ppr_A_MAXTEMP_x = []
        MD1_Ppr_A_MAXTEMP_y = []
        MD1_Ppr_B_MAXTEMP_x = []
        MD1_Ppr_B_MAXTEMP_y = []

        MD2_Ppr_A_MAXTEMP_x = []
        MD2_Ppr_A_MAXTEMP_y = []
        MD2_Ppr_B_MAXTEMP_x = []
        MD2_Ppr_B_MAXTEMP_y = []

        MD3_Ppr_A_MAXTEMP_x = []
        MD3_Ppr_A_MAXTEMP_y = []
        MD3_Ppr_B_MAXTEMP_x = []
        MD3_Ppr_B_MAXTEMP_y = []

        MD4_Ppr_A_MAXTEMP_x = []
        MD4_Ppr_A_MAXTEMP_y = []
        MD4_Ppr_B_MAXTEMP_x = []
        MD4_Ppr_B_MAXTEMP_y = []

	#max_vccint
        MD1_Emu_A_MAXVCCINT_x = []
        MD1_Emu_A_MAXVCCINT_y = []
        MD1_Emu_B_MAXVCCINT_x = []
        MD1_Emu_B_MAXVCCINT_y = []

        MD2_Emu_A_MAXVCCINT_x = []
        MD2_Emu_A_MAXVCCINT_y = []
        MD2_Emu_B_MAXVCCINT_x = []
        MD2_Emu_B_MAXVCCINT_y = []

        MD3_Emu_A_MAXVCCINT_x = []
        MD3_Emu_A_MAXVCCINT_y = []
        MD3_Emu_B_MAXVCCINT_x = []
        MD3_Emu_B_MAXVCCINT_y = []

        MD4_Emu_A_MAXVCCINT_x = []
        MD4_Emu_A_MAXVCCINT_y = []
        MD4_Emu_B_MAXVCCINT_x = []
        MD4_Emu_B_MAXVCCINT_y = []

        MD1_Ppr_A_MAXVCCINT_x = []
        MD1_Ppr_A_MAXVCCINT_y = []
        MD1_Ppr_B_MAXVCCINT_x = []
        MD1_Ppr_B_MAXVCCINT_y = []

        MD2_Ppr_A_MAXVCCINT_x = []
        MD2_Ppr_A_MAXVCCINT_y = []
        MD2_Ppr_B_MAXVCCINT_x = []
        MD2_Ppr_B_MAXVCCINT_y = []

        MD3_Ppr_A_MAXVCCINT_x = []
        MD3_Ppr_A_MAXVCCINT_y = []
        MD3_Ppr_B_MAXVCCINT_x = []
        MD3_Ppr_B_MAXVCCINT_y = []

        MD4_Ppr_A_MAXVCCINT_x = []
        MD4_Ppr_A_MAXVCCINT_y = []
        MD4_Ppr_B_MAXVCCINT_x = []
        MD4_Ppr_B_MAXVCCINT_y = []

	#min_vccint
        MD1_Emu_A_MINVCCINT_x = []
        MD1_Emu_A_MINVCCINT_y = []
        MD1_Emu_B_MINVCCINT_x = []
        MD1_Emu_B_MINVCCINT_y = []

        MD2_Emu_A_MINVCCINT_x = []
        MD2_Emu_A_MINVCCINT_y = []
        MD2_Emu_B_MINVCCINT_x = []
        MD2_Emu_B_MINVCCINT_y = []

        MD3_Emu_A_MINVCCINT_x = []
        MD3_Emu_A_MINVCCINT_y = []
        MD3_Emu_B_MINVCCINT_x = []
        MD3_Emu_B_MINVCCINT_y = []

        MD4_Emu_A_MINVCCINT_x = []
        MD4_Emu_A_MINVCCINT_y = []
        MD4_Emu_B_MINVCCINT_x = []
        MD4_Emu_B_MINVCCINT_y = []

        MD1_Ppr_A_MINVCCINT_x = []
        MD1_Ppr_A_MINVCCINT_y = []
        MD1_Ppr_B_MINVCCINT_x = []
        MD1_Ppr_B_MINVCCINT_y = []

        MD2_Ppr_A_MINVCCINT_x = []
        MD2_Ppr_A_MINVCCINT_y = []
        MD2_Ppr_B_MINVCCINT_x = []
        MD2_Ppr_B_MINVCCINT_y = []

        MD3_Ppr_A_MINVCCINT_x = []
        MD3_Ppr_A_MINVCCINT_y = []
        MD3_Ppr_B_MINVCCINT_x = []
        MD3_Ppr_B_MINVCCINT_y = []

        MD4_Ppr_A_MINVCCINT_x = []
        MD4_Ppr_A_MINVCCINT_y = []
        MD4_Ppr_B_MINVCCINT_x = []
        MD4_Ppr_B_MINVCCINT_y = []

	#max_vccout
        MD1_Emu_A_MAXVCCOUT_x = []
        MD1_Emu_A_MAXVCCOUT_y = []
        MD1_Emu_B_MAXVCCOUT_x = []
        MD1_Emu_B_MAXVCCOUT_y = []

        MD2_Emu_A_MAXVCCOUT_x = []
        MD2_Emu_A_MAXVCCOUT_y = []
        MD2_Emu_B_MAXVCCOUT_x = []
        MD2_Emu_B_MAXVCCOUT_y = []

        MD3_Emu_A_MAXVCCOUT_x = []
        MD3_Emu_A_MAXVCCOUT_y = []
        MD3_Emu_B_MAXVCCOUT_x = []
        MD3_Emu_B_MAXVCCOUT_y = []

        MD4_Emu_A_MAXVCCOUT_x = []
        MD4_Emu_A_MAXVCCOUT_y = []
        MD4_Emu_B_MAXVCCOUT_x = []
        MD4_Emu_B_MAXVCCOUT_y = []

        MD1_Ppr_A_MAXVCCOUT_x = []
        MD1_Ppr_A_MAXVCCOUT_y = []
        MD1_Ppr_B_MAXVCCOUT_x = []
        MD1_Ppr_B_MAXVCCOUT_y = []

        MD2_Ppr_A_MAXVCCOUT_x = []
        MD2_Ppr_A_MAXVCCOUT_y = []
        MD2_Ppr_B_MAXVCCOUT_x = []
        MD2_Ppr_B_MAXVCCOUT_y = []

        MD3_Ppr_A_MAXVCCOUT_x = []
        MD3_Ppr_A_MAXVCCOUT_y = []
        MD3_Ppr_B_MAXVCCOUT_x = []
        MD3_Ppr_B_MAXVCCOUT_y = []

        MD4_Ppr_A_MAXVCCOUT_x = []
        MD4_Ppr_A_MAXVCCOUT_y = []
        MD4_Ppr_B_MAXVCCOUT_x = []
        MD4_Ppr_B_MAXVCCOUT_y = []

	#min_vccout
        MD1_Emu_A_MINVCCOUT_x = []
        MD1_Emu_A_MINVCCOUT_y = []
        MD1_Emu_B_MINVCCOUT_x = []
        MD1_Emu_B_MINVCCOUT_y = []

        MD2_Emu_A_MINVCCOUT_x = []
        MD2_Emu_A_MINVCCOUT_y = []
        MD2_Emu_B_MINVCCOUT_x = []
        MD2_Emu_B_MINVCCOUT_y = []

        MD3_Emu_A_MINVCCOUT_x = []
        MD3_Emu_A_MINVCCOUT_y = []
        MD3_Emu_B_MINVCCOUT_x = []
        MD3_Emu_B_MINVCCOUT_y = []

        MD4_Emu_A_MINVCCOUT_x = []
        MD4_Emu_A_MINVCCOUT_y = []
        MD4_Emu_B_MINVCCOUT_x = []
        MD4_Emu_B_MINVCCOUT_y = []

        MD1_Ppr_A_MINVCCOUT_x = []
        MD1_Ppr_A_MINVCCOUT_y = []
        MD1_Ppr_B_MINVCCOUT_x = []
        MD1_Ppr_B_MINVCCOUT_y = []

        MD2_Ppr_A_MINVCCOUT_x = []
        MD2_Ppr_A_MINVCCOUT_y = []
        MD2_Ppr_B_MINVCCOUT_x = []
        MD2_Ppr_B_MINVCCOUT_y = []

        MD3_Ppr_A_MINVCCOUT_x = []
        MD3_Ppr_A_MINVCCOUT_y = []
        MD3_Ppr_B_MINVCCOUT_x = []
        MD3_Ppr_B_MINVCCOUT_y = []

        MD4_Ppr_A_MINVCCOUT_x = []
        MD4_Ppr_A_MINVCCOUT_y = []
        MD4_Ppr_B_MINVCCOUT_x = []
        MD4_Ppr_B_MINVCCOUT_y = []

	#max_vram
        MD1_Emu_A_MAX_VRAM_x = []
        MD1_Emu_A_MAX_VRAM_y = []
        MD1_Emu_B_MAX_VRAM_x = []
        MD1_Emu_B_MAX_VRAM_y = []

        MD2_Emu_A_MAX_VRAM_x = []
        MD2_Emu_A_MAX_VRAM_y = []
        MD2_Emu_B_MAX_VRAM_x = []
        MD2_Emu_B_MAX_VRAM_y = []

        MD3_Emu_A_MAX_VRAM_x = []
        MD3_Emu_A_MAX_VRAM_y = []
        MD3_Emu_B_MAX_VRAM_x = []
        MD3_Emu_B_MAX_VRAM_y = []

        MD4_Emu_A_MAX_VRAM_x = []
        MD4_Emu_A_MAX_VRAM_y = []
        MD4_Emu_B_MAX_VRAM_x = []
        MD4_Emu_B_MAX_VRAM_y = []

        MD1_Ppr_A_MAX_VRAM_x = []
        MD1_Ppr_A_MAX_VRAM_y = []
        MD1_Ppr_B_MAX_VRAM_x = []
        MD1_Ppr_B_MAX_VRAM_y = []

        MD2_Ppr_A_MAX_VRAM_x = []
        MD2_Ppr_A_MAX_VRAM_y = []
        MD2_Ppr_B_MAX_VRAM_x = []
        MD2_Ppr_B_MAX_VRAM_y = []

        MD3_Ppr_A_MAX_VRAM_x = []
        MD3_Ppr_A_MAX_VRAM_y = []
        MD3_Ppr_B_MAX_VRAM_x = []
        MD3_Ppr_B_MAX_VRAM_y = []

        MD4_Ppr_A_MAX_VRAM_x = []
        MD4_Ppr_A_MAX_VRAM_y = []
        MD4_Ppr_B_MAX_VRAM_x = []
        MD4_Ppr_B_MAX_VRAM_y = []

	#min_vram
        MD1_Emu_A_MIN_VRAM_x = []
        MD1_Emu_A_MIN_VRAM_y = []
        MD1_Emu_B_MIN_VRAM_x = []
        MD1_Emu_B_MIN_VRAM_y = []

        MD2_Emu_A_MIN_VRAM_x = []
        MD2_Emu_A_MIN_VRAM_y = []
        MD2_Emu_B_MIN_VRAM_x = []
        MD2_Emu_B_MIN_VRAM_y = []

        MD3_Emu_A_MIN_VRAM_x = []
        MD3_Emu_A_MIN_VRAM_y = []
        MD3_Emu_B_MIN_VRAM_x = []
        MD3_Emu_B_MIN_VRAM_y = []

        MD4_Emu_A_MIN_VRAM_x = []
        MD4_Emu_A_MIN_VRAM_y = []
        MD4_Emu_B_MIN_VRAM_x = []
        MD4_Emu_B_MIN_VRAM_y = []

        MD1_Ppr_A_MIN_VRAM_x = []
        MD1_Ppr_A_MIN_VRAM_y = []
        MD1_Ppr_B_MIN_VRAM_x = []
        MD1_Ppr_B_MIN_VRAM_y = []

        MD2_Ppr_A_MIN_VRAM_x = []
        MD2_Ppr_A_MIN_VRAM_y = []
        MD2_Ppr_B_MIN_VRAM_x = []
        MD2_Ppr_B_MIN_VRAM_y = []

        MD3_Ppr_A_MIN_VRAM_x = []
        MD3_Ppr_A_MIN_VRAM_y = []
        MD3_Ppr_B_MIN_VRAM_x = []
        MD3_Ppr_B_MIN_VRAM_y = []

        MD4_Ppr_A_MIN_VRAM_x = []
        MD4_Ppr_A_MIN_VRAM_y = []
        MD4_Ppr_B_MIN_VRAM_x = []
        MD4_Ppr_B_MIN_VRAM_y = []

	#pgood_db_0v95
        MD1_Emu_A_DBPGOOD0v95_x = []
        MD1_Emu_A_DBPGOOD0v95_y = []
        MD1_Emu_B_DBPGOOD0v95_x = []
        MD1_Emu_B_DBPGOOD0v95_y = []

        MD2_Emu_A_DBPGOOD0v95_x = []
        MD2_Emu_A_DBPGOOD0v95_y = []
        MD2_Emu_B_DBPGOOD0v95_x = []
        MD2_Emu_B_DBPGOOD0v95_y = []

        MD3_Emu_A_DBPGOOD0v95_x = []
        MD3_Emu_A_DBPGOOD0v95_y = []
        MD3_Emu_B_DBPGOOD0v95_x = []
        MD3_Emu_B_DBPGOOD0v95_y = []

        MD4_Emu_A_DBPGOOD0v95_x = []
        MD4_Emu_A_DBPGOOD0v95_y = []
        MD4_Emu_B_DBPGOOD0v95_x = []
        MD4_Emu_B_DBPGOOD0v95_y = []

        MD1_Ppr_A_DBPGOOD0v95_x = []
        MD1_Ppr_A_DBPGOOD0v95_y = []
        MD1_Ppr_B_DBPGOOD0v95_x = []
        MD1_Ppr_B_DBPGOOD0v95_y = []

        MD2_Ppr_A_DBPGOOD0v95_x = []
        MD2_Ppr_A_DBPGOOD0v95_y = []
        MD2_Ppr_B_DBPGOOD0v95_x = []
        MD2_Ppr_B_DBPGOOD0v95_y = []

        MD3_Ppr_A_DBPGOOD0v95_x = []
        MD3_Ppr_A_DBPGOOD0v95_y = []
        MD3_Ppr_B_DBPGOOD0v95_x = []
        MD3_Ppr_B_DBPGOOD0v95_y = []

        MD4_Ppr_A_DBPGOOD0v95_x = []
        MD4_Ppr_A_DBPGOOD0v95_y = []
        MD4_Ppr_B_DBPGOOD0v95_x = []
        MD4_Ppr_B_DBPGOOD0v95_y = []

        #pgood_db_1v0
        MD1_Emu_A_DBPGOOD1v0_x = []
        MD1_Emu_A_DBPGOOD1v0_y = []
        MD1_Emu_B_DBPGOOD1v0_x = []
        MD1_Emu_B_DBPGOOD1v0_y = []

        MD2_Emu_A_DBPGOOD1v0_x = []
        MD2_Emu_A_DBPGOOD1v0_y = []
        MD2_Emu_B_DBPGOOD1v0_x = []
        MD2_Emu_B_DBPGOOD1v0_y = []

        MD3_Emu_A_DBPGOOD1v0_x = []
        MD3_Emu_A_DBPGOOD1v0_y = []
        MD3_Emu_B_DBPGOOD1v0_x = []
        MD3_Emu_B_DBPGOOD1v0_y = []

        MD4_Emu_A_DBPGOOD1v0_x = []
        MD4_Emu_A_DBPGOOD1v0_y = []
        MD4_Emu_B_DBPGOOD1v0_x = []
        MD4_Emu_B_DBPGOOD1v0_y = []

        MD1_Ppr_A_DBPGOOD1v0_x = []
        MD1_Ppr_A_DBPGOOD1v0_y = []
        MD1_Ppr_B_DBPGOOD1v0_x = []
        MD1_Ppr_B_DBPGOOD1v0_y = []

        MD2_Ppr_A_DBPGOOD1v0_x = []
        MD2_Ppr_A_DBPGOOD1v0_y = []
        MD2_Ppr_B_DBPGOOD1v0_x = []
        MD2_Ppr_B_DBPGOOD1v0_y = []

        MD3_Ppr_A_DBPGOOD1v0_x = []
        MD3_Ppr_A_DBPGOOD1v0_y = []
        MD3_Ppr_B_DBPGOOD1v0_x = []
        MD3_Ppr_B_DBPGOOD1v0_y = []

        MD4_Ppr_A_DBPGOOD1v0_x = []
        MD4_Ppr_A_DBPGOOD1v0_y = []
        MD4_Ppr_B_DBPGOOD1v0_x = []
        MD4_Ppr_B_DBPGOOD1v0_y = []

	#pgood_db_1v2
        MD1_Emu_A_DBPGOOD1v2_x = []
        MD1_Emu_A_DBPGOOD1v2_y = []
        MD1_Emu_B_DBPGOOD1v2_x = []
        MD1_Emu_B_DBPGOOD1v2_y = []

        MD2_Emu_A_DBPGOOD1v2_x = []
        MD2_Emu_A_DBPGOOD1v2_y = []
        MD2_Emu_B_DBPGOOD1v2_x = []
        MD2_Emu_B_DBPGOOD1v2_y = []

        MD3_Emu_A_DBPGOOD1v2_x = []
        MD3_Emu_A_DBPGOOD1v2_y = []
        MD3_Emu_B_DBPGOOD1v2_x = []
        MD3_Emu_B_DBPGOOD1v2_y = []

        MD4_Emu_A_DBPGOOD1v2_x = []
        MD4_Emu_A_DBPGOOD1v2_y = []
        MD4_Emu_B_DBPGOOD1v2_x = []
        MD4_Emu_B_DBPGOOD1v2_y = []

        MD1_Ppr_A_DBPGOOD1v2_x = []
        MD1_Ppr_A_DBPGOOD1v2_y = []
        MD1_Ppr_B_DBPGOOD1v2_x = []
        MD1_Ppr_B_DBPGOOD1v2_y = []

        MD2_Ppr_A_DBPGOOD1v2_x = []
        MD2_Ppr_A_DBPGOOD1v2_y = []
        MD2_Ppr_B_DBPGOOD1v2_x = []
        MD2_Ppr_B_DBPGOOD1v2_y = []

        MD3_Ppr_A_DBPGOOD1v2_x = []
        MD3_Ppr_A_DBPGOOD1v2_y = []
        MD3_Ppr_B_DBPGOOD1v2_x = []
        MD3_Ppr_B_DBPGOOD1v2_y = []

        MD4_Ppr_A_DBPGOOD1v2_x = []
        MD4_Ppr_A_DBPGOOD1v2_y = []
        MD4_Ppr_B_DBPGOOD1v2_x = []
        MD4_Ppr_B_DBPGOOD1v2_y = []

	#pgood_db_1v5
        MD1_Emu_A_DBPGOOD1v5_x = []
        MD1_Emu_A_DBPGOOD1v5_y = []
        MD1_Emu_B_DBPGOOD1v5_x = []
        MD1_Emu_B_DBPGOOD1v5_y = []

        MD2_Emu_A_DBPGOOD1v5_x = []
        MD2_Emu_A_DBPGOOD1v5_y = []
        MD2_Emu_B_DBPGOOD1v5_x = []
        MD2_Emu_B_DBPGOOD1v5_y = []

        MD3_Emu_A_DBPGOOD1v5_x = []
        MD3_Emu_A_DBPGOOD1v5_y = []
        MD3_Emu_B_DBPGOOD1v5_x = []
        MD3_Emu_B_DBPGOOD1v5_y = []

        MD4_Emu_A_DBPGOOD1v5_x = []
        MD4_Emu_A_DBPGOOD1v5_y = []
        MD4_Emu_B_DBPGOOD1v5_x = []
        MD4_Emu_B_DBPGOOD1v5_y = []

        MD1_Ppr_A_DBPGOOD1v5_x = []
        MD1_Ppr_A_DBPGOOD1v5_y = []
        MD1_Ppr_B_DBPGOOD1v5_x = []
        MD1_Ppr_B_DBPGOOD1v5_y = []

        MD2_Ppr_A_DBPGOOD1v5_x = []
        MD2_Ppr_A_DBPGOOD1v5_y = []
        MD2_Ppr_B_DBPGOOD1v5_x = []
        MD2_Ppr_B_DBPGOOD1v5_y = []

        MD3_Ppr_A_DBPGOOD1v5_x = []
        MD3_Ppr_A_DBPGOOD1v5_y = []
        MD3_Ppr_B_DBPGOOD1v5_x = []
        MD3_Ppr_B_DBPGOOD1v5_y = []

        MD4_Ppr_A_DBPGOOD1v5_x = []
        MD4_Ppr_A_DBPGOOD1v5_y = []
        MD4_Ppr_B_DBPGOOD1v5_x = []
        MD4_Ppr_B_DBPGOOD1v5_y = []

	#pgood_db_1v8
        MD1_Emu_A_DBPGOOD1v8_x = []
        MD1_Emu_A_DBPGOOD1v8_y = []
        MD1_Emu_B_DBPGOOD1v8_x = []
        MD1_Emu_B_DBPGOOD1v8_y = []

        MD2_Emu_A_DBPGOOD1v8_x = []
        MD2_Emu_A_DBPGOOD1v8_y = []
        MD2_Emu_B_DBPGOOD1v8_x = []
        MD2_Emu_B_DBPGOOD1v8_y = []

        MD3_Emu_A_DBPGOOD1v8_x = []
        MD3_Emu_A_DBPGOOD1v8_y = []
        MD3_Emu_B_DBPGOOD1v8_x = []
        MD3_Emu_B_DBPGOOD1v8_y = []

        MD4_Emu_A_DBPGOOD1v8_x = []
        MD4_Emu_A_DBPGOOD1v8_y = []
        MD4_Emu_B_DBPGOOD1v8_x = []
        MD4_Emu_B_DBPGOOD1v8_y = []

        MD1_Ppr_A_DBPGOOD1v8_x = []
        MD1_Ppr_A_DBPGOOD1v8_y = []
        MD1_Ppr_B_DBPGOOD1v8_x = []
        MD1_Ppr_B_DBPGOOD1v8_y = []

        MD2_Ppr_A_DBPGOOD1v8_x = []
        MD2_Ppr_A_DBPGOOD1v8_y = []
        MD2_Ppr_B_DBPGOOD1v8_x = []
        MD2_Ppr_B_DBPGOOD1v8_y = []

        MD3_Ppr_A_DBPGOOD1v8_x = []
        MD3_Ppr_A_DBPGOOD1v8_y = []
        MD3_Ppr_B_DBPGOOD1v8_x = []
        MD3_Ppr_B_DBPGOOD1v8_y = []

        MD4_Ppr_A_DBPGOOD1v8_x = []
        MD4_Ppr_A_DBPGOOD1v8_y = []
        MD4_Ppr_B_DBPGOOD1v8_x = []
        MD4_Ppr_B_DBPGOOD1v8_y = []

	#pgood_db_2v5
        MD1_Emu_A_DBPGOOD2v5_x = []
        MD1_Emu_A_DBPGOOD2v5_y = []
        MD1_Emu_B_DBPGOOD2v5_x = []
        MD1_Emu_B_DBPGOOD2v5_y = []

        MD2_Emu_A_DBPGOOD2v5_x = []
        MD2_Emu_A_DBPGOOD2v5_y = []
        MD2_Emu_B_DBPGOOD2v5_x = []
        MD2_Emu_B_DBPGOOD2v5_y = []

        MD3_Emu_A_DBPGOOD2v5_x = []
        MD3_Emu_A_DBPGOOD2v5_y = []
        MD3_Emu_B_DBPGOOD2v5_x = []
        MD3_Emu_B_DBPGOOD2v5_y = []

        MD4_Emu_A_DBPGOOD2v5_x = []
        MD4_Emu_A_DBPGOOD2v5_y = []
        MD4_Emu_B_DBPGOOD2v5_x = []
        MD4_Emu_B_DBPGOOD2v5_y = []

        MD1_Ppr_A_DBPGOOD2v5_x = []
        MD1_Ppr_A_DBPGOOD2v5_y = []
        MD1_Ppr_B_DBPGOOD2v5_x = []
        MD1_Ppr_B_DBPGOOD2v5_y = []

        MD2_Ppr_A_DBPGOOD2v5_x = []
        MD2_Ppr_A_DBPGOOD2v5_y = []
        MD2_Ppr_B_DBPGOOD2v5_x = []
        MD2_Ppr_B_DBPGOOD2v5_y = []

        MD3_Ppr_A_DBPGOOD2v5_x = []
        MD3_Ppr_A_DBPGOOD2v5_y = []
        MD3_Ppr_B_DBPGOOD2v5_x = []
        MD3_Ppr_B_DBPGOOD2v5_y = []

        MD4_Ppr_A_DBPGOOD2v5_x = []
        MD4_Ppr_A_DBPGOOD2v5_y = []
        MD4_Ppr_B_DBPGOOD2v5_x = []
        MD4_Ppr_B_DBPGOOD2v5_y = []

	#pgood_db_3v3
        MD1_Emu_A_DBPGOOD3v3_x = []
        MD1_Emu_A_DBPGOOD3v3_y = []
        MD1_Emu_B_DBPGOOD3v3_x = []
        MD1_Emu_B_DBPGOOD3v3_y = []

        MD2_Emu_A_DBPGOOD3v3_x = []
        MD2_Emu_A_DBPGOOD3v3_y = []
        MD2_Emu_B_DBPGOOD3v3_x = []
        MD2_Emu_B_DBPGOOD3v3_y = []

        MD3_Emu_A_DBPGOOD3v3_x = []
        MD3_Emu_A_DBPGOOD3v3_y = []
        MD3_Emu_B_DBPGOOD3v3_x = []
        MD3_Emu_B_DBPGOOD3v3_y = []

        MD4_Emu_A_DBPGOOD3v3_x = []
        MD4_Emu_A_DBPGOOD3v3_y = []
        MD4_Emu_B_DBPGOOD3v3_x = []
        MD4_Emu_B_DBPGOOD3v3_y = []

        MD1_Ppr_A_DBPGOOD3v3_x = []
        MD1_Ppr_A_DBPGOOD3v3_y = []
        MD1_Ppr_B_DBPGOOD3v3_x = []
        MD1_Ppr_B_DBPGOOD3v3_y = []

        MD2_Ppr_A_DBPGOOD3v3_x = []
        MD2_Ppr_A_DBPGOOD3v3_y = []
        MD2_Ppr_B_DBPGOOD3v3_x = []
        MD2_Ppr_B_DBPGOOD3v3_y = []

        MD3_Ppr_A_DBPGOOD3v3_x = []
        MD3_Ppr_A_DBPGOOD3v3_y = []
        MD3_Ppr_B_DBPGOOD3v3_x = []
        MD3_Ppr_B_DBPGOOD3v3_y = []

        MD4_Ppr_A_DBPGOOD3v3_x = []
        MD4_Ppr_A_DBPGOOD3v3_y = []
        MD4_Ppr_B_DBPGOOD3v3_x = []
        MD4_Ppr_B_DBPGOOD3v3_y = []

        #pgood_mb_5v0
        MD1_Emu_A_MBPGOODP5v_x = []
        MD1_Emu_A_MBPGOODP5v_y = []
        MD1_Emu_B_MBPGOODP5v_x = []
        MD1_Emu_B_MBPGOODP5v_y = []

        MD2_Emu_A_MBPGOODP5v_x = []
        MD2_Emu_A_MBPGOODP5v_y = []
        MD2_Emu_B_MBPGOODP5v_x = []
        MD2_Emu_B_MBPGOODP5v_y = []

        MD3_Emu_A_MBPGOODP5v_x = []
        MD3_Emu_A_MBPGOODP5v_y = []
        MD3_Emu_B_MBPGOODP5v_x = []
        MD3_Emu_B_MBPGOODP5v_y = []

        MD4_Emu_A_MBPGOODP5v_x = []
        MD4_Emu_A_MBPGOODP5v_y = []
        MD4_Emu_B_MBPGOODP5v_x = []
        MD4_Emu_B_MBPGOODP5v_y = []

        MD1_Ppr_A_MBPGOODP5v_x = []
        MD1_Ppr_A_MBPGOODP5v_y = []
        MD1_Ppr_B_MBPGOODP5v_x = []
        MD1_Ppr_B_MBPGOODP5v_y = []

        MD2_Ppr_A_MBPGOODP5v_x = []
        MD2_Ppr_A_MBPGOODP5v_y = []
        MD2_Ppr_B_MBPGOODP5v_x = []
        MD2_Ppr_B_MBPGOODP5v_y = []

        MD3_Ppr_A_MBPGOODP5v_x = []
        MD3_Ppr_A_MBPGOODP5v_y = []
        MD3_Ppr_B_MBPGOODP5v_x = []
        MD3_Ppr_B_MBPGOODP5v_y = []

        MD4_Ppr_A_MBPGOODP5v_x = []
        MD4_Ppr_A_MBPGOODP5v_y = []
        MD4_Ppr_B_MBPGOODP5v_x = []
        MD4_Ppr_B_MBPGOODP5v_y = []

	#pgood_mb_5v0_n
        MD1_Emu_A_MBPGOODN5v_x = []
        MD1_Emu_A_MBPGOODN5v_y = []
        MD1_Emu_B_MBPGOODN5v_x = []
        MD1_Emu_B_MBPGOODN5v_y = []

        MD2_Emu_A_MBPGOODN5v_x = []
        MD2_Emu_A_MBPGOODN5v_y = []
        MD2_Emu_B_MBPGOODN5v_x = []
        MD2_Emu_B_MBPGOODN5v_y = []

        MD3_Emu_A_MBPGOODN5v_x = []
        MD3_Emu_A_MBPGOODN5v_y = []
        MD3_Emu_B_MBPGOODN5v_x = []
        MD3_Emu_B_MBPGOODN5v_y = []

        MD4_Emu_A_MBPGOODN5v_x = []
        MD4_Emu_A_MBPGOODN5v_y = []
        MD4_Emu_B_MBPGOODN5v_x = []
        MD4_Emu_B_MBPGOODN5v_y = []

        MD1_Ppr_A_MBPGOODN5v_x = []
        MD1_Ppr_A_MBPGOODN5v_y = []
        MD1_Ppr_B_MBPGOODN5v_x = []
        MD1_Ppr_B_MBPGOODN5v_y = []

        MD2_Ppr_A_MBPGOODN5v_x = []
        MD2_Ppr_A_MBPGOODN5v_y = []
        MD2_Ppr_B_MBPGOODN5v_x = []
        MD2_Ppr_B_MBPGOODN5v_y = []

        MD3_Ppr_A_MBPGOODN5v_x = []
        MD3_Ppr_A_MBPGOODN5v_y = []
        MD3_Ppr_B_MBPGOODN5v_x = []
        MD3_Ppr_B_MBPGOODN5v_y = []

        MD4_Ppr_A_MBPGOODN5v_x = []
        MD4_Ppr_A_MBPGOODN5v_y = []
        MD4_Ppr_B_MBPGOODN5v_x = []
        MD4_Ppr_B_MBPGOODN5v_y = []

	#pgood_mb_1v2
        MD1_Emu_A_MBPGOOD1v2_x = []
        MD1_Emu_A_MBPGOOD1v2_y = []
        MD1_Emu_B_MBPGOOD1v2_x = []
        MD1_Emu_B_MBPGOOD1v2_y = []

        MD2_Emu_A_MBPGOOD1v2_x = []
        MD2_Emu_A_MBPGOOD1v2_y = []
        MD2_Emu_B_MBPGOOD1v2_x = []
        MD2_Emu_B_MBPGOOD1v2_y = []

        MD3_Emu_A_MBPGOOD1v2_x = []
        MD3_Emu_A_MBPGOOD1v2_y = []
        MD3_Emu_B_MBPGOOD1v2_x = []
        MD3_Emu_B_MBPGOOD1v2_y = []

        MD4_Emu_A_MBPGOOD1v2_x = []
        MD4_Emu_A_MBPGOOD1v2_y = []
        MD4_Emu_B_MBPGOOD1v2_x = []
        MD4_Emu_B_MBPGOOD1v2_y = []

        MD1_Ppr_A_MBPGOOD1v2_x = []
        MD1_Ppr_A_MBPGOOD1v2_y = []
        MD1_Ppr_B_MBPGOOD1v2_x = []
        MD1_Ppr_B_MBPGOOD1v2_y = []

        MD2_Ppr_A_MBPGOOD1v2_x = []
        MD2_Ppr_A_MBPGOOD1v2_y = []
        MD2_Ppr_B_MBPGOOD1v2_x = []
        MD2_Ppr_B_MBPGOOD1v2_y = []

        MD3_Ppr_A_MBPGOOD1v2_x = []
        MD3_Ppr_A_MBPGOOD1v2_y = []
        MD3_Ppr_B_MBPGOOD1v2_x = []
        MD3_Ppr_B_MBPGOOD1v2_y = []

        MD4_Ppr_A_MBPGOOD1v2_x = []
        MD4_Ppr_A_MBPGOOD1v2_y = []
        MD4_Ppr_B_MBPGOOD1v2_x = []
        MD4_Ppr_B_MBPGOOD1v2_y = []

	#pgood_mb_1v8
        MD1_Emu_A_MBPGOOD1v8_x = []
        MD1_Emu_A_MBPGOOD1v8_y = []
        MD1_Emu_B_MBPGOOD1v8_x = []
        MD1_Emu_B_MBPGOOD1v8_y = []

        MD2_Emu_A_MBPGOOD1v8_x = []
        MD2_Emu_A_MBPGOOD1v8_y = []
        MD2_Emu_B_MBPGOOD1v8_x = []
        MD2_Emu_B_MBPGOOD1v8_y = []

        MD3_Emu_A_MBPGOOD1v8_x = []
        MD3_Emu_A_MBPGOOD1v8_y = []
        MD3_Emu_B_MBPGOOD1v8_x = []
        MD3_Emu_B_MBPGOOD1v8_y = []

        MD4_Emu_A_MBPGOOD1v8_x = []
        MD4_Emu_A_MBPGOOD1v8_y = []
        MD4_Emu_B_MBPGOOD1v8_x = []
        MD4_Emu_B_MBPGOOD1v8_y = []

        MD1_Ppr_A_MBPGOOD1v8_x = []
        MD1_Ppr_A_MBPGOOD1v8_y = []
        MD1_Ppr_B_MBPGOOD1v8_x = []
        MD1_Ppr_B_MBPGOOD1v8_y = []

        MD2_Ppr_A_MBPGOOD1v8_x = []
        MD2_Ppr_A_MBPGOOD1v8_y = []
        MD2_Ppr_B_MBPGOOD1v8_x = []
        MD2_Ppr_B_MBPGOOD1v8_y = []

        MD3_Ppr_A_MBPGOOD1v8_x = []
        MD3_Ppr_A_MBPGOOD1v8_y = []
        MD3_Ppr_B_MBPGOOD1v8_x = []
        MD3_Ppr_B_MBPGOOD1v8_y = []

        MD4_Ppr_A_MBPGOOD1v8_x = []
        MD4_Ppr_A_MBPGOOD1v8_y = []
        MD4_Ppr_B_MBPGOOD1v8_x = []
        MD4_Ppr_B_MBPGOOD1v8_y = []

	#pgood_mb_2v5
        MD1_Emu_A_MBPGOOD2v5_x = []
        MD1_Emu_A_MBPGOOD2v5_y = []
        MD1_Emu_B_MBPGOOD2v5_x = []
        MD1_Emu_B_MBPGOOD2v5_y = []

        MD2_Emu_A_MBPGOOD2v5_x = []
        MD2_Emu_A_MBPGOOD2v5_y = []
        MD2_Emu_B_MBPGOOD2v5_x = []
        MD2_Emu_B_MBPGOOD2v5_y = []

        MD3_Emu_A_MBPGOOD2v5_x = []
        MD3_Emu_A_MBPGOOD2v5_y = []
        MD3_Emu_B_MBPGOOD2v5_x = []
        MD3_Emu_B_MBPGOOD2v5_y = []

        MD4_Emu_A_MBPGOOD2v5_x = []
        MD4_Emu_A_MBPGOOD2v5_y = []
        MD4_Emu_B_MBPGOOD2v5_x = []
        MD4_Emu_B_MBPGOOD2v5_y = []

        MD1_Ppr_A_MBPGOOD2v5_x = []
        MD1_Ppr_A_MBPGOOD2v5_y = []
        MD1_Ppr_B_MBPGOOD2v5_x = []
        MD1_Ppr_B_MBPGOOD2v5_y = []

        MD2_Ppr_A_MBPGOOD2v5_x = []
        MD2_Ppr_A_MBPGOOD2v5_y = []
        MD2_Ppr_B_MBPGOOD2v5_x = []
        MD2_Ppr_B_MBPGOOD2v5_y = []

        MD3_Ppr_A_MBPGOOD2v5_x = []
        MD3_Ppr_A_MBPGOOD2v5_y = []
        MD3_Ppr_B_MBPGOOD2v5_x = []
        MD3_Ppr_B_MBPGOOD2v5_y = []

        MD4_Ppr_A_MBPGOOD2v5_x = []
        MD4_Ppr_A_MBPGOOD2v5_y = []
        MD4_Ppr_B_MBPGOOD2v5_x = []
        MD4_Ppr_B_MBPGOOD2v5_y = []

        # Retrieving, Printing, Filtering and Storing data from result object
        print("---------------- Reading Data: ----------------")

        for point in result_xADC.get_points():
            # Printing timestamp for each measurement
            print(f"Time: {point['time']}")

            # Incrementing Event Count
            nevents = nevents+1

            for key,value in point.items():
                if key != 'time':
                    print(f'{key} : {value}')

                # Defining Filters
                if (key == 'PPrEmu MD1') and (value == 'KU FPGA A'):
                    selectMD1 = 1
                    selectEmu = 1
                    selectA   = 1
                elif (key == 'PPrEmu MD1') and (value == 'KU FPGA B'):
                    selectMD1 = 1
                    selectEmu = 1
                    selectB   = 1
                elif (key == 'PPrEmu MD2') and (value == 'KU FPGA A'):
                    selectMD2 = 1
                    selectEmu = 1
                    selectA   = 1
                elif (key == 'PPrEmu MD2') and (value == 'KU FPGA B'):
                    selectMD2 = 1
                    selectEmu = 1
                    selectB   = 1
                elif (key == 'PPrEmu MD3') and (value == 'KU FPGA A'):
                    selectMD3 = 1
                    selectEmu = 1
                    selectA   = 1
                elif (key == 'PPrEmu MD3') and (value == 'KU FPGA B'):
                    selectMD3 = 1
                    selectEmu = 1
                    selectB   = 1
                elif (key == 'PPrEmu MD4') and (value == 'KU FPGA A'):
                    selectMD4 = 1
                    selectEmu = 1
                    selectA   = 1
                elif (key == 'PPrEmu MD4') and (value == 'KU FPGA B'):
                    selectMD4 = 1
                    selectEmu = 1
                    selectB   = 1
                elif (key == 'PprGTH MD1') and (value == 'KU FPGA A'):
                    selectMD1 = 1
                    selectPpr = 1
                    selectA   = 1
                elif (key == 'PprGTH MD1') and (value == 'KU FPGA B'):
                    selectMD1 = 1
                    selectPpr = 1
                    selectB   = 1
                elif (key == 'PprGTH MD2') and (value == 'KU FPGA A'):
                    selectMD2 = 1
                    selectPpr = 1
                    selectA   = 1
                elif (key == 'PprGTH MD2') and (value == 'KU FPGA B'):
                    selectMD2 = 1
                    selectPpr = 1
                    selectB   = 1
                elif (key == 'PprGTH MD3') and (value == 'KU FPGA A'):
                    selectMD3 = 1
                    selectPpr = 1
                    selectA   = 1
                elif (key == 'PprGTH MD3') and (value == 'KU FPGA B'):
                    selectMD3 = 1
                    selectPpr = 1
                    selectB   = 1
                elif (key == 'PprGTH MD4') and (value == 'KU FPGA A'):
                    selectMD4 = 1
                    selectPpr = 1
                    selectA   = 1
                elif (key == 'PprGTH MD4') and (value == 'KU FPGA B'):
                    selectMD4 = 1
                    selectPpr = 1
                    selectB   = 1

                # Storing Data
                if key == "db_mon_0.95v(vaux0)":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_DBC0v95_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_DBC0v95_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_DBC0v95_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_DBC0v95_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_DBC0v95_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_DBC0v95_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_DBC0v95_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_DBC0v95_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_DBC0v95_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_DBC0v95_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_DBC0v95_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_DBC0v95_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_DBC0v95_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_DBC0v95_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_DBC0v95_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_DBC0v95_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_DBC0v95_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_DBC0v95_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_DBC0v95_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_DBC0v95_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_DBC0v95_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_DBC0v95_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_DBC0v95_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_DBC0v95_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_DBC0v95_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_DBC0v95_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_DBC0v95_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_DBC0v95_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_DBC0v95_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_DBC0v95_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_DBC0v95_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_DBC0v95_y.append(value)

                if key == "db_mon_1.0v(vaux5)":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_DBC1v0_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_DBC1v0_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_DBC1v0_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_DBC1v0_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_DBC1v0_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_DBC1v0_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_DBC1v0_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_DBC1v0_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_DBC1v0_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_DBC1v0_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_DBC1v0_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_DBC1v0_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_DBC1v0_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_DBC1v0_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_DBC1v0_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_DBC1v0_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_DBC1v0_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_DBC1v0_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_DBC1v0_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_DBC1v0_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_DBC1v0_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_DBC1v0_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_DBC1v0_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_DBC1v0_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_DBC1v0_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_DBC1v0_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_DBC1v0_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_DBC1v0_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_DBC1v0_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_DBC1v0_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_DBC1v0_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_DBC1v0_y.append(value)

                if key == "db_mon_1.2v(vaux9)":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_DBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_DBC1v2_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_DBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_DBC1v2_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_DBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_DBC1v2_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_DBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_DBC1v2_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_DBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_DBC1v2_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_DBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_DBC1v2_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_DBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_DBC1v2_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_DBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_DBC1v2_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_DBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_DBC1v2_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_DBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_DBC1v2_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_DBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_DBC1v2_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_DBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_DBC1v2_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_DBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_DBC1v2_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_DBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_DBC1v2_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_DBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_DBC1v2_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_DBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_DBC1v2_y.append(value)

                if key == "db_mon_1.5v(vaux3)":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_DBC1v5_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_DBC1v5_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_DBC1v5_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_DBC1v5_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_DBC1v5_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_DBC1v5_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_DBC1v5_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_DBC1v5_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_DBC1v5_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_DBC1v5_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_DBC1v5_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_DBC1v5_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_DBC1v5_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_DBC1v5_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_DBC1v5_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_DBC1v5_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_DBC1v5_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_DBC1v5_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_DBC1v5_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_DBC1v5_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_DBC1v5_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_DBC1v5_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_DBC1v5_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_DBC1v5_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_DBC1v5_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_DBC1v5_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_DBC1v5_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_DBC1v5_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_DBC1v5_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_DBC1v5_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_DBC1v5_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_DBC1v5_y.append(value)

                if key == "db_mon_1.8v(vaux8)":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_DBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_DBC1v8_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_DBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_DBC1v8_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_DBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_DBC1v8_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_DBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_DBC1v8_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_DBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_DBC1v8_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_DBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_DBC1v8_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_DBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_DBC1v8_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_DBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_DBC1v8_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_DBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_DBC1v8_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_DBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_DBC1v8_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_DBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_DBC1v8_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_DBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_DBC1v8_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_DBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_DBC1v8_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_DBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_DBC1v8_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_DBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_DBC1v8_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_DBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_DBC1v8_y.append(value)

                if key == "db_mon_2.5v(vaux1)":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_DBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_DBC2v5_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_DBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_DBC2v5_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_DBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_DBC2v5_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_DBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_DBC2v5_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_DBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_DBC2v5_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_DBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_DBC2v5_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_DBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_DBC2v5_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_DBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_DBC2v5_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_DBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_DBC2v5_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_DBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_DBC2v5_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_DBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_DBC2v5_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_DBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_DBC2v5_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_DBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_DBC2v5_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_DBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_DBC2v5_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_DBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_DBC2v5_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_DBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_DBC2v5_y.append(value)

                if key == "db_mon_3.3v(vaux11)":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_DBC3v3_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_DBC3v3_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_DBC3v3_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_DBC3v3_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_DBC3v3_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_DBC3v3_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_DBC3v3_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_DBC3v3_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_DBC3v3_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_DBC3v3_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_DBC3v3_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_DBC3v3_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_DBC3v3_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_DBC3v3_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_DBC3v3_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_DBC3v3_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_DBC3v3_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_DBC3v3_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_DBC3v3_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_DBC3v3_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_DBC3v3_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_DBC3v3_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_DBC3v3_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_DBC3v3_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_DBC3v3_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_DBC3v3_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_DBC3v3_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_DBC3v3_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_DBC3v3_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_DBC3v3_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_DBC3v3_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_DBC3v3_y.append(value)

                if key == "mb_mon_+5v(vaux10)":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_MBCP5v_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_MBCP5v_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_MBCP5v_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_MBCP5v_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_MBCP5v_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_MBCP5v_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_MBCP5v_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_MBCP5v_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_MBCP5v_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_MBCP5v_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_MBCP5v_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_MBCP5v_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_MBCP5v_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_MBCP5v_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_MBCP5v_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_MBCP5v_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_MBCP5v_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_MBCP5v_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_MBCP5v_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_MBCP5v_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_MBCP5v_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_MBCP5v_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_MBCP5v_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_MBCP5v_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_MBCP5v_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_MBCP5v_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_MBCP5v_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_MBCP5v_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_MBCP5v_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_MBCP5v_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_MBCP5v_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_MBCP5v_y.append(value)

                if key == "mb_mon_-5v(vaux7)":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_MBCN5v_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_MBCN5v_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_MBCN5v_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_MBCN5v_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_MBCN5v_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_MBCN5v_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_MBCN5v_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_MBCN5v_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_MBCN5v_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_MBCN5v_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_MBCN5v_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_MBCN5v_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_MBCN5v_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_MBCN5v_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_MBCN5v_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_MBCN5v_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_MBCN5v_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_MBCN5v_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_MBCN5v_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_MBCN5v_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_MBCN5v_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_MBCN5v_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_MBCN5v_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_MBCN5v_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_MBCN5v_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_MBCN5v_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_MBCN5v_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_MBCN5v_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_MBCN5v_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_MBCN5v_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_MBCN5v_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_MBCN5v_y.append(value)

                if key == "mb_mon_1.2v(vaux14)":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_MBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_MBC1v2_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_MBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_MBC1v2_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_MBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_MBC1v2_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_MBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_MBC1v2_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_MBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_MBC1v2_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_MBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_MBC1v2_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_MBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_MBC1v2_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_MBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_MBC1v2_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_MBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_MBC1v2_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_MBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_MBC1v2_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_MBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_MBC1v2_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_MBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_MBC1v2_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_MBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_MBC1v2_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_MBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_MBC1v2_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_MBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_MBC1v2_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_MBC1v2_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_MBC1v2_y.append(value)

                if key == "mb_mon_1.8v(vaux12)":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_MBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_MBC1v8_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_MBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_MBC1v8_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_MBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_MBC1v8_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_MBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_MBC1v8_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_MBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_MBC1v8_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_MBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_MBC1v8_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_MBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_MBC1v8_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_MBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_MBC1v8_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_MBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_MBC1v8_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_MBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_MBC1v8_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_MBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_MBC1v8_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_MBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_MBC1v8_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_MBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_MBC1v8_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_MBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_MBC1v8_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_MBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_MBC1v8_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_MBC1v8_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_MBC1v8_y.append(value)

                if key == "mb_mon_2.5v(vaux15)":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_MBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_MBC2v5_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_MBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_MBC2v5_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_MBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_MBC2v5_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_MBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_MBC2v5_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_MBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_MBC2v5_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_MBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_MBC2v5_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_MBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_MBC2v5_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_MBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_MBC2v5_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_MBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_MBC2v5_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_MBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_MBC2v5_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_MBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_MBC2v5_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_MBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_MBC2v5_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_MBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_MBC2v5_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_MBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_MBC2v5_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_MBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_MBC2v5_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_MBC2v5_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_MBC2v5_y.append(value)

                if key == "max_temp":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_MAXTEMP_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_MAXTEMP_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_MAXTEMP_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_MAXTEMP_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_MAXTEMP_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_MAXTEMP_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_MAXTEMP_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_MAXTEMP_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_MAXTEMP_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_MAXTEMP_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_MAXTEMP_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_MAXTEMP_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_MAXTEMP_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_MAXTEMP_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_MAXTEMP_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_MAXTEMP_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_MAXTEMP_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_MAXTEMP_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_MAXTEMP_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_MAXTEMP_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_MAXTEMP_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_MAXTEMP_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_MAXTEMP_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_MAXTEMP_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_MAXTEMP_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_MAXTEMP_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_MAXTEMP_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_MAXTEMP_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_MAXTEMP_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_MAXTEMP_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_MAXTEMP_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_MAXTEMP_y.append(value)

                if key == "max_vccint":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_MAXVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_MAXVCCINT_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_MAXVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_MAXVCCINT_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_MAXVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_MAXVCCINT_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_MAXVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_MAXVCCINT_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_MAXVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_MAXVCCINT_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_MAXVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_MAXVCCINT_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_MAXVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_MAXVCCINT_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_MAXVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_MAXVCCINT_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_MAXVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_MAXVCCINT_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_MAXVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_MAXVCCINT_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_MAXVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_MAXVCCINT_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_MAXVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_MAXVCCINT_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_MAXVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_MAXVCCINT_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_MAXVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_MAXVCCINT_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_MAXVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_MAXVCCINT_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_MAXVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_MAXVCCINT_y.append(value)                                

                if key == "min_vccint":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_MINVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_MINVCCINT_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_MINVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_MINVCCINT_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_MINVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_MINVCCINT_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_MINVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_MINVCCINT_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_MINVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_MINVCCINT_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_MINVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_MINVCCINT_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_MINVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_MINVCCINT_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_MINVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_MINVCCINT_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_MINVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_MINVCCINT_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_MINVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_MINVCCINT_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_MINVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_MINVCCINT_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_MINVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_MINVCCINT_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_MINVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_MINVCCINT_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_MINVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_MINVCCINT_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_MINVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_MINVCCINT_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_MINVCCINT_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_MINVCCINT_y.append(value)                                

                if key == "max_vccout":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_MAXVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_MAXVCCOUT_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_MAXVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_MAXVCCOUT_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_MAXVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_MAXVCCOUT_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_MAXVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_MAXVCCOUT_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_MAXVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_MAXVCCOUT_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_MAXVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_MAXVCCOUT_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_MAXVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_MAXVCCOUT_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_MAXVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_MAXVCCOUT_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_MAXVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_MAXVCCOUT_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_MAXVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_MAXVCCOUT_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_MAXVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_MAXVCCOUT_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_MAXVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_MAXVCCOUT_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_MAXVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_MAXVCCOUT_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_MAXVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_MAXVCCOUT_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_MAXVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_MAXVCCOUT_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_MAXVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_MAXVCCOUT_y.append(value)                                

                if key == "min_vccout":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_MINVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_MINVCCOUT_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_MINVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_MINVCCOUT_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_MINVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_MINVCCOUT_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_MINVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_MINVCCOUT_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_MINVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_MINVCCOUT_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_MINVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_MINVCCOUT_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_MINVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_MINVCCOUT_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_MINVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_MINVCCOUT_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_MINVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_MINVCCOUT_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_MINVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_MINVCCOUT_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_MINVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_MINVCCOUT_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_MINVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_MINVCCOUT_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_MINVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_MINVCCOUT_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_MINVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_MINVCCOUT_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_MINVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_MINVCCOUT_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_MINVCCOUT_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_MINVCCOUT_y.append(value)                                

                if key == "max_vram":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_MAX_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_MAX_VRAM_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_MAX_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_MAX_VRAM_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_MAX_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_MAX_VRAM_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_MAX_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_MAX_VRAM_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_MAX_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_MAX_VRAM_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_MAX_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_MAX_VRAM_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_MAX_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_MAX_VRAM_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_MAX_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_MAX_VRAM_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_MAX_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_MAX_VRAM_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_MAX_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_MAX_VRAM_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_MAX_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_MAX_VRAM_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_MAX_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_MAX_VRAM_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_MAX_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_MAX_VRAM_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_MAX_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_MAX_VRAM_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_MAX_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_MAX_VRAM_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_MAX_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_MAX_VRAM_y.append(value)                                

                if key == "min_vram":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_MIN_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_MIN_VRAM_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_MIN_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_MIN_VRAM_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_MIN_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_MIN_VRAM_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_MIN_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_MIN_VRAM_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_MIN_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_MIN_VRAM_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_MIN_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_MIN_VRAM_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_MIN_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_MIN_VRAM_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_MIN_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_MIN_VRAM_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_MIN_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_MIN_VRAM_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_MIN_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_MIN_VRAM_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_MIN_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_MIN_VRAM_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_MIN_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_MIN_VRAM_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_MIN_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_MIN_VRAM_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_MIN_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_MIN_VRAM_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_MIN_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_MIN_VRAM_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_MIN_VRAM_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_MIN_VRAM_y.append(value)

                if key == "pgood_db_0v95":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_DBPGOOD0v95_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_DBPGOOD0v95_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_DBPGOOD0v95_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_DBPGOOD0v95_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_DBPGOOD0v95_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_DBPGOOD0v95_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_DBPGOOD0v95_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_DBPGOOD0v95_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_DBPGOOD0v95_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_DBPGOOD0v95_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_DBPGOOD0v95_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_DBPGOOD0v95_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_DBPGOOD0v95_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_DBPGOOD0v95_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_DBPGOOD0v95_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_DBPGOOD0v95_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_DBPGOOD0v95_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_DBPGOOD0v95_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_DBPGOOD0v95_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_DBPGOOD0v95_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_DBPGOOD0v95_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_DBPGOOD0v95_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_DBPGOOD0v95_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_DBPGOOD0v95_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_DBPGOOD0v95_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_DBPGOOD0v95_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_DBPGOOD0v95_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_DBPGOOD0v95_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_DBPGOOD0v95_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_DBPGOOD0v95_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_DBPGOOD0v95_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_DBPGOOD0v95_y.append(value)

                if key == "pgood_db_1v0":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_DBPGOOD1v0_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_DBPGOOD1v0_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_DBPGOOD1v0_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_DBPGOOD1v0_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_DBPGOOD1v0_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_DBPGOOD1v0_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_DBPGOOD1v0_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_DBPGOOD1v0_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_DBPGOOD1v0_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_DBPGOOD1v0_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_DBPGOOD1v0_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_DBPGOOD1v0_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_DBPGOOD1v0_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_DBPGOOD1v0_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_DBPGOOD1v0_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_DBPGOOD1v0_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_DBPGOOD1v0_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_DBPGOOD1v0_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_DBPGOOD1v0_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_DBPGOOD1v0_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_DBPGOOD1v0_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_DBPGOOD1v0_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_DBPGOOD1v0_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_DBPGOOD1v0_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_DBPGOOD1v0_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_DBPGOOD1v0_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_DBPGOOD1v0_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_DBPGOOD1v0_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_DBPGOOD1v0_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_DBPGOOD1v0_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_DBPGOOD1v0_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_DBPGOOD1v0_y.append(value)

                if key == "pgood_db_1v2":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_DBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_DBPGOOD1v2_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_DBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_DBPGOOD1v2_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_DBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_DBPGOOD1v2_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_DBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_DBPGOOD1v2_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_DBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_DBPGOOD1v2_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_DBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_DBPGOOD1v2_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_DBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_DBPGOOD1v2_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_DBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_DBPGOOD1v2_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_DBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_DBPGOOD1v2_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_DBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_DBPGOOD1v2_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_DBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_DBPGOOD1v2_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_DBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_DBPGOOD1v2_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_DBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_DBPGOOD1v2_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_DBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_DBPGOOD1v2_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_DBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_DBPGOOD1v2_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_DBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_DBPGOOD1v2_y.append(value)

                if key == "pgood_db_1v5":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_DBPGOOD1v5_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_DBPGOOD1v5_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_DBPGOOD1v5_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_DBPGOOD1v5_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_DBPGOOD1v5_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_DBPGOOD1v5_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_DBPGOOD1v5_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_DBPGOOD1v5_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_DBPGOOD1v5_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_DBPGOOD1v5_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_DBPGOOD1v5_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_DBPGOOD1v5_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_DBPGOOD1v5_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_DBPGOOD1v5_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_DBPGOOD1v5_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_DBPGOOD1v5_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_DBPGOOD1v5_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_DBPGOOD1v5_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_DBPGOOD1v5_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_DBPGOOD1v5_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_DBPGOOD1v5_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_DBPGOOD1v5_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_DBPGOOD1v5_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_DBPGOOD1v5_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_DBPGOOD1v5_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_DBPGOOD1v5_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_DBPGOOD1v5_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_DBPGOOD1v5_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_DBPGOOD1v5_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_DBPGOOD1v5_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_DBPGOOD1v5_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_DBPGOOD1v5_y.append(value)

                if key == "pgood_db_1v8":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_DBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_DBPGOOD1v8_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_DBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_DBPGOOD1v8_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_DBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_DBPGOOD1v8_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_DBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_DBPGOOD1v8_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_DBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_DBPGOOD1v8_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_DBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_DBPGOOD1v8_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_DBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_DBPGOOD1v8_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_DBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_DBPGOOD1v8_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_DBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_DBPGOOD1v8_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_DBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_DBPGOOD1v8_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_DBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_DBPGOOD1v8_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_DBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_DBPGOOD1v8_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_DBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_DBPGOOD1v8_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_DBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_DBPGOOD1v8_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_DBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_DBPGOOD1v8_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_DBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_DBPGOOD1v8_y.append(value)

                if key == "pgood_db_2v5":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_DBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_DBPGOOD2v5_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_DBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_DBPGOOD2v5_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_DBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_DBPGOOD2v5_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_DBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_DBPGOOD2v5_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_DBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_DBPGOOD2v5_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_DBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_DBPGOOD2v5_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_DBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_DBPGOOD2v5_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_DBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_DBPGOOD2v5_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_DBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_DBPGOOD2v5_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_DBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_DBPGOOD2v5_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_DBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_DBPGOOD2v5_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_DBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_DBPGOOD2v5_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_DBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_DBPGOOD2v5_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_DBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_DBPGOOD2v5_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_DBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_DBPGOOD2v5_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_DBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_DBPGOOD2v5_y.append(value)

                if key == "pgood_db_3v3":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_DBPGOOD3v3_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_DBPGOOD3v3_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_DBPGOOD3v3_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_DBPGOOD3v3_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_DBPGOOD3v3_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_DBPGOOD3v3_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_DBPGOOD3v3_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_DBPGOOD3v3_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_DBPGOOD3v3_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_DBPGOOD3v3_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_DBPGOOD3v3_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_DBPGOOD3v3_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_DBPGOOD3v3_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_DBPGOOD3v3_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_DBPGOOD3v3_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_DBPGOOD3v3_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_DBPGOOD3v3_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_DBPGOOD3v3_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_DBPGOOD3v3_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_DBPGOOD3v3_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_DBPGOOD3v3_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_DBPGOOD3v3_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_DBPGOOD3v3_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_DBPGOOD3v3_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_DBPGOOD3v3_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_DBPGOOD3v3_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_DBPGOOD3v3_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_DBPGOOD3v3_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_DBPGOOD3v3_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_DBPGOOD3v3_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_DBPGOOD3v3_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_DBPGOOD3v3_y.append(value)

                if key == "pgood_mb_5v0":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_MBPGOODP5v_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_MBPGOODP5v_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_MBPGOODP5v_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_MBPGOODP5v_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_MBPGOODP5v_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_MBPGOODP5v_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_MBPGOODP5v_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_MBPGOODP5v_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_MBPGOODP5v_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_MBPGOODP5v_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_MBPGOODP5v_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_MBPGOODP5v_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_MBPGOODP5v_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_MBPGOODP5v_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_MBPGOODP5v_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_MBPGOODP5v_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_MBPGOODP5v_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_MBPGOODP5v_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_MBPGOODP5v_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_MBPGOODP5v_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_MBPGOODP5v_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_MBPGOODP5v_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_MBPGOODP5v_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_MBPGOODP5v_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_MBPGOODP5v_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_MBPGOODP5v_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_MBPGOODP5v_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_MBPGOODP5v_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_MBPGOODP5v_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_MBPGOODP5v_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_MBPGOODP5v_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_MBPGOODP5v_y.append(value)

                if key == "pgood_mb_5v0_n":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_MBPGOODN5v_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_MBPGOODN5v_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_MBPGOODN5v_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_MBPGOODN5v_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_MBPGOODN5v_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_MBPGOODN5v_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_MBPGOODN5v_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_MBPGOODN5v_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_MBPGOODN5v_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_MBPGOODN5v_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_MBPGOODN5v_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_MBPGOODN5v_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_MBPGOODN5v_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_MBPGOODN5v_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_MBPGOODN5v_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_MBPGOODN5v_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_MBPGOODN5v_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_MBPGOODN5v_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_MBPGOODN5v_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_MBPGOODN5v_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_MBPGOODN5v_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_MBPGOODN5v_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_MBPGOODN5v_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_MBPGOODN5v_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_MBPGOODN5v_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_MBPGOODN5v_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_MBPGOODN5v_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_MBPGOODN5v_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_MBPGOODN5v_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_MBPGOODN5v_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_MBPGOODN5v_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_MBPGOODN5v_y.append(value)

                if key == "pgood_mb_1v2":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_MBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_MBPGOOD1v2_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_MBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_MBPGOOD1v2_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_MBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_MBPGOOD1v2_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_MBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_MBPGOOD1v2_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_MBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_MBPGOOD1v2_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_MBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_MBPGOOD1v2_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_MBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_MBPGOOD1v2_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_MBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_MBPGOOD1v2_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_MBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_MBPGOOD1v2_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_MBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_MBPGOOD1v2_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_MBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_MBPGOOD1v2_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_MBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_MBPGOOD1v2_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_MBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_MBPGOOD1v2_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_MBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_MBPGOOD1v2_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_MBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_MBPGOOD1v2_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_MBPGOOD1v2_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_MBPGOOD1v2_y.append(value)

                if key == "pgood_mb_1v8":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_MBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_MBPGOOD1v8_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_MBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_MBPGOOD1v8_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_MBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_MBPGOOD1v8_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_MBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_MBPGOOD1v8_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_MBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_MBPGOOD1v8_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_MBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_MBPGOOD1v8_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_MBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_MBPGOOD1v8_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_MBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_MBPGOOD1v8_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_MBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_MBPGOOD1v8_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_MBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_MBPGOOD1v8_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_MBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_MBPGOOD1v8_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_MBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_MBPGOOD1v8_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_MBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_MBPGOOD1v8_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_MBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_MBPGOOD1v8_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_MBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_MBPGOOD1v8_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_MBPGOOD1v8_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_MBPGOOD1v8_y.append(value)

                if key == "pgood_mb_2v5":
                    if selectMD1 and selectEmu and selectA:
                        MD1_Emu_A_MBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_A_MBPGOOD2v5_y.append(value)
                    elif selectMD1 and selectEmu and selectB:
                        MD1_Emu_B_MBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD1_Emu_B_MBPGOOD2v5_y.append(value)
                    elif selectMD2 and selectEmu and selectA:
                        MD2_Emu_A_MBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_A_MBPGOOD2v5_y.append(value)
                    elif selectMD2 and selectEmu and selectB:
                        MD2_Emu_B_MBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD2_Emu_B_MBPGOOD2v5_y.append(value)
                    elif selectMD3 and selectEmu and selectA:
                        MD3_Emu_A_MBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_A_MBPGOOD2v5_y.append(value)
                    elif selectMD3 and selectEmu and selectB:
                        MD3_Emu_B_MBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD3_Emu_B_MBPGOOD2v5_y.append(value)
                    elif selectMD4 and selectEmu and selectA:
                        MD4_Emu_A_MBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_A_MBPGOOD2v5_y.append(value)
                    elif selectMD4 and selectEmu and selectB:
                        MD4_Emu_B_MBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD4_Emu_B_MBPGOOD2v5_y.append(value)
                    elif selectMD1 and selectPpr and selectA:
                        MD1_Ppr_A_MBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_A_MBPGOOD2v5_y.append(value)
                    elif selectMD1 and selectPpr and selectB:
                        MD1_Ppr_B_MBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD1_Ppr_B_MBPGOOD2v5_y.append(value)
                    elif selectMD2 and selectPpr and selectA:
                        MD2_Ppr_A_MBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_A_MBPGOOD2v5_y.append(value)
                    elif selectMD2 and selectPpr and selectB:
                        MD2_Ppr_B_MBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD2_Ppr_B_MBPGOOD2v5_y.append(value)
                    elif selectMD3 and selectPpr and selectA:
                        MD3_Ppr_A_MBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_A_MBPGOOD2v5_y.append(value)
                    elif selectMD3 and selectPpr and selectB:
                        MD3_Ppr_B_MBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD3_Ppr_B_MBPGOOD2v5_y.append(value)
                    elif selectMD4 and selectPpr and selectA:
                        MD4_Ppr_A_MBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_A_MBPGOOD2v5_y.append(value)
                    elif selectMD4 and selectPpr and selectB:
                        MD4_Ppr_B_MBPGOOD2v5_x.append(datetime.fromisoformat(point['time']))
                        MD4_Ppr_B_MBPGOOD2v5_y.append(value)

            # Reset Selection
            selectMD1 = 0
            selectMD2 = 0
            selectMD3 = 0
            selectMD4 = 0
            selectEmu = 0
            selectPpr = 0
            selectA   = 0
            selectB   = 0

        print(f'Number of Events: {nevents}')

        ### DataFrames ###
        # db_mon_0.95v(aux0)
        # MD1 Emu
        df_DBC0v95_MD1EmuA = pd.DataFrame( {'name': ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_DBC0v95_x), # Fix Naming Nomenclature
                                            'x'   : MD1_Emu_A_DBC0v95_x,
                                            'y'   : MD1_Emu_A_DBC0v95_y} )
        df_DBC0v95_MD1EmuB = pd.DataFrame( {'name': ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_DBC0v95_x), # Fix Naming Nomenclature
                                            'x'   : MD1_Emu_B_DBC0v95_x,
                                            'y'   : MD1_Emu_B_DBC0v95_y} )

        df_DBC0v95_MD1Emu = pd.concat( [df_DBC0v95_MD1EmuA, df_DBC0v95_MD1EmuB] )

        # MD2 Emu
        df_DBC0v95_MD2EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD2_Emu_A_DBC0v95_x), # Fix Naming Nomenclature
                                            'x'   : MD2_Emu_A_DBC0v95_x,
                                            'y'   : MD2_Emu_A_DBC0v95_y} )
        df_DBC0v95_MD2EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD2_Emu_B_DBC0v95_x), # Fix Naming Nomenclature
                                            'x'   : MD2_Emu_B_DBC0v95_x,
                                            'y'   : MD2_Emu_B_DBC0v95_y} )

        df_DBC0v95_MD2Emu = pd.concat( [df_DBC0v95_MD2EmuA, df_DBC0v95_MD2EmuB] )

        # MD3 Emu
        df_DBC0v95_MD3EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD3_Emu_A_DBC0v95_x), # Fix Naming Nomenclature
                                            'x'   : MD3_Emu_A_DBC0v95_x,
                                            'y'   : MD3_Emu_A_DBC0v95_y} )
        df_DBC0v95_MD3EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD3_Emu_B_DBC0v95_x), # Fix Naming Nomenclature
                                            'x'   : MD3_Emu_B_DBC0v95_x,
                                            'y'   : MD3_Emu_B_DBC0v95_y} )

        df_DBC0v95_MD3Emu = pd.concat( [df_DBC0v95_MD3EmuA, df_DBC0v95_MD3EmuB] )

        # MD4 Emu
        df_DBC0v95_MD4EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD4_Emu_A_DBC0v95_x), # Fix Naming Nomenclature
                                            'x'   : MD4_Emu_A_DBC0v95_x,
                                            'y'   : MD4_Emu_A_DBC0v95_y} )
        df_DBC0v95_MD4EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD4_Emu_B_DBC0v95_x), # Fix Naming Nomenclature
                                            'x'   : MD4_Emu_B_DBC0v95_x,
                                            'y'   : MD4_Emu_B_DBC0v95_y} )

        df_DBC0v95_MD4Emu = pd.concat( [df_DBC0v95_MD4EmuA, df_DBC0v95_MD4EmuB] )

        # MD1 Ppr
        df_DBC0v95_MD1PprA = pd.DataFrame( {'name': ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_DBC0v95_x), # Fix Naming Nomenclature
                                            'x'   : MD1_Ppr_A_DBC0v95_x,
                                            'y'   : MD1_Ppr_A_DBC0v95_y} )
        df_DBC0v95_MD1PprB = pd.DataFrame( {'name': ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_DBC0v95_x), # Fix Naming Nomenclature
                                            'x'   : MD1_Ppr_B_DBC0v95_x,
                                            'y'   : MD1_Ppr_B_DBC0v95_y} )

        df_DBC0v95_MD1Ppr = pd.concat( [df_DBC0v95_MD1PprA, df_DBC0v95_MD1PprB] )

        # MD2 Ppr
        df_DBC0v95_MD2PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD2_Ppr_A_DBC0v95_x), # Fix Naming Nomenclature
                                            'x'   : MD2_Ppr_A_DBC0v95_x,
                                            'y'   : MD2_Ppr_A_DBC0v95_y} )
        df_DBC0v95_MD2PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD2_Ppr_B_DBC0v95_x), # Fix Naming Nomenclature
                                            'x'   : MD2_Ppr_B_DBC0v95_x,
                                            'y'   : MD2_Ppr_B_DBC0v95_y} )

        df_DBC0v95_MD2Ppr = pd.concat( [df_DBC0v95_MD2PprA, df_DBC0v95_MD2PprB] )

        # MD3 Ppr
        df_DBC0v95_MD3PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD3_Ppr_A_DBC0v95_x), # Fix Naming Nomenclature
                                            'x'   : MD3_Ppr_A_DBC0v95_x,
                                            'y'   : MD3_Ppr_A_DBC0v95_y} )
        df_DBC0v95_MD3PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD3_Ppr_B_DBC0v95_x), # Fix Naming Nomenclature
                                            'x'   : MD3_Ppr_B_DBC0v95_x,
                                            'y'   : MD3_Ppr_B_DBC0v95_y} )

        df_DBC0v95_MD3Ppr = pd.concat( [df_DBC0v95_MD3PprA, df_DBC0v95_MD3PprB] )

        # MD4 Ppr
        df_DBC0v95_MD4PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD4_Ppr_A_DBC0v95_x), # Fix Naming Nomenclature
                                            'x'   : MD4_Ppr_A_DBC0v95_x,
                                            'y'   : MD4_Ppr_A_DBC0v95_y} )
        df_DBC0v95_MD4PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD4_Ppr_B_DBC0v95_x), # Fix Naming Nomenclature
                                            'x'   : MD4_Ppr_B_DBC0v95_x,
                                            'y'   : MD4_Ppr_B_DBC0v95_y} )

        df_DBC0v95_MD4Ppr = pd.concat( [df_DBC0v95_MD4PprA, df_DBC0v95_MD4PprB] )



        #db_mon_1.0v(vaux5)
        # MD1 Emu
        df_DBC1v0_MD1EmuA = pd.DataFrame( {'name': ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_DBC1v0_x), # Fix Naming Nomenclature
                                            'x'   : MD1_Emu_A_DBC1v0_x,
                                            'y'   : MD1_Emu_A_DBC1v0_y} )
        df_DBC1v0_MD1EmuB = pd.DataFrame( {'name': ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_DBC1v0_x), # Fix Naming Nomenclature
                                            'x'   : MD1_Emu_B_DBC1v0_x,
                                            'y'   : MD1_Emu_B_DBC1v0_y} )

        df_DBC1v0_MD1Emu = pd.concat( [df_DBC1v0_MD1EmuA, df_DBC1v0_MD1EmuB] )

        # MD2 Emu
        df_DBC1v0_MD2EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD2_Emu_A_DBC1v0_x), # Fix Naming Nomenclature
                                            'x'   : MD2_Emu_A_DBC1v0_x,
                                            'y'   : MD2_Emu_A_DBC1v0_y} )
        df_DBC1v0_MD2EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD2_Emu_B_DBC1v0_x), # Fix Naming Nomenclature
                                            'x'   : MD2_Emu_B_DBC1v0_x,
                                            'y'   : MD2_Emu_B_DBC1v0_y} )

        df_DBC1v0_MD2Emu = pd.concat( [df_DBC1v0_MD2EmuA, df_DBC1v0_MD2EmuB] )

        # MD3 Emu
        df_DBC1v0_MD3EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD3_Emu_A_DBC1v0_x), # Fix Naming Nomenclature
                                            'x'   : MD3_Emu_A_DBC1v0_x,
                                            'y'   : MD3_Emu_A_DBC1v0_y} )
        df_DBC1v0_MD3EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD3_Emu_B_DBC1v0_x), # Fix Naming Nomenclature
                                            'x'   : MD3_Emu_B_DBC1v0_x,
                                            'y'   : MD3_Emu_B_DBC1v0_y} )

        df_DBC1v0_MD3Emu = pd.concat( [df_DBC1v0_MD3EmuA, df_DBC1v0_MD3EmuB] )

        # MD4 Emu
        df_DBC1v0_MD4EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD4_Emu_A_DBC1v0_x), # Fix Naming Nomenclature
                                            'x'   : MD4_Emu_A_DBC1v0_x,
                                            'y'   : MD4_Emu_A_DBC1v0_y} )
        df_DBC1v0_MD4EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD4_Emu_B_DBC1v0_x), # Fix Naming Nomenclature
                                            'x'   : MD4_Emu_B_DBC1v0_x,
                                            'y'   : MD4_Emu_B_DBC1v0_y} )

        df_DBC1v0_MD4Emu = pd.concat( [df_DBC1v0_MD4EmuA, df_DBC1v0_MD4EmuB] )

        # MD1 Ppr
        df_DBC1v0_MD1PprA = pd.DataFrame( {'name': ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_DBC1v0_x), # Fix Naming Nomenclature
                                            'x'   : MD1_Ppr_A_DBC1v0_x,
                                            'y'   : MD1_Ppr_A_DBC1v0_y} )
        df_DBC1v0_MD1PprB = pd.DataFrame( {'name': ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_DBC1v0_x), # Fix Naming Nomenclature
                                            'x'   : MD1_Ppr_B_DBC1v0_x,
                                            'y'   : MD1_Ppr_B_DBC1v0_y} )

        df_DBC1v0_MD1Ppr = pd.concat( [df_DBC1v0_MD1PprA, df_DBC1v0_MD1PprB] )

        # MD2 Ppr
        df_DBC1v0_MD2PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD2_Ppr_A_DBC1v0_x), # Fix Naming Nomenclature
                                            'x'   : MD2_Ppr_A_DBC1v0_x,
                                            'y'   : MD2_Ppr_A_DBC1v0_y} )
        df_DBC1v0_MD2PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD2_Ppr_B_DBC1v0_x), # Fix Naming Nomenclature
                                            'x'   : MD2_Ppr_B_DBC1v0_x,
                                            'y'   : MD2_Ppr_B_DBC1v0_y} )

        df_DBC1v0_MD2Ppr = pd.concat( [df_DBC1v0_MD2PprA, df_DBC1v0_MD2PprB] )

        # MD3 Ppr
        df_DBC1v0_MD3PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD3_Ppr_A_DBC1v0_x), # Fix Naming Nomenclature
                                            'x'   : MD3_Ppr_A_DBC1v0_x,
                                            'y'   : MD3_Ppr_A_DBC1v0_y} )
        df_DBC1v0_MD3PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD3_Ppr_B_DBC1v0_x), # Fix Naming Nomenclature
                                            'x'   : MD3_Ppr_B_DBC1v0_x,
                                            'y'   : MD3_Ppr_B_DBC1v0_y} )

        df_DBC1v0_MD3Ppr = pd.concat( [df_DBC1v0_MD3PprA, df_DBC1v0_MD3PprB] )

        # MD4 Ppr
        df_DBC1v0_MD4PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD4_Ppr_A_DBC1v0_x), # Fix Naming Nomenclature
                                            'x'   : MD4_Ppr_A_DBC1v0_x,
                                            'y'   : MD4_Ppr_A_DBC1v0_y} )
        df_DBC1v0_MD4PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD4_Ppr_B_DBC1v0_x), # Fix Naming Nomenclature
                                            'x'   : MD4_Ppr_B_DBC1v0_x,
                                            'y'   : MD4_Ppr_B_DBC1v0_y} )

        df_DBC1v0_MD4Ppr = pd.concat( [df_DBC1v0_MD4PprA, df_DBC1v0_MD4PprB] )



        #db_mon_1.2v(vaux9)
        # MD1 Emu
        df_DBC1v2_MD1EmuA = pd.DataFrame( {'name': ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_DBC1v2_x), # Fix Naming Nomenclature
                                            'x'   : MD1_Emu_A_DBC1v2_x,
                                            'y'   : MD1_Emu_A_DBC1v2_y} )
        df_DBC1v2_MD1EmuB = pd.DataFrame( {'name': ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_DBC1v2_x), # Fix Naming Nomenclature
                                            'x'   : MD1_Emu_B_DBC1v2_x,
                                            'y'   : MD1_Emu_B_DBC1v2_y} )

        df_DBC1v2_MD1Emu = pd.concat( [df_DBC1v2_MD1EmuA, df_DBC1v2_MD1EmuB] )

        # MD2 Emu
        df_DBC1v2_MD2EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD2_Emu_A_DBC1v2_x), # Fix Naming Nomenclature
                                            'x'   : MD2_Emu_A_DBC1v2_x,
                                            'y'   : MD2_Emu_A_DBC1v2_y} )
        df_DBC1v2_MD2EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD2_Emu_B_DBC1v2_x), # Fix Naming Nomenclature
                                            'x'   : MD2_Emu_B_DBC1v2_x,
                                            'y'   : MD2_Emu_B_DBC1v2_y} )

        df_DBC1v2_MD2Emu = pd.concat( [df_DBC1v2_MD2EmuA, df_DBC1v2_MD2EmuB] )

        # MD3 Emu
        df_DBC1v2_MD3EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD3_Emu_A_DBC1v2_x), # Fix Naming Nomenclature
                                            'x'   : MD3_Emu_A_DBC1v2_x,
                                            'y'   : MD3_Emu_A_DBC1v2_y} )
        df_DBC1v2_MD3EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD3_Emu_B_DBC1v2_x), # Fix Naming Nomenclature
                                            'x'   : MD3_Emu_B_DBC1v2_x,
                                            'y'   : MD3_Emu_B_DBC1v2_y} )

        df_DBC1v2_MD3Emu = pd.concat( [df_DBC1v2_MD3EmuA, df_DBC1v2_MD3EmuB] )

        # MD4 Emu
        df_DBC1v2_MD4EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD4_Emu_A_DBC1v2_x), # Fix Naming Nomenclature
                                            'x'   : MD4_Emu_A_DBC1v2_x,
                                            'y'   : MD4_Emu_A_DBC1v2_y} )
        df_DBC1v2_MD4EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD4_Emu_B_DBC1v2_x), # Fix Naming Nomenclature
                                            'x'   : MD4_Emu_B_DBC1v2_x,
                                            'y'   : MD4_Emu_B_DBC1v2_y} )

        df_DBC1v2_MD4Emu = pd.concat( [df_DBC1v2_MD4EmuA, df_DBC1v2_MD4EmuB] )

        # MD1 Ppr
        df_DBC1v2_MD1PprA = pd.DataFrame( {'name': ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_DBC1v2_x), # Fix Naming Nomenclature
                                            'x'   : MD1_Ppr_A_DBC1v2_x,
                                            'y'   : MD1_Ppr_A_DBC1v2_y} )
        df_DBC1v2_MD1PprB = pd.DataFrame( {'name': ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_DBC1v2_x), # Fix Naming Nomenclature
                                            'x'   : MD1_Ppr_B_DBC1v2_x,
                                            'y'   : MD1_Ppr_B_DBC1v2_y} )

        df_DBC1v2_MD1Ppr = pd.concat( [df_DBC1v2_MD1PprA, df_DBC1v2_MD1PprB] )

        # MD2 Ppr
        df_DBC1v2_MD2PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD2_Ppr_A_DBC1v2_x), # Fix Naming Nomenclature
                                            'x'   : MD2_Ppr_A_DBC1v2_x,
                                            'y'   : MD2_Ppr_A_DBC1v2_y} )
        df_DBC1v2_MD2PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD2_Ppr_B_DBC1v2_x), # Fix Naming Nomenclature
                                            'x'   : MD2_Ppr_B_DBC1v2_x,
                                            'y'   : MD2_Ppr_B_DBC1v2_y} )

        df_DBC1v2_MD2Ppr = pd.concat( [df_DBC1v2_MD2PprA, df_DBC1v2_MD2PprB] )

        # MD3 Ppr
        df_DBC1v2_MD3PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD3_Ppr_A_DBC1v2_x), # Fix Naming Nomenclature
                                            'x'   : MD3_Ppr_A_DBC1v2_x,
                                            'y'   : MD3_Ppr_A_DBC1v2_y} )
        df_DBC1v2_MD3PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD3_Ppr_B_DBC1v2_x), # Fix Naming Nomenclature
                                            'x'   : MD3_Ppr_B_DBC1v2_x,
                                            'y'   : MD3_Ppr_B_DBC1v2_y} )

        df_DBC1v2_MD3Ppr = pd.concat( [df_DBC1v2_MD3PprA, df_DBC1v2_MD3PprB] )

        # MD4 Ppr
        df_DBC1v2_MD4PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD4_Ppr_A_DBC1v2_x), # Fix Naming Nomenclature
                                            'x'   : MD4_Ppr_A_DBC1v2_x,
                                            'y'   : MD4_Ppr_A_DBC1v2_y} )
        df_DBC1v2_MD4PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD4_Ppr_B_DBC1v2_x), # Fix Naming Nomenclature
                                            'x'   : MD4_Ppr_B_DBC1v2_x,
                                            'y'   : MD4_Ppr_B_DBC1v2_y} )

        df_DBC1v2_MD4Ppr = pd.concat( [df_DBC1v2_MD4PprA, df_DBC1v2_MD4PprB] )



        #db_mon_1.5v(vaux3)
        # MD1 Emu
        df_DBC1v5_MD1EmuA = pd.DataFrame( {'name': ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_DBC1v5_x), # Fix Naming Nomenclature
                                            'x'   : MD1_Emu_A_DBC1v5_x,
                                            'y'   : MD1_Emu_A_DBC1v5_y} )
        df_DBC1v5_MD1EmuB = pd.DataFrame( {'name': ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_DBC1v5_x), # Fix Naming Nomenclature
                                            'x'   : MD1_Emu_B_DBC1v5_x,
                                            'y'   : MD1_Emu_B_DBC1v5_y} )

        df_DBC1v5_MD1Emu = pd.concat( [df_DBC1v5_MD1EmuA, df_DBC1v5_MD1EmuB] )

        # MD2 Emu
        df_DBC1v5_MD2EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD2_Emu_A_DBC1v5_x), # Fix Naming Nomenclature
                                            'x'   : MD2_Emu_A_DBC1v5_x,
                                            'y'   : MD2_Emu_A_DBC1v5_y} )
        df_DBC1v5_MD2EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD2_Emu_B_DBC1v5_x), # Fix Naming Nomenclature
                                            'x'   : MD2_Emu_B_DBC1v5_x,
                                            'y'   : MD2_Emu_B_DBC1v5_y} )

        df_DBC1v5_MD2Emu = pd.concat( [df_DBC1v5_MD2EmuA, df_DBC1v5_MD2EmuB] )

        # MD3 Emu
        df_DBC1v5_MD3EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD3_Emu_A_DBC1v5_x), # Fix Naming Nomenclature
                                            'x'   : MD3_Emu_A_DBC1v5_x,
                                            'y'   : MD3_Emu_A_DBC1v5_y} )
        df_DBC1v5_MD3EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD3_Emu_B_DBC1v5_x), # Fix Naming Nomenclature
                                            'x'   : MD3_Emu_B_DBC1v5_x,
                                            'y'   : MD3_Emu_B_DBC1v5_y} )

        df_DBC1v5_MD3Emu = pd.concat( [df_DBC1v5_MD3EmuA, df_DBC1v5_MD3EmuB] )

        # MD4 Emu
        df_DBC1v5_MD4EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD4_Emu_A_DBC1v5_x), # Fix Naming Nomenclature
                                            'x'   : MD4_Emu_A_DBC1v5_x,
                                            'y'   : MD4_Emu_A_DBC1v5_y} )
        df_DBC1v5_MD4EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD4_Emu_B_DBC1v5_x), # Fix Naming Nomenclature
                                            'x'   : MD4_Emu_B_DBC1v5_x,
                                            'y'   : MD4_Emu_B_DBC1v5_y} )

        df_DBC1v5_MD4Emu = pd.concat( [df_DBC1v5_MD4EmuA, df_DBC1v5_MD4EmuB] )

        # MD1 Ppr
        df_DBC1v5_MD1PprA = pd.DataFrame( {'name': ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_DBC1v5_x), # Fix Naming Nomenclature
                                            'x'   : MD1_Ppr_A_DBC1v5_x,
                                            'y'   : MD1_Ppr_A_DBC1v5_y} )
        df_DBC1v5_MD1PprB = pd.DataFrame( {'name': ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_DBC1v5_x), # Fix Naming Nomenclature
                                            'x'   : MD1_Ppr_B_DBC1v5_x,
                                            'y'   : MD1_Ppr_B_DBC1v5_y} )

        df_DBC1v5_MD1Ppr = pd.concat( [df_DBC1v5_MD1PprA, df_DBC1v5_MD1PprB] )

        # MD2 Ppr
        df_DBC1v5_MD2PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD2_Ppr_A_DBC1v5_x), # Fix Naming Nomenclature
                                            'x'   : MD2_Ppr_A_DBC1v5_x,
                                            'y'   : MD2_Ppr_A_DBC1v5_y} )
        df_DBC1v5_MD2PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD2_Ppr_B_DBC1v5_x), # Fix Naming Nomenclature
                                            'x'   : MD2_Ppr_B_DBC1v5_x,
                                            'y'   : MD2_Ppr_B_DBC1v5_y} )

        df_DBC1v5_MD2Ppr = pd.concat( [df_DBC1v5_MD2PprA, df_DBC1v5_MD2PprB] )

        # MD3 Ppr
        df_DBC1v5_MD3PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD3_Ppr_A_DBC1v5_x), # Fix Naming Nomenclature
                                            'x'   : MD3_Ppr_A_DBC1v5_x,
                                            'y'   : MD3_Ppr_A_DBC1v5_y} )
        df_DBC1v5_MD3PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD3_Ppr_B_DBC1v5_x), # Fix Naming Nomenclature
                                            'x'   : MD3_Ppr_B_DBC1v5_x,
                                            'y'   : MD3_Ppr_B_DBC1v5_y} )

        df_DBC1v5_MD3Ppr = pd.concat( [df_DBC1v5_MD3PprA, df_DBC1v5_MD3PprB] )

        # MD4 Ppr
        df_DBC1v5_MD4PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD4_Ppr_A_DBC1v5_x), # Fix Naming Nomenclature
                                            'x'   : MD4_Ppr_A_DBC1v5_x,
                                            'y'   : MD4_Ppr_A_DBC1v5_y} )
        df_DBC1v5_MD4PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD4_Ppr_B_DBC1v5_x), # Fix Naming Nomenclature
                                            'x'   : MD4_Ppr_B_DBC1v5_x,
                                            'y'   : MD4_Ppr_B_DBC1v5_y} )

        df_DBC1v5_MD4Ppr = pd.concat( [df_DBC1v5_MD4PprA, df_DBC1v5_MD4PprB] )



        #db_mon_1.8v(vaux8)
        # MD1 Emu
        df_DBC1v8_MD1EmuA = pd.DataFrame( {'name': ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_DBC1v8_x), # Fix Naming Nomenclature
                                            'x'   : MD1_Emu_A_DBC1v8_x,
                                            'y'   : MD1_Emu_A_DBC1v8_y} )
        df_DBC1v8_MD1EmuB = pd.DataFrame( {'name': ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_DBC1v8_x), # Fix Naming Nomenclature
                                            'x'   : MD1_Emu_B_DBC1v8_x,
                                            'y'   : MD1_Emu_B_DBC1v8_y} )

        df_DBC1v8_MD1Emu = pd.concat( [df_DBC1v8_MD1EmuA, df_DBC1v8_MD1EmuB] )

        # MD2 Emu
        df_DBC1v8_MD2EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD2_Emu_A_DBC1v8_x), # Fix Naming Nomenclature
                                            'x'   : MD2_Emu_A_DBC1v8_x,
                                            'y'   : MD2_Emu_A_DBC1v8_y} )
        df_DBC1v8_MD2EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD2_Emu_B_DBC1v8_x), # Fix Naming Nomenclature
                                            'x'   : MD2_Emu_B_DBC1v8_x,
                                            'y'   : MD2_Emu_B_DBC1v8_y} )

        df_DBC1v8_MD2Emu = pd.concat( [df_DBC1v8_MD2EmuA, df_DBC1v8_MD2EmuB] )

        # MD3 Emu
        df_DBC1v8_MD3EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD3_Emu_A_DBC1v8_x), # Fix Naming Nomenclature
                                            'x'   : MD3_Emu_A_DBC1v8_x,
                                            'y'   : MD3_Emu_A_DBC1v8_y} )
        df_DBC1v8_MD3EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD3_Emu_B_DBC1v8_x), # Fix Naming Nomenclature
                                            'x'   : MD3_Emu_B_DBC1v8_x,
                                            'y'   : MD3_Emu_B_DBC1v8_y} )

        df_DBC1v8_MD3Emu = pd.concat( [df_DBC1v8_MD3EmuA, df_DBC1v8_MD3EmuB] )

        # MD4 Emu
        df_DBC1v8_MD4EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD4_Emu_A_DBC1v8_x), # Fix Naming Nomenclature
                                            'x'   : MD4_Emu_A_DBC1v8_x,
                                            'y'   : MD4_Emu_A_DBC1v8_y} )
        df_DBC1v8_MD4EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD4_Emu_B_DBC1v8_x), # Fix Naming Nomenclature
                                            'x'   : MD4_Emu_B_DBC1v8_x,
                                            'y'   : MD4_Emu_B_DBC1v8_y} )

        df_DBC1v8_MD4Emu = pd.concat( [df_DBC1v8_MD4EmuA, df_DBC1v8_MD4EmuB] )

        # MD1 Ppr
        df_DBC1v8_MD1PprA = pd.DataFrame( {'name': ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_DBC1v8_x), # Fix Naming Nomenclature
                                            'x'   : MD1_Ppr_A_DBC1v8_x,
                                            'y'   : MD1_Ppr_A_DBC1v8_y} )
        df_DBC1v8_MD1PprB = pd.DataFrame( {'name': ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_DBC1v8_x), # Fix Naming Nomenclature
                                            'x'   : MD1_Ppr_B_DBC1v8_x,
                                            'y'   : MD1_Ppr_B_DBC1v8_y} )

        df_DBC1v8_MD1Ppr = pd.concat( [df_DBC1v8_MD1PprA, df_DBC1v8_MD1PprB] )

        # MD2 Ppr
        df_DBC1v8_MD2PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD2_Ppr_A_DBC1v8_x), # Fix Naming Nomenclature
                                            'x'   : MD2_Ppr_A_DBC1v8_x,
                                            'y'   : MD2_Ppr_A_DBC1v8_y} )
        df_DBC1v8_MD2PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD2_Ppr_B_DBC1v8_x), # Fix Naming Nomenclature
                                            'x'   : MD2_Ppr_B_DBC1v8_x,
                                            'y'   : MD2_Ppr_B_DBC1v8_y} )

        df_DBC1v8_MD2Ppr = pd.concat( [df_DBC1v8_MD2PprA, df_DBC1v8_MD2PprB] )

        # MD3 Ppr
        df_DBC1v8_MD3PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD3_Ppr_A_DBC1v8_x), # Fix Naming Nomenclature
                                            'x'   : MD3_Ppr_A_DBC1v8_x,
                                            'y'   : MD3_Ppr_A_DBC1v8_y} )
        df_DBC1v8_MD3PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD3_Ppr_B_DBC1v8_x), # Fix Naming Nomenclature
                                            'x'   : MD3_Ppr_B_DBC1v8_x,
                                            'y'   : MD3_Ppr_B_DBC1v8_y} )

        df_DBC1v8_MD3Ppr = pd.concat( [df_DBC1v8_MD3PprA, df_DBC1v8_MD3PprB] )

        # MD4 Ppr
        df_DBC1v8_MD4PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD4_Ppr_A_DBC1v8_x), # Fix Naming Nomenclature
                                            'x'   : MD4_Ppr_A_DBC1v8_x,
                                            'y'   : MD4_Ppr_A_DBC1v8_y} )
        df_DBC1v8_MD4PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD4_Ppr_B_DBC1v8_x), # Fix Naming Nomenclature
                                            'x'   : MD4_Ppr_B_DBC1v8_x,
                                            'y'   : MD4_Ppr_B_DBC1v8_y} )

        df_DBC1v8_MD4Ppr = pd.concat( [df_DBC1v8_MD4PprA, df_DBC1v8_MD4PprB] )



        #db_mon_2.5v(vaux1)
        # MD1 Emu
        df_DBC2v5_MD1EmuA = pd.DataFrame( {'name': ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_DBC2v5_x), # Fix Naming Nomenclature
                                            'x'   : MD1_Emu_A_DBC2v5_x,
                                            'y'   : MD1_Emu_A_DBC2v5_y} )
        df_DBC2v5_MD1EmuB = pd.DataFrame( {'name': ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_DBC2v5_x), # Fix Naming Nomenclature
                                            'x'   : MD1_Emu_B_DBC2v5_x,
                                            'y'   : MD1_Emu_B_DBC2v5_y} )

        df_DBC2v5_MD1Emu = pd.concat( [df_DBC2v5_MD1EmuA, df_DBC2v5_MD1EmuB] )

        # MD2 Emu
        df_DBC2v5_MD2EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD2_Emu_A_DBC2v5_x), # Fix Naming Nomenclature
                                            'x'   : MD2_Emu_A_DBC2v5_x,
                                            'y'   : MD2_Emu_A_DBC2v5_y} )
        df_DBC2v5_MD2EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD2_Emu_B_DBC2v5_x), # Fix Naming Nomenclature
                                            'x'   : MD2_Emu_B_DBC2v5_x,
                                            'y'   : MD2_Emu_B_DBC2v5_y} )

        df_DBC2v5_MD2Emu = pd.concat( [df_DBC2v5_MD2EmuA, df_DBC2v5_MD2EmuB] )

        # MD3 Emu
        df_DBC2v5_MD3EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD3_Emu_A_DBC2v5_x), # Fix Naming Nomenclature
                                            'x'   : MD3_Emu_A_DBC2v5_x,
                                            'y'   : MD3_Emu_A_DBC2v5_y} )
        df_DBC2v5_MD3EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD3_Emu_B_DBC2v5_x), # Fix Naming Nomenclature
                                            'x'   : MD3_Emu_B_DBC2v5_x,
                                            'y'   : MD3_Emu_B_DBC2v5_y} )

        df_DBC2v5_MD3Emu = pd.concat( [df_DBC2v5_MD3EmuA, df_DBC2v5_MD3EmuB] )

        # MD4 Emu
        df_DBC2v5_MD4EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD4_Emu_A_DBC2v5_x), # Fix Naming Nomenclature
                                            'x'   : MD4_Emu_A_DBC2v5_x,
                                            'y'   : MD4_Emu_A_DBC2v5_y} )
        df_DBC2v5_MD4EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD4_Emu_B_DBC2v5_x), # Fix Naming Nomenclature
                                            'x'   : MD4_Emu_B_DBC2v5_x,
                                            'y'   : MD4_Emu_B_DBC2v5_y} )

        df_DBC2v5_MD4Emu = pd.concat( [df_DBC2v5_MD4EmuA, df_DBC2v5_MD4EmuB] )

        # MD1 Ppr
        df_DBC2v5_MD1PprA = pd.DataFrame( {'name': ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_DBC2v5_x), # Fix Naming Nomenclature
                                            'x'   : MD1_Ppr_A_DBC2v5_x,
                                            'y'   : MD1_Ppr_A_DBC2v5_y} )
        df_DBC2v5_MD1PprB = pd.DataFrame( {'name': ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_DBC2v5_x), # Fix Naming Nomenclature
                                            'x'   : MD1_Ppr_B_DBC2v5_x,
                                            'y'   : MD1_Ppr_B_DBC2v5_y} )

        df_DBC2v5_MD1Ppr = pd.concat( [df_DBC2v5_MD1PprA, df_DBC2v5_MD1PprB] )

        # MD2 Ppr
        df_DBC2v5_MD2PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD2_Ppr_A_DBC2v5_x), # Fix Naming Nomenclature
                                            'x'   : MD2_Ppr_A_DBC2v5_x,
                                            'y'   : MD2_Ppr_A_DBC2v5_y} )
        df_DBC2v5_MD2PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD2_Ppr_B_DBC2v5_x), # Fix Naming Nomenclature
                                            'x'   : MD2_Ppr_B_DBC2v5_x,
                                            'y'   : MD2_Ppr_B_DBC2v5_y} )

        df_DBC2v5_MD2Ppr = pd.concat( [df_DBC2v5_MD2PprA, df_DBC2v5_MD2PprB] )

        # MD3 Ppr
        df_DBC2v5_MD3PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD3_Ppr_A_DBC2v5_x), # Fix Naming Nomenclature
                                            'x'   : MD3_Ppr_A_DBC2v5_x,
                                            'y'   : MD3_Ppr_A_DBC2v5_y} )
        df_DBC2v5_MD3PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD3_Ppr_B_DBC2v5_x), # Fix Naming Nomenclature
                                            'x'   : MD3_Ppr_B_DBC2v5_x,
                                            'y'   : MD3_Ppr_B_DBC2v5_y} )

        df_DBC2v5_MD3Ppr = pd.concat( [df_DBC2v5_MD3PprA, df_DBC2v5_MD3PprB] )

        # MD4 Ppr
        df_DBC2v5_MD4PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD4_Ppr_A_DBC2v5_x), # Fix Naming Nomenclature
                                            'x'   : MD4_Ppr_A_DBC2v5_x,
                                            'y'   : MD4_Ppr_A_DBC2v5_y} )
        df_DBC2v5_MD4PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD4_Ppr_B_DBC2v5_x), # Fix Naming Nomenclature
                                            'x'   : MD4_Ppr_B_DBC2v5_x,
                                            'y'   : MD4_Ppr_B_DBC2v5_y} )

        df_DBC2v5_MD4Ppr = pd.concat( [df_DBC2v5_MD4PprA, df_DBC2v5_MD4PprB] )



        #db_mon_3.3v(vaux11)
        # MD1 Emu
        df_DBC3v3_MD1EmuA = pd.DataFrame( {'name': ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_DBC3v3_x), # Fix Naming Nomenclature
                                            'x'   : MD1_Emu_A_DBC3v3_x,
                                            'y'   : MD1_Emu_A_DBC3v3_y} )
        df_DBC3v3_MD1EmuB = pd.DataFrame( {'name': ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_DBC3v3_x), # Fix Naming Nomenclature
                                            'x'   : MD1_Emu_B_DBC3v3_x,
                                            'y'   : MD1_Emu_B_DBC3v3_y} )

        df_DBC3v3_MD1Emu = pd.concat( [df_DBC3v3_MD1EmuA, df_DBC3v3_MD1EmuB] )

        # MD2 Emu
        df_DBC3v3_MD2EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD2_Emu_A_DBC3v3_x), # Fix Naming Nomenclature
                                            'x'   : MD2_Emu_A_DBC3v3_x,
                                            'y'   : MD2_Emu_A_DBC3v3_y} )
        df_DBC3v3_MD2EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD2_Emu_B_DBC3v3_x), # Fix Naming Nomenclature
                                            'x'   : MD2_Emu_B_DBC3v3_x,
                                            'y'   : MD2_Emu_B_DBC3v3_y} )

        df_DBC3v3_MD2Emu = pd.concat( [df_DBC3v3_MD2EmuA, df_DBC3v3_MD2EmuB] )

        # MD3 Emu
        df_DBC3v3_MD3EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD3_Emu_A_DBC3v3_x), # Fix Naming Nomenclature
                                            'x'   : MD3_Emu_A_DBC3v3_x,
                                            'y'   : MD3_Emu_A_DBC3v3_y} )
        df_DBC3v3_MD3EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD3_Emu_B_DBC3v3_x), # Fix Naming Nomenclature
                                            'x'   : MD3_Emu_B_DBC3v3_x,
                                            'y'   : MD3_Emu_B_DBC3v3_y} )

        df_DBC3v3_MD3Emu = pd.concat( [df_DBC3v3_MD3EmuA, df_DBC3v3_MD3EmuB] )

        # MD4 Emu
        df_DBC3v3_MD4EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD4_Emu_A_DBC3v3_x), # Fix Naming Nomenclature
                                            'x'   : MD4_Emu_A_DBC3v3_x,
                                            'y'   : MD4_Emu_A_DBC3v3_y} )
        df_DBC3v3_MD4EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD4_Emu_B_DBC3v3_x), # Fix Naming Nomenclature
                                            'x'   : MD4_Emu_B_DBC3v3_x,
                                            'y'   : MD4_Emu_B_DBC3v3_y} )

        df_DBC3v3_MD4Emu = pd.concat( [df_DBC3v3_MD4EmuA, df_DBC3v3_MD4EmuB] )

        # MD1 Ppr
        df_DBC3v3_MD1PprA = pd.DataFrame( {'name': ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_DBC3v3_x), # Fix Naming Nomenclature
                                            'x'   : MD1_Ppr_A_DBC3v3_x,
                                            'y'   : MD1_Ppr_A_DBC3v3_y} )
        df_DBC3v3_MD1PprB = pd.DataFrame( {'name': ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_DBC3v3_x), # Fix Naming Nomenclature
                                            'x'   : MD1_Ppr_B_DBC3v3_x,
                                            'y'   : MD1_Ppr_B_DBC3v3_y} )

        df_DBC3v3_MD1Ppr = pd.concat( [df_DBC3v3_MD1PprA, df_DBC3v3_MD1PprB] )

        # MD2 Ppr
        df_DBC3v3_MD2PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD2_Ppr_A_DBC3v3_x), # Fix Naming Nomenclature
                                            'x'   : MD2_Ppr_A_DBC3v3_x,
                                            'y'   : MD2_Ppr_A_DBC3v3_y} )
        df_DBC3v3_MD2PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD2_Ppr_B_DBC3v3_x), # Fix Naming Nomenclature
                                            'x'   : MD2_Ppr_B_DBC3v3_x,
                                            'y'   : MD2_Ppr_B_DBC3v3_y} )

        df_DBC3v3_MD2Ppr = pd.concat( [df_DBC3v3_MD2PprA, df_DBC3v3_MD2PprB] )

        # MD3 Ppr
        df_DBC3v3_MD3PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD3_Ppr_A_DBC3v3_x), # Fix Naming Nomenclature
                                            'x'   : MD3_Ppr_A_DBC3v3_x,
                                            'y'   : MD3_Ppr_A_DBC3v3_y} )
        df_DBC3v3_MD3PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD3_Ppr_B_DBC3v3_x), # Fix Naming Nomenclature
                                            'x'   : MD3_Ppr_B_DBC3v3_x,
                                            'y'   : MD3_Ppr_B_DBC3v3_y} )

        df_DBC3v3_MD3Ppr = pd.concat( [df_DBC3v3_MD3PprA, df_DBC3v3_MD3PprB] )

        # MD4 Ppr
        df_DBC3v3_MD4PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD4_Ppr_A_DBC3v3_x), # Fix Naming Nomenclature
                                            'x'   : MD4_Ppr_A_DBC3v3_x,
                                            'y'   : MD4_Ppr_A_DBC3v3_y} )
        df_DBC3v3_MD4PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD4_Ppr_B_DBC3v3_x), # Fix Naming Nomenclature
                                            'x'   : MD4_Ppr_B_DBC3v3_x,
                                            'y'   : MD4_Ppr_B_DBC3v3_y} )

        df_DBC3v3_MD4Ppr = pd.concat( [df_DBC3v3_MD4PprA, df_DBC3v3_MD4PprB] )



        # mb_mon_+5v(vaux10)
        # MD1 Emu
        df_MBCP5v_MD1EmuA = pd.DataFrame( {'name': ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_MBCP5v_x),
                                          'x'   : MD1_Emu_A_MBCP5v_x,
                                          'y'   : MD1_Emu_A_MBCP5v_y} )
        df_MBCP5v_MD1EmuB = pd.DataFrame( {'name': ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_MBCP5v_x),
                                          'x'   : MD1_Emu_B_MBCP5v_x,
                                          'y'   : MD1_Emu_B_MBCP5v_y} )

        df_MBCP5v_MD1Emu = pd.concat( [df_MBCP5v_MD1EmuA, df_MBCP5v_MD1EmuB] )

        # MD2 Emu
        df_MBCP5v_MD2EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD2_Emu_A_MBCP5v_x),
                                          'x'   : MD2_Emu_A_MBCP5v_x,
                                          'y'   : MD2_Emu_A_MBCP5v_y} )
        df_MBCP5v_MD2EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD2_Emu_B_MBCP5v_x),
                                          'x'   : MD2_Emu_B_MBCP5v_x,
                                          'y'   : MD2_Emu_B_MBCP5v_y} )

        df_MBCP5v_MD2Emu = pd.concat( [df_MBCP5v_MD2EmuA, df_MBCP5v_MD2EmuB] )

        # MD3 Emu
        df_MBCP5v_MD3EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD3_Emu_A_MBCP5v_x),
                                          'x'   : MD3_Emu_A_MBCP5v_x,
                                          'y'   : MD3_Emu_A_MBCP5v_y} )
        df_MBCP5v_MD3EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD3_Emu_B_MBCP5v_x),
                                          'x'   : MD3_Emu_B_MBCP5v_x,
                                          'y'   : MD3_Emu_B_MBCP5v_y} )

        df_MBCP5v_MD3Emu = pd.concat( [df_MBCP5v_MD3EmuA, df_MBCP5v_MD3EmuB] )

        # MD4 Emu
        df_MBCP5v_MD4EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD4_Emu_A_MBCP5v_x),
                                          'x'   : MD4_Emu_A_MBCP5v_x,
                                          'y'   : MD4_Emu_A_MBCP5v_y} )
        df_MBCP5v_MD4EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD4_Emu_B_MBCP5v_x),
                                          'x'   : MD4_Emu_B_MBCP5v_x,
                                          'y'   : MD4_Emu_B_MBCP5v_y} )

        df_MBCP5v_MD4Emu = pd.concat( [df_MBCP5v_MD4EmuA, df_MBCP5v_MD4EmuB] )

        # MD1 Ppr
        df_MBCP5v_MD1PprA = pd.DataFrame( {'name': ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_MBCP5v_x),
                                          'x'   : MD1_Ppr_A_MBCP5v_x,
                                          'y'   : MD1_Ppr_A_MBCP5v_y} )
        df_MBCP5v_MD1PprB = pd.DataFrame( {'name': ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_MBCP5v_x),
                                          'x'   : MD1_Ppr_B_MBCP5v_x,
                                          'y'   : MD1_Ppr_B_MBCP5v_y} )

        df_MBCP5v_MD1Ppr = pd.concat( [df_MBCP5v_MD1PprA, df_MBCP5v_MD1PprB] )

        # MD2 Ppr
        df_MBCP5v_MD2PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD2_Ppr_A_MBCP5v_x),
                                          'x'   : MD2_Ppr_A_MBCP5v_x,
                                          'y'   : MD2_Ppr_A_MBCP5v_y} )
        df_MBCP5v_MD2PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD2_Ppr_B_MBCP5v_x),
                                          'x'   : MD2_Ppr_B_MBCP5v_x,
                                          'y'   : MD2_Ppr_B_MBCP5v_y} )

        df_MBCP5v_MD2Ppr = pd.concat( [df_MBCP5v_MD2PprA, df_MBCP5v_MD2PprB] )

        # MD3 Ppr
        df_MBCP5v_MD3PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD3_Ppr_A_MBCP5v_x),
                                          'x'   : MD3_Ppr_A_MBCP5v_x,
                                          'y'   : MD3_Ppr_A_MBCP5v_y} )
        df_MBCP5v_MD3PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD3_Ppr_B_MBCP5v_x),
                                          'x'   : MD3_Ppr_B_MBCP5v_x,
                                          'y'   : MD3_Ppr_B_MBCP5v_y} )

        df_MBCP5v_MD3Ppr = pd.concat( [df_MBCP5v_MD3PprA, df_MBCP5v_MD3PprB] )

        # MD4 Ppr
        df_MBCP5v_MD4PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD4_Ppr_A_MBCP5v_x),
                                          'x'   : MD4_Ppr_A_MBCP5v_x,
                                          'y'   : MD4_Ppr_A_MBCP5v_y} )
        df_MBCP5v_MD4PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD4_Ppr_B_MBCP5v_x),
                                          'x'   : MD4_Ppr_B_MBCP5v_x,
                                          'y'   : MD4_Ppr_B_MBCP5v_y} )

        df_MBCP5v_MD4Ppr = pd.concat( [df_MBCP5v_MD4PprA, df_MBCP5v_MD4PprB] )

        #mb_mon_-5v(vaux7)
        # MD1 Emu
        df_MBCN5v_MD1EmuA = pd.DataFrame( {'name': ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_MBCN5v_x),
                                          'x'   : MD1_Emu_A_MBCN5v_x,
                                          'y'   : MD1_Emu_A_MBCN5v_y} )
        df_MBCN5v_MD1EmuB = pd.DataFrame( {'name': ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_MBCN5v_x),
                                          'x'   : MD1_Emu_B_MBCN5v_x,
                                          'y'   : MD1_Emu_B_MBCN5v_y} )

        df_MBCN5v_MD1Emu = pd.concat( [df_MBCN5v_MD1EmuA, df_MBCN5v_MD1EmuB] )

        # MD2 Emu
        df_MBCN5v_MD2EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD2_Emu_A_MBCN5v_x),
                                          'x'   : MD2_Emu_A_MBCN5v_x,
                                          'y'   : MD2_Emu_A_MBCN5v_y} )
        df_MBCN5v_MD2EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD2_Emu_B_MBCN5v_x),
                                          'x'   : MD2_Emu_B_MBCN5v_x,
                                          'y'   : MD2_Emu_B_MBCN5v_y} )

        df_MBCN5v_MD2Emu = pd.concat( [df_MBCN5v_MD2EmuA, df_MBCN5v_MD2EmuB] )

        # MD3 Emu
        df_MBCN5v_MD3EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD3_Emu_A_MBCN5v_x),
                                          'x'   : MD3_Emu_A_MBCN5v_x,
                                          'y'   : MD3_Emu_A_MBCN5v_y} )
        df_MBCN5v_MD3EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD3_Emu_B_MBCN5v_x),
                                          'x'   : MD3_Emu_B_MBCN5v_x,
                                          'y'   : MD3_Emu_B_MBCN5v_y} )

        df_MBCN5v_MD3Emu = pd.concat( [df_MBCN5v_MD3EmuA, df_MBCN5v_MD3EmuB] )

        # MD4 Emu
        df_MBCN5v_MD4EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD4_Emu_A_MBCN5v_x),
                                          'x'   : MD4_Emu_A_MBCN5v_x,
                                          'y'   : MD4_Emu_A_MBCN5v_y} )
        df_MBCN5v_MD4EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD4_Emu_B_MBCN5v_x),
                                          'x'   : MD4_Emu_B_MBCN5v_x,
                                          'y'   : MD4_Emu_B_MBCN5v_y} )

        df_MBCN5v_MD4Emu = pd.concat( [df_MBCN5v_MD4EmuA, df_MBCN5v_MD4EmuB] )

        # MD1 Ppr
        df_MBCN5v_MD1PprA = pd.DataFrame( {'name': ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_MBCN5v_x),
                                          'x'   : MD1_Ppr_A_MBCN5v_x,
                                          'y'   : MD1_Ppr_A_MBCN5v_y} )
        df_MBCN5v_MD1PprB = pd.DataFrame( {'name': ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_MBCN5v_x),
                                          'x'   : MD1_Ppr_B_MBCN5v_x,
                                          'y'   : MD1_Ppr_B_MBCN5v_y} )

        df_MBCN5v_MD1Ppr = pd.concat( [df_MBCN5v_MD1PprA, df_MBCN5v_MD1PprB] )

        # MD2 Ppr
        df_MBCN5v_MD2PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD2_Ppr_A_MBCN5v_x),
                                          'x'   : MD2_Ppr_A_MBCN5v_x,
                                          'y'   : MD2_Ppr_A_MBCN5v_y} )
        df_MBCN5v_MD2PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD2_Ppr_B_MBCN5v_x),
                                          'x'   : MD2_Ppr_B_MBCN5v_x,
                                          'y'   : MD2_Ppr_B_MBCN5v_y} )

        df_MBCN5v_MD2Ppr = pd.concat( [df_MBCN5v_MD2PprA, df_MBCN5v_MD2PprB] )

        # MD3 Ppr
        df_MBCN5v_MD3PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD3_Ppr_A_MBCN5v_x),
                                          'x'   : MD3_Ppr_A_MBCN5v_x,
                                          'y'   : MD3_Ppr_A_MBCN5v_y} )
        df_MBCN5v_MD3PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD3_Ppr_B_MBCN5v_x),
                                          'x'   : MD3_Ppr_B_MBCN5v_x,
                                          'y'   : MD3_Ppr_B_MBCN5v_y} )

        df_MBCN5v_MD3Ppr = pd.concat( [df_MBCN5v_MD3PprA, df_MBCN5v_MD3PprB] )

        # MD4 Ppr
        df_MBCN5v_MD4PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD4_Ppr_A_MBCN5v_x),
                                          'x'   : MD4_Ppr_A_MBCN5v_x,
                                          'y'   : MD4_Ppr_A_MBCN5v_y} )
        df_MBCN5v_MD4PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD4_Ppr_B_MBCN5v_x),
                                          'x'   : MD4_Ppr_B_MBCN5v_x,
                                          'y'   : MD4_Ppr_B_MBCN5v_y} )

        df_MBCN5v_MD4Ppr = pd.concat( [df_MBCN5v_MD4PprA, df_MBCN5v_MD4PprB] )

        #mb_mon_1.2v(vaux14)
        # MD1 Emu
        df_MBC1v2_MD1EmuA = pd.DataFrame( {'name': ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_MBC1v2_x),
                                          'x'   : MD1_Emu_A_MBC1v2_x,
                                          'y'   : MD1_Emu_A_MBC1v2_y} )
        df_MBC1v2_MD1EmuB = pd.DataFrame( {'name': ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_MBC1v2_x),
                                          'x'   : MD1_Emu_B_MBC1v2_x,
                                          'y'   : MD1_Emu_B_MBC1v2_y} )

        df_MBC1v2_MD1Emu = pd.concat( [df_MBC1v2_MD1EmuA, df_MBC1v2_MD1EmuB] )

        # MD2 Emu
        df_MBC1v2_MD2EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD2_Emu_A_MBC1v2_x),
                                          'x'   : MD2_Emu_A_MBC1v2_x,
                                          'y'   : MD2_Emu_A_MBC1v2_y} )
        df_MBC1v2_MD2EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD2_Emu_B_MBC1v2_x),
                                          'x'   : MD2_Emu_B_MBC1v2_x,
                                          'y'   : MD2_Emu_B_MBC1v2_y} )

        df_MBC1v2_MD2Emu = pd.concat( [df_MBC1v2_MD2EmuA, df_MBC1v2_MD2EmuB] )

        # MD3 Emu
        df_MBC1v2_MD3EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD3_Emu_A_MBC1v2_x),
                                          'x'   : MD3_Emu_A_MBC1v2_x,
                                          'y'   : MD3_Emu_A_MBC1v2_y} )
        df_MBC1v2_MD3EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD3_Emu_B_MBC1v2_x),
                                          'x'   : MD3_Emu_B_MBC1v2_x,
                                          'y'   : MD3_Emu_B_MBC1v2_y} )

        df_MBC1v2_MD3Emu = pd.concat( [df_MBC1v2_MD3EmuA, df_MBC1v2_MD3EmuB] )

        # MD4 Emu
        df_MBC1v2_MD4EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD4_Emu_A_MBC1v2_x),
                                          'x'   : MD4_Emu_A_MBC1v2_x,
                                          'y'   : MD4_Emu_A_MBC1v2_y} )
        df_MBC1v2_MD4EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD4_Emu_B_MBC1v2_x),
                                          'x'   : MD4_Emu_B_MBC1v2_x,
                                          'y'   : MD4_Emu_B_MBC1v2_y} )

        df_MBC1v2_MD4Emu = pd.concat( [df_MBC1v2_MD4EmuA, df_MBC1v2_MD4EmuB] )

        # MD1 Ppr
        df_MBC1v2_MD1PprA = pd.DataFrame( {'name': ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_MBC1v2_x),
                                          'x'   : MD1_Ppr_A_MBC1v2_x,
                                          'y'   : MD1_Ppr_A_MBC1v2_y} )
        df_MBC1v2_MD1PprB = pd.DataFrame( {'name': ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_MBC1v2_x),
                                          'x'   : MD1_Ppr_B_MBC1v2_x,
                                          'y'   : MD1_Ppr_B_MBC1v2_y} )

        df_MBC1v2_MD1Ppr = pd.concat( [df_MBC1v2_MD1PprA, df_MBC1v2_MD1PprB] )

        # MD2 Ppr
        df_MBC1v2_MD2PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD2_Ppr_A_MBC1v2_x),
                                          'x'   : MD2_Ppr_A_MBC1v2_x,
                                          'y'   : MD2_Ppr_A_MBC1v2_y} )
        df_MBC1v2_MD2PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD2_Ppr_B_MBC1v2_x),
                                          'x'   : MD2_Ppr_B_MBC1v2_x,
                                          'y'   : MD2_Ppr_B_MBC1v2_y} )

        df_MBC1v2_MD2Ppr = pd.concat( [df_MBC1v2_MD2PprA, df_MBC1v2_MD2PprB] )

        # MD3 Ppr
        df_MBC1v2_MD3PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD3_Ppr_A_MBC1v2_x),
                                          'x'   : MD3_Ppr_A_MBC1v2_x,
                                          'y'   : MD3_Ppr_A_MBC1v2_y} )
        df_MBC1v2_MD3PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD3_Ppr_B_MBC1v2_x),
                                          'x'   : MD3_Ppr_B_MBC1v2_x,
                                          'y'   : MD3_Ppr_B_MBC1v2_y} )

        df_MBC1v2_MD3Ppr = pd.concat( [df_MBC1v2_MD3PprA, df_MBC1v2_MD3PprB] )

        # MD4 Ppr
        df_MBC1v2_MD4PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD4_Ppr_A_MBC1v2_x),
                                          'x'   : MD4_Ppr_A_MBC1v2_x,
                                          'y'   : MD4_Ppr_A_MBC1v2_y} )
        df_MBC1v2_MD4PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD4_Ppr_B_MBC1v2_x),
                                          'x'   : MD4_Ppr_B_MBC1v2_x,
                                          'y'   : MD4_Ppr_B_MBC1v2_y} )

        df_MBC1v2_MD4Ppr = pd.concat( [df_MBC1v2_MD4PprA, df_MBC1v2_MD4PprB] )

        #mb_mon_1.8v(vaux12)
        # MD1 Emu
        df_MBC1v8_MD1EmuA = pd.DataFrame( {'name': ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_MBC1v8_x),
                                          'x'   : MD1_Emu_A_MBC1v8_x,
                                          'y'   : MD1_Emu_A_MBC1v8_y} )
        df_MBC1v8_MD1EmuB = pd.DataFrame( {'name': ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_MBC1v8_x),
                                          'x'   : MD1_Emu_B_MBC1v8_x,
                                          'y'   : MD1_Emu_B_MBC1v8_y} )

        df_MBC1v8_MD1Emu = pd.concat( [df_MBC1v8_MD1EmuA, df_MBC1v8_MD1EmuB] )

        # MD2 Emu
        df_MBC1v8_MD2EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD2_Emu_A_MBC1v8_x),
                                          'x'   : MD2_Emu_A_MBC1v8_x,
                                          'y'   : MD2_Emu_A_MBC1v8_y} )
        df_MBC1v8_MD2EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD2_Emu_B_MBC1v8_x),
                                          'x'   : MD2_Emu_B_MBC1v8_x,
                                          'y'   : MD2_Emu_B_MBC1v8_y} )

        df_MBC1v8_MD2Emu = pd.concat( [df_MBC1v8_MD2EmuA, df_MBC1v8_MD2EmuB] )

        # MD3 Emu
        df_MBC1v8_MD3EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD3_Emu_A_MBC1v8_x),
                                          'x'   : MD3_Emu_A_MBC1v8_x,
                                          'y'   : MD3_Emu_A_MBC1v8_y} )
        df_MBC1v8_MD3EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD3_Emu_B_MBC1v8_x),
                                          'x'   : MD3_Emu_B_MBC1v8_x,
                                          'y'   : MD3_Emu_B_MBC1v8_y} )

        df_MBC1v8_MD3Emu = pd.concat( [df_MBC1v8_MD3EmuA, df_MBC1v8_MD3EmuB] )

        # MD4 Emu
        df_MBC1v8_MD4EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD4_Emu_A_MBC1v8_x),
                                          'x'   : MD4_Emu_A_MBC1v8_x,
                                          'y'   : MD4_Emu_A_MBC1v8_y} )
        df_MBC1v8_MD4EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD4_Emu_B_MBC1v8_x),
                                          'x'   : MD4_Emu_B_MBC1v8_x,
                                          'y'   : MD4_Emu_B_MBC1v8_y} )

        df_MBC1v8_MD4Emu = pd.concat( [df_MBC1v8_MD4EmuA, df_MBC1v8_MD4EmuB] )

        # MD1 Ppr
        df_MBC1v8_MD1PprA = pd.DataFrame( {'name': ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_MBC1v8_x),
                                          'x'   : MD1_Ppr_A_MBC1v8_x,
                                          'y'   : MD1_Ppr_A_MBC1v8_y} )
        df_MBC1v8_MD1PprB = pd.DataFrame( {'name': ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_MBC1v8_x),
                                          'x'   : MD1_Ppr_B_MBC1v8_x,
                                          'y'   : MD1_Ppr_B_MBC1v8_y} )

        df_MBC1v8_MD1Ppr = pd.concat( [df_MBC1v8_MD1PprA, df_MBC1v8_MD1PprB] )

        # MD2 Ppr
        df_MBC1v8_MD2PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD2_Ppr_A_MBC1v8_x),
                                          'x'   : MD2_Ppr_A_MBC1v8_x,
                                          'y'   : MD2_Ppr_A_MBC1v8_y} )
        df_MBC1v8_MD2PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD2_Ppr_B_MBC1v8_x),
                                          'x'   : MD2_Ppr_B_MBC1v8_x,
                                          'y'   : MD2_Ppr_B_MBC1v8_y} )

        df_MBC1v8_MD2Ppr = pd.concat( [df_MBC1v8_MD2PprA, df_MBC1v8_MD2PprB] )

        # MD3 Ppr
        df_MBC1v8_MD3PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD3_Ppr_A_MBC1v8_x),
                                          'x'   : MD3_Ppr_A_MBC1v8_x,
                                          'y'   : MD3_Ppr_A_MBC1v8_y} )
        df_MBC1v8_MD3PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD3_Ppr_B_MBC1v8_x),
                                          'x'   : MD3_Ppr_B_MBC1v8_x,
                                          'y'   : MD3_Ppr_B_MBC1v8_y} )

        df_MBC1v8_MD3Ppr = pd.concat( [df_MBC1v8_MD3PprA, df_MBC1v8_MD3PprB] )

        # MD4 Ppr
        df_MBC1v8_MD4PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD4_Ppr_A_MBC1v8_x),
                                          'x'   : MD4_Ppr_A_MBC1v8_x,
                                          'y'   : MD4_Ppr_A_MBC1v8_y} )
        df_MBC1v8_MD4PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD4_Ppr_B_MBC1v8_x),
                                          'x'   : MD4_Ppr_B_MBC1v8_x,
                                          'y'   : MD4_Ppr_B_MBC1v8_y} )

        df_MBC1v8_MD4Ppr = pd.concat( [df_MBC1v8_MD4PprA, df_MBC1v8_MD4PprB] )

        #mb_mon_2.5v(vaux15)
        # MD1 Emu
        df_MBC2v5_MD1EmuA = pd.DataFrame( {'name': ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_MBC2v5_x),
                                          'x'   : MD1_Emu_A_MBC2v5_x,
                                          'y'   : MD1_Emu_A_MBC2v5_y} )
        df_MBC2v5_MD1EmuB = pd.DataFrame( {'name': ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_MBC2v5_x),
                                          'x'   : MD1_Emu_B_MBC2v5_x,
                                          'y'   : MD1_Emu_B_MBC2v5_y} )

        df_MBC2v5_MD1Emu = pd.concat( [df_MBC2v5_MD1EmuA, df_MBC2v5_MD1EmuB] )

        # MD2 Emu
        df_MBC2v5_MD2EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD2_Emu_A_MBC2v5_x),
                                          'x'   : MD2_Emu_A_MBC2v5_x,
                                          'y'   : MD2_Emu_A_MBC2v5_y} )
        df_MBC2v5_MD2EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD2_Emu_B_MBC2v5_x),
                                          'x'   : MD2_Emu_B_MBC2v5_x,
                                          'y'   : MD2_Emu_B_MBC2v5_y} )

        df_MBC2v5_MD2Emu = pd.concat( [df_MBC2v5_MD2EmuA, df_MBC2v5_MD2EmuB] )

        # MD3 Emu
        df_MBC2v5_MD3EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD3_Emu_A_MBC2v5_x),
                                          'x'   : MD3_Emu_A_MBC2v5_x,
                                          'y'   : MD3_Emu_A_MBC2v5_y} )
        df_MBC2v5_MD3EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD3_Emu_B_MBC2v5_x),
                                          'x'   : MD3_Emu_B_MBC2v5_x,
                                          'y'   : MD3_Emu_B_MBC2v5_y} )

        df_MBC2v5_MD3Emu = pd.concat( [df_MBC2v5_MD3EmuA, df_MBC2v5_MD3EmuB] )

        # MD4 Emu
        df_MBC2v5_MD4EmuA = pd.DataFrame( {'name': [' - Emu - KU FPGA A']*len(MD4_Emu_A_MBC2v5_x),
                                          'x'   : MD4_Emu_A_MBC2v5_x,
                                          'y'   : MD4_Emu_A_MBC2v5_y} )
        df_MBC2v5_MD4EmuB = pd.DataFrame( {'name': [' - Emu - KU FPGA B']*len(MD4_Emu_B_MBC2v5_x),
                                          'x'   : MD4_Emu_B_MBC2v5_x,
                                          'y'   : MD4_Emu_B_MBC2v5_y} )

        df_MBC2v5_MD4Emu = pd.concat( [df_MBC2v5_MD4EmuA, df_MBC2v5_MD4EmuB] )

        # MD1 Ppr
        df_MBC2v5_MD1PprA = pd.DataFrame( {'name': ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_MBC2v5_x),
                                          'x'   : MD1_Ppr_A_MBC2v5_x,
                                          'y'   : MD1_Ppr_A_MBC2v5_y} )
        df_MBC2v5_MD1PprB = pd.DataFrame( {'name': ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_MBC2v5_x),
                                          'x'   : MD1_Ppr_B_MBC2v5_x,
                                          'y'   : MD1_Ppr_B_MBC2v5_y} )

        df_MBC2v5_MD1Ppr = pd.concat( [df_MBC2v5_MD1PprA, df_MBC2v5_MD1PprB] )

        # MD2 Ppr
        df_MBC2v5_MD2PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD2_Ppr_A_MBC2v5_x),
                                          'x'   : MD2_Ppr_A_MBC2v5_x,
                                          'y'   : MD2_Ppr_A_MBC2v5_y} )
        df_MBC2v5_MD2PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD2_Ppr_B_MBC2v5_x),
                                          'x'   : MD2_Ppr_B_MBC2v5_x,
                                          'y'   : MD2_Ppr_B_MBC2v5_y} )

        df_MBC2v5_MD2Ppr = pd.concat( [df_MBC2v5_MD2PprA, df_MBC2v5_MD2PprB] )

        # MD3 Ppr
        df_MBC2v5_MD3PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD3_Ppr_A_MBC2v5_x),
                                          'x'   : MD3_Ppr_A_MBC2v5_x,
                                          'y'   : MD3_Ppr_A_MBC2v5_y} )
        df_MBC2v5_MD3PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD3_Ppr_B_MBC2v5_x),
                                          'x'   : MD3_Ppr_B_MBC2v5_x,
                                          'y'   : MD3_Ppr_B_MBC2v5_y} )

        df_MBC2v5_MD3Ppr = pd.concat( [df_MBC2v5_MD3PprA, df_MBC2v5_MD3PprB] )

        # MD4 Ppr
        df_MBC2v5_MD4PprA = pd.DataFrame( {'name': [' - Ppr - KU FPGA A']*len(MD4_Ppr_A_MBC2v5_x),
                                          'x'   : MD4_Ppr_A_MBC2v5_x,
                                          'y'   : MD4_Ppr_A_MBC2v5_y} )
        df_MBC2v5_MD4PprB = pd.DataFrame( {'name': [' - Ppr - KU FPGA B']*len(MD4_Ppr_B_MBC2v5_x),
                                          'x'   : MD4_Ppr_B_MBC2v5_x,
                                          'y'   : MD4_Ppr_B_MBC2v5_y} )

        df_MBC2v5_MD4Ppr = pd.concat( [df_MBC2v5_MD4PprA, df_MBC2v5_MD4PprB] )



        # max_temp
        # MD1 Emu
        df_MAXTEMP_MD1EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_MAXTEMP_x),
                                            'x'    : MD1_Emu_A_MAXTEMP_x,
                                            'y'    : MD1_Emu_A_MAXTEMP_y} )
        df_MAXTEMP_MD1EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_MAXTEMP_x),
                                            'x'    : MD1_Emu_B_MAXTEMP_x,
                                            'y'    : MD1_Emu_B_MAXTEMP_y} )

        df_MAXTEMP_MD1Emu = pd.concat( [df_MAXTEMP_MD1EmuA, df_MAXTEMP_MD1EmuB] )

        # MD2 Emu
        df_MAXTEMP_MD2EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD2_Emu_A_MAXTEMP_x),
                                            'x'    : MD2_Emu_A_MAXTEMP_x,
                                            'y'    : MD2_Emu_A_MAXTEMP_y} )
        df_MAXTEMP_MD2EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD2_Emu_B_MAXTEMP_x),
                                            'x'    : MD2_Emu_B_MAXTEMP_x,
                                            'y'    : MD2_Emu_B_MAXTEMP_y} )

        df_MAXTEMP_MD2Emu = pd.concat( [df_MAXTEMP_MD2EmuA, df_MAXTEMP_MD2EmuB] )
        
        # MD3 Emu
        df_MAXTEMP_MD3EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD3_Emu_A_MAXTEMP_x),
                                            'x'    : MD3_Emu_A_MAXTEMP_x,
                                            'y'    : MD3_Emu_A_MAXTEMP_y} )
        df_MAXTEMP_MD3EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD3_Emu_B_MAXTEMP_x),
                                            'x'    : MD3_Emu_B_MAXTEMP_x,
                                            'y'    : MD3_Emu_B_MAXTEMP_y} )

        df_MAXTEMP_MD3Emu = pd.concat( [df_MAXTEMP_MD3EmuA, df_MAXTEMP_MD3EmuB] )

        # MD4 Emu
        df_MAXTEMP_MD4EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD4_Emu_A_MAXTEMP_x),
                                            'x'    : MD4_Emu_A_MAXTEMP_x,
                                            'y'    : MD4_Emu_A_MAXTEMP_y} )
        df_MAXTEMP_MD4EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD4_Emu_B_MAXTEMP_x),
                                            'x'    : MD4_Emu_B_MAXTEMP_x,
                                            'y'    : MD4_Emu_B_MAXTEMP_y} )

        df_MAXTEMP_MD4Emu = pd.concat( [df_MAXTEMP_MD4EmuA, df_MAXTEMP_MD4EmuB] )

        # MD1 Ppr
        df_MAXTEMP_MD1PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_MAXTEMP_x),
                                            'x'    : MD1_Ppr_A_MAXTEMP_x,
                                            'y'    : MD1_Ppr_A_MAXTEMP_y} )
        df_MAXTEMP_MD1PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_MAXTEMP_x),
                                            'x'    : MD1_Ppr_B_MAXTEMP_x,
                                            'y'    : MD1_Ppr_B_MAXTEMP_y} )

        df_MAXTEMP_MD1Ppr = pd.concat( [df_MAXTEMP_MD1PprA, df_MAXTEMP_MD1PprB] )

        # MD2 Ppr
        df_MAXTEMP_MD2PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD2_Ppr_A_MAXTEMP_x),
                                            'x'    : MD2_Ppr_A_MAXTEMP_x,
                                            'y'    : MD2_Ppr_A_MAXTEMP_y} )
        df_MAXTEMP_MD2PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD2_Ppr_B_MAXTEMP_x),
                                            'x'    : MD2_Ppr_B_MAXTEMP_x,
                                            'y'    : MD2_Ppr_B_MAXTEMP_y} )

        df_MAXTEMP_MD2Ppr = pd.concat( [df_MAXTEMP_MD2PprA, df_MAXTEMP_MD2PprB] )
        
        # MD3 Ppr
        df_MAXTEMP_MD3PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD3_Ppr_A_MAXTEMP_x),
                                            'x'    : MD3_Ppr_A_MAXTEMP_x,
                                            'y'    : MD3_Ppr_A_MAXTEMP_y} )
        df_MAXTEMP_MD3PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD3_Ppr_B_MAXTEMP_x),
                                            'x'    : MD3_Ppr_B_MAXTEMP_x,
                                            'y'    : MD3_Ppr_B_MAXTEMP_y} )

        df_MAXTEMP_MD3Ppr = pd.concat( [df_MAXTEMP_MD3PprA, df_MAXTEMP_MD3PprB] )

        # MD4 Ppr
        df_MAXTEMP_MD4PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD4_Ppr_A_MAXTEMP_x),
                                            'x'    : MD4_Ppr_A_MAXTEMP_x,
                                            'y'    : MD4_Ppr_A_MAXTEMP_y} )
        df_MAXTEMP_MD4PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD4_Ppr_B_MAXTEMP_x),
                                            'x'    : MD4_Ppr_B_MAXTEMP_x,
                                            'y'    : MD4_Ppr_B_MAXTEMP_y} )

        df_MAXTEMP_MD4Ppr = pd.concat( [df_MAXTEMP_MD4PprA, df_MAXTEMP_MD4PprB] )

        # max_vccint
        # MD1 Emu
        df_MAXVCCINT_MD1EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_MAXVCCINT_x),
                                            'x'    : MD1_Emu_A_MAXVCCINT_x,
                                            'y'    : MD1_Emu_A_MAXVCCINT_y} )
        df_MAXVCCINT_MD1EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_MAXVCCINT_x),
                                            'x'    : MD1_Emu_B_MAXVCCINT_x,
                                            'y'    : MD1_Emu_B_MAXVCCINT_y} )

        df_MAXVCCINT_MD1Emu = pd.concat( [df_MAXVCCINT_MD1EmuA, df_MAXVCCINT_MD1EmuB] )

        # MD2 Emu
        df_MAXVCCINT_MD2EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD2_Emu_A_MAXVCCINT_x),
                                            'x'    : MD2_Emu_A_MAXVCCINT_x,
                                            'y'    : MD2_Emu_A_MAXVCCINT_y} )
        df_MAXVCCINT_MD2EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD2_Emu_B_MAXVCCINT_x),
                                            'x'    : MD2_Emu_B_MAXVCCINT_x,
                                            'y'    : MD2_Emu_B_MAXVCCINT_y} )

        df_MAXVCCINT_MD2Emu = pd.concat( [df_MAXVCCINT_MD2EmuA, df_MAXVCCINT_MD2EmuB] )
        
        # MD3 Emu
        df_MAXVCCINT_MD3EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD3_Emu_A_MAXVCCINT_x),
                                            'x'    : MD3_Emu_A_MAXVCCINT_x,
                                            'y'    : MD3_Emu_A_MAXVCCINT_y} )
        df_MAXVCCINT_MD3EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD3_Emu_B_MAXVCCINT_x),
                                            'x'    : MD3_Emu_B_MAXVCCINT_x,
                                            'y'    : MD3_Emu_B_MAXVCCINT_y} )

        df_MAXVCCINT_MD3Emu = pd.concat( [df_MAXVCCINT_MD3EmuA, df_MAXVCCINT_MD3EmuB] )

        # MD4 Emu
        df_MAXVCCINT_MD4EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD4_Emu_A_MAXVCCINT_x),
                                            'x'    : MD4_Emu_A_MAXVCCINT_x,
                                            'y'    : MD4_Emu_A_MAXVCCINT_y} )
        df_MAXVCCINT_MD4EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD4_Emu_B_MAXVCCINT_x),
                                            'x'    : MD4_Emu_B_MAXVCCINT_x,
                                            'y'    : MD4_Emu_B_MAXVCCINT_y} )

        df_MAXVCCINT_MD4Emu = pd.concat( [df_MAXVCCINT_MD4EmuA, df_MAXVCCINT_MD4EmuB] )

        # MD1 Ppr
        df_MAXVCCINT_MD1PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_MAXVCCINT_x),
                                            'x'    : MD1_Ppr_A_MAXVCCINT_x,
                                            'y'    : MD1_Ppr_A_MAXVCCINT_y} )
        df_MAXVCCINT_MD1PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_MAXVCCINT_x),
                                            'x'    : MD1_Ppr_B_MAXVCCINT_x,
                                            'y'    : MD1_Ppr_B_MAXVCCINT_y} )

        df_MAXVCCINT_MD1Ppr = pd.concat( [df_MAXVCCINT_MD1PprA, df_MAXVCCINT_MD1PprB] )

        # MD2 Ppr
        df_MAXVCCINT_MD2PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD2_Ppr_A_MAXVCCINT_x),
                                            'x'    : MD2_Ppr_A_MAXVCCINT_x,
                                            'y'    : MD2_Ppr_A_MAXVCCINT_y} )
        df_MAXVCCINT_MD2PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD2_Ppr_B_MAXVCCINT_x),
                                            'x'    : MD2_Ppr_B_MAXVCCINT_x,
                                            'y'    : MD2_Ppr_B_MAXVCCINT_y} )

        df_MAXVCCINT_MD2Ppr = pd.concat( [df_MAXVCCINT_MD2PprA, df_MAXVCCINT_MD2PprB] )
        
        # MD3 Ppr
        df_MAXVCCINT_MD3PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD3_Ppr_A_MAXVCCINT_x),
                                            'x'    : MD3_Ppr_A_MAXVCCINT_x,
                                            'y'    : MD3_Ppr_A_MAXVCCINT_y} )
        df_MAXVCCINT_MD3PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD3_Ppr_B_MAXVCCINT_x),
                                            'x'    : MD3_Ppr_B_MAXVCCINT_x,
                                            'y'    : MD3_Ppr_B_MAXVCCINT_y} )

        df_MAXVCCINT_MD3Ppr = pd.concat( [df_MAXVCCINT_MD3PprA, df_MAXVCCINT_MD3PprB] )

        # MD4 Ppr
        df_MAXVCCINT_MD4PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD4_Ppr_A_MAXVCCINT_x),
                                            'x'    : MD4_Ppr_A_MAXVCCINT_x,
                                            'y'    : MD4_Ppr_A_MAXVCCINT_y} )
        df_MAXVCCINT_MD4PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD4_Ppr_B_MAXVCCINT_x),
                                            'x'    : MD4_Ppr_B_MAXVCCINT_x,
                                            'y'    : MD4_Ppr_B_MAXVCCINT_y} )

        df_MAXVCCINT_MD4Ppr = pd.concat( [df_MAXVCCINT_MD4PprA, df_MAXVCCINT_MD4PprB] )

        # min_vccint
        # MD1 Emu
        df_MINVCCINT_MD1EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_MINVCCINT_x),
                                            'x'    : MD1_Emu_A_MINVCCINT_x,
                                            'y'    : MD1_Emu_A_MINVCCINT_y} )
        df_MINVCCINT_MD1EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_MINVCCINT_x),
                                            'x'    : MD1_Emu_B_MINVCCINT_x,
                                            'y'    : MD1_Emu_B_MINVCCINT_y} )

        df_MINVCCINT_MD1Emu = pd.concat( [df_MINVCCINT_MD1EmuA, df_MINVCCINT_MD1EmuB] )

        # MD2 Emu
        df_MINVCCINT_MD2EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD2_Emu_A_MINVCCINT_x),
                                            'x'    : MD2_Emu_A_MINVCCINT_x,
                                            'y'    : MD2_Emu_A_MINVCCINT_y} )
        df_MINVCCINT_MD2EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD2_Emu_B_MINVCCINT_x),
                                            'x'    : MD2_Emu_B_MINVCCINT_x,
                                            'y'    : MD2_Emu_B_MINVCCINT_y} )

        df_MINVCCINT_MD2Emu = pd.concat( [df_MINVCCINT_MD2EmuA, df_MINVCCINT_MD2EmuB] )
        
        # MD3 Emu
        df_MINVCCINT_MD3EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD3_Emu_A_MINVCCINT_x),
                                            'x'    : MD3_Emu_A_MINVCCINT_x,
                                            'y'    : MD3_Emu_A_MINVCCINT_y} )
        df_MINVCCINT_MD3EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD3_Emu_B_MINVCCINT_x),
                                            'x'    : MD3_Emu_B_MINVCCINT_x,
                                            'y'    : MD3_Emu_B_MINVCCINT_y} )

        df_MINVCCINT_MD3Emu = pd.concat( [df_MINVCCINT_MD3EmuA, df_MINVCCINT_MD3EmuB] )

        # MD4 Emu
        df_MINVCCINT_MD4EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD4_Emu_A_MINVCCINT_x),
                                            'x'    : MD4_Emu_A_MINVCCINT_x,
                                            'y'    : MD4_Emu_A_MINVCCINT_y} )
        df_MINVCCINT_MD4EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD4_Emu_B_MINVCCINT_x),
                                            'x'    : MD4_Emu_B_MINVCCINT_x,
                                            'y'    : MD4_Emu_B_MINVCCINT_y} )

        df_MINVCCINT_MD4Emu = pd.concat( [df_MINVCCINT_MD4EmuA, df_MINVCCINT_MD4EmuB] )

        # MD1 Ppr
        df_MINVCCINT_MD1PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_MINVCCINT_x),
                                            'x'    : MD1_Ppr_A_MINVCCINT_x,
                                            'y'    : MD1_Ppr_A_MINVCCINT_y} )
        df_MINVCCINT_MD1PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_MINVCCINT_x),
                                            'x'    : MD1_Ppr_B_MINVCCINT_x,
                                            'y'    : MD1_Ppr_B_MINVCCINT_y} )

        df_MINVCCINT_MD1Ppr = pd.concat( [df_MINVCCINT_MD1PprA, df_MINVCCINT_MD1PprB] )

        # MD2 Ppr
        df_MINVCCINT_MD2PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD2_Ppr_A_MINVCCINT_x),
                                            'x'    : MD2_Ppr_A_MINVCCINT_x,
                                            'y'    : MD2_Ppr_A_MINVCCINT_y} )
        df_MINVCCINT_MD2PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD2_Ppr_B_MINVCCINT_x),
                                            'x'    : MD2_Ppr_B_MINVCCINT_x,
                                            'y'    : MD2_Ppr_B_MINVCCINT_y} )

        df_MINVCCINT_MD2Ppr = pd.concat( [df_MINVCCINT_MD2PprA, df_MINVCCINT_MD2PprB] )
        
        # MD3 Ppr
        df_MINVCCINT_MD3PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD3_Ppr_A_MINVCCINT_x),
                                            'x'    : MD3_Ppr_A_MINVCCINT_x,
                                            'y'    : MD3_Ppr_A_MINVCCINT_y} )
        df_MINVCCINT_MD3PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD3_Ppr_B_MINVCCINT_x),
                                            'x'    : MD3_Ppr_B_MINVCCINT_x,
                                            'y'    : MD3_Ppr_B_MINVCCINT_y} )

        df_MINVCCINT_MD3Ppr = pd.concat( [df_MINVCCINT_MD3PprA, df_MINVCCINT_MD3PprB] )

        # MD4 Ppr
        df_MINVCCINT_MD4PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD4_Ppr_A_MINVCCINT_x),
                                            'x'    : MD4_Ppr_A_MINVCCINT_x,
                                            'y'    : MD4_Ppr_A_MINVCCINT_y} )
        df_MINVCCINT_MD4PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD4_Ppr_B_MINVCCINT_x),
                                            'x'    : MD4_Ppr_B_MINVCCINT_x,
                                            'y'    : MD4_Ppr_B_MINVCCINT_y} )

        df_MINVCCINT_MD4Ppr = pd.concat( [df_MINVCCINT_MD4PprA, df_MINVCCINT_MD4PprB] )

        # max_vccout
        # MD1 Emu
        df_MAXVCCOUT_MD1EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_MAXVCCOUT_x),
                                            'x'    : MD1_Emu_A_MAXVCCOUT_x,
                                            'y'    : MD1_Emu_A_MAXVCCOUT_y} )
        df_MAXVCCOUT_MD1EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_MAXVCCOUT_x),
                                            'x'    : MD1_Emu_B_MAXVCCOUT_x,
                                            'y'    : MD1_Emu_B_MAXVCCOUT_y} )

        df_MAXVCCOUT_MD1Emu = pd.concat( [df_MAXVCCOUT_MD1EmuA, df_MAXVCCOUT_MD1EmuB] )

        # MD2 Emu
        df_MAXVCCOUT_MD2EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD2_Emu_A_MAXVCCOUT_x),
                                            'x'    : MD2_Emu_A_MAXVCCOUT_x,
                                            'y'    : MD2_Emu_A_MAXVCCOUT_y} )
        df_MAXVCCOUT_MD2EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD2_Emu_B_MAXVCCOUT_x),
                                            'x'    : MD2_Emu_B_MAXVCCOUT_x,
                                            'y'    : MD2_Emu_B_MAXVCCOUT_y} )

        df_MAXVCCOUT_MD2Emu = pd.concat( [df_MAXVCCOUT_MD2EmuA, df_MAXVCCOUT_MD2EmuB] )
        
        # MD3 Emu
        df_MAXVCCOUT_MD3EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD3_Emu_A_MAXVCCOUT_x),
                                            'x'    : MD3_Emu_A_MAXVCCOUT_x,
                                            'y'    : MD3_Emu_A_MAXVCCOUT_y} )
        df_MAXVCCOUT_MD3EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD3_Emu_B_MAXVCCOUT_x),
                                            'x'    : MD3_Emu_B_MAXVCCOUT_x,
                                            'y'    : MD3_Emu_B_MAXVCCOUT_y} )

        df_MAXVCCOUT_MD3Emu = pd.concat( [df_MAXVCCOUT_MD3EmuA, df_MAXVCCOUT_MD3EmuB] )

        # MD4 Emu
        df_MAXVCCOUT_MD4EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD4_Emu_A_MAXVCCOUT_x),
                                            'x'    : MD4_Emu_A_MAXVCCOUT_x,
                                            'y'    : MD4_Emu_A_MAXVCCOUT_y} )
        df_MAXVCCOUT_MD4EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD4_Emu_B_MAXVCCOUT_x),
                                            'x'    : MD4_Emu_B_MAXVCCOUT_x,
                                            'y'    : MD4_Emu_B_MAXVCCOUT_y} )

        df_MAXVCCOUT_MD4Emu = pd.concat( [df_MAXVCCOUT_MD4EmuA, df_MAXVCCOUT_MD4EmuB] )

        # MD1 Ppr
        df_MAXVCCOUT_MD1PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_MAXVCCOUT_x),
                                            'x'    : MD1_Ppr_A_MAXVCCOUT_x,
                                            'y'    : MD1_Ppr_A_MAXVCCOUT_y} )
        df_MAXVCCOUT_MD1PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_MAXVCCOUT_x),
                                            'x'    : MD1_Ppr_B_MAXVCCOUT_x,
                                            'y'    : MD1_Ppr_B_MAXVCCOUT_y} )

        df_MAXVCCOUT_MD1Ppr = pd.concat( [df_MAXVCCOUT_MD1PprA, df_MAXVCCOUT_MD1PprB] )

        # MD2 Ppr
        df_MAXVCCOUT_MD2PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD2_Ppr_A_MAXVCCOUT_x),
                                            'x'    : MD2_Ppr_A_MAXVCCOUT_x,
                                            'y'    : MD2_Ppr_A_MAXVCCOUT_y} )
        df_MAXVCCOUT_MD2PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD2_Ppr_B_MAXVCCOUT_x),
                                            'x'    : MD2_Ppr_B_MAXVCCOUT_x,
                                            'y'    : MD2_Ppr_B_MAXVCCOUT_y} )

        df_MAXVCCOUT_MD2Ppr = pd.concat( [df_MAXVCCOUT_MD2PprA, df_MAXVCCOUT_MD2PprB] )
        
        # MD3 Ppr
        df_MAXVCCOUT_MD3PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD3_Ppr_A_MAXVCCOUT_x),
                                            'x'    : MD3_Ppr_A_MAXVCCOUT_x,
                                            'y'    : MD3_Ppr_A_MAXVCCOUT_y} )
        df_MAXVCCOUT_MD3PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD3_Ppr_B_MAXVCCOUT_x),
                                            'x'    : MD3_Ppr_B_MAXVCCOUT_x,
                                            'y'    : MD3_Ppr_B_MAXVCCOUT_y} )

        df_MAXVCCOUT_MD3Ppr = pd.concat( [df_MAXVCCOUT_MD3PprA, df_MAXVCCOUT_MD3PprB] )

        # MD4 Ppr
        df_MAXVCCOUT_MD4PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD4_Ppr_A_MAXVCCOUT_x),
                                            'x'    : MD4_Ppr_A_MAXVCCOUT_x,
                                            'y'    : MD4_Ppr_A_MAXVCCOUT_y} )
        df_MAXVCCOUT_MD4PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD4_Ppr_B_MAXVCCOUT_x),
                                            'x'    : MD4_Ppr_B_MAXVCCOUT_x,
                                            'y'    : MD4_Ppr_B_MAXVCCOUT_y} )

        df_MAXVCCOUT_MD4Ppr = pd.concat( [df_MAXVCCOUT_MD4PprA, df_MAXVCCOUT_MD4PprB] )

        # min_vccout
        # MD1 Emu
        df_MINVCCOUT_MD1EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_MINVCCOUT_x),
                                            'x'    : MD1_Emu_A_MINVCCOUT_x,
                                            'y'    : MD1_Emu_A_MINVCCOUT_y} )
        df_MINVCCOUT_MD1EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_MINVCCOUT_x),
                                            'x'    : MD1_Emu_B_MINVCCOUT_x,
                                            'y'    : MD1_Emu_B_MINVCCOUT_y} )

        df_MINVCCOUT_MD1Emu = pd.concat( [df_MINVCCOUT_MD1EmuA, df_MINVCCOUT_MD1EmuB] )

        # MD2 Emu
        df_MINVCCOUT_MD2EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD2_Emu_A_MINVCCOUT_x),
                                            'x'    : MD2_Emu_A_MINVCCOUT_x,
                                            'y'    : MD2_Emu_A_MINVCCOUT_y} )
        df_MINVCCOUT_MD2EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD2_Emu_B_MINVCCOUT_x),
                                            'x'    : MD2_Emu_B_MINVCCOUT_x,
                                            'y'    : MD2_Emu_B_MINVCCOUT_y} )

        df_MINVCCOUT_MD2Emu = pd.concat( [df_MINVCCOUT_MD2EmuA, df_MINVCCOUT_MD2EmuB] )
        
        # MD3 Emu
        df_MINVCCOUT_MD3EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD3_Emu_A_MINVCCOUT_x),
                                            'x'    : MD3_Emu_A_MINVCCOUT_x,
                                            'y'    : MD3_Emu_A_MINVCCOUT_y} )
        df_MINVCCOUT_MD3EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD3_Emu_B_MINVCCOUT_x),
                                            'x'    : MD3_Emu_B_MINVCCOUT_x,
                                            'y'    : MD3_Emu_B_MINVCCOUT_y} )

        df_MINVCCOUT_MD3Emu = pd.concat( [df_MINVCCOUT_MD3EmuA, df_MINVCCOUT_MD3EmuB] )

        # MD4 Emu
        df_MINVCCOUT_MD4EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD4_Emu_A_MINVCCOUT_x),
                                            'x'    : MD4_Emu_A_MINVCCOUT_x,
                                            'y'    : MD4_Emu_A_MINVCCOUT_y} )
        df_MINVCCOUT_MD4EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD4_Emu_B_MINVCCOUT_x),
                                            'x'    : MD4_Emu_B_MINVCCOUT_x,
                                            'y'    : MD4_Emu_B_MINVCCOUT_y} )

        df_MINVCCOUT_MD4Emu = pd.concat( [df_MINVCCOUT_MD4EmuA, df_MINVCCOUT_MD4EmuB] )

        # MD1 Ppr
        df_MINVCCOUT_MD1PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_MINVCCOUT_x),
                                            'x'    : MD1_Ppr_A_MINVCCOUT_x,
                                            'y'    : MD1_Ppr_A_MINVCCOUT_y} )
        df_MINVCCOUT_MD1PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_MINVCCOUT_x),
                                            'x'    : MD1_Ppr_B_MINVCCOUT_x,
                                            'y'    : MD1_Ppr_B_MINVCCOUT_y} )

        df_MINVCCOUT_MD1Ppr = pd.concat( [df_MINVCCOUT_MD1PprA, df_MINVCCOUT_MD1PprB] )

        # MD2 Ppr
        df_MINVCCOUT_MD2PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD2_Ppr_A_MINVCCOUT_x),
                                            'x'    : MD2_Ppr_A_MINVCCOUT_x,
                                            'y'    : MD2_Ppr_A_MINVCCOUT_y} )
        df_MINVCCOUT_MD2PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD2_Ppr_B_MINVCCOUT_x),
                                            'x'    : MD2_Ppr_B_MINVCCOUT_x,
                                            'y'    : MD2_Ppr_B_MINVCCOUT_y} )

        df_MINVCCOUT_MD2Ppr = pd.concat( [df_MINVCCOUT_MD2PprA, df_MINVCCOUT_MD2PprB] )
        
        # MD3 Ppr
        df_MINVCCOUT_MD3PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD3_Ppr_A_MINVCCOUT_x),
                                            'x'    : MD3_Ppr_A_MINVCCOUT_x,
                                            'y'    : MD3_Ppr_A_MINVCCOUT_y} )
        df_MINVCCOUT_MD3PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD3_Ppr_B_MINVCCOUT_x),
                                            'x'    : MD3_Ppr_B_MINVCCOUT_x,
                                            'y'    : MD3_Ppr_B_MINVCCOUT_y} )

        df_MINVCCOUT_MD3Ppr = pd.concat( [df_MINVCCOUT_MD3PprA, df_MINVCCOUT_MD3PprB] )

        # MD4 Ppr
        df_MINVCCOUT_MD4PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD4_Ppr_A_MINVCCOUT_x),
                                            'x'    : MD4_Ppr_A_MINVCCOUT_x,
                                            'y'    : MD4_Ppr_A_MINVCCOUT_y} )
        df_MINVCCOUT_MD4PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD4_Ppr_B_MINVCCOUT_x),
                                            'x'    : MD4_Ppr_B_MINVCCOUT_x,
                                            'y'    : MD4_Ppr_B_MINVCCOUT_y} )

        df_MINVCCOUT_MD4Ppr = pd.concat( [df_MINVCCOUT_MD4PprA, df_MINVCCOUT_MD4PprB] )

        # max_vram
        # MD1 Emu
        df_MAX_VRAM_MD1EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_MAX_VRAM_x),
                                            'x'    : MD1_Emu_A_MAX_VRAM_x,
                                            'y'    : MD1_Emu_A_MAX_VRAM_y} )
        df_MAX_VRAM_MD1EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_MAX_VRAM_x),
                                            'x'    : MD1_Emu_B_MAX_VRAM_x,
                                            'y'    : MD1_Emu_B_MAX_VRAM_y} )

        df_MAX_VRAM_MD1Emu = pd.concat( [df_MAX_VRAM_MD1EmuA, df_MAX_VRAM_MD1EmuB] )

        # MD2 Emu
        df_MAX_VRAM_MD2EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD2_Emu_A_MAX_VRAM_x),
                                            'x'    : MD2_Emu_A_MAX_VRAM_x,
                                            'y'    : MD2_Emu_A_MAX_VRAM_y} )
        df_MAX_VRAM_MD2EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD2_Emu_B_MAX_VRAM_x),
                                            'x'    : MD2_Emu_B_MAX_VRAM_x,
                                            'y'    : MD2_Emu_B_MAX_VRAM_y} )

        df_MAX_VRAM_MD2Emu = pd.concat( [df_MAX_VRAM_MD2EmuA, df_MAX_VRAM_MD2EmuB] )
        
        # MD3 Emu
        df_MAX_VRAM_MD3EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD3_Emu_A_MAX_VRAM_x),
                                            'x'    : MD3_Emu_A_MAX_VRAM_x,
                                            'y'    : MD3_Emu_A_MAX_VRAM_y} )
        df_MAX_VRAM_MD3EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD3_Emu_B_MAX_VRAM_x),
                                            'x'    : MD3_Emu_B_MAX_VRAM_x,
                                            'y'    : MD3_Emu_B_MAX_VRAM_y} )

        df_MAX_VRAM_MD3Emu = pd.concat( [df_MAX_VRAM_MD3EmuA, df_MAX_VRAM_MD3EmuB] )

        # MD4 Emu
        df_MAX_VRAM_MD4EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD4_Emu_A_MAX_VRAM_x),
                                            'x'    : MD4_Emu_A_MAX_VRAM_x,
                                            'y'    : MD4_Emu_A_MAX_VRAM_y} )
        df_MAX_VRAM_MD4EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD4_Emu_B_MAX_VRAM_x),
                                            'x'    : MD4_Emu_B_MAX_VRAM_x,
                                            'y'    : MD4_Emu_B_MAX_VRAM_y} )

        df_MAX_VRAM_MD4Emu = pd.concat( [df_MAX_VRAM_MD4EmuA, df_MAX_VRAM_MD4EmuB] )

        # MD1 Ppr
        df_MAX_VRAM_MD1PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_MAX_VRAM_x),
                                            'x'    : MD1_Ppr_A_MAX_VRAM_x,
                                            'y'    : MD1_Ppr_A_MAX_VRAM_y} )
        df_MAX_VRAM_MD1PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_MAX_VRAM_x),
                                            'x'    : MD1_Ppr_B_MAX_VRAM_x,
                                            'y'    : MD1_Ppr_B_MAX_VRAM_y} )

        df_MAX_VRAM_MD1Ppr = pd.concat( [df_MAX_VRAM_MD1PprA, df_MAX_VRAM_MD1PprB] )

        # MD2 Ppr
        df_MAX_VRAM_MD2PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD2_Ppr_A_MAX_VRAM_x),
                                            'x'    : MD2_Ppr_A_MAX_VRAM_x,
                                            'y'    : MD2_Ppr_A_MAX_VRAM_y} )
        df_MAX_VRAM_MD2PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD2_Ppr_B_MAX_VRAM_x),
                                            'x'    : MD2_Ppr_B_MAX_VRAM_x,
                                            'y'    : MD2_Ppr_B_MAX_VRAM_y} )

        df_MAX_VRAM_MD2Ppr = pd.concat( [df_MAX_VRAM_MD2PprA, df_MAX_VRAM_MD2PprB] )
        
        # MD3 Ppr
        df_MAX_VRAM_MD3PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD3_Ppr_A_MAX_VRAM_x),
                                            'x'    : MD3_Ppr_A_MAX_VRAM_x,
                                            'y'    : MD3_Ppr_A_MAX_VRAM_y} )
        df_MAX_VRAM_MD3PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD3_Ppr_B_MAX_VRAM_x),
                                            'x'    : MD3_Ppr_B_MAX_VRAM_x,
                                            'y'    : MD3_Ppr_B_MAX_VRAM_y} )

        df_MAX_VRAM_MD3Ppr = pd.concat( [df_MAX_VRAM_MD3PprA, df_MAX_VRAM_MD3PprB] )

        # MD4 Ppr
        df_MAX_VRAM_MD4PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD4_Ppr_A_MAX_VRAM_x),
                                            'x'    : MD4_Ppr_A_MAX_VRAM_x,
                                            'y'    : MD4_Ppr_A_MAX_VRAM_y} )
        df_MAX_VRAM_MD4PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD4_Ppr_B_MAX_VRAM_x),
                                            'x'    : MD4_Ppr_B_MAX_VRAM_x,
                                            'y'    : MD4_Ppr_B_MAX_VRAM_y} )

        df_MAX_VRAM_MD4Ppr = pd.concat( [df_MAX_VRAM_MD4PprA, df_MAX_VRAM_MD4PprB] )

        # min_vram
        # MD1 Emu
        df_MIN_VRAM_MD1EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_MIN_VRAM_x),
                                            'x'    : MD1_Emu_A_MIN_VRAM_x,
                                            'y'    : MD1_Emu_A_MIN_VRAM_y} )
        df_MIN_VRAM_MD1EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_MIN_VRAM_x),
                                            'x'    : MD1_Emu_B_MIN_VRAM_x,
                                            'y'    : MD1_Emu_B_MIN_VRAM_y} )

        df_MIN_VRAM_MD1Emu = pd.concat( [df_MIN_VRAM_MD1EmuA, df_MIN_VRAM_MD1EmuB] )

        # MD2 Emu
        df_MIN_VRAM_MD2EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD2_Emu_A_MIN_VRAM_x),
                                            'x'    : MD2_Emu_A_MIN_VRAM_x,
                                            'y'    : MD2_Emu_A_MIN_VRAM_y} )
        df_MIN_VRAM_MD2EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD2_Emu_B_MIN_VRAM_x),
                                            'x'    : MD2_Emu_B_MIN_VRAM_x,
                                            'y'    : MD2_Emu_B_MIN_VRAM_y} )

        df_MIN_VRAM_MD2Emu = pd.concat( [df_MIN_VRAM_MD2EmuA, df_MIN_VRAM_MD2EmuB] )
        
        # MD3 Emu
        df_MIN_VRAM_MD3EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD3_Emu_A_MIN_VRAM_x),
                                            'x'    : MD3_Emu_A_MIN_VRAM_x,
                                            'y'    : MD3_Emu_A_MIN_VRAM_y} )
        df_MIN_VRAM_MD3EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD3_Emu_B_MIN_VRAM_x),
                                            'x'    : MD3_Emu_B_MIN_VRAM_x,
                                            'y'    : MD3_Emu_B_MIN_VRAM_y} )

        df_MIN_VRAM_MD3Emu = pd.concat( [df_MIN_VRAM_MD3EmuA, df_MIN_VRAM_MD3EmuB] )

        # MD4 Emu
        df_MIN_VRAM_MD4EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD4_Emu_A_MIN_VRAM_x),
                                            'x'    : MD4_Emu_A_MIN_VRAM_x,
                                            'y'    : MD4_Emu_A_MIN_VRAM_y} )
        df_MIN_VRAM_MD4EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD4_Emu_B_MIN_VRAM_x),
                                            'x'    : MD4_Emu_B_MIN_VRAM_x,
                                            'y'    : MD4_Emu_B_MIN_VRAM_y} )

        df_MIN_VRAM_MD4Emu = pd.concat( [df_MIN_VRAM_MD4EmuA, df_MIN_VRAM_MD4EmuB] )

        # MD1 Ppr
        df_MIN_VRAM_MD1PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_MIN_VRAM_x),
                                            'x'    : MD1_Ppr_A_MIN_VRAM_x,
                                            'y'    : MD1_Ppr_A_MIN_VRAM_y} )
        df_MIN_VRAM_MD1PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_MIN_VRAM_x),
                                            'x'    : MD1_Ppr_B_MIN_VRAM_x,
                                            'y'    : MD1_Ppr_B_MIN_VRAM_y} )

        df_MIN_VRAM_MD1Ppr = pd.concat( [df_MIN_VRAM_MD1PprA, df_MIN_VRAM_MD1PprB] )

        # MD2 Ppr
        df_MIN_VRAM_MD2PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD2_Ppr_A_MIN_VRAM_x),
                                            'x'    : MD2_Ppr_A_MIN_VRAM_x,
                                            'y'    : MD2_Ppr_A_MIN_VRAM_y} )
        df_MIN_VRAM_MD2PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD2_Ppr_B_MIN_VRAM_x),
                                            'x'    : MD2_Ppr_B_MIN_VRAM_x,
                                            'y'    : MD2_Ppr_B_MIN_VRAM_y} )

        df_MIN_VRAM_MD2Ppr = pd.concat( [df_MIN_VRAM_MD2PprA, df_MIN_VRAM_MD2PprB] )
        
        # MD3 Ppr
        df_MIN_VRAM_MD3PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD3_Ppr_A_MIN_VRAM_x),
                                            'x'    : MD3_Ppr_A_MIN_VRAM_x,
                                            'y'    : MD3_Ppr_A_MIN_VRAM_y} )
        df_MIN_VRAM_MD3PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD3_Ppr_B_MIN_VRAM_x),
                                            'x'    : MD3_Ppr_B_MIN_VRAM_x,
                                            'y'    : MD3_Ppr_B_MIN_VRAM_y} )

        df_MIN_VRAM_MD3Ppr = pd.concat( [df_MIN_VRAM_MD3PprA, df_MIN_VRAM_MD3PprB] )

        # MD4 Ppr
        df_MIN_VRAM_MD4PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD4_Ppr_A_MIN_VRAM_x),
                                            'x'    : MD4_Ppr_A_MIN_VRAM_x,
                                            'y'    : MD4_Ppr_A_MIN_VRAM_y} )
        df_MIN_VRAM_MD4PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD4_Ppr_B_MIN_VRAM_x),
                                            'x'    : MD4_Ppr_B_MIN_VRAM_x,
                                            'y'    : MD4_Ppr_B_MIN_VRAM_y} )

        df_MIN_VRAM_MD4Ppr = pd.concat( [df_MIN_VRAM_MD4PprA, df_MIN_VRAM_MD4PprB] )



        #pgood_db_0v95
        # MD1 Emu
        df_DBPGOOD0v95_MD1EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_DBPGOOD0v95_x),
                                                'x'    : MD1_Emu_A_DBPGOOD0v95_x,
                                                'y'    : MD1_Emu_A_DBPGOOD0v95_y} )
        df_DBPGOOD0v95_MD1EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_DBPGOOD0v95_x),
                                                'x'    : MD1_Emu_B_DBPGOOD0v95_x,
                                                'y'    : MD1_Emu_B_DBPGOOD0v95_y} )

        df_DBPGOOD0v95_MD1Emu = pd.concat( [df_DBPGOOD0v95_MD1EmuA, df_DBPGOOD0v95_MD1EmuB] )

        # MD2 Emu
        df_DBPGOOD0v95_MD2EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD2_Emu_A_DBPGOOD0v95_x),
                                                'x'    : MD2_Emu_A_DBPGOOD0v95_x,
                                                'y'    : MD2_Emu_A_DBPGOOD0v95_y} )
        df_DBPGOOD0v95_MD2EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD2_Emu_B_DBPGOOD0v95_x),
                                                'x'    : MD2_Emu_B_DBPGOOD0v95_x,
                                                'y'    : MD2_Emu_B_DBPGOOD0v95_y} )

        df_DBPGOOD0v95_MD2Emu = pd.concat( [df_DBPGOOD0v95_MD2EmuA, df_DBPGOOD0v95_MD2EmuB] )

        # MD3 Emu
        df_DBPGOOD0v95_MD3EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD3_Emu_A_DBPGOOD0v95_x),
                                                'x'    : MD3_Emu_A_DBPGOOD0v95_x,
                                                'y'    : MD3_Emu_A_DBPGOOD0v95_y} )
        df_DBPGOOD0v95_MD3EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD3_Emu_B_DBPGOOD0v95_x),
                                                'x'    : MD3_Emu_B_DBPGOOD0v95_x,
                                                'y'    : MD3_Emu_B_DBPGOOD0v95_y} )

        df_DBPGOOD0v95_MD3Emu = pd.concat( [df_DBPGOOD0v95_MD3EmuA, df_DBPGOOD0v95_MD3EmuB] )

        # MD4 Emu
        df_DBPGOOD0v95_MD4EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD4_Emu_A_DBPGOOD0v95_x),
                                                'x'    : MD4_Emu_A_DBPGOOD0v95_x,
                                                'y'    : MD4_Emu_A_DBPGOOD0v95_y} )
        df_DBPGOOD0v95_MD4EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD4_Emu_B_DBPGOOD0v95_x),
                                                'x'    : MD4_Emu_B_DBPGOOD0v95_x,
                                                'y'    : MD4_Emu_B_DBPGOOD0v95_y} )

        df_DBPGOOD0v95_MD4Emu = pd.concat( [df_DBPGOOD0v95_MD4EmuA, df_DBPGOOD0v95_MD4EmuB] )

        # MD1 Ppr
        df_DBPGOOD0v95_MD1PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_DBPGOOD0v95_x),
                                                'x'    : MD1_Ppr_A_DBPGOOD0v95_x,
                                                'y'    : MD1_Ppr_A_DBPGOOD0v95_y} )
        df_DBPGOOD0v95_MD1PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_DBPGOOD0v95_x),
                                                'x'    : MD1_Ppr_B_DBPGOOD0v95_x,
                                                'y'    : MD1_Ppr_B_DBPGOOD0v95_y} )

        df_DBPGOOD0v95_MD1Ppr = pd.concat( [df_DBPGOOD0v95_MD1PprA, df_DBPGOOD0v95_MD1PprB] )

        # MD2 Ppr
        df_DBPGOOD0v95_MD2PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD2_Ppr_A_DBPGOOD0v95_x),
                                                'x'    : MD2_Ppr_A_DBPGOOD0v95_x,
                                                'y'    : MD2_Ppr_A_DBPGOOD0v95_y} )
        df_DBPGOOD0v95_MD2PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD2_Ppr_B_DBPGOOD0v95_x),
                                                'x'    : MD2_Ppr_B_DBPGOOD0v95_x,
                                                'y'    : MD2_Ppr_B_DBPGOOD0v95_y} )

        df_DBPGOOD0v95_MD2Ppr = pd.concat( [df_DBPGOOD0v95_MD2PprA, df_DBPGOOD0v95_MD2PprB] )

        # MD3 Ppr
        df_DBPGOOD0v95_MD3PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD3_Ppr_A_DBPGOOD0v95_x),
                                                'x'    : MD3_Ppr_A_DBPGOOD0v95_x,
                                                'y'    : MD3_Ppr_A_DBPGOOD0v95_y} )
        df_DBPGOOD0v95_MD3PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD3_Ppr_B_DBPGOOD0v95_x),
                                                'x'    : MD3_Ppr_B_DBPGOOD0v95_x,
                                                'y'    : MD3_Ppr_B_DBPGOOD0v95_y} )

        df_DBPGOOD0v95_MD3Ppr = pd.concat( [df_DBPGOOD0v95_MD3PprA, df_DBPGOOD0v95_MD3PprB] )

        # MD4 Ppr
        df_DBPGOOD0v95_MD4PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD4_Ppr_A_DBPGOOD0v95_x),
                                                'x'    : MD4_Ppr_A_DBPGOOD0v95_x,
                                                'y'    : MD4_Ppr_A_DBPGOOD0v95_y} )
        df_DBPGOOD0v95_MD4PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD4_Ppr_B_DBPGOOD0v95_x),
                                                'x'    : MD4_Ppr_B_DBPGOOD0v95_x,
                                                'y'    : MD4_Ppr_B_DBPGOOD0v95_y} )

        df_DBPGOOD0v95_MD4Ppr = pd.concat( [df_DBPGOOD0v95_MD4PprA, df_DBPGOOD0v95_MD4PprB] )

        #pgood_db_1v0
        # MD1 Emu
        df_DBPGOOD1v0_MD1EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_DBPGOOD1v0_x),
                                                'x'    : MD1_Emu_A_DBPGOOD1v0_x,
                                                'y'    : MD1_Emu_A_DBPGOOD1v0_y} )
        df_DBPGOOD1v0_MD1EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_DBPGOOD1v0_x),
                                                'x'    : MD1_Emu_B_DBPGOOD1v0_x,
                                                'y'    : MD1_Emu_B_DBPGOOD1v0_y} )

        df_DBPGOOD1v0_MD1Emu = pd.concat( [df_DBPGOOD1v0_MD1EmuA, df_DBPGOOD1v0_MD1EmuB] )

        # MD2 Emu
        df_DBPGOOD1v0_MD2EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD2_Emu_A_DBPGOOD1v0_x),
                                                'x'    : MD2_Emu_A_DBPGOOD1v0_x,
                                                'y'    : MD2_Emu_A_DBPGOOD1v0_y} )
        df_DBPGOOD1v0_MD2EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD2_Emu_B_DBPGOOD1v0_x),
                                                'x'    : MD2_Emu_B_DBPGOOD1v0_x,
                                                'y'    : MD2_Emu_B_DBPGOOD1v0_y} )

        df_DBPGOOD1v0_MD2Emu = pd.concat( [df_DBPGOOD1v0_MD2EmuA, df_DBPGOOD1v0_MD2EmuB] )

        # MD3 Emu
        df_DBPGOOD1v0_MD3EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD3_Emu_A_DBPGOOD1v0_x),
                                                'x'    : MD3_Emu_A_DBPGOOD1v0_x,
                                                'y'    : MD3_Emu_A_DBPGOOD1v0_y} )
        df_DBPGOOD1v0_MD3EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD3_Emu_B_DBPGOOD1v0_x),
                                                'x'    : MD3_Emu_B_DBPGOOD1v0_x,
                                                'y'    : MD3_Emu_B_DBPGOOD1v0_y} )

        df_DBPGOOD1v0_MD3Emu = pd.concat( [df_DBPGOOD1v0_MD3EmuA, df_DBPGOOD1v0_MD3EmuB] )

        # MD4 Emu
        df_DBPGOOD1v0_MD4EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD4_Emu_A_DBPGOOD1v0_x),
                                                'x'    : MD4_Emu_A_DBPGOOD1v0_x,
                                                'y'    : MD4_Emu_A_DBPGOOD1v0_y} )
        df_DBPGOOD1v0_MD4EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD4_Emu_B_DBPGOOD1v0_x),
                                                'x'    : MD4_Emu_B_DBPGOOD1v0_x,
                                                'y'    : MD4_Emu_B_DBPGOOD1v0_y} )

        df_DBPGOOD1v0_MD4Emu = pd.concat( [df_DBPGOOD1v0_MD4EmuA, df_DBPGOOD1v0_MD4EmuB] )

        # MD1 Ppr
        df_DBPGOOD1v0_MD1PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_DBPGOOD1v0_x),
                                                'x'    : MD1_Ppr_A_DBPGOOD1v0_x,
                                                'y'    : MD1_Ppr_A_DBPGOOD1v0_y} )
        df_DBPGOOD1v0_MD1PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_DBPGOOD1v0_x),
                                                'x'    : MD1_Ppr_B_DBPGOOD1v0_x,
                                                'y'    : MD1_Ppr_B_DBPGOOD1v0_y} )

        df_DBPGOOD1v0_MD1Ppr = pd.concat( [df_DBPGOOD1v0_MD1PprA, df_DBPGOOD1v0_MD1PprB] )

        # MD2 Ppr
        df_DBPGOOD1v0_MD2PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD2_Ppr_A_DBPGOOD1v0_x),
                                                'x'    : MD2_Ppr_A_DBPGOOD1v0_x,
                                                'y'    : MD2_Ppr_A_DBPGOOD1v0_y} )
        df_DBPGOOD1v0_MD2PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD2_Ppr_B_DBPGOOD1v0_x),
                                                'x'    : MD2_Ppr_B_DBPGOOD1v0_x,
                                                'y'    : MD2_Ppr_B_DBPGOOD1v0_y} )

        df_DBPGOOD1v0_MD2Ppr = pd.concat( [df_DBPGOOD1v0_MD2PprA, df_DBPGOOD1v0_MD2PprB] )

        # MD3 Ppr
        df_DBPGOOD1v0_MD3PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD3_Ppr_A_DBPGOOD1v0_x),
                                                'x'    : MD3_Ppr_A_DBPGOOD1v0_x,
                                                'y'    : MD3_Ppr_A_DBPGOOD1v0_y} )
        df_DBPGOOD1v0_MD3PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD3_Ppr_B_DBPGOOD1v0_x),
                                                'x'    : MD3_Ppr_B_DBPGOOD1v0_x,
                                                'y'    : MD3_Ppr_B_DBPGOOD1v0_y} )

        df_DBPGOOD1v0_MD3Ppr = pd.concat( [df_DBPGOOD1v0_MD3PprA, df_DBPGOOD1v0_MD3PprB] )

        # MD4 Ppr
        df_DBPGOOD1v0_MD4PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD4_Ppr_A_DBPGOOD1v0_x),
                                                'x'    : MD4_Ppr_A_DBPGOOD1v0_x,
                                                'y'    : MD4_Ppr_A_DBPGOOD1v0_y} )
        df_DBPGOOD1v0_MD4PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD4_Ppr_B_DBPGOOD1v0_x),
                                                'x'    : MD4_Ppr_B_DBPGOOD1v0_x,
                                                'y'    : MD4_Ppr_B_DBPGOOD1v0_y} )

        df_DBPGOOD1v0_MD4Ppr = pd.concat( [df_DBPGOOD1v0_MD4PprA, df_DBPGOOD1v0_MD4PprB] )

        #pgood_db_1v2
        # MD1 Emu
        df_DBPGOOD1v2_MD1EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_DBPGOOD1v2_x),
                                                'x'    : MD1_Emu_A_DBPGOOD1v2_x,
                                                'y'    : MD1_Emu_A_DBPGOOD1v2_y} )
        df_DBPGOOD1v2_MD1EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_DBPGOOD1v2_x),
                                                'x'    : MD1_Emu_B_DBPGOOD1v2_x,
                                                'y'    : MD1_Emu_B_DBPGOOD1v2_y} )

        df_DBPGOOD1v2_MD1Emu = pd.concat( [df_DBPGOOD1v2_MD1EmuA, df_DBPGOOD1v2_MD1EmuB] )

        # MD2 Emu
        df_DBPGOOD1v2_MD2EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD2_Emu_A_DBPGOOD1v2_x),
                                                'x'    : MD2_Emu_A_DBPGOOD1v2_x,
                                                'y'    : MD2_Emu_A_DBPGOOD1v2_y} )
        df_DBPGOOD1v2_MD2EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD2_Emu_B_DBPGOOD1v2_x),
                                                'x'    : MD2_Emu_B_DBPGOOD1v2_x,
                                                'y'    : MD2_Emu_B_DBPGOOD1v2_y} )

        df_DBPGOOD1v2_MD2Emu = pd.concat( [df_DBPGOOD1v2_MD2EmuA, df_DBPGOOD1v2_MD2EmuB] )

        # MD3 Emu
        df_DBPGOOD1v2_MD3EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD3_Emu_A_DBPGOOD1v2_x),
                                                'x'    : MD3_Emu_A_DBPGOOD1v2_x,
                                                'y'    : MD3_Emu_A_DBPGOOD1v2_y} )
        df_DBPGOOD1v2_MD3EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD3_Emu_B_DBPGOOD1v2_x),
                                                'x'    : MD3_Emu_B_DBPGOOD1v2_x,
                                                'y'    : MD3_Emu_B_DBPGOOD1v2_y} )

        df_DBPGOOD1v2_MD3Emu = pd.concat( [df_DBPGOOD1v2_MD3EmuA, df_DBPGOOD1v2_MD3EmuB] )

        # MD4 Emu
        df_DBPGOOD1v2_MD4EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD4_Emu_A_DBPGOOD1v2_x),
                                                'x'    : MD4_Emu_A_DBPGOOD1v2_x,
                                                'y'    : MD4_Emu_A_DBPGOOD1v2_y} )
        df_DBPGOOD1v2_MD4EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD4_Emu_B_DBPGOOD1v2_x),
                                                'x'    : MD4_Emu_B_DBPGOOD1v2_x,
                                                'y'    : MD4_Emu_B_DBPGOOD1v2_y} )

        df_DBPGOOD1v2_MD4Emu = pd.concat( [df_DBPGOOD1v2_MD4EmuA, df_DBPGOOD1v2_MD4EmuB] )

        # MD1 Ppr
        df_DBPGOOD1v2_MD1PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_DBPGOOD1v2_x),
                                                'x'    : MD1_Ppr_A_DBPGOOD1v2_x,
                                                'y'    : MD1_Ppr_A_DBPGOOD1v2_y} )
        df_DBPGOOD1v2_MD1PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_DBPGOOD1v2_x),
                                                'x'    : MD1_Ppr_B_DBPGOOD1v2_x,
                                                'y'    : MD1_Ppr_B_DBPGOOD1v2_y} )

        df_DBPGOOD1v2_MD1Ppr = pd.concat( [df_DBPGOOD1v2_MD1PprA, df_DBPGOOD1v2_MD1PprB] )

        # MD2 Ppr
        df_DBPGOOD1v2_MD2PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD2_Ppr_A_DBPGOOD1v2_x),
                                                'x'    : MD2_Ppr_A_DBPGOOD1v2_x,
                                                'y'    : MD2_Ppr_A_DBPGOOD1v2_y} )
        df_DBPGOOD1v2_MD2PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD2_Ppr_B_DBPGOOD1v2_x),
                                                'x'    : MD2_Ppr_B_DBPGOOD1v2_x,
                                                'y'    : MD2_Ppr_B_DBPGOOD1v2_y} )

        df_DBPGOOD1v2_MD2Ppr = pd.concat( [df_DBPGOOD1v2_MD2PprA, df_DBPGOOD1v2_MD2PprB] )

        # MD3 Ppr
        df_DBPGOOD1v2_MD3PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD3_Ppr_A_DBPGOOD1v2_x),
                                                'x'    : MD3_Ppr_A_DBPGOOD1v2_x,
                                                'y'    : MD3_Ppr_A_DBPGOOD1v2_y} )
        df_DBPGOOD1v2_MD3PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD3_Ppr_B_DBPGOOD1v2_x),
                                                'x'    : MD3_Ppr_B_DBPGOOD1v2_x,
                                                'y'    : MD3_Ppr_B_DBPGOOD1v2_y} )

        df_DBPGOOD1v2_MD3Ppr = pd.concat( [df_DBPGOOD1v2_MD3PprA, df_DBPGOOD1v2_MD3PprB] )

        # MD4 Ppr
        df_DBPGOOD1v2_MD4PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD4_Ppr_A_DBPGOOD1v2_x),
                                                'x'    : MD4_Ppr_A_DBPGOOD1v2_x,
                                                'y'    : MD4_Ppr_A_DBPGOOD1v2_y} )
        df_DBPGOOD1v2_MD4PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD4_Ppr_B_DBPGOOD1v2_x),
                                                'x'    : MD4_Ppr_B_DBPGOOD1v2_x,
                                                'y'    : MD4_Ppr_B_DBPGOOD1v2_y} )

        df_DBPGOOD1v2_MD4Ppr = pd.concat( [df_DBPGOOD1v2_MD4PprA, df_DBPGOOD1v2_MD4PprB] )

        #pgood_db_1v5
        # MD1 Emu
        df_DBPGOOD1v5_MD1EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_DBPGOOD1v5_x),
                                                'x'    : MD1_Emu_A_DBPGOOD1v5_x,
                                                'y'    : MD1_Emu_A_DBPGOOD1v5_y} )
        df_DBPGOOD1v5_MD1EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_DBPGOOD1v5_x),
                                                'x'    : MD1_Emu_B_DBPGOOD1v5_x,
                                                'y'    : MD1_Emu_B_DBPGOOD1v5_y} )

        df_DBPGOOD1v5_MD1Emu = pd.concat( [df_DBPGOOD1v5_MD1EmuA, df_DBPGOOD1v5_MD1EmuB] )

        # MD2 Emu
        df_DBPGOOD1v5_MD2EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD2_Emu_A_DBPGOOD1v5_x),
                                                'x'    : MD2_Emu_A_DBPGOOD1v5_x,
                                                'y'    : MD2_Emu_A_DBPGOOD1v5_y} )
        df_DBPGOOD1v5_MD2EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD2_Emu_B_DBPGOOD1v5_x),
                                                'x'    : MD2_Emu_B_DBPGOOD1v5_x,
                                                'y'    : MD2_Emu_B_DBPGOOD1v5_y} )

        df_DBPGOOD1v5_MD2Emu = pd.concat( [df_DBPGOOD1v5_MD2EmuA, df_DBPGOOD1v5_MD2EmuB] )

        # MD3 Emu
        df_DBPGOOD1v5_MD3EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD3_Emu_A_DBPGOOD1v5_x),
                                                'x'    : MD3_Emu_A_DBPGOOD1v5_x,
                                                'y'    : MD3_Emu_A_DBPGOOD1v5_y} )
        df_DBPGOOD1v5_MD3EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD3_Emu_B_DBPGOOD1v5_x),
                                                'x'    : MD3_Emu_B_DBPGOOD1v5_x,
                                                'y'    : MD3_Emu_B_DBPGOOD1v5_y} )

        df_DBPGOOD1v5_MD3Emu = pd.concat( [df_DBPGOOD1v5_MD3EmuA, df_DBPGOOD1v5_MD3EmuB] )

        # MD4 Emu
        df_DBPGOOD1v5_MD4EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD4_Emu_A_DBPGOOD1v5_x),
                                                'x'    : MD4_Emu_A_DBPGOOD1v5_x,
                                                'y'    : MD4_Emu_A_DBPGOOD1v5_y} )
        df_DBPGOOD1v5_MD4EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD4_Emu_B_DBPGOOD1v5_x),
                                                'x'    : MD4_Emu_B_DBPGOOD1v5_x,
                                                'y'    : MD4_Emu_B_DBPGOOD1v5_y} )

        df_DBPGOOD1v5_MD4Emu = pd.concat( [df_DBPGOOD1v5_MD4EmuA, df_DBPGOOD1v5_MD4EmuB] )

        # MD1 Ppr
        df_DBPGOOD1v5_MD1PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_DBPGOOD1v5_x),
                                                'x'    : MD1_Ppr_A_DBPGOOD1v5_x,
                                                'y'    : MD1_Ppr_A_DBPGOOD1v5_y} )
        df_DBPGOOD1v5_MD1PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_DBPGOOD1v5_x),
                                                'x'    : MD1_Ppr_B_DBPGOOD1v5_x,
                                                'y'    : MD1_Ppr_B_DBPGOOD1v5_y} )

        df_DBPGOOD1v5_MD1Ppr = pd.concat( [df_DBPGOOD1v5_MD1PprA, df_DBPGOOD1v5_MD1PprB] )

        # MD2 Ppr
        df_DBPGOOD1v5_MD2PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD2_Ppr_A_DBPGOOD1v5_x),
                                                'x'    : MD2_Ppr_A_DBPGOOD1v5_x,
                                                'y'    : MD2_Ppr_A_DBPGOOD1v5_y} )
        df_DBPGOOD1v5_MD2PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD2_Ppr_B_DBPGOOD1v5_x),
                                                'x'    : MD2_Ppr_B_DBPGOOD1v5_x,
                                                'y'    : MD2_Ppr_B_DBPGOOD1v5_y} )

        df_DBPGOOD1v5_MD2Ppr = pd.concat( [df_DBPGOOD1v5_MD2PprA, df_DBPGOOD1v5_MD2PprB] )

        # MD3 Ppr
        df_DBPGOOD1v5_MD3PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD3_Ppr_A_DBPGOOD1v5_x),
                                                'x'    : MD3_Ppr_A_DBPGOOD1v5_x,
                                                'y'    : MD3_Ppr_A_DBPGOOD1v5_y} )
        df_DBPGOOD1v5_MD3PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD3_Ppr_B_DBPGOOD1v5_x),
                                                'x'    : MD3_Ppr_B_DBPGOOD1v5_x,
                                                'y'    : MD3_Ppr_B_DBPGOOD1v5_y} )

        df_DBPGOOD1v5_MD3Ppr = pd.concat( [df_DBPGOOD1v5_MD3PprA, df_DBPGOOD1v5_MD3PprB] )

        # MD4 Ppr
        df_DBPGOOD1v5_MD4PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD4_Ppr_A_DBPGOOD1v5_x),
                                                'x'    : MD4_Ppr_A_DBPGOOD1v5_x,
                                                'y'    : MD4_Ppr_A_DBPGOOD1v5_y} )
        df_DBPGOOD1v5_MD4PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD4_Ppr_B_DBPGOOD1v5_x),
                                                'x'    : MD4_Ppr_B_DBPGOOD1v5_x,
                                                'y'    : MD4_Ppr_B_DBPGOOD1v5_y} )

        df_DBPGOOD1v5_MD4Ppr = pd.concat( [df_DBPGOOD1v5_MD4PprA, df_DBPGOOD1v5_MD4PprB] )

        #pgood_db_1v8
        # MD1 Emu
        df_DBPGOOD1v8_MD1EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_DBPGOOD1v8_x),
                                                'x'    : MD1_Emu_A_DBPGOOD1v8_x,
                                                'y'    : MD1_Emu_A_DBPGOOD1v8_y} )
        df_DBPGOOD1v8_MD1EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_DBPGOOD1v8_x),
                                                'x'    : MD1_Emu_B_DBPGOOD1v8_x,
                                                'y'    : MD1_Emu_B_DBPGOOD1v8_y} )

        df_DBPGOOD1v8_MD1Emu = pd.concat( [df_DBPGOOD1v8_MD1EmuA, df_DBPGOOD1v8_MD1EmuB] )

        # MD2 Emu
        df_DBPGOOD1v8_MD2EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD2_Emu_A_DBPGOOD1v8_x),
                                                'x'    : MD2_Emu_A_DBPGOOD1v8_x,
                                                'y'    : MD2_Emu_A_DBPGOOD1v8_y} )
        df_DBPGOOD1v8_MD2EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD2_Emu_B_DBPGOOD1v8_x),
                                                'x'    : MD2_Emu_B_DBPGOOD1v8_x,
                                                'y'    : MD2_Emu_B_DBPGOOD1v8_y} )

        df_DBPGOOD1v8_MD2Emu = pd.concat( [df_DBPGOOD1v8_MD2EmuA, df_DBPGOOD1v8_MD2EmuB] )

        # MD3 Emu
        df_DBPGOOD1v8_MD3EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD3_Emu_A_DBPGOOD1v8_x),
                                                'x'    : MD3_Emu_A_DBPGOOD1v8_x,
                                                'y'    : MD3_Emu_A_DBPGOOD1v8_y} )
        df_DBPGOOD1v8_MD3EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD3_Emu_B_DBPGOOD1v8_x),
                                                'x'    : MD3_Emu_B_DBPGOOD1v8_x,
                                                'y'    : MD3_Emu_B_DBPGOOD1v8_y} )

        df_DBPGOOD1v8_MD3Emu = pd.concat( [df_DBPGOOD1v8_MD3EmuA, df_DBPGOOD1v8_MD3EmuB] )

        # MD4 Emu
        df_DBPGOOD1v8_MD4EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD4_Emu_A_DBPGOOD1v8_x),
                                                'x'    : MD4_Emu_A_DBPGOOD1v8_x,
                                                'y'    : MD4_Emu_A_DBPGOOD1v8_y} )
        df_DBPGOOD1v8_MD4EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD4_Emu_B_DBPGOOD1v8_x),
                                                'x'    : MD4_Emu_B_DBPGOOD1v8_x,
                                                'y'    : MD4_Emu_B_DBPGOOD1v8_y} )

        df_DBPGOOD1v8_MD4Emu = pd.concat( [df_DBPGOOD1v8_MD4EmuA, df_DBPGOOD1v8_MD4EmuB] )

        # MD1 Ppr
        df_DBPGOOD1v8_MD1PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_DBPGOOD1v8_x),
                                                'x'    : MD1_Ppr_A_DBPGOOD1v8_x,
                                                'y'    : MD1_Ppr_A_DBPGOOD1v8_y} )
        df_DBPGOOD1v8_MD1PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_DBPGOOD1v8_x),
                                                'x'    : MD1_Ppr_B_DBPGOOD1v8_x,
                                                'y'    : MD1_Ppr_B_DBPGOOD1v8_y} )

        df_DBPGOOD1v8_MD1Ppr = pd.concat( [df_DBPGOOD1v8_MD1PprA, df_DBPGOOD1v8_MD1PprB] )

        # MD2 Ppr
        df_DBPGOOD1v8_MD2PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD2_Ppr_A_DBPGOOD1v8_x),
                                                'x'    : MD2_Ppr_A_DBPGOOD1v8_x,
                                                'y'    : MD2_Ppr_A_DBPGOOD1v8_y} )
        df_DBPGOOD1v8_MD2PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD2_Ppr_B_DBPGOOD1v8_x),
                                                'x'    : MD2_Ppr_B_DBPGOOD1v8_x,
                                                'y'    : MD2_Ppr_B_DBPGOOD1v8_y} )

        df_DBPGOOD1v8_MD2Ppr = pd.concat( [df_DBPGOOD1v8_MD2PprA, df_DBPGOOD1v8_MD2PprB] )

        # MD3 Ppr
        df_DBPGOOD1v8_MD3PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD3_Ppr_A_DBPGOOD1v8_x),
                                                'x'    : MD3_Ppr_A_DBPGOOD1v8_x,
                                                'y'    : MD3_Ppr_A_DBPGOOD1v8_y} )
        df_DBPGOOD1v8_MD3PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD3_Ppr_B_DBPGOOD1v8_x),
                                                'x'    : MD3_Ppr_B_DBPGOOD1v8_x,
                                                'y'    : MD3_Ppr_B_DBPGOOD1v8_y} )

        df_DBPGOOD1v8_MD3Ppr = pd.concat( [df_DBPGOOD1v8_MD3PprA, df_DBPGOOD1v8_MD3PprB] )

        # MD4 Ppr
        df_DBPGOOD1v8_MD4PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD4_Ppr_A_DBPGOOD1v8_x),
                                                'x'    : MD4_Ppr_A_DBPGOOD1v8_x,
                                                'y'    : MD4_Ppr_A_DBPGOOD1v8_y} )
        df_DBPGOOD1v8_MD4PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD4_Ppr_B_DBPGOOD1v8_x),
                                                'x'    : MD4_Ppr_B_DBPGOOD1v8_x,
                                                'y'    : MD4_Ppr_B_DBPGOOD1v8_y} )

        df_DBPGOOD1v8_MD4Ppr = pd.concat( [df_DBPGOOD1v8_MD4PprA, df_DBPGOOD1v8_MD4PprB] )

        #pgood_db_2v5
        # MD1 Emu
        df_DBPGOOD2v5_MD1EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_DBPGOOD2v5_x),
                                                'x'    : MD1_Emu_A_DBPGOOD2v5_x,
                                                'y'    : MD1_Emu_A_DBPGOOD2v5_y} )
        df_DBPGOOD2v5_MD1EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_DBPGOOD2v5_x),
                                                'x'    : MD1_Emu_B_DBPGOOD2v5_x,
                                                'y'    : MD1_Emu_B_DBPGOOD2v5_y} )

        df_DBPGOOD2v5_MD1Emu = pd.concat( [df_DBPGOOD2v5_MD1EmuA, df_DBPGOOD2v5_MD1EmuB] )

        # MD2 Emu
        df_DBPGOOD2v5_MD2EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD2_Emu_A_DBPGOOD2v5_x),
                                                'x'    : MD2_Emu_A_DBPGOOD2v5_x,
                                                'y'    : MD2_Emu_A_DBPGOOD2v5_y} )
        df_DBPGOOD2v5_MD2EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD2_Emu_B_DBPGOOD2v5_x),
                                                'x'    : MD2_Emu_B_DBPGOOD2v5_x,
                                                'y'    : MD2_Emu_B_DBPGOOD2v5_y} )

        df_DBPGOOD2v5_MD2Emu = pd.concat( [df_DBPGOOD2v5_MD2EmuA, df_DBPGOOD2v5_MD2EmuB] )

        # MD3 Emu
        df_DBPGOOD2v5_MD3EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD3_Emu_A_DBPGOOD2v5_x),
                                                'x'    : MD3_Emu_A_DBPGOOD2v5_x,
                                                'y'    : MD3_Emu_A_DBPGOOD2v5_y} )
        df_DBPGOOD2v5_MD3EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD3_Emu_B_DBPGOOD2v5_x),
                                                'x'    : MD3_Emu_B_DBPGOOD2v5_x,
                                                'y'    : MD3_Emu_B_DBPGOOD2v5_y} )

        df_DBPGOOD2v5_MD3Emu = pd.concat( [df_DBPGOOD2v5_MD3EmuA, df_DBPGOOD2v5_MD3EmuB] )

        # MD4 Emu
        df_DBPGOOD2v5_MD4EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD4_Emu_A_DBPGOOD2v5_x),
                                                'x'    : MD4_Emu_A_DBPGOOD2v5_x,
                                                'y'    : MD4_Emu_A_DBPGOOD2v5_y} )
        df_DBPGOOD2v5_MD4EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD4_Emu_B_DBPGOOD2v5_x),
                                                'x'    : MD4_Emu_B_DBPGOOD2v5_x,
                                                'y'    : MD4_Emu_B_DBPGOOD2v5_y} )

        df_DBPGOOD2v5_MD4Emu = pd.concat( [df_DBPGOOD2v5_MD4EmuA, df_DBPGOOD2v5_MD4EmuB] )

        # MD1 Ppr
        df_DBPGOOD2v5_MD1PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_DBPGOOD2v5_x),
                                                'x'    : MD1_Ppr_A_DBPGOOD2v5_x,
                                                'y'    : MD1_Ppr_A_DBPGOOD2v5_y} )
        df_DBPGOOD2v5_MD1PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_DBPGOOD2v5_x),
                                                'x'    : MD1_Ppr_B_DBPGOOD2v5_x,
                                                'y'    : MD1_Ppr_B_DBPGOOD2v5_y} )

        df_DBPGOOD2v5_MD1Ppr = pd.concat( [df_DBPGOOD2v5_MD1PprA, df_DBPGOOD2v5_MD1PprB] )

        # MD2 Ppr
        df_DBPGOOD2v5_MD2PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD2_Ppr_A_DBPGOOD2v5_x),
                                                'x'    : MD2_Ppr_A_DBPGOOD2v5_x,
                                                'y'    : MD2_Ppr_A_DBPGOOD2v5_y} )
        df_DBPGOOD2v5_MD2PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD2_Ppr_B_DBPGOOD2v5_x),
                                                'x'    : MD2_Ppr_B_DBPGOOD2v5_x,
                                                'y'    : MD2_Ppr_B_DBPGOOD2v5_y} )

        df_DBPGOOD2v5_MD2Ppr = pd.concat( [df_DBPGOOD2v5_MD2PprA, df_DBPGOOD2v5_MD2PprB] )

        # MD3 Ppr
        df_DBPGOOD2v5_MD3PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD3_Ppr_A_DBPGOOD2v5_x),
                                                'x'    : MD3_Ppr_A_DBPGOOD2v5_x,
                                                'y'    : MD3_Ppr_A_DBPGOOD2v5_y} )
        df_DBPGOOD2v5_MD3PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD3_Ppr_B_DBPGOOD2v5_x),
                                                'x'    : MD3_Ppr_B_DBPGOOD2v5_x,
                                                'y'    : MD3_Ppr_B_DBPGOOD2v5_y} )

        df_DBPGOOD2v5_MD3Ppr = pd.concat( [df_DBPGOOD2v5_MD3PprA, df_DBPGOOD2v5_MD3PprB] )

        # MD4 Ppr
        df_DBPGOOD2v5_MD4PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD4_Ppr_A_DBPGOOD2v5_x),
                                                'x'    : MD4_Ppr_A_DBPGOOD2v5_x,
                                                'y'    : MD4_Ppr_A_DBPGOOD2v5_y} )
        df_DBPGOOD2v5_MD4PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD4_Ppr_B_DBPGOOD2v5_x),
                                                'x'    : MD4_Ppr_B_DBPGOOD2v5_x,
                                                'y'    : MD4_Ppr_B_DBPGOOD2v5_y} )

        df_DBPGOOD2v5_MD4Ppr = pd.concat( [df_DBPGOOD2v5_MD4PprA, df_DBPGOOD2v5_MD4PprB] )

        #pgood_db_3v3
        # MD1 Emu
        df_DBPGOOD3v3_MD1EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_DBPGOOD3v3_x),
                                                'x'    : MD1_Emu_A_DBPGOOD3v3_x,
                                                'y'    : MD1_Emu_A_DBPGOOD3v3_y} )
        df_DBPGOOD3v3_MD1EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_DBPGOOD3v3_x),
                                                'x'    : MD1_Emu_B_DBPGOOD3v3_x,
                                                'y'    : MD1_Emu_B_DBPGOOD3v3_y} )

        df_DBPGOOD3v3_MD1Emu = pd.concat( [df_DBPGOOD3v3_MD1EmuA, df_DBPGOOD3v3_MD1EmuB] )

        # MD2 Emu
        df_DBPGOOD3v3_MD2EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD2_Emu_A_DBPGOOD3v3_x),
                                                'x'    : MD2_Emu_A_DBPGOOD3v3_x,
                                                'y'    : MD2_Emu_A_DBPGOOD3v3_y} )
        df_DBPGOOD3v3_MD2EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD2_Emu_B_DBPGOOD3v3_x),
                                                'x'    : MD2_Emu_B_DBPGOOD3v3_x,
                                                'y'    : MD2_Emu_B_DBPGOOD3v3_y} )

        df_DBPGOOD3v3_MD2Emu = pd.concat( [df_DBPGOOD3v3_MD2EmuA, df_DBPGOOD3v3_MD2EmuB] )

        # MD3 Emu
        df_DBPGOOD3v3_MD3EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD3_Emu_A_DBPGOOD3v3_x),
                                                'x'    : MD3_Emu_A_DBPGOOD3v3_x,
                                                'y'    : MD3_Emu_A_DBPGOOD3v3_y} )
        df_DBPGOOD3v3_MD3EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD3_Emu_B_DBPGOOD3v3_x),
                                                'x'    : MD3_Emu_B_DBPGOOD3v3_x,
                                                'y'    : MD3_Emu_B_DBPGOOD3v3_y} )

        df_DBPGOOD3v3_MD3Emu = pd.concat( [df_DBPGOOD3v3_MD3EmuA, df_DBPGOOD3v3_MD3EmuB] )

        # MD4 Emu
        df_DBPGOOD3v3_MD4EmuA = pd.DataFrame( {'name' : [' - Emu - KU FPGA A']*len(MD4_Emu_A_DBPGOOD3v3_x),
                                                'x'    : MD4_Emu_A_DBPGOOD3v3_x,
                                                'y'    : MD4_Emu_A_DBPGOOD3v3_y} )
        df_DBPGOOD3v3_MD4EmuB = pd.DataFrame( {'name' : [' - Emu - KU FPGA B']*len(MD4_Emu_B_DBPGOOD3v3_x),
                                                'x'    : MD4_Emu_B_DBPGOOD3v3_x,
                                                'y'    : MD4_Emu_B_DBPGOOD3v3_y} )

        df_DBPGOOD3v3_MD4Emu = pd.concat( [df_DBPGOOD3v3_MD4EmuA, df_DBPGOOD3v3_MD4EmuB] )

        # MD1 Ppr
        df_DBPGOOD3v3_MD1PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_DBPGOOD3v3_x),
                                                'x'    : MD1_Ppr_A_DBPGOOD3v3_x,
                                                'y'    : MD1_Ppr_A_DBPGOOD3v3_y} )
        df_DBPGOOD3v3_MD1PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_DBPGOOD3v3_x),
                                                'x'    : MD1_Ppr_B_DBPGOOD3v3_x,
                                                'y'    : MD1_Ppr_B_DBPGOOD3v3_y} )

        df_DBPGOOD3v3_MD1Ppr = pd.concat( [df_DBPGOOD3v3_MD1PprA, df_DBPGOOD3v3_MD1PprB] )

        # MD2 Ppr
        df_DBPGOOD3v3_MD2PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD2_Ppr_A_DBPGOOD3v3_x),
                                                'x'    : MD2_Ppr_A_DBPGOOD3v3_x,
                                                'y'    : MD2_Ppr_A_DBPGOOD3v3_y} )
        df_DBPGOOD3v3_MD2PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD2_Ppr_B_DBPGOOD3v3_x),
                                                'x'    : MD2_Ppr_B_DBPGOOD3v3_x,
                                                'y'    : MD2_Ppr_B_DBPGOOD3v3_y} )

        df_DBPGOOD3v3_MD2Ppr = pd.concat( [df_DBPGOOD3v3_MD2PprA, df_DBPGOOD3v3_MD2PprB] )

        # MD3 Ppr
        df_DBPGOOD3v3_MD3PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD3_Ppr_A_DBPGOOD3v3_x),
                                                'x'    : MD3_Ppr_A_DBPGOOD3v3_x,
                                                'y'    : MD3_Ppr_A_DBPGOOD3v3_y} )
        df_DBPGOOD3v3_MD3PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD3_Ppr_B_DBPGOOD3v3_x),
                                                'x'    : MD3_Ppr_B_DBPGOOD3v3_x,
                                                'y'    : MD3_Ppr_B_DBPGOOD3v3_y} )

        df_DBPGOOD3v3_MD3Ppr = pd.concat( [df_DBPGOOD3v3_MD3PprA, df_DBPGOOD3v3_MD3PprB] )

        # MD4 Ppr
        df_DBPGOOD3v3_MD4PprA = pd.DataFrame( {'name' : [' - Ppr - KU FPGA A']*len(MD4_Ppr_A_DBPGOOD3v3_x),
                                                'x'    : MD4_Ppr_A_DBPGOOD3v3_x,
                                                'y'    : MD4_Ppr_A_DBPGOOD3v3_y} )
        df_DBPGOOD3v3_MD4PprB = pd.DataFrame( {'name' : [' - Ppr - KU FPGA B']*len(MD4_Ppr_B_DBPGOOD3v3_x),
                                                'x'    : MD4_Ppr_B_DBPGOOD3v3_x,
                                                'y'    : MD4_Ppr_B_DBPGOOD3v3_y} )

        df_DBPGOOD3v3_MD4Ppr = pd.concat( [df_DBPGOOD3v3_MD4PprA, df_DBPGOOD3v3_MD4PprB] )

        # pgood_mb_5v0
        # MD1 Emu
        df_MBPGOODP5v_MD1EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_MBPGOODP5v_x),
                                               'x'    : MD1_Emu_A_MBPGOODP5v_x,
                                               'y'    : MD1_Emu_A_MBPGOODP5v_y} )
        df_MBPGOODP5v_MD1EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_MBPGOODP5v_x),
                                               'x'    : MD1_Emu_B_MBPGOODP5v_x,
                                               'y'    : MD1_Emu_B_MBPGOODP5v_y} )

        df_MBPGOODP5v_MD1Emu = pd.concat( [df_MBPGOODP5v_MD1EmuA, df_MBPGOODP5v_MD1EmuB] )

        # MD2 Emu
        df_MBPGOODP5v_MD2EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD2_Emu_A_MBPGOODP5v_x),
                                               'x'    : MD2_Emu_A_MBPGOODP5v_x,
                                               'y'    : MD2_Emu_A_MBPGOODP5v_y} )
        df_MBPGOODP5v_MD2EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD2_Emu_B_MBPGOODP5v_x),
                                               'x'    : MD2_Emu_B_MBPGOODP5v_x,
                                               'y'    : MD2_Emu_B_MBPGOODP5v_y} )

        df_MBPGOODP5v_MD2Emu = pd.concat( [df_MBPGOODP5v_MD2EmuA, df_MBPGOODP5v_MD2EmuB] )

        # MD3 Emu
        df_MBPGOODP5v_MD3EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD3_Emu_A_MBPGOODP5v_x),
                                               'x'    : MD3_Emu_A_MBPGOODP5v_x,
                                               'y'    : MD3_Emu_A_MBPGOODP5v_y} )
        df_MBPGOODP5v_MD3EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD3_Emu_B_MBPGOODP5v_x),
                                               'x'    : MD3_Emu_B_MBPGOODP5v_x,
                                               'y'    : MD3_Emu_B_MBPGOODP5v_y} )

        df_MBPGOODP5v_MD3Emu = pd.concat( [df_MBPGOODP5v_MD3EmuA, df_MBPGOODP5v_MD3EmuB] )

        # MD4 Emu
        df_MBPGOODP5v_MD4EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD4_Emu_A_MBPGOODP5v_x),
                                               'x'    : MD4_Emu_A_MBPGOODP5v_x,
                                               'y'    : MD4_Emu_A_MBPGOODP5v_y} )
        df_MBPGOODP5v_MD4EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD4_Emu_B_MBPGOODP5v_x),
                                               'x'    : MD4_Emu_B_MBPGOODP5v_x,
                                               'y'    : MD4_Emu_B_MBPGOODP5v_y} )

        df_MBPGOODP5v_MD4Emu = pd.concat( [df_MBPGOODP5v_MD4EmuA, df_MBPGOODP5v_MD4EmuB] )

        # MD1 Ppr
        df_MBPGOODP5v_MD1PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_MBPGOODP5v_x),
                                               'x'    : MD1_Ppr_A_MBPGOODP5v_x,
                                               'y'    : MD1_Ppr_A_MBPGOODP5v_y} )
        df_MBPGOODP5v_MD1PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_MBPGOODP5v_x),
                                               'x'    : MD1_Ppr_B_MBPGOODP5v_x,
                                               'y'    : MD1_Ppr_B_MBPGOODP5v_y} )

        df_MBPGOODP5v_MD1Ppr = pd.concat( [df_MBPGOODP5v_MD1PprA, df_MBPGOODP5v_MD1PprB] )

        # MD2 Ppr
        df_MBPGOODP5v_MD2PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD2_Ppr_A_MBPGOODP5v_x),
                                               'x'    : MD2_Ppr_A_MBPGOODP5v_x,
                                               'y'    : MD2_Ppr_A_MBPGOODP5v_y} )
        df_MBPGOODP5v_MD2PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD2_Ppr_B_MBPGOODP5v_x),
                                               'x'    : MD2_Ppr_B_MBPGOODP5v_x,
                                               'y'    : MD2_Ppr_B_MBPGOODP5v_y} )

        df_MBPGOODP5v_MD2Ppr = pd.concat( [df_MBPGOODP5v_MD2PprA, df_MBPGOODP5v_MD2PprB] )

        # MD3 Ppr
        df_MBPGOODP5v_MD3PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD3_Ppr_A_MBPGOODP5v_x),
                                               'x'    : MD3_Ppr_A_MBPGOODP5v_x,
                                               'y'    : MD3_Ppr_A_MBPGOODP5v_y} )
        df_MBPGOODP5v_MD3PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD3_Ppr_B_MBPGOODP5v_x),
                                               'x'    : MD3_Ppr_B_MBPGOODP5v_x,
                                               'y'    : MD3_Ppr_B_MBPGOODP5v_y} )

        df_MBPGOODP5v_MD3Ppr = pd.concat( [df_MBPGOODP5v_MD3PprA, df_MBPGOODP5v_MD3PprB] )

        # MD4 Ppr
        df_MBPGOODP5v_MD4PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD4_Ppr_A_MBPGOODP5v_x),
                                               'x'    : MD4_Ppr_A_MBPGOODP5v_x,
                                               'y'    : MD4_Ppr_A_MBPGOODP5v_y} )
        df_MBPGOODP5v_MD4PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD4_Ppr_B_MBPGOODP5v_x),
                                               'x'    : MD4_Ppr_B_MBPGOODP5v_x,
                                               'y'    : MD4_Ppr_B_MBPGOODP5v_y} )

        df_MBPGOODP5v_MD4Ppr = pd.concat( [df_MBPGOODP5v_MD4PprA, df_MBPGOODP5v_MD4PprB] )

        # pgood_mb_5v0_n
        # MD1 Emu
        df_MBPGOODN5v_MD1EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_MBPGOODN5v_x),
                                               'x'    : MD1_Emu_A_MBPGOODN5v_x,
                                               'y'    : MD1_Emu_A_MBPGOODN5v_y} )
        df_MBPGOODN5v_MD1EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_MBPGOODN5v_x),
                                               'x'    : MD1_Emu_B_MBPGOODN5v_x,
                                               'y'    : MD1_Emu_B_MBPGOODN5v_y} )

        df_MBPGOODN5v_MD1Emu = pd.concat( [df_MBPGOODN5v_MD1EmuA, df_MBPGOODN5v_MD1EmuB] )

        # MD2 Emu
        df_MBPGOODN5v_MD2EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD2_Emu_A_MBPGOODN5v_x),
                                               'x'    : MD2_Emu_A_MBPGOODN5v_x,
                                               'y'    : MD2_Emu_A_MBPGOODN5v_y} )
        df_MBPGOODN5v_MD2EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD2_Emu_B_MBPGOODN5v_x),
                                               'x'    : MD2_Emu_B_MBPGOODN5v_x,
                                               'y'    : MD2_Emu_B_MBPGOODN5v_y} )

        df_MBPGOODN5v_MD2Emu = pd.concat( [df_MBPGOODN5v_MD2EmuA, df_MBPGOODN5v_MD2EmuB] )

        # MD3 Emu
        df_MBPGOODN5v_MD3EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD3_Emu_A_MBPGOODN5v_x),
                                               'x'    : MD3_Emu_A_MBPGOODN5v_x,
                                               'y'    : MD3_Emu_A_MBPGOODN5v_y} )
        df_MBPGOODN5v_MD3EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD3_Emu_B_MBPGOODN5v_x),
                                               'x'    : MD3_Emu_B_MBPGOODN5v_x,
                                               'y'    : MD3_Emu_B_MBPGOODN5v_y} )

        df_MBPGOODN5v_MD3Emu = pd.concat( [df_MBPGOODN5v_MD3EmuA, df_MBPGOODN5v_MD3EmuB] )

        # MD4 Emu
        df_MBPGOODN5v_MD4EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD4_Emu_A_MBPGOODN5v_x),
                                               'x'    : MD4_Emu_A_MBPGOODN5v_x,
                                               'y'    : MD4_Emu_A_MBPGOODN5v_y} )
        df_MBPGOODN5v_MD4EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD4_Emu_B_MBPGOODN5v_x),
                                               'x'    : MD4_Emu_B_MBPGOODN5v_x,
                                               'y'    : MD4_Emu_B_MBPGOODN5v_y} )

        df_MBPGOODN5v_MD4Emu = pd.concat( [df_MBPGOODN5v_MD4EmuA, df_MBPGOODN5v_MD4EmuB] )

        # MD1 Ppr
        df_MBPGOODN5v_MD1PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_MBPGOODN5v_x),
                                               'x'    : MD1_Ppr_A_MBPGOODN5v_x,
                                               'y'    : MD1_Ppr_A_MBPGOODN5v_y} )
        df_MBPGOODN5v_MD1PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_MBPGOODN5v_x),
                                               'x'    : MD1_Ppr_B_MBPGOODN5v_x,
                                               'y'    : MD1_Ppr_B_MBPGOODN5v_y} )

        df_MBPGOODN5v_MD1Ppr = pd.concat( [df_MBPGOODN5v_MD1PprA, df_MBPGOODN5v_MD1PprB] )

        # MD2 Ppr
        df_MBPGOODN5v_MD2PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD2_Ppr_A_MBPGOODN5v_x),
                                               'x'    : MD2_Ppr_A_MBPGOODN5v_x,
                                               'y'    : MD2_Ppr_A_MBPGOODN5v_y} )
        df_MBPGOODN5v_MD2PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD2_Ppr_B_MBPGOODN5v_x),
                                               'x'    : MD2_Ppr_B_MBPGOODN5v_x,
                                               'y'    : MD2_Ppr_B_MBPGOODN5v_y} )

        df_MBPGOODN5v_MD2Ppr = pd.concat( [df_MBPGOODN5v_MD2PprA, df_MBPGOODN5v_MD2PprB] )

        # MD3 Ppr
        df_MBPGOODN5v_MD3PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD3_Ppr_A_MBPGOODN5v_x),
                                               'x'    : MD3_Ppr_A_MBPGOODN5v_x,
                                               'y'    : MD3_Ppr_A_MBPGOODN5v_y} )
        df_MBPGOODN5v_MD3PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD3_Ppr_B_MBPGOODN5v_x),
                                               'x'    : MD3_Ppr_B_MBPGOODN5v_x,
                                               'y'    : MD3_Ppr_B_MBPGOODN5v_y} )

        df_MBPGOODN5v_MD3Ppr = pd.concat( [df_MBPGOODN5v_MD3PprA, df_MBPGOODN5v_MD3PprB] )

        # MD4 Ppr
        df_MBPGOODN5v_MD4PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD4_Ppr_A_MBPGOODN5v_x),
                                               'x'    : MD4_Ppr_A_MBPGOODN5v_x,
                                               'y'    : MD4_Ppr_A_MBPGOODN5v_y} )
        df_MBPGOODN5v_MD4PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD4_Ppr_B_MBPGOODN5v_x),
                                               'x'    : MD4_Ppr_B_MBPGOODN5v_x,
                                               'y'    : MD4_Ppr_B_MBPGOODN5v_y} )

        df_MBPGOODN5v_MD4Ppr = pd.concat( [df_MBPGOODN5v_MD4PprA, df_MBPGOODN5v_MD4PprB] )

        # pgood_mb_1v2
        # MD1 Emu
        df_MBPGOOD1v2_MD1EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_MBPGOOD1v2_x),
                                               'x'    : MD1_Emu_A_MBPGOOD1v2_x,
                                               'y'    : MD1_Emu_A_MBPGOOD1v2_y} )
        df_MBPGOOD1v2_MD1EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_MBPGOOD1v2_x),
                                               'x'    : MD1_Emu_B_MBPGOOD1v2_x,
                                               'y'    : MD1_Emu_B_MBPGOOD1v2_y} )

        df_MBPGOOD1v2_MD1Emu = pd.concat( [df_MBPGOOD1v2_MD1EmuA, df_MBPGOOD1v2_MD1EmuB] )

        # MD2 Emu
        df_MBPGOOD1v2_MD2EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD2_Emu_A_MBPGOOD1v2_x),
                                               'x'    : MD2_Emu_A_MBPGOOD1v2_x,
                                               'y'    : MD2_Emu_A_MBPGOOD1v2_y} )
        df_MBPGOOD1v2_MD2EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD2_Emu_B_MBPGOOD1v2_x),
                                               'x'    : MD2_Emu_B_MBPGOOD1v2_x,
                                               'y'    : MD2_Emu_B_MBPGOOD1v2_y} )

        df_MBPGOOD1v2_MD2Emu = pd.concat( [df_MBPGOOD1v2_MD2EmuA, df_MBPGOOD1v2_MD2EmuB] )

        # MD3 Emu
        df_MBPGOOD1v2_MD3EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD3_Emu_A_MBPGOOD1v2_x),
                                               'x'    : MD3_Emu_A_MBPGOOD1v2_x,
                                               'y'    : MD3_Emu_A_MBPGOOD1v2_y} )
        df_MBPGOOD1v2_MD3EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD3_Emu_B_MBPGOOD1v2_x),
                                               'x'    : MD3_Emu_B_MBPGOOD1v2_x,
                                               'y'    : MD3_Emu_B_MBPGOOD1v2_y} )

        df_MBPGOOD1v2_MD3Emu = pd.concat( [df_MBPGOOD1v2_MD3EmuA, df_MBPGOOD1v2_MD3EmuB] )

        # MD4 Emu
        df_MBPGOOD1v2_MD4EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD4_Emu_A_MBPGOOD1v2_x),
                                               'x'    : MD4_Emu_A_MBPGOOD1v2_x,
                                               'y'    : MD4_Emu_A_MBPGOOD1v2_y} )
        df_MBPGOOD1v2_MD4EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD4_Emu_B_MBPGOOD1v2_x),
                                               'x'    : MD4_Emu_B_MBPGOOD1v2_x,
                                               'y'    : MD4_Emu_B_MBPGOOD1v2_y} )

        df_MBPGOOD1v2_MD4Emu = pd.concat( [df_MBPGOOD1v2_MD4EmuA, df_MBPGOOD1v2_MD4EmuB] )

        # MD1 Ppr
        df_MBPGOOD1v2_MD1PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_MBPGOOD1v2_x),
                                               'x'    : MD1_Ppr_A_MBPGOOD1v2_x,
                                               'y'    : MD1_Ppr_A_MBPGOOD1v2_y} )
        df_MBPGOOD1v2_MD1PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_MBPGOOD1v2_x),
                                               'x'    : MD1_Ppr_B_MBPGOOD1v2_x,
                                               'y'    : MD1_Ppr_B_MBPGOOD1v2_y} )

        df_MBPGOOD1v2_MD1Ppr = pd.concat( [df_MBPGOOD1v2_MD1PprA, df_MBPGOOD1v2_MD1PprB] )

        # MD2 Ppr
        df_MBPGOOD1v2_MD2PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD2_Ppr_A_MBPGOOD1v2_x),
                                               'x'    : MD2_Ppr_A_MBPGOOD1v2_x,
                                               'y'    : MD2_Ppr_A_MBPGOOD1v2_y} )
        df_MBPGOOD1v2_MD2PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD2_Ppr_B_MBPGOOD1v2_x),
                                               'x'    : MD2_Ppr_B_MBPGOOD1v2_x,
                                               'y'    : MD2_Ppr_B_MBPGOOD1v2_y} )

        df_MBPGOOD1v2_MD2Ppr = pd.concat( [df_MBPGOOD1v2_MD2PprA, df_MBPGOOD1v2_MD2PprB] )

        # MD3 Ppr
        df_MBPGOOD1v2_MD3PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD3_Ppr_A_MBPGOOD1v2_x),
                                               'x'    : MD3_Ppr_A_MBPGOOD1v2_x,
                                               'y'    : MD3_Ppr_A_MBPGOOD1v2_y} )
        df_MBPGOOD1v2_MD3PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD3_Ppr_B_MBPGOOD1v2_x),
                                               'x'    : MD3_Ppr_B_MBPGOOD1v2_x,
                                               'y'    : MD3_Ppr_B_MBPGOOD1v2_y} )

        df_MBPGOOD1v2_MD3Ppr = pd.concat( [df_MBPGOOD1v2_MD3PprA, df_MBPGOOD1v2_MD3PprB] )

        # MD4 Ppr
        df_MBPGOOD1v2_MD4PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD4_Ppr_A_MBPGOOD1v2_x),
                                               'x'    : MD4_Ppr_A_MBPGOOD1v2_x,
                                               'y'    : MD4_Ppr_A_MBPGOOD1v2_y} )
        df_MBPGOOD1v2_MD4PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD4_Ppr_B_MBPGOOD1v2_x),
                                               'x'    : MD4_Ppr_B_MBPGOOD1v2_x,
                                               'y'    : MD4_Ppr_B_MBPGOOD1v2_y} )

        df_MBPGOOD1v2_MD4Ppr = pd.concat( [df_MBPGOOD1v2_MD4PprA, df_MBPGOOD1v2_MD4PprB] )

        # pgood_mb_1v8
        # MD1 Emu
        df_MBPGOOD1v8_MD1EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_MBPGOOD1v8_x),
                                               'x'    : MD1_Emu_A_MBPGOOD1v8_x,
                                               'y'    : MD1_Emu_A_MBPGOOD1v8_y} )
        df_MBPGOOD1v8_MD1EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_MBPGOOD1v8_x),
                                               'x'    : MD1_Emu_B_MBPGOOD1v8_x,
                                               'y'    : MD1_Emu_B_MBPGOOD1v8_y} )

        df_MBPGOOD1v8_MD1Emu = pd.concat( [df_MBPGOOD1v8_MD1EmuA, df_MBPGOOD1v8_MD1EmuB] )

        # MD2 Emu
        df_MBPGOOD1v8_MD2EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD2_Emu_A_MBPGOOD1v8_x),
                                               'x'    : MD2_Emu_A_MBPGOOD1v8_x,
                                               'y'    : MD2_Emu_A_MBPGOOD1v8_y} )
        df_MBPGOOD1v8_MD2EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD2_Emu_B_MBPGOOD1v8_x),
                                               'x'    : MD2_Emu_B_MBPGOOD1v8_x,
                                               'y'    : MD2_Emu_B_MBPGOOD1v8_y} )

        df_MBPGOOD1v8_MD2Emu = pd.concat( [df_MBPGOOD1v8_MD2EmuA, df_MBPGOOD1v8_MD2EmuB] )

        # MD3 Emu
        df_MBPGOOD1v8_MD3EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD3_Emu_A_MBPGOOD1v8_x),
                                               'x'    : MD3_Emu_A_MBPGOOD1v8_x,
                                               'y'    : MD3_Emu_A_MBPGOOD1v8_y} )
        df_MBPGOOD1v8_MD3EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD3_Emu_B_MBPGOOD1v8_x),
                                               'x'    : MD3_Emu_B_MBPGOOD1v8_x,
                                               'y'    : MD3_Emu_B_MBPGOOD1v8_y} )

        df_MBPGOOD1v8_MD3Emu = pd.concat( [df_MBPGOOD1v8_MD3EmuA, df_MBPGOOD1v8_MD3EmuB] )

        # MD4 Emu
        df_MBPGOOD1v8_MD4EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD4_Emu_A_MBPGOOD1v8_x),
                                               'x'    : MD4_Emu_A_MBPGOOD1v8_x,
                                               'y'    : MD4_Emu_A_MBPGOOD1v8_y} )
        df_MBPGOOD1v8_MD4EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD4_Emu_B_MBPGOOD1v8_x),
                                               'x'    : MD4_Emu_B_MBPGOOD1v8_x,
                                               'y'    : MD4_Emu_B_MBPGOOD1v8_y} )

        df_MBPGOOD1v8_MD4Emu = pd.concat( [df_MBPGOOD1v8_MD4EmuA, df_MBPGOOD1v8_MD4EmuB] )

        # MD1 Ppr
        df_MBPGOOD1v8_MD1PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_MBPGOOD1v8_x),
                                               'x'    : MD1_Ppr_A_MBPGOOD1v8_x,
                                               'y'    : MD1_Ppr_A_MBPGOOD1v8_y} )
        df_MBPGOOD1v8_MD1PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_MBPGOOD1v8_x),
                                               'x'    : MD1_Ppr_B_MBPGOOD1v8_x,
                                               'y'    : MD1_Ppr_B_MBPGOOD1v8_y} )

        df_MBPGOOD1v8_MD1Ppr = pd.concat( [df_MBPGOOD1v8_MD1PprA, df_MBPGOOD1v8_MD1PprB] )

        # MD2 Ppr
        df_MBPGOOD1v8_MD2PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD2_Ppr_A_MBPGOOD1v8_x),
                                               'x'    : MD2_Ppr_A_MBPGOOD1v8_x,
                                               'y'    : MD2_Ppr_A_MBPGOOD1v8_y} )
        df_MBPGOOD1v8_MD2PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD2_Ppr_B_MBPGOOD1v8_x),
                                               'x'    : MD2_Ppr_B_MBPGOOD1v8_x,
                                               'y'    : MD2_Ppr_B_MBPGOOD1v8_y} )

        df_MBPGOOD1v8_MD2Ppr = pd.concat( [df_MBPGOOD1v8_MD2PprA, df_MBPGOOD1v8_MD2PprB] )

        # MD3 Ppr
        df_MBPGOOD1v8_MD3PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD3_Ppr_A_MBPGOOD1v8_x),
                                               'x'    : MD3_Ppr_A_MBPGOOD1v8_x,
                                               'y'    : MD3_Ppr_A_MBPGOOD1v8_y} )
        df_MBPGOOD1v8_MD3PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD3_Ppr_B_MBPGOOD1v8_x),
                                               'x'    : MD3_Ppr_B_MBPGOOD1v8_x,
                                               'y'    : MD3_Ppr_B_MBPGOOD1v8_y} )

        df_MBPGOOD1v8_MD3Ppr = pd.concat( [df_MBPGOOD1v8_MD3PprA, df_MBPGOOD1v8_MD3PprB] )

        # MD4 Ppr
        df_MBPGOOD1v8_MD4PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD4_Ppr_A_MBPGOOD1v8_x),
                                               'x'    : MD4_Ppr_A_MBPGOOD1v8_x,
                                               'y'    : MD4_Ppr_A_MBPGOOD1v8_y} )
        df_MBPGOOD1v8_MD4PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD4_Ppr_B_MBPGOOD1v8_x),
                                               'x'    : MD4_Ppr_B_MBPGOOD1v8_x,
                                               'y'    : MD4_Ppr_B_MBPGOOD1v8_y} )

        df_MBPGOOD1v8_MD4Ppr = pd.concat( [df_MBPGOOD1v8_MD4PprA, df_MBPGOOD1v8_MD4PprB] )

        # pgood_mb_2v5
        # MD1 Emu
        df_MBPGOOD2v5_MD1EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD1_Emu_A_MBPGOOD2v5_x),
                                               'x'    : MD1_Emu_A_MBPGOOD2v5_x,
                                               'y'    : MD1_Emu_A_MBPGOOD2v5_y} )
        df_MBPGOOD2v5_MD1EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD1_Emu_B_MBPGOOD2v5_x),
                                               'x'    : MD1_Emu_B_MBPGOOD2v5_x,
                                               'y'    : MD1_Emu_B_MBPGOOD2v5_y} )

        df_MBPGOOD2v5_MD1Emu = pd.concat( [df_MBPGOOD2v5_MD1EmuA, df_MBPGOOD2v5_MD1EmuB] )

        # MD2 Emu
        df_MBPGOOD2v5_MD2EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD2_Emu_A_MBPGOOD2v5_x),
                                               'x'    : MD2_Emu_A_MBPGOOD2v5_x,
                                               'y'    : MD2_Emu_A_MBPGOOD2v5_y} )
        df_MBPGOOD2v5_MD2EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD2_Emu_B_MBPGOOD2v5_x),
                                               'x'    : MD2_Emu_B_MBPGOOD2v5_x,
                                               'y'    : MD2_Emu_B_MBPGOOD2v5_y} )

        df_MBPGOOD2v5_MD2Emu = pd.concat( [df_MBPGOOD2v5_MD2EmuA, df_MBPGOOD2v5_MD2EmuB] )

        # MD3 Emu
        df_MBPGOOD2v5_MD3EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD3_Emu_A_MBPGOOD2v5_x),
                                               'x'    : MD3_Emu_A_MBPGOOD2v5_x,
                                               'y'    : MD3_Emu_A_MBPGOOD2v5_y} )
        df_MBPGOOD2v5_MD3EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD3_Emu_B_MBPGOOD2v5_x),
                                               'x'    : MD3_Emu_B_MBPGOOD2v5_x,
                                               'y'    : MD3_Emu_B_MBPGOOD2v5_y} )

        df_MBPGOOD2v5_MD3Emu = pd.concat( [df_MBPGOOD2v5_MD3EmuA, df_MBPGOOD2v5_MD3EmuB] )

        # MD4 Emu
        df_MBPGOOD2v5_MD4EmuA = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA A']*len(MD4_Emu_A_MBPGOOD2v5_x),
                                               'x'    : MD4_Emu_A_MBPGOOD2v5_x,
                                               'y'    : MD4_Emu_A_MBPGOOD2v5_y} )
        df_MBPGOOD2v5_MD4EmuB = pd.DataFrame( {'name' : ['9000001 - Emu - KU FPGA B']*len(MD4_Emu_B_MBPGOOD2v5_x),
                                               'x'    : MD4_Emu_B_MBPGOOD2v5_x,
                                               'y'    : MD4_Emu_B_MBPGOOD2v5_y} )

        df_MBPGOOD2v5_MD4Emu = pd.concat( [df_MBPGOOD2v5_MD4EmuA, df_MBPGOOD2v5_MD4EmuB] )

        # MD1 Ppr
        df_MBPGOOD2v5_MD1PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD1_Ppr_A_MBPGOOD2v5_x),
                                               'x'    : MD1_Ppr_A_MBPGOOD2v5_x,
                                               'y'    : MD1_Ppr_A_MBPGOOD2v5_y} )
        df_MBPGOOD2v5_MD1PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD1_Ppr_B_MBPGOOD2v5_x),
                                               'x'    : MD1_Ppr_B_MBPGOOD2v5_x,
                                               'y'    : MD1_Ppr_B_MBPGOOD2v5_y} )

        df_MBPGOOD2v5_MD1Ppr = pd.concat( [df_MBPGOOD2v5_MD1PprA, df_MBPGOOD2v5_MD1PprB] )

        # MD2 Ppr
        df_MBPGOOD2v5_MD2PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD2_Ppr_A_MBPGOOD2v5_x),
                                               'x'    : MD2_Ppr_A_MBPGOOD2v5_x,
                                               'y'    : MD2_Ppr_A_MBPGOOD2v5_y} )
        df_MBPGOOD2v5_MD2PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD2_Ppr_B_MBPGOOD2v5_x),
                                               'x'    : MD2_Ppr_B_MBPGOOD2v5_x,
                                               'y'    : MD2_Ppr_B_MBPGOOD2v5_y} )

        df_MBPGOOD2v5_MD2Ppr = pd.concat( [df_MBPGOOD2v5_MD2PprA, df_MBPGOOD2v5_MD2PprB] )

        # MD3 Ppr
        df_MBPGOOD2v5_MD3PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD3_Ppr_A_MBPGOOD2v5_x),
                                               'x'    : MD3_Ppr_A_MBPGOOD2v5_x,
                                               'y'    : MD3_Ppr_A_MBPGOOD2v5_y} )
        df_MBPGOOD2v5_MD3PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD3_Ppr_B_MBPGOOD2v5_x),
                                               'x'    : MD3_Ppr_B_MBPGOOD2v5_x,
                                               'y'    : MD3_Ppr_B_MBPGOOD2v5_y} )

        df_MBPGOOD2v5_MD3Ppr = pd.concat( [df_MBPGOOD2v5_MD3PprA, df_MBPGOOD2v5_MD3PprB] )

        # MD4 Ppr
        df_MBPGOOD2v5_MD4PprA = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA A']*len(MD4_Ppr_A_MBPGOOD2v5_x),
                                               'x'    : MD4_Ppr_A_MBPGOOD2v5_x,
                                               'y'    : MD4_Ppr_A_MBPGOOD2v5_y} )
        df_MBPGOOD2v5_MD4PprB = pd.DataFrame( {'name' : ['9000001 - Ppr - KU FPGA B']*len(MD4_Ppr_B_MBPGOOD2v5_x),
                                               'x'    : MD4_Ppr_B_MBPGOOD2v5_x,
                                               'y'    : MD4_Ppr_B_MBPGOOD2v5_y} )

        df_MBPGOOD2v5_MD4Ppr = pd.concat( [df_MBPGOOD2v5_MD4PprA, df_MBPGOOD2v5_MD4PprB] )

        ### Plotting ###
        #db_mon_0.95v(vaux0)
        fig_DBC0v95_MD1Emu = plotlyEX.line( df_DBC0v95_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_0.95v(vaux0)", "name":"FPGA Side"})
        fig_DBC0v95_MD1Emu.update_layout(title='PPrEmu MD1: DBCurrent - 0.95V')
        fig_DBC0v95_MD1Emu.write_html("plotly_MD1EmuDBC0.95V_combined.html")

        fig_DBC0v95_MD2Emu = plotlyEX.line( df_DBC0v95_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_0.95v(vaux0)", "name":"FPGA Side"})
        fig_DBC0v95_MD2Emu.update_layout(title='PPrEmu MD2: DBCurrent - 0.95V')
        fig_DBC0v95_MD2Emu.write_html("plotly_MD2EmuDBC0.95V_combined.html")

        fig_DBC0v95_MD3Emu = plotlyEX.line( df_DBC0v95_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_0.95v(vaux0)", "name":"FPGA Side"})
        fig_DBC0v95_MD3Emu.update_layout(title='PPrEmu MD3: DBCurrent - 0.95V')
        fig_DBC0v95_MD3Emu.write_html("plotly_MD3EmuDBC0.95V_combined.html")

        fig_DBC0v95_MD4Emu = plotlyEX.line( df_DBC0v95_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_0.95v(vaux0)", "name":"FPGA Side"})
        fig_DBC0v95_MD4Emu.update_layout(title='PPrEmu MD4: DBCurrent - 0.95V')
        fig_DBC0v95_MD4Emu.write_html("plotly_MD4EmuDBC0.95V_combined.html")

        fig_DBC0v95_MD1Ppr = plotlyEX.line( df_DBC0v95_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_0.95v(vaux0)", "name":"FPGA Side"})
        fig_DBC0v95_MD1Ppr.update_layout(title='PPrPpr MD1: DBCurrent - 0.95V')
        fig_DBC0v95_MD1Ppr.write_html("plotly_MD1PprDBC0.95V_combined.html")

        fig_DBC0v95_MD2Ppr = plotlyEX.line( df_DBC0v95_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_0.95v(vaux0)", "name":"FPGA Side"})
        fig_DBC0v95_MD2Ppr.update_layout(title='PPrPpr MD2: DBCurrent - 0.95V')
        fig_DBC0v95_MD2Ppr.write_html("plotly_MD2PprDBC0.95V_combined.html")

        fig_DBC0v95_MD3Ppr = plotlyEX.line( df_DBC0v95_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_0.95v(vaux0)", "name":"FPGA Side"})
        fig_DBC0v95_MD3Ppr.update_layout(title='PPrPpr MD3: DBCurrent - 0.95V')
        fig_DBC0v95_MD3Ppr.write_html("plotly_MD3PprDBC0.95V_combined.html")

        fig_DBC0v95_MD4Ppr = plotlyEX.line( df_DBC0v95_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_0.95v(vaux0)", "name":"FPGA Side"})
        fig_DBC0v95_MD4Ppr.update_layout(title='PPrPpr MD4: DBCurrent - 0.95V')
        fig_DBC0v95_MD4Ppr.write_html("plotly_MD4PprDBC0.95V_combined.html")

        #db_mon_1.0v(vaux5)
        fig_DBC1v0_MD1Emu = plotlyEX.line( df_DBC1v0_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.0v(vaux5)", "name":"FPGA Side"})
        fig_DBC1v0_MD1Emu.update_layout(title='PPrEmu MD1: DBCurrent - 1.0V')
        fig_DBC1v0_MD1Emu.write_html("plotly_MD1EmuDBC1.0V_combined.html")

        fig_DBC1v0_MD2Emu = plotlyEX.line( df_DBC1v0_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.0v(vaux5)", "name":"FPGA Side"})
        fig_DBC1v0_MD2Emu.update_layout(title='PPrEmu MD2: DBCurrent - 1.0V')
        fig_DBC1v0_MD2Emu.write_html("plotly_MD2EmuDBC1.0V_combined.html")

        fig_DBC1v0_MD3Emu = plotlyEX.line( df_DBC1v0_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.0v(vaux5)", "name":"FPGA Side"})
        fig_DBC1v0_MD3Emu.update_layout(title='PPrEmu MD3: DBCurrent - 1.0V')
        fig_DBC1v0_MD3Emu.write_html("plotly_MD3EmuDBC1.0V_combined.html")

        fig_DBC1v0_MD4Emu = plotlyEX.line( df_DBC1v0_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.0v(vaux5)", "name":"FPGA Side"})
        fig_DBC1v0_MD4Emu.update_layout(title='PPrEmu MD4: DBCurrent - 1.0V')
        fig_DBC1v0_MD4Emu.write_html("plotly_MD4EmuDBC1.0V_combined.html")

        fig_DBC1v0_MD1Ppr = plotlyEX.line( df_DBC1v0_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.0v(vaux5)", "name":"FPGA Side"})
        fig_DBC1v0_MD1Ppr.update_layout(title='PPrPpr MD1: DBCurrent - 1.0V')
        fig_DBC1v0_MD1Ppr.write_html("plotly_MD1PprDBC1.0V_combined.html")

        fig_DBC1v0_MD2Ppr = plotlyEX.line( df_DBC1v0_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.0v(vaux5)", "name":"FPGA Side"})
        fig_DBC1v0_MD2Ppr.update_layout(title='PPrPpr MD2: DBCurrent - 1.0V')
        fig_DBC1v0_MD2Ppr.write_html("plotly_MD2PprDBC1.0V_combined.html")

        fig_DBC1v0_MD3Ppr = plotlyEX.line( df_DBC1v0_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.0v(vaux5)", "name":"FPGA Side"})
        fig_DBC1v0_MD3Ppr.update_layout(title='PPrPpr MD3: DBCurrent - 1.0V')
        fig_DBC1v0_MD3Ppr.write_html("plotly_MD3PprDBC1.0V_combined.html")

        fig_DBC1v0_MD4Ppr = plotlyEX.line( df_DBC1v0_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.0v(vaux5)", "name":"FPGA Side"})
        fig_DBC1v0_MD4Ppr.update_layout(title='PPrPpr MD4: DBCurrent - 1.0V')
        fig_DBC1v0_MD4Ppr.write_html("plotly_MD4PprDBC1.0V_combined.html")

        #db_mon_1.2v(vaux9)
        fig_DBC1v2_MD1Emu = plotlyEX.line( df_DBC1v2_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.2v(vaux9)", "name":"FPGA Side"})
        fig_DBC1v2_MD1Emu.update_layout(title='PPrEmu MD1: DBCurrent - 1.2V')
        fig_DBC1v2_MD1Emu.write_html("plotly_MD1EmuDBC1.2V_combined.html")

        fig_DBC1v2_MD2Emu = plotlyEX.line( df_DBC1v2_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.2v(vaux9)", "name":"FPGA Side"})
        fig_DBC1v2_MD2Emu.update_layout(title='PPrEmu MD2: DBCurrent - 1.2V')
        fig_DBC1v2_MD2Emu.write_html("plotly_MD2EmuDBC1.2V_combined.html")

        fig_DBC1v2_MD3Emu = plotlyEX.line( df_DBC1v2_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.2v(vaux9)", "name":"FPGA Side"})
        fig_DBC1v2_MD3Emu.update_layout(title='PPrEmu MD3: DBCurrent - 1.2V')
        fig_DBC1v2_MD3Emu.write_html("plotly_MD3EmuDBC1.2V_combined.html")

        fig_DBC1v2_MD4Emu = plotlyEX.line( df_DBC1v2_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.2v(vaux9)", "name":"FPGA Side"})
        fig_DBC1v2_MD4Emu.update_layout(title='PPrEmu MD4: DBCurrent - 1.2V')
        fig_DBC1v2_MD4Emu.write_html("plotly_MD4EmuDBC1.2V_combined.html")

        fig_DBC1v2_MD1Ppr = plotlyEX.line( df_DBC1v2_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.2v(vaux9)", "name":"FPGA Side"})
        fig_DBC1v2_MD1Ppr.update_layout(title='PPrPpr MD1: DBCurrent - 1.2V')
        fig_DBC1v2_MD1Ppr.write_html("plotly_MD1PprDBC1.2V_combined.html")

        fig_DBC1v2_MD2Ppr = plotlyEX.line( df_DBC1v2_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.2v(vaux9)", "name":"FPGA Side"})
        fig_DBC1v2_MD2Ppr.update_layout(title='PPrPpr MD2: DBCurrent - 1.2V')
        fig_DBC1v2_MD2Ppr.write_html("plotly_MD2PprDBC1.2V_combined.html")

        fig_DBC1v2_MD3Ppr = plotlyEX.line( df_DBC1v2_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.2v(vaux9)", "name":"FPGA Side"})
        fig_DBC1v2_MD3Ppr.update_layout(title='PPrPpr MD3: DBCurrent - 1.2V')
        fig_DBC1v2_MD3Ppr.write_html("plotly_MD3PprDBC1.2V_combined.html")

        fig_DBC1v2_MD4Ppr = plotlyEX.line( df_DBC1v2_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.2v(vaux9)", "name":"FPGA Side"})
        fig_DBC1v2_MD4Ppr.update_layout(title='PPrPpr MD4: DBCurrent - 1.2V')
        fig_DBC1v2_MD4Ppr.write_html("plotly_MD4PprDBC1.2V_combined.html")

        #db_mon_1.5v(vaux3)
        fig_DBC1v5_MD1Emu = plotlyEX.line( df_DBC1v5_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.5v(vaux3)", "name":"FPGA Side"})
        fig_DBC1v5_MD1Emu.update_layout(title='PPrEmu MD1: DBCurrent - 1.5V')
        fig_DBC1v5_MD1Emu.write_html("plotly_MD1EmuDBC1.5V_combined.html")

        fig_DBC1v5_MD2Emu = plotlyEX.line( df_DBC1v5_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.5v(vaux3)", "name":"FPGA Side"})
        fig_DBC1v5_MD2Emu.update_layout(title='PPrEmu MD2: DBCurrent - 1.5V')
        fig_DBC1v5_MD2Emu.write_html("plotly_MD2EmuDBC1.5V_combined.html")

        fig_DBC1v5_MD3Emu = plotlyEX.line( df_DBC1v5_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.5v(vaux3)", "name":"FPGA Side"})
        fig_DBC1v5_MD3Emu.update_layout(title='PPrEmu MD3: DBCurrent - 1.5V')
        fig_DBC1v5_MD3Emu.write_html("plotly_MD3EmuDBC1.5V_combined.html")

        fig_DBC1v5_MD4Emu = plotlyEX.line( df_DBC1v5_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.5v(vaux3)", "name":"FPGA Side"})
        fig_DBC1v5_MD4Emu.update_layout(title='PPrEmu MD4: DBCurrent - 1.5V')
        fig_DBC1v5_MD4Emu.write_html("plotly_MD4EmuDBC1.5V_combined.html")

        fig_DBC1v5_MD1Ppr = plotlyEX.line( df_DBC1v5_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.5v(vaux3)", "name":"FPGA Side"})
        fig_DBC1v5_MD1Ppr.update_layout(title='PPrPpr MD1: DBCurrent - 1.5V')
        fig_DBC1v5_MD1Ppr.write_html("plotly_MD1PprDBC1.5V_combined.html")

        fig_DBC1v5_MD2Ppr = plotlyEX.line( df_DBC1v5_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.5v(vaux3)", "name":"FPGA Side"})
        fig_DBC1v5_MD2Ppr.update_layout(title='PPrPpr MD2: DBCurrent - 1.5V')
        fig_DBC1v5_MD2Ppr.write_html("plotly_MD2PprDBC1.5V_combined.html")

        fig_DBC1v5_MD3Ppr = plotlyEX.line( df_DBC1v5_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.5v(vaux3)", "name":"FPGA Side"})
        fig_DBC1v5_MD3Ppr.update_layout(title='PPrPpr MD3: DBCurrent - 1.5V')
        fig_DBC1v5_MD3Ppr.write_html("plotly_MD3PprDBC1.5V_combined.html")

        fig_DBC1v5_MD4Ppr = plotlyEX.line( df_DBC1v5_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.5v(vaux3)", "name":"FPGA Side"})
        fig_DBC1v5_MD4Ppr.update_layout(title='PPrPpr MD4: DBCurrent - 1.5V')
        fig_DBC1v5_MD4Ppr.write_html("plotly_MD4PprDBC1.5V_combined.html")

        #db_mon_1.8v(vaux8)
        fig_DBC1v8_MD1Emu = plotlyEX.line( df_DBC1v8_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.8v(vaux8)", "name":"FPGA Side"})
        fig_DBC1v8_MD1Emu.update_layout(title='PPrEmu MD1: DBCurrent - 1.8V')
        fig_DBC1v8_MD1Emu.write_html("plotly_MD1EmuDBC1.8V_combined.html")

        fig_DBC1v8_MD2Emu = plotlyEX.line( df_DBC1v8_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.8v(vaux8)", "name":"FPGA Side"})
        fig_DBC1v8_MD2Emu.update_layout(title='PPrEmu MD2: DBCurrent - 1.8V')
        fig_DBC1v8_MD2Emu.write_html("plotly_MD2EmuDBC1.8V_combined.html")

        fig_DBC1v8_MD3Emu = plotlyEX.line( df_DBC1v8_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.8v(vaux8)", "name":"FPGA Side"})
        fig_DBC1v8_MD3Emu.update_layout(title='PPrEmu MD3: DBCurrent - 1.8V')
        fig_DBC1v8_MD3Emu.write_html("plotly_MD3EmuDBC1.8V_combined.html")

        fig_DBC1v8_MD4Emu = plotlyEX.line( df_DBC1v8_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.8v(vaux8)", "name":"FPGA Side"})
        fig_DBC1v8_MD4Emu.update_layout(title='PPrEmu MD4: DBCurrent - 1.8V')
        fig_DBC1v8_MD4Emu.write_html("plotly_MD4EmuDBC1.8V_combined.html")

        fig_DBC1v8_MD1Ppr = plotlyEX.line( df_DBC1v8_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.8v(vaux8)", "name":"FPGA Side"})
        fig_DBC1v8_MD1Ppr.update_layout(title='PPrPpr MD1: DBCurrent - 1.8V')
        fig_DBC1v8_MD1Ppr.write_html("plotly_MD1PprDBC1.8V_combined.html")

        fig_DBC1v8_MD2Ppr = plotlyEX.line( df_DBC1v8_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.8v(vaux8)", "name":"FPGA Side"})
        fig_DBC1v8_MD2Ppr.update_layout(title='PPrPpr MD2: DBCurrent - 1.8V')
        fig_DBC1v8_MD2Ppr.write_html("plotly_MD2PprDBC1.8V_combined.html")

        fig_DBC1v8_MD3Ppr = plotlyEX.line( df_DBC1v8_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.8v(vaux8)", "name":"FPGA Side"})
        fig_DBC1v8_MD3Ppr.update_layout(title='PPrPpr MD3: DBCurrent - 1.8V')
        fig_DBC1v8_MD3Ppr.write_html("plotly_MD3PprDBC1.8V_combined.html")

        fig_DBC1v8_MD4Ppr = plotlyEX.line( df_DBC1v8_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_1.8v(vaux8)", "name":"FPGA Side"})
        fig_DBC1v8_MD4Ppr.update_layout(title='PPrPpr MD4: DBCurrent - 1.8V')
        fig_DBC1v8_MD4Ppr.write_html("plotly_MD4PprDBC1.8V_combined.html")

        #db_mon_2.5v(vaux1)
        fig_DBC2v5_MD1Emu = plotlyEX.line( df_DBC2v5_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_2.5v(vaux1)", "name":"FPGA Side"})
        fig_DBC2v5_MD1Emu.update_layout(title='PPrEmu MD1: DBCurrent - 2.5V')
        fig_DBC2v5_MD1Emu.write_html("plotly_MD1EmuDBC2.5V_combined.html")

        fig_DBC2v5_MD2Emu = plotlyEX.line( df_DBC2v5_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_2.5v(vaux1)", "name":"FPGA Side"})
        fig_DBC2v5_MD2Emu.update_layout(title='PPrEmu MD2: DBCurrent - 2.5V')
        fig_DBC2v5_MD2Emu.write_html("plotly_MD2EmuDBC2.5V_combined.html")

        fig_DBC2v5_MD3Emu = plotlyEX.line( df_DBC2v5_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_2.5v(vaux1)", "name":"FPGA Side"})
        fig_DBC2v5_MD3Emu.update_layout(title='PPrEmu MD3: DBCurrent - 2.5V')
        fig_DBC2v5_MD3Emu.write_html("plotly_MD3EmuDBC2.5V_combined.html")

        fig_DBC2v5_MD4Emu = plotlyEX.line( df_DBC2v5_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_2.5v(vaux1)", "name":"FPGA Side"})
        fig_DBC2v5_MD4Emu.update_layout(title='PPrEmu MD4: DBCurrent - 2.5V')
        fig_DBC2v5_MD4Emu.write_html("plotly_MD4EmuDBC2.5V_combined.html")

        fig_DBC2v5_MD1Ppr = plotlyEX.line( df_DBC2v5_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_2.5v(vaux1)", "name":"FPGA Side"})
        fig_DBC2v5_MD1Ppr.update_layout(title='PPrPpr MD1: DBCurrent - 2.5V')
        fig_DBC2v5_MD1Ppr.write_html("plotly_MD1PprDBC2.5V_combined.html")

        fig_DBC2v5_MD2Ppr = plotlyEX.line( df_DBC2v5_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_2.5v(vaux1)", "name":"FPGA Side"})
        fig_DBC2v5_MD2Ppr.update_layout(title='PPrPpr MD2: DBCurrent - 2.5V')
        fig_DBC2v5_MD2Ppr.write_html("plotly_MD2PprDBC2.5V_combined.html")

        fig_DBC2v5_MD3Ppr = plotlyEX.line( df_DBC2v5_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_2.5v(vaux1)", "name":"FPGA Side"})
        fig_DBC2v5_MD3Ppr.update_layout(title='PPrPpr MD3: DBCurrent - 2.5V')
        fig_DBC2v5_MD3Ppr.write_html("plotly_MD3PprDBC2.5V_combined.html")

        fig_DBC2v5_MD4Ppr = plotlyEX.line( df_DBC2v5_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_2.5v(vaux1)", "name":"FPGA Side"})
        fig_DBC2v5_MD4Ppr.update_layout(title='PPrPpr MD4: DBCurrent - 2.5V')
        fig_DBC2v5_MD4Ppr.write_html("plotly_MD4PprDBC2.5V_combined.html")

        #db_mon_3.3v(vaux11)
        fig_DBC3v3_MD1Emu = plotlyEX.line( df_DBC3v3_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_3.3v(vaux11)", "name":"FPGA Side"})
        fig_DBC3v3_MD1Emu.update_layout(title='PPrEmu MD1: DBCurrent - 3.3V')
        fig_DBC3v3_MD1Emu.write_html("plotly_MD1EmuDBC3.3V_combined.html")

        fig_DBC3v3_MD2Emu = plotlyEX.line( df_DBC3v3_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_3.3v(vaux11)", "name":"FPGA Side"})
        fig_DBC3v3_MD2Emu.update_layout(title='PPrEmu MD2: DBCurrent - 3.3V')
        fig_DBC3v3_MD2Emu.write_html("plotly_MD2EmuDBC3.3V_combined.html")

        fig_DBC3v3_MD3Emu = plotlyEX.line( df_DBC3v3_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_3.3v(vaux11)", "name":"FPGA Side"})
        fig_DBC3v3_MD3Emu.update_layout(title='PPrEmu MD3: DBCurrent - 3.3V')
        fig_DBC3v3_MD3Emu.write_html("plotly_MD3EmuDBC3.3V_combined.html")

        fig_DBC3v3_MD4Emu = plotlyEX.line( df_DBC3v3_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_3.3v(vaux11)", "name":"FPGA Side"})
        fig_DBC3v3_MD4Emu.update_layout(title='PPrEmu MD4: DBCurrent - 3.3V')
        fig_DBC3v3_MD4Emu.write_html("plotly_MD4EmuDBC3.3V_combined.html")

        fig_DBC3v3_MD1Ppr = plotlyEX.line( df_DBC3v3_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_3.3v(vaux11)", "name":"FPGA Side"})
        fig_DBC3v3_MD1Ppr.update_layout(title='PPrPpr MD1: DBCurrent - 3.3V')
        fig_DBC3v3_MD1Ppr.write_html("plotly_MD1PprDBC3.3V_combined.html")

        fig_DBC3v3_MD2Ppr = plotlyEX.line( df_DBC3v3_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_3.3v(vaux11)", "name":"FPGA Side"})
        fig_DBC3v3_MD2Ppr.update_layout(title='PPrPpr MD2: DBCurrent - 3.3V')
        fig_DBC3v3_MD2Ppr.write_html("plotly_MD2PprDBC3.3V_combined.html")

        fig_DBC3v3_MD3Ppr = plotlyEX.line( df_DBC3v3_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_3.3v(vaux11)", "name":"FPGA Side"})
        fig_DBC3v3_MD3Ppr.update_layout(title='PPrPpr MD3: DBCurrent - 3.3V')
        fig_DBC3v3_MD3Ppr.write_html("plotly_MD3PprDBC3.3V_combined.html")

        fig_DBC3v3_MD4Ppr = plotlyEX.line( df_DBC3v3_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"db_mon_3.3v(vaux11)", "name":"FPGA Side"})
        fig_DBC3v3_MD4Ppr.update_layout(title='PPrPpr MD4: DBCurrent - 3.3V')
        fig_DBC3v3_MD4Ppr.write_html("plotly_MD4PprDBC3.3V_combined.html")

        # mb_mon_+5v(vaux10)
        fig_MBCP5v_MD1Emu = plotlyEX.line( df_MBCP5v_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_+5v(vaux10)", "name":"FPGA Side"})
        fig_MBCP5v_MD1Emu.update_layout(title='Emu MD1: MBCurrent - +5V')
        fig_MBCP5v_MD1Emu.write_html("plotly_MD1EmuMBCP5V_combined.html")

        fig_MBCP5v_MD2Emu = plotlyEX.line( df_MBCP5v_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_+5v(vaux10)", "name":"FPGA Side"})
        fig_MBCP5v_MD2Emu.update_layout(title='Emu MD2: MBCurrent - +5V')
        fig_MBCP5v_MD2Emu.write_html("plotly_MD2EmuMBCP5V_combined.html")

        fig_MBCP5v_MD3Emu = plotlyEX.line( df_MBCP5v_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_+5v(vaux10)", "name":"FPGA Side"})
        fig_MBCP5v_MD3Emu.update_layout(title='Emu MD3: MBCurrent - +5V')
        fig_MBCP5v_MD3Emu.write_html("plotly_MD3EmuMBCP5V_combined.html")

        fig_MBCP5v_MD4Emu = plotlyEX.line( df_MBCP5v_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_+5v(vaux10)", "name":"FPGA Side"})
        fig_MBCP5v_MD4Emu.update_layout(title='Emu MD4: MBCurrent - +5V')
        fig_MBCP5v_MD4Emu.write_html("plotly_MD4EmuMBCP5V_combined.html")

        fig_MBCP5v_MD1Ppr = plotlyEX.line( df_MBCP5v_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_+5v(vaux10)", "name":"FPGA Side"})
        fig_MBCP5v_MD1Ppr.update_layout(title='Ppr MD1: MBCurrent - +5V')
        fig_MBCP5v_MD1Ppr.write_html("plotly_MD1PprMBCP5V_combined.html")

        fig_MBCP5v_MD2Ppr = plotlyEX.line( df_MBCP5v_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_+5v(vaux10)", "name":"FPGA Side"})
        fig_MBCP5v_MD2Ppr.update_layout(title='Ppr MD2: MBCurrent - +5V')
        fig_MBCP5v_MD2Ppr.write_html("plotly_MD2PprMBCP5V_combined.html")

        fig_MBCP5v_MD3Ppr = plotlyEX.line( df_MBCP5v_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_+5v(vaux10)", "name":"FPGA Side"})
        fig_MBCP5v_MD3Ppr.update_layout(title='Ppr MD3: MBCurrent - +5V')
        fig_MBCP5v_MD3Ppr.write_html("plotly_MD3PprMBCP5V_combined.html")

        fig_MBCP5v_MD4Ppr = plotlyEX.line( df_MBCP5v_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_+5v(vaux10)", "name":"FPGA Side"})
        fig_MBCP5v_MD4Ppr.update_layout(title='Ppr MD4: MBCurrent - +5V')
        fig_MBCP5v_MD4Ppr.write_html("plotly_MD4PprMBCP5V_combined.html")

        #mb_mon_-5v(vaux7)
        fig_MBCN5v_MD1Emu = plotlyEX.line( df_MBCN5v_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_-5v(vaux7)", "name":"FPGA Side"})
        fig_MBCN5v_MD1Emu.update_layout(title='Emu MD1: MBCurrent - -5V')
        fig_MBCN5v_MD1Emu.write_html("plotly_MD1EmuMBCN5V_combined.html")

        fig_MBCN5v_MD2Emu = plotlyEX.line( df_MBCN5v_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_-5v(vaux7)", "name":"FPGA Side"})
        fig_MBCN5v_MD2Emu.update_layout(title='Emu MD2: MBCurrent - -5V')
        fig_MBCN5v_MD2Emu.write_html("plotly_MD2EmuMBCN5V_combined.html")

        fig_MBCN5v_MD3Emu = plotlyEX.line( df_MBCN5v_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_-5v(vaux7)", "name":"FPGA Side"})
        fig_MBCN5v_MD3Emu.update_layout(title='Emu MD3: MBCurrent - -5V')
        fig_MBCN5v_MD3Emu.write_html("plotly_MD3EmuMBCN5V_combined.html")

        fig_MBCN5v_MD4Emu = plotlyEX.line( df_MBCN5v_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_-5v(vaux7)", "name":"FPGA Side"})
        fig_MBCN5v_MD4Emu.update_layout(title='Emu MD4: MBCurrent - -5V')
        fig_MBCN5v_MD4Emu.write_html("plotly_MD4EmuMBCN5V_combined.html")

        fig_MBCN5v_MD1Ppr = plotlyEX.line( df_MBCN5v_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_-5v(vaux7)", "name":"FPGA Side"})
        fig_MBCN5v_MD1Ppr.update_layout(title='Ppr MD1: MBCurrent - -5V')
        fig_MBCN5v_MD1Ppr.write_html("plotly_MD1PprMBCN5V_combined.html")

        fig_MBCN5v_MD2Ppr = plotlyEX.line( df_MBCN5v_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_-5v(vaux7)", "name":"FPGA Side"})
        fig_MBCN5v_MD2Ppr.update_layout(title='Ppr MD2: MBCurrent - -5V')
        fig_MBCN5v_MD2Ppr.write_html("plotly_MD2PprMBCN5V_combined.html")

        fig_MBCN5v_MD3Ppr = plotlyEX.line( df_MBCN5v_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_-5v(vaux7)", "name":"FPGA Side"})
        fig_MBCN5v_MD3Ppr.update_layout(title='Ppr MD3: MBCurrent - -5V')
        fig_MBCN5v_MD3Ppr.write_html("plotly_MD3PprMBCN5V_combined.html")

        fig_MBCN5v_MD4Ppr = plotlyEX.line( df_MBCN5v_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_-5v(vaux7)", "name":"FPGA Side"})
        fig_MBCN5v_MD4Ppr.update_layout(title='Ppr MD4: MBCurrent - -5V')
        fig_MBCN5v_MD4Ppr.write_html("plotly_MD4PprMBCN5V_combined.html")

        #mb_mon_1.2v(vaux14)
        fig_MBC1v2_MD1Emu = plotlyEX.line( df_MBC1v2_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_1.2v(vaux14)", "name":"FPGA Side"})
        fig_MBC1v2_MD1Emu.update_layout(title='Emu MD1: MBCurrent - 1.2V')
        fig_MBC1v2_MD1Emu.write_html("plotly_MD1EmuMBC1V2_combined.html")

        fig_MBC1v2_MD2Emu = plotlyEX.line( df_MBC1v2_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_1.2v(vaux14)", "name":"FPGA Side"})
        fig_MBC1v2_MD2Emu.update_layout(title='Emu MD2: MBCurrent - 1.2V')
        fig_MBC1v2_MD2Emu.write_html("plotly_MD2EmuMBC1V2_combined.html")

        fig_MBC1v2_MD3Emu = plotlyEX.line( df_MBC1v2_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_1.2v(vaux14)", "name":"FPGA Side"})
        fig_MBC1v2_MD3Emu.update_layout(title='Emu MD3: MBCurrent - 1.2V')
        fig_MBC1v2_MD3Emu.write_html("plotly_MD3EmuMBC1V2_combined.html")

        fig_MBC1v2_MD4Emu = plotlyEX.line( df_MBC1v2_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_1.2v(vaux14)", "name":"FPGA Side"})
        fig_MBC1v2_MD4Emu.update_layout(title='Emu MD4: MBCurrent - 1.2V')
        fig_MBC1v2_MD4Emu.write_html("plotly_MD4EmuMBC1V2_combined.html")

        fig_MBC1v2_MD1Ppr = plotlyEX.line( df_MBC1v2_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_1.2v(vaux14)", "name":"FPGA Side"})
        fig_MBC1v2_MD1Ppr.update_layout(title='Ppr MD1: MBCurrent - 1.2V')
        fig_MBC1v2_MD1Ppr.write_html("plotly_MD1PprMBC1V2_combined.html")

        fig_MBC1v2_MD2Ppr = plotlyEX.line( df_MBC1v2_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_1.2v(vaux14)", "name":"FPGA Side"})
        fig_MBC1v2_MD2Ppr.update_layout(title='Ppr MD2: MBCurrent - 1.2V')
        fig_MBC1v2_MD2Ppr.write_html("plotly_MD2PprMBC1V2_combined.html")

        fig_MBC1v2_MD3Ppr = plotlyEX.line( df_MBC1v2_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_1.2v(vaux14)", "name":"FPGA Side"})
        fig_MBC1v2_MD3Ppr.update_layout(title='Ppr MD3: MBCurrent - 1.2V')
        fig_MBC1v2_MD3Ppr.write_html("plotly_MD3PprMBC1V2_combined.html")

        fig_MBC1v2_MD4Ppr = plotlyEX.line( df_MBC1v2_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_1.2v(vaux14)", "name":"FPGA Side"})
        fig_MBC1v2_MD4Ppr.update_layout(title='Ppr MD4: MBCurrent - 1.2V')
        fig_MBC1v2_MD4Ppr.write_html("plotly_MD4PprMBC1V2_combined.html")

        #mb_mon_1.8v(vaux12)
        fig_MBC1v8_MD1Emu = plotlyEX.line( df_MBC1v8_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_1.8v(vaux12)", "name":"FPGA Side"})
        fig_MBC1v8_MD1Emu.update_layout(title='Emu MD1: MBCurrent - 1.8V')
        fig_MBC1v8_MD1Emu.write_html("plotly_MD1EmuMBC1V8_combined.html")

        fig_MBC1v8_MD2Emu = plotlyEX.line( df_MBC1v8_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_1.8v(vaux12)", "name":"FPGA Side"})
        fig_MBC1v8_MD2Emu.update_layout(title='Emu MD2: MBCurrent - 1.8V')
        fig_MBC1v8_MD2Emu.write_html("plotly_MD2EmuMBC1V8_combined.html")

        fig_MBC1v8_MD3Emu = plotlyEX.line( df_MBC1v8_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_1.8v(vaux12)", "name":"FPGA Side"})
        fig_MBC1v8_MD3Emu.update_layout(title='Emu MD3: MBCurrent - 1.8V')
        fig_MBC1v8_MD3Emu.write_html("plotly_MD3EmuMBC1V8_combined.html")

        fig_MBC1v8_MD4Emu = plotlyEX.line( df_MBC1v8_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_1.8v(vaux12)", "name":"FPGA Side"})
        fig_MBC1v8_MD4Emu.update_layout(title='Emu MD4: MBCurrent - 1.8V')
        fig_MBC1v8_MD4Emu.write_html("plotly_MD4EmuMBC1V8_combined.html")

        fig_MBC1v8_MD1Ppr = plotlyEX.line( df_MBC1v8_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_1.8v(vaux12)", "name":"FPGA Side"})
        fig_MBC1v8_MD1Ppr.update_layout(title='Ppr MD1: MBCurrent - 1.8V')
        fig_MBC1v8_MD1Ppr.write_html("plotly_MD1PprMBC1V8_combined.html")

        fig_MBC1v8_MD2Ppr = plotlyEX.line( df_MBC1v8_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_1.8v(vaux12)", "name":"FPGA Side"})
        fig_MBC1v8_MD2Ppr.update_layout(title='Ppr MD2: MBCurrent - 1.8V')
        fig_MBC1v8_MD2Ppr.write_html("plotly_MD2PprMBC1V8_combined.html")

        fig_MBC1v8_MD3Ppr = plotlyEX.line( df_MBC1v8_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_1.8v(vaux12)", "name":"FPGA Side"})
        fig_MBC1v8_MD3Ppr.update_layout(title='Ppr MD3: MBCurrent - 1.8V')
        fig_MBC1v8_MD3Ppr.write_html("plotly_MD3PprMBC1V8_combined.html")

        fig_MBC1v8_MD4Ppr = plotlyEX.line( df_MBC1v8_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_1.8v(vaux12)", "name":"FPGA Side"})
        fig_MBC1v8_MD4Ppr.update_layout(title='Ppr MD4: MBCurrent - 1.8V')
        fig_MBC1v8_MD4Ppr.write_html("plotly_MD4PprMBC1V8_combined.html")

        #mb_mon_2.5v(vaux15)
        fig_MBC2v5_MD1Emu = plotlyEX.line( df_MBC2v5_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_2.5v(vaux15)", "name":"FPGA Side"})
        fig_MBC2v5_MD1Emu.update_layout(title='Emu MD1: MBCurrent - 2.5V')
        fig_MBC2v5_MD1Emu.write_html("plotly_MD1EmuMBC2V5_combined.html")

        fig_MBC2v5_MD2Emu = plotlyEX.line( df_MBC2v5_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_2.5v(vaux15)", "name":"FPGA Side"})
        fig_MBC2v5_MD2Emu.update_layout(title='Emu MD2: MBCurrent - 2.5V')
        fig_MBC2v5_MD2Emu.write_html("plotly_MD2EmuMBC2V5_combined.html")

        fig_MBC2v5_MD3Emu = plotlyEX.line( df_MBC2v5_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_2.5v(vaux15)", "name":"FPGA Side"})
        fig_MBC2v5_MD3Emu.update_layout(title='Emu MD3: MBCurrent - 2.5V')
        fig_MBC2v5_MD3Emu.write_html("plotly_MD3EmuMBC2V5_combined.html")

        fig_MBC2v5_MD4Emu = plotlyEX.line( df_MBC2v5_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_2.5v(vaux15)", "name":"FPGA Side"})
        fig_MBC2v5_MD4Emu.update_layout(title='Emu MD4: MBCurrent - 2.5V')
        fig_MBC2v5_MD4Emu.write_html("plotly_MD4EmuMBC2V5_combined.html")

        fig_MBC2v5_MD1Ppr = plotlyEX.line( df_MBC2v5_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_2.5v(vaux15)", "name":"FPGA Side"})
        fig_MBC2v5_MD1Ppr.update_layout(title='Ppr MD1: MBCurrent - 2.5V')
        fig_MBC2v5_MD1Ppr.write_html("plotly_MD1PprMBC2V5_combined.html")

        fig_MBC2v5_MD2Ppr = plotlyEX.line( df_MBC2v5_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_2.5v(vaux15)", "name":"FPGA Side"})
        fig_MBC2v5_MD2Ppr.update_layout(title='Ppr MD2: MBCurrent - 2.5V')
        fig_MBC2v5_MD2Ppr.write_html("plotly_MD2PprMBC2V5_combined.html")

        fig_MBC2v5_MD3Ppr = plotlyEX.line( df_MBC2v5_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_2.5v(vaux15)", "name":"FPGA Side"})
        fig_MBC2v5_MD3Ppr.update_layout(title='Ppr MD3: MBCurrent - 2.5V')
        fig_MBC2v5_MD3Ppr.write_html("plotly_MD3PprMBC2V5_combined.html")

        fig_MBC2v5_MD4Ppr = plotlyEX.line( df_MBC2v5_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"mb_mon_2.5v(vaux15)", "name":"FPGA Side"})
        fig_MBC2v5_MD4Ppr.update_layout(title='Ppr MD4: MBCurrent - 2.5V')
        fig_MBC2v5_MD4Ppr.write_html("plotly_MD4PprMBC2V5_combined.html")

        # max_temp
        fig_MAXTEMP_MD1Emu = plotlyEX.line( df_MAXTEMP_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"max_temp", "name":"FPGA Side"})
        fig_MAXTEMP_MD1Emu.update_layout(title="Emu MD1: maximum temperature")
        fig_MAXTEMP_MD1Emu.write_html("plotly_MD1EmuMAXTEMP_combined.html")

        fig_MAXTEMP_MD2Emu = plotlyEX.line( df_MAXTEMP_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"max_temp", "name":"FPGA Side"})
        fig_MAXTEMP_MD2Emu.update_layout(title="Emu MD2: maximum temperature")
        fig_MAXTEMP_MD2Emu.write_html("plotly_MD2EmuMAXTEMP_combined.html")

        fig_MAXTEMP_MD3Emu = plotlyEX.line( df_MAXTEMP_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"max_temp", "name":"FPGA Side"})
        fig_MAXTEMP_MD3Emu.update_layout(title="Emu MD3: maximum temperature")
        fig_MAXTEMP_MD3Emu.write_html("plotly_MD3EmuMAXTEMP_combined.html")

        fig_MAXTEMP_MD4Emu = plotlyEX.line( df_MAXTEMP_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"max_temp", "name":"FPGA Side"})
        fig_MAXTEMP_MD4Emu.update_layout(title="Emu MD4: maximum temperature")
        fig_MAXTEMP_MD4Emu.write_html("plotly_MD4EmuMAXTEMP_combined.html")

        fig_MAXTEMP_MD1Ppr = plotlyEX.line( df_MAXTEMP_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"max_temp", "name":"FPGA Side"})
        fig_MAXTEMP_MD1Ppr.update_layout(title="Ppr MD1: maximum temperature")
        fig_MAXTEMP_MD1Ppr.write_html("plotly_MD1PprMAXTEMP_combined.html")

        fig_MAXTEMP_MD2Ppr = plotlyEX.line( df_MAXTEMP_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"max_temp", "name":"FPGA Side"})
        fig_MAXTEMP_MD2Ppr.update_layout(title="Ppr MD2: maximum temperature")
        fig_MAXTEMP_MD2Ppr.write_html("plotly_MD2PprMAXTEMP_combined.html")

        fig_MAXTEMP_MD3Ppr = plotlyEX.line( df_MAXTEMP_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"max_temp", "name":"FPGA Side"})
        fig_MAXTEMP_MD3Ppr.update_layout(title="Ppr MD3: maximum temperature")
        fig_MAXTEMP_MD3Ppr.write_html("plotly_MD3PprMAXTEMP_combined.html")

        fig_MAXTEMP_MD4Ppr = plotlyEX.line( df_MAXTEMP_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"max_temp", "name":"FPGA Side"})
        fig_MAXTEMP_MD4Ppr.update_layout(title="Ppr MD4: maximum temperature")
        fig_MAXTEMP_MD4Ppr.write_html("plotly_MD4PprMAXTEMP_combined.html")

        # max_vccint
        fig_MAXVCCINT_MD1Emu = plotlyEX.line( df_MAXVCCINT_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"max_vccint", "name":"FPGA Side"})
        fig_MAXVCCINT_MD1Emu.update_layout(title="Emu MD1: max vccint")
        fig_MAXVCCINT_MD1Emu.write_html("plotly_MD1EmuMAXVCCINT_combined.html")

        fig_MAXVCCINT_MD2Emu = plotlyEX.line( df_MAXVCCINT_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"max_vccint", "name":"FPGA Side"})
        fig_MAXVCCINT_MD2Emu.update_layout(title="Emu MD2: max vccint")
        fig_MAXVCCINT_MD2Emu.write_html("plotly_MD2EmuMAXVCCINT_combined.html")

        fig_MAXVCCINT_MD3Emu = plotlyEX.line( df_MAXVCCINT_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"max_vccint", "name":"FPGA Side"})
        fig_MAXVCCINT_MD3Emu.update_layout(title="Emu MD3: max vccint")
        fig_MAXVCCINT_MD3Emu.write_html("plotly_MD3EmuMAXVCCINT_combined.html")

        fig_MAXVCCINT_MD4Emu = plotlyEX.line( df_MAXVCCINT_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"max_vccint", "name":"FPGA Side"})
        fig_MAXVCCINT_MD4Emu.update_layout(title="Emu MD4: max vccint")
        fig_MAXVCCINT_MD4Emu.write_html("plotly_MD4EmuMAXVCCINT_combined.html")

        fig_MAXVCCINT_MD1Ppr = plotlyEX.line( df_MAXVCCINT_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"max_vccint", "name":"FPGA Side"})
        fig_MAXVCCINT_MD1Ppr.update_layout(title="Ppr MD1: max vccint")
        fig_MAXVCCINT_MD1Ppr.write_html("plotly_MD1PprMAXVCCINT_combined.html")

        fig_MAXVCCINT_MD2Ppr = plotlyEX.line( df_MAXVCCINT_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"max_vccint", "name":"FPGA Side"})
        fig_MAXVCCINT_MD2Ppr.update_layout(title="Ppr MD2: max vccint")
        fig_MAXVCCINT_MD2Ppr.write_html("plotly_MD2PprMAXVCCINT_combined.html")

        fig_MAXVCCINT_MD3Ppr = plotlyEX.line( df_MAXVCCINT_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"max_vccint", "name":"FPGA Side"})
        fig_MAXVCCINT_MD3Ppr.update_layout(title="Ppr MD3: max vccint")
        fig_MAXVCCINT_MD3Ppr.write_html("plotly_MD3PprMAXVCCINT_combined.html")

        fig_MAXVCCINT_MD4Ppr = plotlyEX.line( df_MAXVCCINT_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"max_vccint", "name":"FPGA Side"})
        fig_MAXVCCINT_MD4Ppr.update_layout(title="Ppr MD4: max vccint")
        fig_MAXVCCINT_MD4Ppr.write_html("plotly_MD4PprMAXVCCINT_combined.html")

        # min_vccint
        fig_MINVCCINT_MD1Emu = plotlyEX.line( df_MINVCCINT_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"min_vccint", "name":"FPGA Side"})
        fig_MINVCCINT_MD1Emu.update_layout(title="Emu MD1: min vccint")
        fig_MINVCCINT_MD1Emu.write_html("plotly_MD1EmuMINVCCINT_combined.html")

        fig_MINVCCINT_MD2Emu = plotlyEX.line( df_MINVCCINT_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"min_vccint", "name":"FPGA Side"})
        fig_MINVCCINT_MD2Emu.update_layout(title="Emu MD2: min vccint")
        fig_MINVCCINT_MD2Emu.write_html("plotly_MD2EmuMINVCCINT_combined.html")

        fig_MINVCCINT_MD3Emu = plotlyEX.line( df_MINVCCINT_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"min_vccint", "name":"FPGA Side"})
        fig_MINVCCINT_MD3Emu.update_layout(title="Emu MD3: min vccint")
        fig_MINVCCINT_MD3Emu.write_html("plotly_MD3EmuMINVCCINT_combined.html")

        fig_MINVCCINT_MD4Emu = plotlyEX.line( df_MINVCCINT_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"min_vccint", "name":"FPGA Side"})
        fig_MINVCCINT_MD4Emu.update_layout(title="Emu MD4: min vccint")
        fig_MINVCCINT_MD4Emu.write_html("plotly_MD4EmuMINVCCINT_combined.html")

        fig_MINVCCINT_MD1Ppr = plotlyEX.line( df_MINVCCINT_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"min_vccint", "name":"FPGA Side"})
        fig_MINVCCINT_MD1Ppr.update_layout(title="Ppr MD1: min vccint")
        fig_MINVCCINT_MD1Ppr.write_html("plotly_MD1PprMINVCCINT_combined.html")

        fig_MINVCCINT_MD2Ppr = plotlyEX.line( df_MINVCCINT_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"min_vccint", "name":"FPGA Side"})
        fig_MINVCCINT_MD2Ppr.update_layout(title="Ppr MD2: min vccint")
        fig_MINVCCINT_MD2Ppr.write_html("plotly_MD2PprMINVCCINT_combined.html")

        fig_MINVCCINT_MD3Ppr = plotlyEX.line( df_MINVCCINT_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"min_vccint", "name":"FPGA Side"})
        fig_MINVCCINT_MD3Ppr.update_layout(title="Ppr MD3: min vccint")
        fig_MINVCCINT_MD3Ppr.write_html("plotly_MD3PprMINVCCINT_combined.html")

        fig_MINVCCINT_MD4Ppr = plotlyEX.line( df_MINVCCINT_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"min_vccint", "name":"FPGA Side"})
        fig_MINVCCINT_MD4Ppr.update_layout(title="Ppr MD4: min vccint")
        fig_MINVCCINT_MD4Ppr.write_html("plotly_MD4PprMINVCCINT_combined.html")

        # max_vccout
        fig_MAXVCCOUT_MD1Emu = plotlyEX.line( df_MAXVCCOUT_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"max_vccout", "name":"FPGA Side"})
        fig_MAXVCCOUT_MD1Emu.update_layout(title="Emu MD1: max vccout")
        fig_MAXVCCOUT_MD1Emu.write_html("plotly_MD1EmuMAXVCCOUT_combined.html")

        fig_MAXVCCOUT_MD2Emu = plotlyEX.line( df_MAXVCCOUT_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"max_vccout", "name":"FPGA Side"})
        fig_MAXVCCOUT_MD2Emu.update_layout(title="Emu MD2: max vccout")
        fig_MAXVCCOUT_MD2Emu.write_html("plotly_MD2EmuMAXVCCOUT_combined.html")

        fig_MAXVCCOUT_MD3Emu = plotlyEX.line( df_MAXVCCOUT_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"max_vccout", "name":"FPGA Side"})
        fig_MAXVCCOUT_MD3Emu.update_layout(title="Emu MD3: max vccout")
        fig_MAXVCCOUT_MD3Emu.write_html("plotly_MD3EmuMAXVCCOUT_combined.html")

        fig_MAXVCCOUT_MD4Emu = plotlyEX.line( df_MAXVCCOUT_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"max_vccout", "name":"FPGA Side"})
        fig_MAXVCCOUT_MD4Emu.update_layout(title="Emu MD4: max vccout")
        fig_MAXVCCOUT_MD4Emu.write_html("plotly_MD4EmuMAXVCCOUT_combined.html")

        fig_MAXVCCOUT_MD1Ppr = plotlyEX.line( df_MAXVCCOUT_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"max_vccout", "name":"FPGA Side"})
        fig_MAXVCCOUT_MD1Ppr.update_layout(title="Ppr MD1: max vccout")
        fig_MAXVCCOUT_MD1Ppr.write_html("plotly_MD1PprMAXVCCOUT_combined.html")

        fig_MAXVCCOUT_MD2Ppr = plotlyEX.line( df_MAXVCCOUT_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"max_vccout", "name":"FPGA Side"})
        fig_MAXVCCOUT_MD2Ppr.update_layout(title="Ppr MD2: max vccout")
        fig_MAXVCCOUT_MD2Ppr.write_html("plotly_MD2PprMAXVCCOUT_combined.html")

        fig_MAXVCCOUT_MD3Ppr = plotlyEX.line( df_MAXVCCOUT_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"max_vccout", "name":"FPGA Side"})
        fig_MAXVCCOUT_MD3Ppr.update_layout(title="Ppr MD3: max vccout")
        fig_MAXVCCOUT_MD3Ppr.write_html("plotly_MD3PprMAXVCCOUT_combined.html")

        fig_MAXVCCOUT_MD4Ppr = plotlyEX.line( df_MAXVCCOUT_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"max_vccout", "name":"FPGA Side"})
        fig_MAXVCCOUT_MD4Ppr.update_layout(title="Ppr MD4: max vccout")
        fig_MAXVCCOUT_MD4Ppr.write_html("plotly_MD4PprMAXVCCOUT_combined.html")

        # min_vccout
        fig_MINVCCOUT_MD1Emu = plotlyEX.line( df_MINVCCOUT_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"min_vccout", "name":"FPGA Side"})
        fig_MINVCCOUT_MD1Emu.update_layout(title="Emu MD1: min vccout")
        fig_MINVCCOUT_MD1Emu.write_html("plotly_MD1EmuMINVCCOUT_combined.html")

        fig_MINVCCOUT_MD2Emu = plotlyEX.line( df_MINVCCOUT_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"min_vccout", "name":"FPGA Side"})
        fig_MINVCCOUT_MD2Emu.update_layout(title="Emu MD2: min vccout")
        fig_MINVCCOUT_MD2Emu.write_html("plotly_MD2EmuMINVCCOUT_combined.html")

        fig_MINVCCOUT_MD3Emu = plotlyEX.line( df_MINVCCOUT_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"min_vccout", "name":"FPGA Side"})
        fig_MINVCCOUT_MD3Emu.update_layout(title="Emu MD3: min vccout")
        fig_MINVCCOUT_MD3Emu.write_html("plotly_MD3EmuMINVCCOUT_combined.html")

        fig_MINVCCOUT_MD4Emu = plotlyEX.line( df_MINVCCOUT_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"min_vccout", "name":"FPGA Side"})
        fig_MINVCCOUT_MD4Emu.update_layout(title="Emu MD4: min vccout")
        fig_MINVCCOUT_MD4Emu.write_html("plotly_MD4EmuMINVCCOUT_combined.html")

        fig_MINVCCOUT_MD1Ppr = plotlyEX.line( df_MINVCCOUT_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"min_vccout", "name":"FPGA Side"})
        fig_MINVCCOUT_MD1Ppr.update_layout(title="Ppr MD1: min vccout")
        fig_MINVCCOUT_MD1Ppr.write_html("plotly_MD1PprMINVCCOUT_combined.html")

        fig_MINVCCOUT_MD2Ppr = plotlyEX.line( df_MINVCCOUT_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"min_vccout", "name":"FPGA Side"})
        fig_MINVCCOUT_MD2Ppr.update_layout(title="Ppr MD2: min vccout")
        fig_MINVCCOUT_MD2Ppr.write_html("plotly_MD2PprMINVCCOUT_combined.html")

        fig_MINVCCOUT_MD3Ppr = plotlyEX.line( df_MINVCCOUT_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"min_vccout", "name":"FPGA Side"})
        fig_MINVCCOUT_MD3Ppr.update_layout(title="Ppr MD3: min vccout")
        fig_MINVCCOUT_MD3Ppr.write_html("plotly_MD3PprMINVCCOUT_combined.html")

        fig_MINVCCOUT_MD4Ppr = plotlyEX.line( df_MINVCCOUT_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"min_vccout", "name":"FPGA Side"})
        fig_MINVCCOUT_MD4Ppr.update_layout(title="Ppr MD4: min vccout")
        fig_MINVCCOUT_MD4Ppr.write_html("plotly_MD4PprMINVCCOUT_combined.html")

        # max_vram
        fig_MAX_VRAM_MD1Emu = plotlyEX.line( df_MAX_VRAM_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"max_vram", "name":"FPGA Side"})
        fig_MAX_VRAM_MD1Emu.update_layout(title="Emu MD1: max vram")
        fig_MAX_VRAM_MD1Emu.write_html("plotly_MD1EmuMAX_VRAM_combined.html")

        fig_MAX_VRAM_MD2Emu = plotlyEX.line( df_MAX_VRAM_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"max_vram", "name":"FPGA Side"})
        fig_MAX_VRAM_MD2Emu.update_layout(title="Emu MD2: max vram")
        fig_MAX_VRAM_MD2Emu.write_html("plotly_MD2EmuMAX_VRAM_combined.html")

        fig_MAX_VRAM_MD3Emu = plotlyEX.line( df_MAX_VRAM_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"max_vram", "name":"FPGA Side"})
        fig_MAX_VRAM_MD3Emu.update_layout(title="Emu MD3: max vram")
        fig_MAX_VRAM_MD3Emu.write_html("plotly_MD3EmuMAX_VRAM_combined.html")

        fig_MAX_VRAM_MD4Emu = plotlyEX.line( df_MAX_VRAM_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"max_vram", "name":"FPGA Side"})
        fig_MAX_VRAM_MD4Emu.update_layout(title="Emu MD4: max vram")
        fig_MAX_VRAM_MD4Emu.write_html("plotly_MD4EmuMAX_VRAM_combined.html")

        fig_MAX_VRAM_MD1Ppr = plotlyEX.line( df_MAX_VRAM_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"max_vram", "name":"FPGA Side"})
        fig_MAX_VRAM_MD1Ppr.update_layout(title="Ppr MD1: max vram")
        fig_MAX_VRAM_MD1Ppr.write_html("plotly_MD1PprMAX_VRAM_combined.html")

        fig_MAX_VRAM_MD2Ppr = plotlyEX.line( df_MAX_VRAM_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"max_vram", "name":"FPGA Side"})
        fig_MAX_VRAM_MD2Ppr.update_layout(title="Ppr MD2: max vram")
        fig_MAX_VRAM_MD2Ppr.write_html("plotly_MD2PprMAX_VRAM_combined.html")

        fig_MAX_VRAM_MD3Ppr = plotlyEX.line( df_MAX_VRAM_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"max_vram", "name":"FPGA Side"})
        fig_MAX_VRAM_MD3Ppr.update_layout(title="Ppr MD3: max vram")
        fig_MAX_VRAM_MD3Ppr.write_html("plotly_MD3PprMAX_VRAM_combined.html")

        fig_MAX_VRAM_MD4Ppr = plotlyEX.line( df_MAX_VRAM_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"max_vram", "name":"FPGA Side"})
        fig_MAX_VRAM_MD4Ppr.update_layout(title="Ppr MD4: max vram")
        fig_MAX_VRAM_MD4Ppr.write_html("plotly_MD4PprMAX_VRAM_combined.html")

        # min_vram
        fig_MIN_VRAM_MD1Emu = plotlyEX.line( df_MIN_VRAM_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"min_vram", "name":"FPGA Side"})
        fig_MIN_VRAM_MD1Emu.update_layout(title="Emu MD1: min vram")
        fig_MIN_VRAM_MD1Emu.write_html("plotly_MD1EmuMIN_VRAM_combined.html")

        fig_MIN_VRAM_MD2Emu = plotlyEX.line( df_MIN_VRAM_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"min_vram", "name":"FPGA Side"})
        fig_MIN_VRAM_MD2Emu.update_layout(title="Emu MD2: min vram")
        fig_MIN_VRAM_MD2Emu.write_html("plotly_MD2EmuMIN_VRAM_combined.html")

        fig_MIN_VRAM_MD3Emu = plotlyEX.line( df_MIN_VRAM_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"min_vram", "name":"FPGA Side"})
        fig_MIN_VRAM_MD3Emu.update_layout(title="Emu MD3: min vram")
        fig_MIN_VRAM_MD3Emu.write_html("plotly_MD3EmuMIN_VRAM_combined.html")

        fig_MIN_VRAM_MD4Emu = plotlyEX.line( df_MIN_VRAM_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"min_vram", "name":"FPGA Side"})
        fig_MIN_VRAM_MD4Emu.update_layout(title="Emu MD4: min vram")
        fig_MIN_VRAM_MD4Emu.write_html("plotly_MD4EmuMIN_VRAM_combined.html")

        fig_MIN_VRAM_MD1Ppr = plotlyEX.line( df_MIN_VRAM_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"min_vram", "name":"FPGA Side"})
        fig_MIN_VRAM_MD1Ppr.update_layout(title="Ppr MD1: min vram")
        fig_MIN_VRAM_MD1Ppr.write_html("plotly_MD1PprMIN_VRAM_combined.html")

        fig_MIN_VRAM_MD2Ppr = plotlyEX.line( df_MIN_VRAM_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"min_vram", "name":"FPGA Side"})
        fig_MIN_VRAM_MD2Ppr.update_layout(title="Ppr MD2: min vram")
        fig_MIN_VRAM_MD2Ppr.write_html("plotly_MD2PprMIN_VRAM_combined.html")

        fig_MIN_VRAM_MD3Ppr = plotlyEX.line( df_MIN_VRAM_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"min_vram", "name":"FPGA Side"})
        fig_MIN_VRAM_MD3Ppr.update_layout(title="Ppr MD3: min vram")
        fig_MIN_VRAM_MD3Ppr.write_html("plotly_MD3PprMIN_VRAM_combined.html")

        fig_MIN_VRAM_MD4Ppr = plotlyEX.line( df_MIN_VRAM_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"min_vram", "name":"FPGA Side"})
        fig_MIN_VRAM_MD4Ppr.update_layout(title="Ppr MD4: min vram")
        fig_MIN_VRAM_MD4Ppr.write_html("plotly_MD4PprMIN_VRAM_combined.html")

        # pgood_db_0v95
        fig_DBPGOOD0v95_MD1Emu = plotlyEX.line( df_DBPGOOD0v95_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_0v95", "name":"FPGA Side"})
        fig_DBPGOOD0v95_MD1Emu.update_layout(title="Emu MD1: pgood_db_0v95")
        fig_DBPGOOD0v95_MD1Emu.write_html("plotly_MD1EmuDBPGOOD0v95_combined.html")

        fig_DBPGOOD0v95_MD2Emu = plotlyEX.line( df_DBPGOOD0v95_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_0v95", "name":"FPGA Side"})
        fig_DBPGOOD0v95_MD2Emu.update_layout(title="Emu MD2: pgood_db_0v95")
        fig_DBPGOOD0v95_MD2Emu.write_html("plotly_MD2EmuDBPGOOD0v95_combined.html")

        fig_DBPGOOD0v95_MD3Emu = plotlyEX.line( df_DBPGOOD0v95_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_0v95", "name":"FPGA Side"})
        fig_DBPGOOD0v95_MD3Emu.update_layout(title="Emu MD3: pgood_db_0v95")
        fig_DBPGOOD0v95_MD3Emu.write_html("plotly_MD3EmuDBPGOOD0v95_combined.html")

        fig_DBPGOOD0v95_MD4Emu = plotlyEX.line( df_DBPGOOD0v95_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_0v95", "name":"FPGA Side"})
        fig_DBPGOOD0v95_MD4Emu.update_layout(title="Emu MD4: pgood_db_0v95")
        fig_DBPGOOD0v95_MD4Emu.write_html("plotly_MD4EmuDBPGOOD0v95_combined.html")

        fig_DBPGOOD0v95_MD1Ppr = plotlyEX.line( df_DBPGOOD0v95_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_0v95", "name":"FPGA Side"})
        fig_DBPGOOD0v95_MD1Ppr.update_layout(title="Ppr MD1: pgood_db_0v95")
        fig_DBPGOOD0v95_MD1Ppr.write_html("plotly_MD1PprDBPGOOD0v95_combined.html")

        fig_DBPGOOD0v95_MD2Ppr = plotlyEX.line( df_DBPGOOD0v95_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_0v95", "name":"FPGA Side"})
        fig_DBPGOOD0v95_MD2Ppr.update_layout(title="Ppr MD2: pgood_db_0v95")
        fig_DBPGOOD0v95_MD2Ppr.write_html("plotly_MD2PprDBPGOOD0v95_combined.html")

        fig_DBPGOOD0v95_MD3Ppr = plotlyEX.line( df_DBPGOOD0v95_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_0v95", "name":"FPGA Side"})
        fig_DBPGOOD0v95_MD3Ppr.update_layout(title="Ppr MD3: pgood_db_0v95")
        fig_DBPGOOD0v95_MD3Ppr.write_html("plotly_MD3PprDBPGOOD0v95_combined.html")

        fig_DBPGOOD0v95_MD4Ppr = plotlyEX.line( df_DBPGOOD0v95_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_0v95", "name":"FPGA Side"})
        fig_DBPGOOD0v95_MD4Ppr.update_layout(title="Ppr MD4: pgood_db_0v95")
        fig_DBPGOOD0v95_MD4Ppr.write_html("plotly_MD4PprDBPGOOD0v95_combined.html")

	# pgood_db_1v0
        fig_DBPGOOD1v0_MD1Emu = plotlyEX.line( df_DBPGOOD1v0_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v0", "name":"FPGA Side"})
        fig_DBPGOOD1v0_MD1Emu.update_layout(title="Emu MD1: pgood_db_1v0")
        fig_DBPGOOD1v0_MD1Emu.write_html("plotly_MD1EmuDBPGOOD1v0_combined.html")

        fig_DBPGOOD1v0_MD2Emu = plotlyEX.line( df_DBPGOOD1v0_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v0", "name":"FPGA Side"})
        fig_DBPGOOD1v0_MD2Emu.update_layout(title="Emu MD2: pgood_db_1v0")
        fig_DBPGOOD1v0_MD2Emu.write_html("plotly_MD2EmuDBPGOOD1v0_combined.html")

        fig_DBPGOOD1v0_MD3Emu = plotlyEX.line( df_DBPGOOD1v0_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v0", "name":"FPGA Side"})
        fig_DBPGOOD1v0_MD3Emu.update_layout(title="Emu MD3: pgood_db_1v0")
        fig_DBPGOOD1v0_MD3Emu.write_html("plotly_MD3EmuDBPGOOD1v0_combined.html")

        fig_DBPGOOD1v0_MD4Emu = plotlyEX.line( df_DBPGOOD1v0_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v0", "name":"FPGA Side"})
        fig_DBPGOOD1v0_MD4Emu.update_layout(title="Emu MD4: pgood_db_1v0")
        fig_DBPGOOD1v0_MD4Emu.write_html("plotly_MD4EmuDBPGOOD1v0_combined.html")

        fig_DBPGOOD1v0_MD1Ppr = plotlyEX.line( df_DBPGOOD1v0_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v0", "name":"FPGA Side"})
        fig_DBPGOOD1v0_MD1Ppr.update_layout(title="Ppr MD1: pgood_db_1v0")
        fig_DBPGOOD1v0_MD1Ppr.write_html("plotly_MD1PprDBPGOOD1v0_combined.html")

        fig_DBPGOOD1v0_MD2Ppr = plotlyEX.line( df_DBPGOOD1v0_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v0", "name":"FPGA Side"})
        fig_DBPGOOD1v0_MD2Ppr.update_layout(title="Ppr MD2: pgood_db_1v0")
        fig_DBPGOOD1v0_MD2Ppr.write_html("plotly_MD2PprDBPGOOD1v0_combined.html")

        fig_DBPGOOD1v0_MD3Ppr = plotlyEX.line( df_DBPGOOD1v0_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v0", "name":"FPGA Side"})
        fig_DBPGOOD1v0_MD3Ppr.update_layout(title="Ppr MD3: pgood_db_1v0")
        fig_DBPGOOD1v0_MD3Ppr.write_html("plotly_MD3PprDBPGOOD1v0_combined.html")

        fig_DBPGOOD1v0_MD4Ppr = plotlyEX.line( df_DBPGOOD1v0_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v0", "name":"FPGA Side"})
        fig_DBPGOOD1v0_MD4Ppr.update_layout(title="Ppr MD4: pgood_db_1v0")
        fig_DBPGOOD1v0_MD4Ppr.write_html("plotly_MD4PprDBPGOOD1v0_combined.html")

	# pgood_db_1v2
        fig_DBPGOOD1v2_MD1Emu = plotlyEX.line( df_DBPGOOD1v2_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v2", "name":"FPGA Side"})
        fig_DBPGOOD1v2_MD1Emu.update_layout(title="Emu MD1: pgood_db_1v2")
        fig_DBPGOOD1v2_MD1Emu.write_html("plotly_MD1EmuDBPGOOD1v2_combined.html")

        fig_DBPGOOD1v2_MD2Emu = plotlyEX.line( df_DBPGOOD1v2_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v2", "name":"FPGA Side"})
        fig_DBPGOOD1v2_MD2Emu.update_layout(title="Emu MD2: pgood_db_1v2")
        fig_DBPGOOD1v2_MD2Emu.write_html("plotly_MD2EmuDBPGOOD1v2_combined.html")

        fig_DBPGOOD1v2_MD3Emu = plotlyEX.line( df_DBPGOOD1v2_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v2", "name":"FPGA Side"})
        fig_DBPGOOD1v2_MD3Emu.update_layout(title="Emu MD3: pgood_db_1v2")
        fig_DBPGOOD1v2_MD3Emu.write_html("plotly_MD3EmuDBPGOOD1v2_combined.html")

        fig_DBPGOOD1v2_MD4Emu = plotlyEX.line( df_DBPGOOD1v2_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v2", "name":"FPGA Side"})
        fig_DBPGOOD1v2_MD4Emu.update_layout(title="Emu MD4: pgood_db_1v2")
        fig_DBPGOOD1v2_MD4Emu.write_html("plotly_MD4EmuDBPGOOD1v2_combined.html")

        fig_DBPGOOD1v2_MD1Ppr = plotlyEX.line( df_DBPGOOD1v2_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v2", "name":"FPGA Side"})
        fig_DBPGOOD1v2_MD1Ppr.update_layout(title="Ppr MD1: pgood_db_1v2")
        fig_DBPGOOD1v2_MD1Ppr.write_html("plotly_MD1PprDBPGOOD1v2_combined.html")

        fig_DBPGOOD1v2_MD2Ppr = plotlyEX.line( df_DBPGOOD1v2_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v2", "name":"FPGA Side"})
        fig_DBPGOOD1v2_MD2Ppr.update_layout(title="Ppr MD2: pgood_db_1v2")
        fig_DBPGOOD1v2_MD2Ppr.write_html("plotly_MD2PprDBPGOOD1v2_combined.html")

        fig_DBPGOOD1v2_MD3Ppr = plotlyEX.line( df_DBPGOOD1v2_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v2", "name":"FPGA Side"})
        fig_DBPGOOD1v2_MD3Ppr.update_layout(title="Ppr MD3: pgood_db_1v2")
        fig_DBPGOOD1v2_MD3Ppr.write_html("plotly_MD3PprDBPGOOD1v2_combined.html")

        fig_DBPGOOD1v2_MD4Ppr = plotlyEX.line( df_DBPGOOD1v2_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v2", "name":"FPGA Side"})
        fig_DBPGOOD1v2_MD4Ppr.update_layout(title="Ppr MD4: pgood_db_1v2")
        fig_DBPGOOD1v2_MD4Ppr.write_html("plotly_MD4PprDBPGOOD1v2_combined.html")

	# pgood_db_1v5
        fig_DBPGOOD1v5_MD1Emu = plotlyEX.line( df_DBPGOOD1v5_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v5", "name":"FPGA Side"})
        fig_DBPGOOD1v5_MD1Emu.update_layout(title="Emu MD1: pgood_db_1v5")
        fig_DBPGOOD1v5_MD1Emu.write_html("plotly_MD1EmuDBPGOOD1v5_combined.html")

        fig_DBPGOOD1v5_MD2Emu = plotlyEX.line( df_DBPGOOD1v5_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v5", "name":"FPGA Side"})
        fig_DBPGOOD1v5_MD2Emu.update_layout(title="Emu MD2: pgood_db_1v5")
        fig_DBPGOOD1v5_MD2Emu.write_html("plotly_MD2EmuDBPGOOD1v5_combined.html")

        fig_DBPGOOD1v5_MD3Emu = plotlyEX.line( df_DBPGOOD1v5_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v5", "name":"FPGA Side"})
        fig_DBPGOOD1v5_MD3Emu.update_layout(title="Emu MD3: pgood_db_1v5")
        fig_DBPGOOD1v5_MD3Emu.write_html("plotly_MD3EmuDBPGOOD1v5_combined.html")

        fig_DBPGOOD1v5_MD4Emu = plotlyEX.line( df_DBPGOOD1v5_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v5", "name":"FPGA Side"})
        fig_DBPGOOD1v5_MD4Emu.update_layout(title="Emu MD4: pgood_db_1v5")
        fig_DBPGOOD1v5_MD4Emu.write_html("plotly_MD4EmuDBPGOOD1v5_combined.html")

        fig_DBPGOOD1v5_MD1Ppr = plotlyEX.line( df_DBPGOOD1v5_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v5", "name":"FPGA Side"})
        fig_DBPGOOD1v5_MD1Ppr.update_layout(title="Ppr MD1: pgood_db_1v5")
        fig_DBPGOOD1v5_MD1Ppr.write_html("plotly_MD1PprDBPGOOD1v5_combined.html")

        fig_DBPGOOD1v5_MD2Ppr = plotlyEX.line( df_DBPGOOD1v5_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v5", "name":"FPGA Side"})
        fig_DBPGOOD1v5_MD2Ppr.update_layout(title="Ppr MD2: pgood_db_1v5")
        fig_DBPGOOD1v5_MD2Ppr.write_html("plotly_MD2PprDBPGOOD1v5_combined.html")

        fig_DBPGOOD1v5_MD3Ppr = plotlyEX.line( df_DBPGOOD1v5_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v5", "name":"FPGA Side"})
        fig_DBPGOOD1v5_MD3Ppr.update_layout(title="Ppr MD3: pgood_db_1v5")
        fig_DBPGOOD1v5_MD3Ppr.write_html("plotly_MD3PprDBPGOOD1v5_combined.html")

        fig_DBPGOOD1v5_MD4Ppr = plotlyEX.line( df_DBPGOOD1v5_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v5", "name":"FPGA Side"})
        fig_DBPGOOD1v5_MD4Ppr.update_layout(title="Ppr MD4: pgood_db_1v5")
        fig_DBPGOOD1v5_MD4Ppr.write_html("plotly_MD4PprDBPGOOD1v5_combined.html")

	# pgood_db_1v8
        fig_DBPGOOD1v8_MD1Emu = plotlyEX.line( df_DBPGOOD1v8_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v8", "name":"FPGA Side"})
        fig_DBPGOOD1v8_MD1Emu.update_layout(title="Emu MD1: pgood_db_1v8")
        fig_DBPGOOD1v8_MD1Emu.write_html("plotly_MD1EmuDBPGOOD1v8_combined.html")

        fig_DBPGOOD1v8_MD2Emu = plotlyEX.line( df_DBPGOOD1v8_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v8", "name":"FPGA Side"})
        fig_DBPGOOD1v8_MD2Emu.update_layout(title="Emu MD2: pgood_db_1v8")
        fig_DBPGOOD1v8_MD2Emu.write_html("plotly_MD2EmuDBPGOOD1v8_combined.html")

        fig_DBPGOOD1v8_MD3Emu = plotlyEX.line( df_DBPGOOD1v8_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v8", "name":"FPGA Side"})
        fig_DBPGOOD1v8_MD3Emu.update_layout(title="Emu MD3: pgood_db_1v8")
        fig_DBPGOOD1v8_MD3Emu.write_html("plotly_MD3EmuDBPGOOD1v8_combined.html")

        fig_DBPGOOD1v8_MD4Emu = plotlyEX.line( df_DBPGOOD1v8_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v8", "name":"FPGA Side"})
        fig_DBPGOOD1v8_MD4Emu.update_layout(title="Emu MD4: pgood_db_1v8")
        fig_DBPGOOD1v8_MD4Emu.write_html("plotly_MD4EmuDBPGOOD1v8_combined.html")

        fig_DBPGOOD1v8_MD1Ppr = plotlyEX.line( df_DBPGOOD1v8_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v8", "name":"FPGA Side"})
        fig_DBPGOOD1v8_MD1Ppr.update_layout(title="Ppr MD1: pgood_db_1v8")
        fig_DBPGOOD1v8_MD1Ppr.write_html("plotly_MD1PprDBPGOOD1v8_combined.html")

        fig_DBPGOOD1v8_MD2Ppr = plotlyEX.line( df_DBPGOOD1v8_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v8", "name":"FPGA Side"})
        fig_DBPGOOD1v8_MD2Ppr.update_layout(title="Ppr MD2: pgood_db_1v8")
        fig_DBPGOOD1v8_MD2Ppr.write_html("plotly_MD2PprDBPGOOD1v8_combined.html")

        fig_DBPGOOD1v8_MD3Ppr = plotlyEX.line( df_DBPGOOD1v8_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v8", "name":"FPGA Side"})
        fig_DBPGOOD1v8_MD3Ppr.update_layout(title="Ppr MD3: pgood_db_1v8")
        fig_DBPGOOD1v8_MD3Ppr.write_html("plotly_MD3PprDBPGOOD1v8_combined.html")

        fig_DBPGOOD1v8_MD4Ppr = plotlyEX.line( df_DBPGOOD1v8_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_1v8", "name":"FPGA Side"})
        fig_DBPGOOD1v8_MD4Ppr.update_layout(title="Ppr MD4: pgood_db_1v8")
        fig_DBPGOOD1v8_MD4Ppr.write_html("plotly_MD4PprDBPGOOD1v8_combined.html")

	# pgood_db_2v5
        fig_DBPGOOD2v5_MD1Emu = plotlyEX.line( df_DBPGOOD2v5_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_2v5", "name":"FPGA Side"})
        fig_DBPGOOD2v5_MD1Emu.update_layout(title="Emu MD1: pgood_db_2v5")
        fig_DBPGOOD2v5_MD1Emu.write_html("plotly_MD1EmuDBPGOOD2v5_combined.html")

        fig_DBPGOOD2v5_MD2Emu = plotlyEX.line( df_DBPGOOD2v5_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_2v5", "name":"FPGA Side"})
        fig_DBPGOOD2v5_MD2Emu.update_layout(title="Emu MD2: pgood_db_2v5")
        fig_DBPGOOD2v5_MD2Emu.write_html("plotly_MD2EmuDBPGOOD2v5_combined.html")

        fig_DBPGOOD2v5_MD3Emu = plotlyEX.line( df_DBPGOOD2v5_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_2v5", "name":"FPGA Side"})
        fig_DBPGOOD2v5_MD3Emu.update_layout(title="Emu MD3: pgood_db_2v5")
        fig_DBPGOOD2v5_MD3Emu.write_html("plotly_MD3EmuDBPGOOD2v5_combined.html")

        fig_DBPGOOD2v5_MD4Emu = plotlyEX.line( df_DBPGOOD2v5_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_2v5", "name":"FPGA Side"})
        fig_DBPGOOD2v5_MD4Emu.update_layout(title="Emu MD4: pgood_db_2v5")
        fig_DBPGOOD2v5_MD4Emu.write_html("plotly_MD4EmuDBPGOOD2v5_combined.html")

        fig_DBPGOOD2v5_MD1Ppr = plotlyEX.line( df_DBPGOOD2v5_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_2v5", "name":"FPGA Side"})
        fig_DBPGOOD2v5_MD1Ppr.update_layout(title="Ppr MD1: pgood_db_2v5")
        fig_DBPGOOD2v5_MD1Ppr.write_html("plotly_MD1PprDBPGOOD2v5_combined.html")

        fig_DBPGOOD2v5_MD2Ppr = plotlyEX.line( df_DBPGOOD2v5_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_2v5", "name":"FPGA Side"})
        fig_DBPGOOD2v5_MD2Ppr.update_layout(title="Ppr MD2: pgood_db_2v5")
        fig_DBPGOOD2v5_MD2Ppr.write_html("plotly_MD2PprDBPGOOD2v5_combined.html")

        fig_DBPGOOD2v5_MD3Ppr = plotlyEX.line( df_DBPGOOD2v5_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_2v5", "name":"FPGA Side"})
        fig_DBPGOOD2v5_MD3Ppr.update_layout(title="Ppr MD3: pgood_db_2v5")
        fig_DBPGOOD2v5_MD3Ppr.write_html("plotly_MD3PprDBPGOOD2v5_combined.html")

        fig_DBPGOOD2v5_MD4Ppr = plotlyEX.line( df_DBPGOOD2v5_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_2v5", "name":"FPGA Side"})
        fig_DBPGOOD2v5_MD4Ppr.update_layout(title="Ppr MD4: pgood_db_2v5")
        fig_DBPGOOD2v5_MD4Ppr.write_html("plotly_MD4PprDBPGOOD2v5_combined.html")

	# pgood_db_3v3
        fig_DBPGOOD3v3_MD1Emu = plotlyEX.line( df_DBPGOOD3v3_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_3v3", "name":"FPGA Side"})
        fig_DBPGOOD3v3_MD1Emu.update_layout(title="Emu MD1: pgood_db_3v3")
        fig_DBPGOOD3v3_MD1Emu.write_html("plotly_MD1EmuDBPGOOD3v3_combined.html")

        fig_DBPGOOD3v3_MD2Emu = plotlyEX.line( df_DBPGOOD3v3_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_3v3", "name":"FPGA Side"})
        fig_DBPGOOD3v3_MD2Emu.update_layout(title="Emu MD2: pgood_db_3v3")
        fig_DBPGOOD3v3_MD2Emu.write_html("plotly_MD2EmuDBPGOOD3v3_combined.html")

        fig_DBPGOOD3v3_MD3Emu = plotlyEX.line( df_DBPGOOD3v3_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_3v3", "name":"FPGA Side"})
        fig_DBPGOOD3v3_MD3Emu.update_layout(title="Emu MD3: pgood_db_3v3")
        fig_DBPGOOD3v3_MD3Emu.write_html("plotly_MD3EmuDBPGOOD3v3_combined.html")

        fig_DBPGOOD3v3_MD4Emu = plotlyEX.line( df_DBPGOOD3v3_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_3v3", "name":"FPGA Side"})
        fig_DBPGOOD3v3_MD4Emu.update_layout(title="Emu MD4: pgood_db_3v3")
        fig_DBPGOOD3v3_MD4Emu.write_html("plotly_MD4EmuDBPGOOD3v3_combined.html")

        fig_DBPGOOD3v3_MD1Ppr = plotlyEX.line( df_DBPGOOD3v3_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_3v3", "name":"FPGA Side"})
        fig_DBPGOOD3v3_MD1Ppr.update_layout(title="Ppr MD1: pgood_db_3v3")
        fig_DBPGOOD3v3_MD1Ppr.write_html("plotly_MD1PprDBPGOOD3v3_combined.html")

        fig_DBPGOOD3v3_MD2Ppr = plotlyEX.line( df_DBPGOOD3v3_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_3v3", "name":"FPGA Side"})
        fig_DBPGOOD3v3_MD2Ppr.update_layout(title="Ppr MD2: pgood_db_3v3")
        fig_DBPGOOD3v3_MD2Ppr.write_html("plotly_MD2PprDBPGOOD3v3_combined.html")

        fig_DBPGOOD3v3_MD3Ppr = plotlyEX.line( df_DBPGOOD3v3_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_3v3", "name":"FPGA Side"})
        fig_DBPGOOD3v3_MD3Ppr.update_layout(title="Ppr MD3: pgood_db_3v3")
        fig_DBPGOOD3v3_MD3Ppr.write_html("plotly_MD3PprDBPGOOD3v3_combined.html")

        fig_DBPGOOD3v3_MD4Ppr = plotlyEX.line( df_DBPGOOD3v3_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_db_3v3", "name":"FPGA Side"})
        fig_DBPGOOD3v3_MD4Ppr.update_layout(title="Ppr MD4: pgood_db_3v3")
        fig_DBPGOOD3v3_MD4Ppr.write_html("plotly_MD4PprDBPGOOD3v3_combined.html")

	# pgood_mb_5v0
        fig_MBPGOODP5v_MD1Emu = plotlyEX.line( df_MBPGOODP5v_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_5v0", "name":"FPGA Side"})
        fig_MBPGOODP5v_MD1Emu.update_layout(title="Emu MD1: pgood_mb_P5v")
        fig_MBPGOODP5v_MD1Emu.write_html("plotly_MD1EmuMBPGOODP5v_combined.html")

        fig_MBPGOODP5v_MD2Emu = plotlyEX.line( df_MBPGOODP5v_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_5v0", "name":"FPGA Side"})
        fig_MBPGOODP5v_MD2Emu.update_layout(title="Emu MD2: pgood_mb_P5v")
        fig_MBPGOODP5v_MD2Emu.write_html("plotly_MD2EmuMBPGOODP5v_combined.html")

        fig_MBPGOODP5v_MD3Emu = plotlyEX.line( df_MBPGOODP5v_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_5v0", "name":"FPGA Side"})
        fig_MBPGOODP5v_MD3Emu.update_layout(title="Emu MD3: pgood_mb_P5v")
        fig_MBPGOODP5v_MD3Emu.write_html("plotly_MD3EmuMBPGOODP5v_combined.html")

        fig_MBPGOODP5v_MD4Emu = plotlyEX.line( df_MBPGOODP5v_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_5v0", "name":"FPGA Side"})
        fig_MBPGOODP5v_MD4Emu.update_layout(title="Emu MD4: pgood_mb_P5v")
        fig_MBPGOODP5v_MD4Emu.write_html("plotly_MD4EmuMBPGOODP5v_combined.html")

        fig_MBPGOODP5v_MD1Ppr = plotlyEX.line( df_MBPGOODP5v_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_5v0", "name":"FPGA Side"})
        fig_MBPGOODP5v_MD1Ppr.update_layout(title="Ppr MD1: pgood_mb_P5v")
        fig_MBPGOODP5v_MD1Ppr.write_html("plotly_MD1PprMBPGOODP5v_combined.html")

        fig_MBPGOODP5v_MD2Ppr = plotlyEX.line( df_MBPGOODP5v_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_5v0", "name":"FPGA Side"})
        fig_MBPGOODP5v_MD2Ppr.update_layout(title="Ppr MD2: pgood_mb_P5v")
        fig_MBPGOODP5v_MD2Ppr.write_html("plotly_MD2PprMBPGOODP5v_combined.html")

        fig_MBPGOODP5v_MD3Ppr = plotlyEX.line( df_MBPGOODP5v_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_5v0", "name":"FPGA Side"})
        fig_MBPGOODP5v_MD3Ppr.update_layout(title="Ppr MD3: pgood_mb_P5v")
        fig_MBPGOODP5v_MD3Ppr.write_html("plotly_MD3PprMBPGOODP5v_combined.html")

        fig_MBPGOODP5v_MD4Ppr = plotlyEX.line( df_MBPGOODP5v_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_5v0", "name":"FPGA Side"})
        fig_MBPGOODP5v_MD4Ppr.update_layout(title="Ppr MD4: pgood_mb_P5v")
        fig_MBPGOODP5v_MD4Ppr.write_html("plotly_MD4PprMBPGOODP5v_combined.html")

	# pgood_mb_5v0_n
        fig_MBPGOODN5v_MD1Emu = plotlyEX.line( df_MBPGOODN5v_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_5v0_n", "name":"FPGA Side"})
        fig_MBPGOODN5v_MD1Emu.update_layout(title="Emu MD1: pgood_mb_N5v")
        fig_MBPGOODN5v_MD1Emu.write_html("plotly_MD1EmuMBPGOODN5v_combined.html")

        fig_MBPGOODN5v_MD2Emu = plotlyEX.line( df_MBPGOODN5v_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_5v0_n", "name":"FPGA Side"})
        fig_MBPGOODN5v_MD2Emu.update_layout(title="Emu MD2: pgood_mb_N5v")
        fig_MBPGOODN5v_MD2Emu.write_html("plotly_MD2EmuMBPGOODN5v_combined.html")

        fig_MBPGOODN5v_MD3Emu = plotlyEX.line( df_MBPGOODN5v_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_5v0_n", "name":"FPGA Side"})
        fig_MBPGOODN5v_MD3Emu.update_layout(title="Emu MD3: pgood_mb_N5v")
        fig_MBPGOODN5v_MD3Emu.write_html("plotly_MD3EmuMBPGOODN5v_combined.html")

        fig_MBPGOODN5v_MD4Emu = plotlyEX.line( df_MBPGOODN5v_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_5v0_n", "name":"FPGA Side"})
        fig_MBPGOODN5v_MD4Emu.update_layout(title="Emu MD4: pgood_mb_N5v")
        fig_MBPGOODN5v_MD4Emu.write_html("plotly_MD4EmuMBPGOODN5v_combined.html")

        fig_MBPGOODN5v_MD1Ppr = plotlyEX.line( df_MBPGOODN5v_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_5v0_n", "name":"FPGA Side"})
        fig_MBPGOODN5v_MD1Ppr.update_layout(title="Ppr MD1: pgood_mb_N5v")
        fig_MBPGOODN5v_MD1Ppr.write_html("plotly_MD1PprMBPGOODN5v_combined.html")

        fig_MBPGOODN5v_MD2Ppr = plotlyEX.line( df_MBPGOODN5v_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_5v0_n", "name":"FPGA Side"})
        fig_MBPGOODN5v_MD2Ppr.update_layout(title="Ppr MD2: pgood_mb_N5v")
        fig_MBPGOODN5v_MD2Ppr.write_html("plotly_MD2PprMBPGOODN5v_combined.html")

        fig_MBPGOODN5v_MD3Ppr = plotlyEX.line( df_MBPGOODN5v_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_5v0_n", "name":"FPGA Side"})
        fig_MBPGOODN5v_MD3Ppr.update_layout(title="Ppr MD3: pgood_mb_N5v")
        fig_MBPGOODN5v_MD3Ppr.write_html("plotly_MD3PprMBPGOODN5v_combined.html")

        fig_MBPGOODN5v_MD4Ppr = plotlyEX.line( df_MBPGOODN5v_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_5v0_n", "name":"FPGA Side"})
        fig_MBPGOODN5v_MD4Ppr.update_layout(title="Ppr MD4: pgood_mb_N5v")
        fig_MBPGOODN5v_MD4Ppr.write_html("plotly_MD4PprMBPGOODN5v_combined.html")

	# pgood_mb_1v2
        fig_MBPGOOD1v2_MD1Emu = plotlyEX.line( df_MBPGOOD1v2_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_1v2", "name":"FPGA Side"})
        fig_MBPGOOD1v2_MD1Emu.update_layout(title="Emu MD1: pgood_mb_1v2")
        fig_MBPGOOD1v2_MD1Emu.write_html("plotly_MD1EmuMBPGOOD1v2_combined.html")

        fig_MBPGOOD1v2_MD2Emu = plotlyEX.line( df_MBPGOOD1v2_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_1v2", "name":"FPGA Side"})
        fig_MBPGOOD1v2_MD2Emu.update_layout(title="Emu MD2: pgood_mb_1v2")
        fig_MBPGOOD1v2_MD2Emu.write_html("plotly_MD2EmuMBPGOOD1v2_combined.html")

        fig_MBPGOOD1v2_MD3Emu = plotlyEX.line( df_MBPGOOD1v2_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_1v2", "name":"FPGA Side"})
        fig_MBPGOOD1v2_MD3Emu.update_layout(title="Emu MD3: pgood_mb_1v2")
        fig_MBPGOOD1v2_MD3Emu.write_html("plotly_MD3EmuMBPGOOD1v2_combined.html")

        fig_MBPGOOD1v2_MD4Emu = plotlyEX.line( df_MBPGOOD1v2_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_1v2", "name":"FPGA Side"})
        fig_MBPGOOD1v2_MD4Emu.update_layout(title="Emu MD4: pgood_mb_1v2")
        fig_MBPGOOD1v2_MD4Emu.write_html("plotly_MD4EmuMBPGOOD1v2_combined.html")

        fig_MBPGOOD1v2_MD1Ppr = plotlyEX.line( df_MBPGOOD1v2_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_1v2", "name":"FPGA Side"})
        fig_MBPGOOD1v2_MD1Ppr.update_layout(title="Ppr MD1: pgood_mb_1v2")
        fig_MBPGOOD1v2_MD1Ppr.write_html("plotly_MD1PprMBPGOOD1v2_combined.html")

        fig_MBPGOOD1v2_MD2Ppr = plotlyEX.line( df_MBPGOOD1v2_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_1v2", "name":"FPGA Side"})
        fig_MBPGOOD1v2_MD2Ppr.update_layout(title="Ppr MD2: pgood_mb_1v2")
        fig_MBPGOOD1v2_MD2Ppr.write_html("plotly_MD2PprMBPGOOD1v2_combined.html")

        fig_MBPGOOD1v2_MD3Ppr = plotlyEX.line( df_MBPGOOD1v2_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_1v2", "name":"FPGA Side"})
        fig_MBPGOOD1v2_MD3Ppr.update_layout(title="Ppr MD3: pgood_mb_1v2")
        fig_MBPGOOD1v2_MD3Ppr.write_html("plotly_MD3PprMBPGOOD1v2_combined.html")

        fig_MBPGOOD1v2_MD4Ppr = plotlyEX.line( df_MBPGOOD1v2_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_1v2", "name":"FPGA Side"})
        fig_MBPGOOD1v2_MD4Ppr.update_layout(title="Ppr MD4: pgood_mb_1v2")
        fig_MBPGOOD1v2_MD4Ppr.write_html("plotly_MD4PprMBPGOOD1v2_combined.html")

	# pgood_mb_1v8
        fig_MBPGOOD1v8_MD1Emu = plotlyEX.line( df_MBPGOOD1v8_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_1v8", "name":"FPGA Side"})
        fig_MBPGOOD1v8_MD1Emu.update_layout(title="Emu MD1: pgood_mb_1v8")
        fig_MBPGOOD1v8_MD1Emu.write_html("plotly_MD1EmuMBPGOOD1v8_combined.html")

        fig_MBPGOOD1v8_MD2Emu = plotlyEX.line( df_MBPGOOD1v8_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_1v8", "name":"FPGA Side"})
        fig_MBPGOOD1v8_MD2Emu.update_layout(title="Emu MD2: pgood_mb_1v8")
        fig_MBPGOOD1v8_MD2Emu.write_html("plotly_MD2EmuMBPGOOD1v8_combined.html")

        fig_MBPGOOD1v8_MD3Emu = plotlyEX.line( df_MBPGOOD1v8_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_1v8", "name":"FPGA Side"})
        fig_MBPGOOD1v8_MD3Emu.update_layout(title="Emu MD3: pgood_mb_1v8")
        fig_MBPGOOD1v8_MD3Emu.write_html("plotly_MD3EmuMBPGOOD1v8_combined.html")

        fig_MBPGOOD1v8_MD4Emu = plotlyEX.line( df_MBPGOOD1v8_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_1v8", "name":"FPGA Side"})
        fig_MBPGOOD1v8_MD4Emu.update_layout(title="Emu MD4: pgood_mb_1v8")
        fig_MBPGOOD1v8_MD4Emu.write_html("plotly_MD4EmuMBPGOOD1v8_combined.html")

        fig_MBPGOOD1v8_MD1Ppr = plotlyEX.line( df_MBPGOOD1v8_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_1v8", "name":"FPGA Side"})
        fig_MBPGOOD1v8_MD1Ppr.update_layout(title="Ppr MD1: pgood_mb_1v8")
        fig_MBPGOOD1v8_MD1Ppr.write_html("plotly_MD1PprMBPGOOD1v8_combined.html")

        fig_MBPGOOD1v8_MD2Ppr = plotlyEX.line( df_MBPGOOD1v8_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_1v8", "name":"FPGA Side"})
        fig_MBPGOOD1v8_MD2Ppr.update_layout(title="Ppr MD2: pgood_mb_1v8")
        fig_MBPGOOD1v8_MD2Ppr.write_html("plotly_MD2PprMBPGOOD1v8_combined.html")

        fig_MBPGOOD1v8_MD3Ppr = plotlyEX.line( df_MBPGOOD1v8_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_1v8", "name":"FPGA Side"})
        fig_MBPGOOD1v8_MD3Ppr.update_layout(title="Ppr MD3: pgood_mb_1v8")
        fig_MBPGOOD1v8_MD3Ppr.write_html("plotly_MD3PprMBPGOOD1v8_combined.html")

        fig_MBPGOOD1v8_MD4Ppr = plotlyEX.line( df_MBPGOOD1v8_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_1v8", "name":"FPGA Side"})
        fig_MBPGOOD1v8_MD4Ppr.update_layout(title="Ppr MD4: pgood_mb_1v8")
        fig_MBPGOOD1v8_MD4Ppr.write_html("plotly_MD4PprMBPGOOD1v8_combined.html")

	# pgood_mb_2v5
        fig_MBPGOOD2v5_MD1Emu = plotlyEX.line( df_MBPGOOD2v5_MD1Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_2v5", "name":"FPGA Side"})
        fig_MBPGOOD2v5_MD1Emu.update_layout(title="Emu MD1: pgood_mb_2v5")
        fig_MBPGOOD2v5_MD1Emu.write_html("plotly_MD1EmuMBPGOOD2v5_combined.html")

        fig_MBPGOOD2v5_MD2Emu = plotlyEX.line( df_MBPGOOD2v5_MD2Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_2v5", "name":"FPGA Side"})
        fig_MBPGOOD2v5_MD2Emu.update_layout(title="Emu MD2: pgood_mb_2v5")
        fig_MBPGOOD2v5_MD2Emu.write_html("plotly_MD2EmuMBPGOOD2v5_combined.html")

        fig_MBPGOOD2v5_MD3Emu = plotlyEX.line( df_MBPGOOD2v5_MD3Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_2v5", "name":"FPGA Side"})
        fig_MBPGOOD2v5_MD3Emu.update_layout(title="Emu MD3: pgood_mb_2v5")
        fig_MBPGOOD2v5_MD3Emu.write_html("plotly_MD3EmuMBPGOOD2v5_combined.html")

        fig_MBPGOOD2v5_MD4Emu = plotlyEX.line( df_MBPGOOD2v5_MD4Emu, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_2v5", "name":"FPGA Side"})
        fig_MBPGOOD2v5_MD4Emu.update_layout(title="Emu MD4: pgood_mb_2v5")
        fig_MBPGOOD2v5_MD4Emu.write_html("plotly_MD4EmuMBPGOOD2v5_combined.html")

        fig_MBPGOOD2v5_MD1Ppr = plotlyEX.line( df_MBPGOOD2v5_MD1Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_2v5", "name":"FPGA Side"})
        fig_MBPGOOD2v5_MD1Ppr.update_layout(title="Ppr MD1: pgood_mb_2v5")
        fig_MBPGOOD2v5_MD1Ppr.write_html("plotly_MD1PprMBPGOOD2v5_combined.html")

        fig_MBPGOOD2v5_MD2Ppr = plotlyEX.line( df_MBPGOOD2v5_MD2Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_2v5", "name":"FPGA Side"})
        fig_MBPGOOD2v5_MD2Ppr.update_layout(title="Ppr MD2: pgood_mb_2v5")
        fig_MBPGOOD2v5_MD2Ppr.write_html("plotly_MD2PprMBPGOOD2v5_combined.html")

        fig_MBPGOOD2v5_MD3Ppr = plotlyEX.line( df_MBPGOOD2v5_MD3Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_2v5", "name":"FPGA Side"})
        fig_MBPGOOD2v5_MD3Ppr.update_layout(title="Ppr MD3: pgood_mb_2v5")
        fig_MBPGOOD2v5_MD3Ppr.write_html("plotly_MD3PprMBPGOOD2v5_combined.html")

        fig_MBPGOOD2v5_MD4Ppr = plotlyEX.line( df_MBPGOOD2v5_MD4Ppr, x="x", y="y", color="name", labels={"x":"Time", "y":"pgood_mb_2v5", "name":"FPGA Side"})
        fig_MBPGOOD2v5_MD4Ppr.update_layout(title="Ppr MD4: pgood_mb_2v5")
        fig_MBPGOOD2v5_MD4Ppr.write_html("plotly_MD4PprMBPGOOD2v5_combined.html")

    except Exception as e:
        print(f"\u274C InfluxDB Connection Failed: {e}")

### ######### ###
### Executing ###
### ######### ###

secrets = load_secrets()

db_qual()
