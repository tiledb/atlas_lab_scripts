### ################################### ###
### DaughterBoard Qualification Program ###
### Version 0.9
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
def load_yaml_conf(filepath):
    with open(filepath, "r") as file:
        return yaml.safe_load(file)
#def load_secrets(filepath="../secrets/secrets.yaml"):
#    with open(filepath, "r") as file:
#        return yaml.safe_load(file)

# Function to print tree structure
def print_tree(level, name, is_last):
    prefix = "└── " if is_last else "├── "
    print(" " * (level * 4) + prefix + name)



# Main
def DBQ_Mk2():

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
                #row[4] = benchtest pass/fail flag: 0
                #row[5] = MD1 DB Serial No
                #row[6] = MD2 DB Serial No
                #row[7] = MD3 DB Serial No
                #row[8] = MD4 DB Serial No
                #print(row)

		# If the benchtest is flagged for reprocessing, then redownload the
                if row[4] == 0:
                    benchtest_proc[row[0]] = dict([("benchtest_pass", row[4]),
                                                   ("benchtest_timestamp", [row[1].strftime("%Y-%m-%dT%H:%M:%SZ"), row[2].strftime("%Y-%m-%dT%H:%M:%SZ")]),
                                                   ("benchtest_serialnos", [row[5], row[6], row[7], row[8]] )])

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



        # Access InfluxDB Table: 'tiledb'
        client.switch_database("tiledb")

        ### Analysing benchtest Data ###
        # Define Query Output Storage Dictionary
        queryResults = {}
        #print(f'queryResults = {queryResults}')

        # Define Data Array
        dataDict = {}

        # benchtest Loop
        for benchtest_id in benchtest_proc.keys():

            print("============================")
            print(f'benchtest id: {benchtest_id}')
            print(f'benchtest start time: {benchtest_proc[benchtest_id]["benchtest_timestamp"][0]}')
            print(f'benchtest stop time:  {benchtest_proc[benchtest_id]["benchtest_timestamp"][1]}')
            print(f'benchtest MD1 DB Serial Number: {benchtest_proc[benchtest_id]["benchtest_serialnos"][0]}')
            print(f'benchtest MD2 DB Serial Number: {benchtest_proc[benchtest_id]["benchtest_serialnos"][1]}')
            print(f'benchtest MD3 DB Serial Number: {benchtest_proc[benchtest_id]["benchtest_serialnos"][2]}')
            print(f'benchtest MD4 DB Serial Number: {benchtest_proc[benchtest_id]["benchtest_serialnos"][3]}')

            # Allocate result dictionary space
            queryResults[benchtest_id] = {}
            #print(f'queryResults = {queryResults}')
            #print(f'queryResults[{benchtest_id}] = {queryResults[benchtest_id]}')

            # Allocate data dictionary space
            dataDict[benchtest_id] = {}

            # Table Loop
            for table in config.keys():
                print("----------------------------")
                print(f'Table: {table}')

                # Define DaughterBoards
                querystr_channels = ''
                my_channels = []

                # Loop over present DaughterBoards
                for MDi in range(0,4):
                    if benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi] != None:
                        print(f'Mini-Drawer {MDi+1} contains DaughterBoard with Serial Number: {benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}')
                        querystr_channels = querystr_channels + '"PPrEmu MD' + str(MDi+1) + '", "PprGTH MD' + str(MDi+1) + '", '
                        my_channels.append("PPrEmu MD" + str(MDi+1))
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
                        dataDict[benchtest_id][ivar][chan[7:10]][chan[3:6]] = {}

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
                print(f'Querying Table: {table} - Success!')
                #print(f'queryResults = {queryResults}')
                #print(f'queryResults[{benchtest_id}] = {queryResults[benchtest_id]}')
                #print(f'queryResults[{benchtest_id}][{table}] = {queryResults[benchtest_id][table]}')

                # Datum Loop
                for point in queryResults[benchtest_id][table].get_points():
                    #print(f'point = {point}')

                    for ppr in my_channels:
                        if point[ppr] != None:
                            #print(f'ppr = "{ppr}"')
                            #print(f'ppr[3:6] = "{ppr[3:6]}"')
                            #print(f'ppr[7:10] = "{ppr[7:10]}"')
                            #print(f'point = {point}')
                            #print(f'point[ppr] = {point[ppr]}')

                            for ivar in my_variables:
                                #print(f'ivar = {ivar}')
                                #print(f'point[ivar] = {point[ivar]}')

                                if point[ppr] not in dataDict[benchtest_id][ivar][ppr[7:10]][ppr[3:6]]:
                                    dataDict[benchtest_id][ivar][ppr[7:10]][ppr[3:6]][point[ppr]] = {}

                                if "x" not in dataDict[benchtest_id][ivar][ppr[7:10]][ppr[3:6]][point[ppr]]:
                                    dataDict[benchtest_id][ivar][ppr[7:10]][ppr[3:6]][point[ppr]]["x"] = []

                                if "y" not in dataDict[benchtest_id][ivar][ppr[7:10]][ppr[3:6]][point[ppr]]:
                                    dataDict[benchtest_id][ivar][ppr[7:10]][ppr[3:6]][point[ppr]]["y"] = []

                                dataDict[benchtest_id][ivar][ppr[7:10]][ppr[3:6]][point[ppr]]["x"].append(datetime.fromisoformat(point['time']))
                                dataDict[benchtest_id][ivar][ppr[7:10]][ppr[3:6]][point[ppr]]["y"].append(point[ivar])

                print("----------------------------")
            print("============================")

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
    #            for ppr in dataDict[btid][variable][MD]:
    #                print(f'      ppr = {ppr}')
    #
    #                for channel in dataDict[btid][variable][MD][ppr]:
    #                    print(f'        channel = {channel}')
    #                    print(f'        dataDict[{btid}][{variable}][{MD}][{ppr}][{channel}]')
    #                    print(f'        dataDict[{btid}][{variable}][{MD}][{ppr}][{channel}] = {dataDict[btid][variable][MD][ppr][channel]}')
    #
    #                    for dim in dataDict[btid][variable][MD][ppr][channel]:
    #                        print(f'          dim = {dim}')
    #                        print(f'          dataDict[{btid}][{variable}][{MD}][{ppr}][{channel}][{dim}] = {dataDict[btid][variable][MD][ppr][channel][dim]}')
    #
    #                    for i in range(0, len(dataDict[btid][variable][MD][ppr][channel]["x"])):
    #                        print(f'          [{dataDict[btid][variable][MD][ppr][channel]["x"][i]}, {dataDict[btid][variable][MD][ppr][channel]["y"][i]}]')

    ### Statistical Tests for Data ###
    statDict = {}
    print(f'statDict = {statDict}')

    for benchtest_id in benchtest_proc.keys():
        statDict[benchtest_id] = {}
        print(f'  statDict[{benchtest_id}] = {statDict[benchtest_id]}')

        for MDi in range(0,4):

            if benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi] != None:
                print(f'    DaughterBoard Serial Number: {benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}')
                statDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]] = {}

                for table in config.keys():
                    print(f'      Table: {table}')

                    for ivar in config[table].keys():
                        print(f'        Variable:  {ivar}')
                        print(f'        config[{table}][{ivar}] = {config[table][ivar]}')

                        var_percent = []
                            
                        for channel in dataDict[benchtest_id][ivar]["MD"+str(MDi+1)]["GTH"]:
                            print(f'          Channel: {channel}')
                            #print(f'          dataDict[{benchtest_id}][{ivar}][{"MD"+str(MDi+1)}][{"GTH"}][{channel}][{"y"}]')

                            if len(config[table][ivar]) == 1:

                                for y in dataDict[benchtest_id][ivar]["MD"+str(MDi+1)]["GTH"][channel]["y"]:
                                    #print(f'            y = {y}')

                                    if y == config[table][ivar][0]:
                                        #print("True")
                                        var_percent.append(1)
                                    else:
                                        #print("False")
                                        var_percent.append(0)

                            if len(config[table][ivar]) == 2:

                                for y in dataDict[benchtest_id][ivar]["MD"+str(MDi+1)]["GTH"][channel]["y"]:
                                    #print(f'            y = {y}')

                                    if y >= config[table][ivar][0] and y <= config[table][ivar][1]:
                                        var_percent.append(1)
                                    else:
                                        var_percent.append(0)

                        #print(f'        var_percent = {var_percent}')
                        
                        statDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ivar] = sum(var_percent)/len(var_percent)

    for btid, dbDict in statDict.items():
        print(f'For benchtest with id: {btid}')

        for DBSN, varDict in dbDict.items():
            print(f'  For DaughterBoard with Serial No: {DBSN}')

            aggregate_passfail = []

            for var, percent in varDict.items():
                print(f'    Variable {var} has a {math.floor(percent*100)} percentage within tolerances.')
                
                aggregate_passfail.append(percent)

            statDict[btid][DBSN]["Overall Pass Rate"] = sum(aggregate_passfail)/len(aggregate_passfail)

    print(f'statDict = {statDict}')

    ### DataFrames and ###
    # Defining DataFRame dictionary
    dfDict = {}

    for benchtest_id in benchtest_proc.keys():
        dfDict[benchtest_id] = {}
        print(f'benchtest_id: {benchtest_id}')
        print(f'dfDict[{benchtest_id}]: {dfDict[benchtest_id]}')

        for MDi in range(0,4):

            if benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi] != None:
                print(f'  DaughterBoard Serial Number: {benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}')
                dfDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]] = {}
                print(f'  dfDict[{benchtest_id}][{benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}]: {dfDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]]}')

                for ppr in ["Emu", "GTH"]:
                    print(f'    PPr{ppr}')
                    dfDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ppr] = {}
                    print(f'    dfDict[{benchtest_id}][{benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}][{ppr}]: {dfDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ppr]}')

                    for table in config.keys():
                        print(f'      Table: {table}')

                        for ivar in config[table].keys():
                            print(f'        Variable: {ivar}')
                            #print(f'    dataDict[{benchtest_id}][{ivar}][{"MD"+str(MDi+1)}][{ppr}] = {dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][ppr]}')
                            #print(f'    len(dataDict[{benchtest_id}][{ivar}][{"MD"+str(MDi+1)}][{ppr}]) = {len(dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][ppr])}')

                            dfDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ppr][ivar] = {}
                            print(f'        dfDict[{benchtest_id}][{benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}][{ppr}][{ivar}]: {dfDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ppr][ivar]}')

                            if len(dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][ppr]) != 0:

                                dfCombo = []

                                for channel in dataDict[benchtest_id][ivar]["MD"+str(MDi+1)]["GTH"]:
                                    print(f'          channel: {channel}')
                                    
                                    dfDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ppr][ivar][channel] = pd.DataFrame( {'channel' : [channel]*len(dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][ppr][channel]["x"]), 'x' : dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][ppr][channel]["x"], 'y' : dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][ppr][channel]["y"] } )

                                    dfCombo.append(dfDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ppr][ivar][channel])

                                    print(f'          dfDict[{benchtest_id}][{benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}][{ppr}][{ivar}][{channel}]:')
                                    print(f'\n{dfDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ppr][ivar][channel]}')


                                #print(f'        dfCombo: {dfCombo}')
                                dfDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ppr][ivar]["Full"] = pd.concat(dfCombo)
                                print(f'        dfDict[{benchtest_id}][{benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}][{ppr}][{ivar}][{"Full"}]:')
                                print(f'\n{dfDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ppr][ivar]["Full"]}')

    # plotly Plotting
    plotDict = {}

    for benchtest_id in benchtest_proc.keys():
        plotDict[benchtest_id] = {}
        print(f'benchtest_id: {benchtest_id}')
        print(f'plotDict[{benchtest_id}]: {plotDict[benchtest_id]}')

        for MDi in range(0,4):

            if benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi] != None:
                print(f'  DaughterBoard Serial Number: {benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}')
                plotDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]] = {}
                print(f'  plotDict[{benchtest_id}][{benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}]: {plotDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]]}')

                for ppr in ["Emu", "GTH"]:
                    print(f'    PPr{ppr}')
                    plotDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ppr] = {}
                    print(f'    plotDict[{benchtest_id}][{benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}][{ppr}]: {plotDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ppr]}')

                    for table in config.keys():
                        print(f'      Table: {table}')

                        for ivar in config[table].keys():
                            print(f'        Variable: {ivar}')
                            #print(f'        dataDict[{benchtest_id}][{ivar}][{"MD"+str(MDi+1)}][{ppr}] = {dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][ppr]}')
                            #print(f'        len(dataDict[{benchtest_id}][{ivar}][{"MD"+str(MDi+1)}][{ppr}]) = {len(dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][ppr])}')

                            plotDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ppr][ivar] = {}
                            print(f'        plotDict[{benchtest_id}][{benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]}][{ppr}][{ivar}]: {plotDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ppr][ivar]}')

                            if len(dataDict[benchtest_id][ivar]["MD"+str(MDi+1)][ppr]) != 0:
                                plotDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ppr][ivar] = plotlyEX.line(
                                dfDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ppr][ivar]["Full"], x="x", y="y", color = "channel",
                                labels = {"x":"Time", "y":ivar, "channel":"Uplink Channel"} )

                                plotDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ppr][ivar].update_layout(title = "DBSNo: "+str(benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi])+" - PPr"+ppr+": "+ivar)
                                plotDict[benchtest_id][benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi]][ppr][ivar].write_html("DBSNo_"+str(benchtest_proc[benchtest_id]["benchtest_serialnos"][MDi])+"_PPr"+ppr+"_"+ivar+".html")
### ######### ###
### Executing ###
### ######### ###

# Load Config
config  = load_yaml_conf("vars.yaml")
secrets = load_yaml_conf("../secrets/secrets.yaml")

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
DBQ_Mk2()
