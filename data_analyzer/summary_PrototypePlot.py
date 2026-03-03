### Import Packages ###

# Basic packages
from datetime import datetime
import math

# Advanced packages
import numpy as np
import pandas as pd
#import matplotlib.pyplot as pypl
import plotly.graph_objects as plotlyGO
import plotly.express as plotlyEX

# Server Connections
import yaml

import mysql.connector
from mysql.connector import Error

from influxdb import InfluxDBClient

# Load secrets from secrets.yaml
def load_secrets(filepath="../secrets/secrets.yaml"):
    with open(filepath, "r") as file:
        return yaml.safe_load(file)

secrets = load_secrets()

# Function to print tree structure
def print_tree(level, name, is_last):
    prefix = "└── " if is_last else "├── "
    print(" " * (level * 4) + prefix + name)

# Function to list databases and measurements in InfluxDB
def list_influxdb_tree():
    try:
        ### MariaDB ###
        #Connect to MariaDB
        print("\n==================== MariaDB Tree ====================")
        print(f"🔗 Connecting to MariaDB at {secrets['tiledb-mariadb']['host']}...")
        connection = mysql.connector.connect(
            host=secrets["tiledb-mariadb"]["host"],
            user=secrets["tiledb-mariadb"]["user"],
            password=secrets["tiledb-mariadb"]["password"]
        )

        #Confirm MariaDB Connection
        if connection.is_connected():
            print("✅ Connected to MariaDB!")
            cursor = connection.cursor()

        #List all databases                                                                                                                                       
        cursor.execute("SHOW DATABASES;")
        databases = [db[0] for db in cursor.fetchall()]

        if not databases:
            print("⚠ No databases found in MariaDB.")
            return

        print("📂 MariaDB Databases:")
        for i, db in enumerate(databases):
            print_tree(0, db, i == len(databases) - 1)

        #Select "tiledb" database
        cursor.execute(f"USE tiledb")
        
        #List all tables in the selected database                                                                                                                 
        cursor.execute("SHOW TABLES;")
        tables = [tbl[0] for tbl in cursor.fetchall()]

        if not tables:
            print("⚠ No tables found in selected database.")
            return

        print("\nTables in tiledb:")
        for i, table in enumerate(tables):
            print_tree(1, table, i == len(tables) - 1)

        #Query table
        cursor.execute("SELECT * FROM benchtest")
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        print(rows)
        print(columns)

        if rows:
            print("\nData from MariaDB benchtest")
            print(" | ".join(columns))
            for row in rows:
                dtSTARTTIME = row[1].strftime("%Y-%m-%dT%H:%M:%SZ")
                dtSTOPTIME  = row[2].strftime("%Y-%m-%dT%H:%M:%SZ")
                print(" | ".join(map(str, row)))
        else:
            print("⚠ No data found in selected table.")

        print(f"Converted start time: {dtSTARTTIME}")
        print(f"Converted stop time:  {dtSTOPTIME}")

        ### Construct Plotly Example ###
        #Define Data
        BoardData = {
            "9100001" : [0.0, 0.4, 0.45, 0.7, 1.0, 1.0, 1.0],
            "9100002" : [1.0, 1.0, 1.0 , 1.0, 1.0, 1.0, 1.0],
            "9100003" : [0.0, 0.7, 0.35, 0.5, 0.7, 0.9, 0.95],
            "9100004" : [0.5, 0.6, 0.75, 0.2, 0.5, 0.5, 0.5]
        }

        dt = pd.DataFrame(BoardData, index = [ datetime.fromisoformat("2026-02-11T09:12:30Z"),
                                               datetime.fromisoformat("2026-02-11T18:09:00Z"),
                                               datetime.fromisoformat("2026-04-11T09:12:20Z"),
                                               datetime.fromisoformat("2026-05-11T09:11:30Z"),
                                               datetime.fromisoformat("2026-05-11T19:33:34Z"),
                                               datetime.fromisoformat("2026-09-11T11:01:30Z"),
                                               datetime.fromisoformat("2026-10-11T11:23:30Z")  ])
        dt.index.name = "Time"

        print(dt)
        print(dt['9100001'].loc["2026-02-11T18:09:00Z"])

        dt2 = pd.concat([dt,dt])
        print(dt2)

        assdict = dict(
            x = [1,2,3,4],
            y = [1,3,2,4])

        assdf = pd.DataFrame(assdict)
        
        print(assdict)
        print(assdf)
        
        #Plotly plotting code
        fig = plotlyEX.line(dt, dt.index, y=["9100001", "9100002", "9100003", "9100004"], title="Test Results")
        fig.write_html ("plotly_SummaryPrototype.html")
        fig.write_image("plotly_SummaryPrototype.png")

    except Error as e:
        print("❌ MariaDB Connection Failed")

