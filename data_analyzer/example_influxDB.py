import yaml
from influxdb import InfluxDBClient
import mysql.connector
from mysql.connector import Error

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
        my_measurement = "xADC" # for current monitoring data
        #my_measurement = "Link Status" # for gbtx ready and crc errors
        #my_measurement = "mA"

        start_time = "2024-09-03T23:06:10Z"
        stop_time  = "2024-09-03T23:08:00Z"

        #start_time = "2024-09-03T19:40:00Z"
        #stop_time  = "2024-09-03T19:42:00Z"

        #start_time= "2025-07-09T17:00:00Z"
        #stop_time= "2025-07-10T17:05:00Z"

        my_time_range = f'WHERE time >= \'{start_time}\' AND time <= \'{stop_time}\''
        #my_time_range = f'WHERE time >= \'{start_time}\''

        print("my_time_range = ")
        print(my_time_range)
        print("----------------------------")
        #my_time_range = 'time >= '''2024-09-01T00:00:00Z''' AND time <= '''2024-09-01T00:01:00Z''' '


        #myquery = f'SELECT * FROM "{my_measurement}" LIMIT 100000' # go to the table called "my_measurement" and fetch the first 10000 entries
        myquery = f'SELECT * FROM "{my_measurement}" {my_time_range}' # go to the table called "my_measurement" and fetch the first 5 entries
        #myquery = f'SELECT gbtrx_rdy FROM "{my_measurement}" {my_time_range}' # go to the table called "my_measurement" and fetch the first 5 entries

        print("myquery = ")
        print(myquery)
        print("----------------------------")
        result = client.query(myquery)

        # print the results
        print("----------------------------")
        for point in result.get_points():
            print(f"Time: {point['time']}")
            for key,value in point.items():
                if key != 'time':
                    print(f'{key} : {value}')
            print("-------")

    except Exception as e:
        print(f"❌ InfluxDB Connection Failed: {e}")

# Run Tree Listing
list_influxdb_tree()
