import yaml
import mysql.connector
from mysql.connector import Error
import readline

# Load secrets from secrets.yaml
def load_secrets(filepath="../../secrets/secrets.yaml"):
    with open(filepath, "r") as file:
        return yaml.safe_load(file)

secrets = load_secrets()

# Function to print tree structure
def print_tree(level, name, is_last):
    prefix = "└── " if is_last else "├── "
    print(" " * (level * 4) + prefix + name)

# Function for enabling auto-completion on the command line
def enable_autocomplete(options):
    def completer(text, state):
        matches = [option for option in options if option.startswith(text)]
        if state < len(matches):
            return matches[state]
        else:
            return None
    readline.set_completer(completer)
    readline.parse_and_bind("tab: complete")  # Tab completion
    readline.parse_and_bind("set enable-keypad on")  # Ensure keypad works for arrow keys

# Function to list MariaDB databases and tables
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

            # List all databases
            cursor.execute("SHOW DATABASES;")
            databases = [db[0] for db in cursor.fetchall()]

            if not databases:
                print("⚠️ No databases found in MariaDB.")
                return

            print("📂 MariaDB Databases:")
            for i, db in enumerate(databases):
                print_tree(0, db, i == len(databases) - 1)

            # Enable auto-completion for database names
            enable_autocomplete(databases)

            # Ask user to select a valid database
            while True:
                db_choice = input("\n📌 Enter the MariaDB database name: ").strip()
                if db_choice in databases:
                    cursor.execute(f"USE {db_choice}")
                    break
                else:
                    print("❌ Database not found. Please enter a valid database.")

            # List all tables in the selected database
            cursor.execute("SHOW TABLES;")
            tables = [tbl[0] for tbl in cursor.fetchall()]

            if not tables:
                print("⚠️ No tables found in the selected database.")
                return

            print(f"\n📊 Tables in '{db_choice}':")
            for i, table in enumerate(tables):
                print_tree(1, table, i == len(tables) - 1)

            # Enable auto-completion for table names
            enable_autocomplete(tables)

            # Ask user to select a valid table
            while True:
                table_choice = input("\n📌 Enter the table to view data: ").strip()
                if table_choice in tables:
                    break
                else:
                    print("❌ Table not found. Please enter a valid table.")

            # Query and display data from the selected table
            cursor.execute(f"SELECT * FROM {table_choice}")
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            if rows:
                print(f"\n📊 Data from MariaDB ({table_choice}):")
                print(" | ".join(columns))
                for row in rows:
                    print(" | ".join(map(str, row)))
            else:
                print("⚠️ No data found in the selected table.")
            
            # Ask if the user wants to insert a new entry
            insert_choice = input("\nDo you want to insert a new entry into this table? (y/n): ").strip().lower()
            if insert_choice == "y":
                # Get column names and data types to prompt for user input, excluding the primary key
                print(f"\n📝 Inserting a new row into '{table_choice}'")
                column_values = {}
                primary_key_column = None

                # Identify the primary key column and retrieve data types
                cursor.execute(f"DESCRIBE {table_choice};")
                columns_info = cursor.fetchall()

                for column in columns_info:
                    column_name, column_type, is_nullable, key = column[0], column[1], column[2], column[3]
                    if key == "PRI":
                        primary_key_column = column_name  # Mark primary key column

                # Collect user input for non-primary key columns and display data type
                for column in columns:
                    if column != primary_key_column:
                        # Get the data type of the column
                        column_type = next((col[1] for col in columns_info if col[0] == column), None)
                        print(f"\nColumn: '{column}' (Type: {column_type})")
                        value = input(f"Enter value for '{column}': ").strip()
                        column_values[column] = value

                # Create SQL INSERT statement excluding the primary key column
                columns_str = ", ".join([col for col in columns if col != primary_key_column])
                values_str = ", ".join([f"'{column_values[col]}'" for col in columns if col != primary_key_column])

                # Insert the data
                insert_query = f"INSERT INTO {table_choice} ({columns_str}) VALUES ({values_str})"
                cursor.execute(insert_query)
                connection.commit()
                print("✅ Data inserted successfully!")

    except Error as e:
        print(f"❌ MariaDB Connection Failed: {e}")

    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()
            print("🔌 MariaDB Connection Closed")

# Run MariaDB Tree Listing
list_mariadb_tree()