#    try:
#        ### InfluxDB ###
#        print("\n==================== InfluxDB Tree ====================")
#        print(f"🔗 Connecting to InfluxDB at {secrets['tiledb-influxdb']['host']}:{secrets['tiledb-influxdb']['port']}...")
#        client = InfluxDBClient(
#            host=secrets["tiledb-influxdb"]["host"],
#            port=secrets["tiledb-influxdb"]["port"],
#            username=secrets["tiledb-influxdb"]["username"],
#            password=secrets["tiledb-influxdb"]["password"]
#        )
#        client.ping()
#        print("✅ Connected to InfluxDB!")
#
#        databases = client.get_list_database()
#        if not databases:
#            print("⚠️ No databases found in InfluxDB.")
#            return
#
#        print("📂 InfluxDB Databases:")
#
#        print(databases)
#
#        print("============================")
#        for i, db in enumerate(databases):
#            db_name = db["name"]
#            print_tree(0, db_name, i == len(databases) - 1)
#
#            client.switch_database(db_name)
#            result = client.query("SHOW MEASUREMENTS")
#            measurements = [m["name"] for m in result.get_points()]
#
#            print("============================")
#            print(measurements)
#            print("============================")
#            if not measurements:
#                print_tree(1, "(No Measurements)", True)
#            else:
#                for j, measurement in enumerate(measurements):
#                    print_tree(1, measurement, j == len(measurements) - 1)
#
#        # example of connecting explicitly to influx DB tiledb and fetching some data
#        client.switch_database("tiledb")
#        #my_measurement = "xADC" # for current monitoring data
#        my_measurement = "Link Status" # for gbtx ready and crc errors
#        #my_measurement = "mA"
#
#        #Query: Intervals
#        #That day in Sept, 2024, from 23:06:10 to 23:08:00
#        #start_time= "2024-09-03T17:40:00Z"
#        #stop_time= "2024-09-03T17:50:00Z"
#        #stop_time= "2024-09-04T00:08:00Z"
#
#        #The day in Early July where (I think) Christophe, Nikola and I were in Eduardo's office (with him on Zoom call)
#        #It was then where we replaced the old DaughterBoard on the test Main Board with a new one. Specifically, around 16:00
#        #start_time= "2025-07-09T17:00:00Z"
#        #stop_time= "2025-07-10T17:05:00Z"
#
#        #start_time = "2025-07-10T14:15:00Z"
#        #stop_time  = "2025-07-10T14:45:00Z"
#
#        start_time = dtSTARTTIME
#        stop_time  = dtSTOPTIME
#
#        my_time_range = f'WHERE time >= \'{start_time}\' AND time <= \'{stop_time}\''
#        #my_time_range = f'WHERE time >= \'{start_time}\''
#
#        print("my_time_range = ")
#        print(my_time_range)
#        print("----------------------------")
#        #my_time_range = 'time >= '''2024-09-01T00:00:00Z''' AND time <= '''2024-09-01T00:01:00Z''' '
#
#        
#        #myquery = f'SELECT * FROM "{my_measurement}" LIMIT 100000' # go to the table called "my_measurement" and fetch the first 10000 entries
#        myquery = f'SELECT "PPrEmu MD1", "gbtrx_rdy" FROM "{my_measurement}" {my_time_range}' # go to the table called "my_measurement" and fetch the first 5 entries
#        #myquery = f'SELECT "PPrEmu MD1", "PPrEmu MD2", "PPrEmu MD3", "PPrEmu MD4", "PprGTH MD1", "PprGTH MD2", "PprGTH MD3", "PprGTH MD4", "gbtrx_rdy" FROM "{my_measurement}" {my_time_range}' # go to the table called "my_measurement" and fetch the first 5 entries
#        # tz(\'Europe/Stockholm\')
#
#        print("myquery = ")
#        print(myquery)
#        print("----------------------------")
#        result = client.query(myquery)
#
#        print('Result Obtained')
#
#        #Defining storage variables
#        nevents = 0
#
#        maskA0 = 0
#        maskA1 = 0
#        maskB0 = 0
#        maskB1 = 0
#
#        array_xGBTRX_RDY_A0 = []
#        array_yGBTRX_RDY_A0 = []
#        array_xGBTRX_RDY_A1 = []
#        array_yGBTRX_RDY_A1 = []
#        array_xGBTRX_RDY_B0 = []
#        array_yGBTRX_RDY_B0 = []
#        array_xGBTRX_RDY_B1 = []
#        array_yGBTRX_RDY_B1 = []
#
#        # print the results
#        print("----------------------------")
#        for point in result.get_points():
#            #print(f"Time: {point['time']}")
#            nevents = nevents+1
#
#            for key,value in point.items():
#                #if key != 'time':
#                    #print(f'{key} : {value}')
#
#                if (key == 'PPrEmu MD1') and (value == 'uplink A0'):
#                    maskA0 = 1
#                elif (key == 'PPrEmu MD1') and (value == 'uplink A1'):
#                    maskA1 = 1
#                elif (key == 'PPrEmu MD1') and (value == 'uplink B0'):
#                    maskB0 = 1
#                elif (key == 'PPrEmu MD1') and (value == 'uplink B1'):
#                    maskB1 = 1
#
#                #print(f"maskA0 = {maskA0}")
#                #print(f"maskA1 = {maskA1}")
#                #print(f"maskB0 = {maskB0}")
#                #print(f"maskB1 = {maskB1}")
#
#                if key == 'gbtrx_rdy':
#                    if maskA0:
#                        array_xGBTRX_RDY_A0.append(datetime.fromisoformat(point['time']))
#                        array_yGBTRX_RDY_A0.append(value)
#                    elif maskA1:
#                        array_xGBTRX_RDY_A1.append(datetime.fromisoformat(point['time']))
#                        array_yGBTRX_RDY_A1.append(value)
#                    elif maskB0:
#                        array_xGBTRX_RDY_B0.append(datetime.fromisoformat(point['time']))
#                        array_yGBTRX_RDY_B0.append(value)
#                    elif maskB1:
#                        array_xGBTRX_RDY_B1.append(datetime.fromisoformat(point['time']))
#                        array_yGBTRX_RDY_B1.append(value)
#
#            maskA0 = 0
#            maskA1 = 0
#            maskB0 = 0
#            maskB1 = 0
#            #print("-------")
#
#        #Debugging
#        print(f"Number of Events: {nevents}")
#        print(f"Factor: {math.ceil(nevents/1000)}")
#        print(f"xA0: {array_xGBTRX_RDY_A0}")
#        print(f"yA0: {array_yGBTRX_RDY_A0}")
#        print(f"xA1: {array_xGBTRX_RDY_A1}")
#        print(f"yA1: {array_yGBTRX_RDY_A1}")
#        print(f"xB0: {array_xGBTRX_RDY_B0}")
#        print(f"yB0: {array_yGBTRX_RDY_B0}")
#        print(f"xB1: {array_xGBTRX_RDY_B1}")
#        print(f"yB1: {array_yGBTRX_RDY_B1}")
#
#        print("TEST")
#
#        #Creating numpy objects
#        numpy_xGBTRX_RDY_A0 = np.array(array_xGBTRX_RDY_A0)
#        numpy_yGBTRX_RDY_A0 = np.array(array_yGBTRX_RDY_A0)
#        numpy_xGBTRX_RDY_A1 = np.array(array_xGBTRX_RDY_A1)
#        numpy_yGBTRX_RDY_A1 = np.array(array_yGBTRX_RDY_A1)
#        numpy_xGBTRX_RDY_B0 = np.array(array_xGBTRX_RDY_B0)
#        numpy_yGBTRX_RDY_B0 = np.array(array_yGBTRX_RDY_B0)
#        numpy_xGBTRX_RDY_B1 = np.array(array_xGBTRX_RDY_B1)
#        numpy_yGBTRX_RDY_B1 = np.array(array_yGBTRX_RDY_B1)
#
#        print("TEST2")
#
#        #Selecting ticks
#        tickArray_xGBTRX_RDY_A0 = []
#        tickArray_yGBTRX_RDY_A0 = []
#        tickArray_xGBTRX_RDY_A1 = []
#        tickArray_yGBTRX_RDY_A1 = []
#        tickArray_xGBTRX_RDY_B0 = []
#        tickArray_yGBTRX_RDY_B0 = []
#        tickArray_xGBTRX_RDY_B1 = []
#        tickArray_yGBTRX_RDY_B1 = []
#
#        print("TEST3")
#        for butt in range(4):
#            print(f"butt: {butt}")
#            print(f"array length: {len(array_xGBTRX_RDY_A0)}")
#            print(f"array length/5: {len(array_xGBTRX_RDY_A0)/5}")
#            print(f"buttplushalf times arraylength/5: {(butt+0.5)*len(array_xGBTRX_RDY_A0)/5}")
#            print(f"floor: {math.floor((butt+0.5)*len(array_xGBTRX_RDY_A0)/5)}")
#
#            #print(array_xGBTRX_RDY_A0[ math.floor((butt+0.5)*len(array_xGBTRX_RDY_A0)/5) ] )
#            tickArray_xGBTRX_RDY_A0.append( array_xGBTRX_RDY_A0[ math.floor( (butt+0.5) * len(array_xGBTRX_RDY_A0)/5 ) -1 ] )
#            tickArray_yGBTRX_RDY_A0.append( array_yGBTRX_RDY_A0[ math.floor( (butt+0.5) * len(array_yGBTRX_RDY_A0)/5 ) -1 ] )
#
#            #print(array_xGBTRX_RDY_A1[ math.floor((butt+0.5)*len(array_xGBTRX_RDY_A1)/5) ] )
#            tickArray_xGBTRX_RDY_A1.append( array_xGBTRX_RDY_A1[ math.floor( (butt+0.5) * len(array_xGBTRX_RDY_A1)/5 ) ] )
#            tickArray_yGBTRX_RDY_A1.append( array_yGBTRX_RDY_A1[ math.floor( (butt+0.5) * len(array_yGBTRX_RDY_A1)/5 ) ] )
#
#            #print(array_xGBTRX_RDY_B0[ math.floor((butt+0.5)*len(array_xGBTRX_RDY_B0)/5) ] )
#            tickArray_xGBTRX_RDY_B0.append( array_xGBTRX_RDY_B0[ math.floor( (butt+0.5) * len(array_xGBTRX_RDY_B0)/5 ) +1 ] )
#            tickArray_yGBTRX_RDY_B0.append( array_yGBTRX_RDY_B0[ math.floor( (butt+0.5) * len(array_yGBTRX_RDY_B0)/5 ) +1 ] )
#
#            #print(array_xGBTRX_RDY_B1[ math.floor((butt+0.5)*len(array_xGBTRX_RDY_B1)/5) ] )
#            tickArray_xGBTRX_RDY_B1.append( array_xGBTRX_RDY_B1[ math.floor( (butt+0.5) * len(array_xGBTRX_RDY_B1)/5 ) +2 ] )
#            tickArray_yGBTRX_RDY_B1.append( array_yGBTRX_RDY_B1[ math.floor( (butt+0.5) * len(array_yGBTRX_RDY_B1)/5 ) +2 ] )
#
#        print("TEST4")
#
#        numpyticks_xGBTRX_RDY_A0 = np.array(tickArray_xGBTRX_RDY_A0)
#        numpyticks_yGBTRX_RDY_A0 = np.array(tickArray_yGBTRX_RDY_A0)
#        numpyticks_xGBTRX_RDY_A1 = np.array(tickArray_xGBTRX_RDY_A1)
#        numpyticks_yGBTRX_RDY_A1 = np.array(tickArray_yGBTRX_RDY_A1)
#        numpyticks_xGBTRX_RDY_B0 = np.array(tickArray_xGBTRX_RDY_B0)
#        numpyticks_yGBTRX_RDY_B0 = np.array(tickArray_yGBTRX_RDY_B0)
#        numpyticks_xGBTRX_RDY_B1 = np.array(tickArray_xGBTRX_RDY_B1)
#        numpyticks_yGBTRX_RDY_B1 = np.array(tickArray_yGBTRX_RDY_B1)
#
#        #Optimal Result
#        optimal_xGBTRX_RDY = [datetime.fromisoformat(start_time), datetime.fromisoformat(stop_time)]
#        optimal_yGBTRX_RDY = [1, 1]
#
#        numpyopt_xGBTRX_RDY = np.array(optimal_xGBTRX_RDY)
#        numpyopt_yGBTRX_RDY = np.array(optimal_yGBTRX_RDY)
#
#        #Plotly Plotting
#        fig = plotlyGO.Figure()
#
#        fig.add_trace( plotlyGO.Scatter(x=numpy_xGBTRX_RDY_A0, y=numpy_yGBTRX_RDY_A0, mode='lines', name='Uplink A0') )
#        fig.add_trace( plotlyGO.Scatter(x=numpy_xGBTRX_RDY_A1, y=numpy_yGBTRX_RDY_A1, mode='lines', name='Uplink A1') )
#        fig.add_trace( plotlyGO.Scatter(x=numpy_xGBTRX_RDY_B0, y=numpy_yGBTRX_RDY_B0, mode='lines', name='Uplink B0') )
#        fig.add_trace( plotlyGO.Scatter(x=numpy_xGBTRX_RDY_B1, y=numpy_yGBTRX_RDY_B1, mode='lines', name='Uplink B1') )
#
#        fig.update_layout(title='PPrEmu MD1: GBTRX_RDY')
#        fig.write_html("plotly_GBTRXRDY_PPrEmuMD1_MariaDB.html")
#        fig.write_image("plotly_GBTRXRDY_PPrEmuMD1_MariaDB.png", width=800, height=600)
#
#        ###Matplotlib Plotting
#        #pypl.figure(1)
#        #pypl.subplot(111)
#        #axes_GBTRX = pypl.gca()
#        ##fig, plot_GBTRX = pypl.subplots()
#        ##Actual Values
#        #axes_GBTRX.plot(numpy_xGBTRX_RDY_A0, numpy_yGBTRX_RDY_A0, "r-", label="A0")
#        #axes_GBTRX.plot(numpy_xGBTRX_RDY_A1, numpy_yGBTRX_RDY_A1, "b-", label="A1")
#        #axes_GBTRX.plot(numpy_xGBTRX_RDY_B0, numpy_yGBTRX_RDY_B0, "g-", label="B0")
#        #axes_GBTRX.plot(numpy_xGBTRX_RDY_B1, numpy_yGBTRX_RDY_B1, "y-", label="B1")
#        #
#        print("TEST5")
#        ##Ticks
#        #axes_GBTRX.plot(numpyticks_xGBTRX_RDY_A0, numpyticks_yGBTRX_RDY_A0, "ro")
#        #axes_GBTRX.plot(numpyticks_xGBTRX_RDY_A1, numpyticks_yGBTRX_RDY_A1, "b<")
#        #axes_GBTRX.plot(numpyticks_xGBTRX_RDY_B0, numpyticks_yGBTRX_RDY_B0, "g>")
#        #axes_GBTRX.plot(numpyticks_xGBTRX_RDY_B1, numpyticks_yGBTRX_RDY_B1, "ys")
#        #
#        ##Optimal Value
#        #axes_GBTRX.plot(numpyopt_xGBTRX_RDY, numpyopt_yGBTRX_RDY, "r-", linewidth=10, alpha=0.25, label="Optimal Value")
#        #print("TEST6")
#        #
#        #axes_GBTRX.set(title = "PprGTH MD1: GBTRX_RDY", xlabel = "Time", ylabel = "GBTRX_RDY",
#        #               #xlim=(0, math.ceil(nevents/100)*100), xticks=np.arange(0, math.ceil(nevents/100)*100, 100),
#        #               ylim=(-0.2,1.2),                      yticks=np.arange(-0.2,1.21,0.2))
#        #axes_GBTRX.grid(True)
#        #
#        #axes_GBTRX.legend(loc="best")
#        #
#        #pypl.savefig("GBTRXRDY_PprGTH_MD1_datetime.png")
#
#    except Exception as e:
#        print(f"❌ InfluxDB Connection Failed: {e}")
#

# Run Tree Listing
list_influxdb_tree()
