import yaml
from influxdb import InfluxDBClient

# Load secrets from secrets.yaml
def load_secrets(filepath="../../secrets/secrets.yaml"):
    with open(filepath, "r") as file:
        return yaml.safe_load(file)

secrets = load_secrets()

# Function to print tree structure
def print_tree(level, name, is_last):
    prefix = "└── " if is_last else "├── "
    print(" " * (level * 4) + prefix + name)

# Function to list InfluxDB databases and measurements
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

        # Fetch and display databases
        databases = [db["name"] for db in client.get_list_database()]
        if not databases:
            print("⚠️ No databases found in InfluxDB.")
            return

        print("📂 InfluxDB Databases:")
        for i, db_name in enumerate(databases):
            print_tree(0, db_name, i == len(databases) - 1)

        # Ask user to select a valid database
        while True:
            db_choice = input("\n📌 Enter the InfluxDB database name: ").strip()
            if db_choice in databases:
                client.switch_database(db_choice)
                break
            else:
                print("❌ Database not found. Please enter a valid database.")

        # Fetch and display measurements
        result = client.query("SHOW MEASUREMENTS")
        measurements = [m["name"] for m in result.get_points()]

        if not measurements:
            print("⚠️ No measurements found in the selected database.")
            return

        print(f"\n📊 Measurements in '{db_choice}':")
        for i, measurement in enumerate(measurements):
            print_tree(1, measurement, i == len(measurements) - 1)

        # Ask user to select a valid measurement
        while True:
            measurement_choice = input("\n📌 Enter the measurement to view data: ").strip()
            if measurement_choice in measurements:
                break
            else:
                print("❌ Measurement not found. Please enter a valid measurement.")

        # Ask user for the number of records to display
        while True:
            try:
                limit = int(input("📌 Enter the number of records to display: "))
                if limit > 0:
                    break
                else:
                    print("❌ Please enter a positive integer.")
            except ValueError:
                print("❌ Invalid input. Please enter a valid number.")

        # Query and display data
        result = client.query(f"SELECT * FROM {measurement_choice} LIMIT {limit}")
        points = list(result.get_points())

        if points:
            print(f"\n📊 Data from InfluxDB ({measurement_choice}):")
            for point in points:
                print(point)
        else:
            print("⚠️ No data found in the selected measurement.")

    except Exception as e:
        print(f"❌ InfluxDB Connection Failed: {e}")

# Run InfluxDB Tree Listing
list_influxdb_tree()
