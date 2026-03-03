from datetime import datetime
import math

import yaml
from influxdb import InfluxDBClient
import mysql.connector
from mysql.connector import Error

import numpy as np
import matplotlib.pyplot as pypl

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

        databases = client.get_list_database()
        if not databases:
            print("⚠️ No databases found in InfluxDB.")
            return

        print("📂 InfluxDB Databases:")

        print(databases)

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

        # example of connecting explicitly to influx DB tiledb and fetching some data
        client.switch_database("tiledb")
        #my_measurement = "xADC" # for current monitoring data
        my_measurement = "Link Status" # for gbtx ready and crc errors
        #my_measurement = "mA"

        #Query: Intervals
        #That day in Sept, 2024, from 23:06:10 to 23:08:00
        #start_time= "2024-09-03T17:40:00Z"
        #stop_time= "2024-09-03T17:50:00Z"
        #stop_time= "2024-09-04T00:08:00Z"

        #The day in Early July where (I think) Christophe, Nikola and I were in Eduardo's office (with him on Zoom call)
        #It was then where we replaced the old DaughterBoard on the test Main Board with a new one. Specifically, around 16:00
        #start_time= "2025-07-09T17:00:00Z"
        #stop_time= "2025-07-10T17:05:00Z"

        start_time = "2025-07-10T14:15:00Z"
        stop_time  = "2025-07-10T14:45:00Z"

        my_time_range = f'WHERE time >= \'{start_time}\' AND time <= \'{stop_time}\''
        #my_time_range = f'WHERE time >= \'{start_time}\''

        print("my_time_range = ")
        print(my_time_range)
        print("----------------------------")
        #my_time_range = 'time >= '''2024-09-01T00:00:00Z''' AND time <= '''2024-09-01T00:01:00Z''' '


        #myquery = f'SELECT * FROM "{my_measurement}" LIMIT 100000' # go to the table called "my_measurement" and fetch the first 10000 entries
        myquery = f'SELECT "PprGTH MD4", "ber" FROM "{my_measurement}" {my_time_range}' # go to the table called "my_measurement" and fetch the first 5 entries
        #myquery = f'SELECT "PPrEmu MD1", "PPrEmu MD2", "PPrEmu MD3", "PPrEmu MD4", "PprGTH MD1", "PprGTH MD2", "PprGTH MD3", "PprGTH MD4", "gbtrx_rdy" FROM "{my_measurement}" {my_time_range}' # go to the table called "my_measurement" and fetch the first 5 entries
        # tz(\'Europe/Stockholm\')

        print("myquery = ")
        print(myquery)
        print("----------------------------")
        result = client.query(myquery)

        print('Result Obtained')

        #Defining storage variables
        nevents = 0

        maskA0 = 0
        maskA1 = 0
        maskB0 = 0
        maskB1 = 0

        array_xBER_A0 = []
        array_yBER_A0 = []
        array_xBER_A1 = []
        array_yBER_A1 = []
        array_xBER_B0 = []
        array_yBER_B0 = []
        array_xBER_B1 = []
        array_yBER_B1 = []

        # print the results
        print("----------------------------")
        for point in result.get_points():
            print(f"Time: {point['time']}")
            nevents = nevents+1

            for key,value in point.items():
                if key != 'time':
                    print(f'{key} : {value}')

                if (key == 'PprGTH MD4') and (value == 'uplink A0'):
                    maskA0 = 1
                elif (key == 'PprGTH MD4') and (value == 'uplink A1'):
                    maskA1 = 1
                elif (key == 'PprGTH MD4') and (value == 'uplink B0'):
                    maskB0 = 1
                elif (key == 'PprGTH MD4') and (value == 'uplink B1'):
                    maskB1 = 1

                #print(f"maskA0 = {maskA0}")
                #print(f"maskA1 = {maskA1}")
                #print(f"maskB0 = {maskB0}")
                #print(f"maskB1 = {maskB1}")

                if key == 'ber':
                    if maskA0:
                        array_xBER_A0.append(datetime.fromisoformat(point['time']))
                        array_yBER_A0.append(value)
                    elif maskA1:
                        array_xBER_A1.append(datetime.fromisoformat(point['time']))
                        array_yBER_A1.append(value)
                    elif maskB0:
                        array_xBER_B0.append(datetime.fromisoformat(point['time']))
                        array_yBER_B0.append(value)
                    elif maskB1:
                        array_xBER_B1.append(datetime.fromisoformat(point['time']))
                        array_yBER_B1.append(value)

            maskA0 = 0
            maskA1 = 0
            maskB0 = 0
            maskB1 = 0
            print("-------")

        #Debugging
        print(f"Number of Events: {nevents}")
        print(f"Factor: {math.ceil(nevents/1000)}")
        print(f"xA0: {array_xBER_A0}")
        print(f"yA0: {array_yBER_A0}")
        print(f"xA1: {array_xBER_A1}")
        print(f"yA1: {array_yBER_A1}")
        print(f"xB0: {array_xBER_B0}")
        print(f"yB0: {array_yBER_B0}")
        print(f"xB1: {array_xBER_B1}")
        print(f"yB1: {array_yBER_B1}")

        print("TEST")

        #Creating numpy objects
        numpy_xBER_A0 = np.array(array_xBER_A0)
        numpy_yBER_A0 = np.array(array_yBER_A0)
        numpy_xBER_A1 = np.array(array_xBER_A1)
        numpy_yBER_A1 = np.array(array_yBER_A1)
        numpy_xBER_B0 = np.array(array_xBER_B0)
        numpy_yBER_B0 = np.array(array_yBER_B0)
        numpy_xBER_B1 = np.array(array_xBER_B1)
        numpy_yBER_B1 = np.array(array_yBER_B1)

        print("TEST2")

        #Selecting ticks
        tickArray_xBER_A0 = []
        tickArray_yBER_A0 = []
        tickArray_xBER_A1 = []
        tickArray_yBER_A1 = []
        tickArray_xBER_B0 = []
        tickArray_yBER_B0 = []
        tickArray_xBER_B1 = []
        tickArray_yBER_B1 = []

        print("TEST3")
        for butt in range(5):
            print(f"butt: {butt}")
            print(f"array length: {len(array_xBER_A0)}")
            print(f"array length/5: {len(array_xBER_A0)/5}")
            print(f"buttplushalf times arraylength/5: {(butt+0.5)*len(array_xBER_A0)/5}")
            print(f"floor: {math.floor((butt+0.5)*len(array_xBER_A0)/5)}")

            #print(array_xBER_A0[ math.floor((butt+0.5)*len(array_xBER_A0)/5) ] )
            tickArray_xBER_A0.append( array_xBER_A0[ math.floor( (butt+0.5) * len(array_xBER_A0)/5 ) -1 ] )
            tickArray_yBER_A0.append( array_yBER_A0[ math.floor( (butt+0.5) * len(array_yBER_A0)/5 ) -1 ] )

            #print(array_xBER_A1[ math.floor((butt+0.5)*len(array_xBER_A1)/5) ] )
            tickArray_xBER_A1.append( array_xBER_A1[ math.floor( (butt+0.5) * len(array_xBER_A1)/5 ) ] )
            tickArray_yBER_A1.append( array_yBER_A1[ math.floor( (butt+0.5) * len(array_yBER_A1)/5 ) ] )

            #print(array_xBER_B0[ math.floor((butt+0.5)*len(array_xBER_B0)/5) ] )
            tickArray_xBER_B0.append( array_xBER_B0[ math.floor( (butt+0.5) * len(array_xBER_B0)/5 ) +1 ] )
            tickArray_yBER_B0.append( array_yBER_B0[ math.floor( (butt+0.5) * len(array_yBER_B0)/5 ) +1 ] )

            #print(array_xBER_B1[ math.floor((butt+0.5)*len(array_xBER_B1)/5) ] )
            tickArray_xBER_B1.append( array_xBER_B1[ math.floor( (butt+0.5) * len(array_xBER_B1)/5 ) +2 ] )
            tickArray_yBER_B1.append( array_yBER_B1[ math.floor( (butt+0.5) * len(array_yBER_B1)/5 ) +2 ] )

        print("TEST4")

        numpyticks_xBER_A0 = np.array(tickArray_xBER_A0)
        numpyticks_yBER_A0 = np.array(tickArray_yBER_A0)
        numpyticks_xBER_A1 = np.array(tickArray_xBER_A1)
        numpyticks_yBER_A1 = np.array(tickArray_yBER_A1)
        numpyticks_xBER_B0 = np.array(tickArray_xBER_B0)
        numpyticks_yBER_B0 = np.array(tickArray_yBER_B0)
        numpyticks_xBER_B1 = np.array(tickArray_xBER_B1)
        numpyticks_yBER_B1 = np.array(tickArray_yBER_B1)

        #Optimal Result
        optimal_xBER = [datetime.fromisoformat(start_time), datetime.fromisoformat(stop_time)]
        optimal_yBER = [0, 0]

        numpyopt_xBER = np.array(optimal_xBER)
        numpyopt_yBER = np.array(optimal_yBER)

        ##Matplotlib Plotting
        pypl.figure(1)
        pypl.subplot(111)
        axes_BER = pypl.gca()
        #fig, plot_BER = pypl.subplots()
        #Actual Values
        axes_BER.plot(numpy_xBER_A0, numpy_yBER_A0, "r-", label="A0")
        axes_BER.plot(numpy_xBER_A1, numpy_yBER_A1, "b-", label="A1")
        axes_BER.plot(numpy_xBER_B0, numpy_yBER_B0, "g-", label="B0")
        axes_BER.plot(numpy_xBER_B1, numpy_yBER_B1, "y-", label="B1")

        print("TEST5")
        #Ticks
        axes_BER.plot(numpyticks_xBER_A0, numpyticks_yBER_A0, "ro")
        axes_BER.plot(numpyticks_xBER_A1, numpyticks_yBER_A1, "b<")
        axes_BER.plot(numpyticks_xBER_B0, numpyticks_yBER_B0, "g>")
        axes_BER.plot(numpyticks_xBER_B1, numpyticks_yBER_B1, "ys")

        #Optimal Value
        axes_BER.plot(numpyopt_xBER, numpyopt_yBER, "r-", linewidth=10, alpha=0.25, label="Optimal Value")
        print("TEST6")

        axes_BER.set(title = "PprGTH MD4: BER", xlabel = "Time", ylabel = "BER",
                       #xlim=(0, math.ceil(nevents/100)*100), xticks=np.arange(0, math.ceil(nevents/100)*100, 100),
                       ylim=(-0.2,1.2),                      yticks=np.arange(-0.2,1.2,0.2))
        axes_BER.grid(True)

        axes_BER.legend(loc="best")

        pypl.savefig("BER_PprGTH_MD4_datetime.png")

    except Exception as e:
        print(f"❌ InfluxDB Connection Failed: {e}")


# Run Tree Listing
list_influxdb_tree()
