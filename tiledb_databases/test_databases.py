import yaml
from influxdb import InfluxDBClient
import mysql.connector
from mysql.connector import Error

# Load secrets from secrets.yaml
def load_secrets(filepath="../secrets/secrets.yaml"):
    with open(filepath, "r") as file:
        return yaml.safe_load(file)

secrets = load_secrets()

# InfluxDB Connection Check with Data Write, Read, Verify, and Delete
def check_influxdb():
    try:
        print("\n==================== InfluxDB Test ====================")
        print(f"🔗 Connecting to InfluxDB at {secrets['tiledb-influxdb']['host']}:{secrets['tiledb-influxdb']['port']}...")
        client = InfluxDBClient(
            host=secrets["tiledb-influxdb"]["host"],
            port=secrets["tiledb-influxdb"]["port"],
            username=secrets["tiledb-influxdb"]["username"],
            password=secrets["tiledb-influxdb"]["password"],
            database=secrets["tiledb-influxdb"]["database"]
        )
        client.ping()
        print("✅ Connected to InfluxDB!")
        
        # Write test data
        written_data = {"value": 1234}  # Store written data
        json_body = [{
            "measurement": "test_measurement",
            "fields": written_data
        }]
        client.write_points(json_body)
        print(f"📝 Data written to InfluxDB: {json_body}")
        
        # Read data
        result = client.query("SELECT * FROM test_measurement")
        points = list(result.get_points())

        if points:
            retrieved_data = points[0]  # Get the first retrieved row
            print(f"🔍 Retrieved data from InfluxDB: {retrieved_data}")
            
            # Compare written and retrieved data
            if retrieved_data["value"] == written_data["value"]:
                print("✅ Data verification successful for InfluxDB!")
            else:
                print("❌ Data mismatch in InfluxDB!")
        else:
            print("⚠️ No data retrieved from InfluxDB")
        
        # Delete data
        client.query("DROP MEASUREMENT test_measurement")
        print("🗑️ Data deleted from InfluxDB: test_measurement")
    
    except Exception as e:
        print(f"❌ InfluxDB Connection Failed: {e}")

# MariaDB Connection Check with Data Write, Read, Verify, and Delete
def check_mariadb():
    try:
        print("\n==================== MariaDB Test ====================")
        print(f"🔗 Connecting to MariaDB at {secrets['tiledb-mariadb']['host']}...")
        connection = mysql.connector.connect(
            host=secrets["tiledb-mariadb"]["host"],
            user=secrets["tiledb-mariadb"]["user"],
            password=secrets["tiledb-mariadb"]["password"],
            database=secrets["tiledb-mariadb"]["database"]
        )
        
        if connection.is_connected():
            print("✅ Connected to MariaDB!")
            cursor = connection.cursor()

            # Write test data
            written_data = 1234  # Store written value
            cursor.execute("CREATE TABLE IF NOT EXISTS test_table (id INT AUTO_INCREMENT PRIMARY KEY, value INT)")
            cursor.execute("INSERT INTO test_table (value) VALUES (%s)", (written_data,))
            connection.commit()
            print(f"📝 Data written to MariaDB: {written_data}")
            
            # Read data
            cursor.execute("SELECT value FROM test_table")
            rows = cursor.fetchall()
            
            if rows:
                retrieved_data = rows[0][0]  # Get the first retrieved value
                print(f"🔍 Retrieved data from MariaDB: {retrieved_data}")

                # Compare written and retrieved data
                if retrieved_data == written_data:
                    print("✅ Data verification successful for MariaDB!")
                else:
                    print("❌ Data mismatch in MariaDB!")
            else:
                print("⚠️ No data retrieved from MariaDB")
            
            # Delete data
            cursor.execute("DROP TABLE test_table")
            connection.commit()
            print("🗑️ Data deleted from MariaDB: test_table")
    
    except Error as e:
        print(f"❌ MariaDB Connection Failed: {e}")
    
    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()
            print("🔌 MariaDB Connection Closed")

# Run Tests
check_influxdb()
check_mariadb()
