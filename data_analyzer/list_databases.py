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
        for i, db in enumerate(databases):
            db_name = db["name"]
            print_tree(0, db_name, i == len(databases) - 1)

            client.switch_database(db_name)
            result = client.query("SHOW MEASUREMENTS")
            measurements = [m["name"] for m in result.get_points()]
            
            if not measurements:
                print_tree(1, "(No Measurements)", True)
            else:
                for j, measurement in enumerate(measurements):
                    print_tree(1, measurement, j == len(measurements) - 1)

    except Exception as e:
        print(f"❌ InfluxDB Connection Failed: {e}")

# Function to list databases and tables in MariaDB
def list_mariadb_tree():
    try:
        print("\n==================== MariaDB Tree ====================")
        print(f"🔗 Connecting to MariaDB at {secrets['tiledb-mariadb']['host']}...")
        connection = mysql.connector.connect(
            host=secrets["tiledb-mariadb"]["host"],
            user=secrets["tiledb-mariadb"]["user"],
            password=secrets["tiledb-mariadb"]["password"]
        )
        
        if connection.is_connected():
            print("✅ Connected to MariaDB!")
            cursor = connection.cursor()

            cursor.execute("SHOW DATABASES;")
            databases = [db[0] for db in cursor.fetchall()]
            
            if not databases:
                print("⚠️ No databases found in MariaDB.")
                return

            print("📂 MariaDB Databases:")
            for i, db in enumerate(databases):
                print_tree(0, db, i == len(databases) - 1)
                cursor.execute(f"USE {db}")
                cursor.execute("SHOW TABLES;")
                tables = [tbl[0] for tbl in cursor.fetchall()]
                
                if not tables:
                    print_tree(1, "(No Tables)", True)
                else:
                    for j, table in enumerate(tables):
                        print_tree(1, table, j == len(tables) - 1)
    
    except Error as e:
        print(f"❌ MariaDB Connection Failed: {e}")
    
    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()
            print("🔌 MariaDB Connection Closed")

# Run Tree Listing
list_influxdb_tree()
list_mariadb_tree()
