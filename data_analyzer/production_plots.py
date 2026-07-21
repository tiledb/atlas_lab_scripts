### ################################### ###
### Production Plots for DaughterBoard ###
### Version 1.0.0 ###
### ################################### ###

### ############### ###
### Package Imports ###
### ############### ###

# Basic Packages
from datetime import datetime, timedelta
import math
from pathlib import Path
import shutil

# Mathematics Packages
import numpy as np
import pandas as pd

# Plotting Packages (plotly)
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

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

# Function to print tree structure
def print_tree(level, name, is_last):
    prefix = "└── " if is_last else "├── "
    print(" " * (level * 4) + prefix + name)


# Function to backup existing plots to old subfolder with timestamp
def backup_old_plots(output_dir):
    output_path = Path(output_dir)
    old_dir = output_path / "old"
    old_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    # List of plot files to backup
    plot_files = [
        "production_overview.html",
        "lot_quality_analysis.html",
        "production_timeline.html",
        "summary_dashboard.html"
    ]
    
    for plot_file in plot_files:
        source_file = output_path / plot_file
        if source_file.exists():
            # Create backup filename with timestamp prefix
            backup_file = old_dir / f"{timestamp}_{plot_file}"
            shutil.copy2(source_file, backup_file)
            print(f"Backed up: {plot_file} -> {backup_file.name}")


# ---------------------------------------------------------
# Decode Serial Number
#
# Format: TTBBDDD
#   TT  = Tag
#   BB  = Batch
#   DDD = Position inside batch
#
# Example: 1102020
#   11 -> tag
#   02 -> batch
#   020 -> position
# ---------------------------------------------------------
def decode_serial(serial):
    serial = str(serial).zfill(7)
    return {
        "tag": int(serial[:2]),
        "batch": int(serial[2:4]),
        "position": int(serial[4:7])
    }


### ######### ###
### Main Function ###
### ######### ###

def production_plots():
    
    timenow = datetime.now()
    print(f'Current Date/Time: {timenow}')
    
    # Define output directory
    output_dir = "/var/www/html/drive/production_plots/"
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Backup existing plots before generating new ones
    print("\n==================== Backing Up Old Plots ====================")
    backup_old_plots(output_dir)
    
    ### ####### ###
    ### MariaDB ###
    ### ####### ###
    try:
        print("\n==================== MariaDB Connection ====================")
        print(f"🔗 Connecting to MariaDB at {secrets['tiledb-mariadb']['host']}...")
        connection = mysql.connector.connect(
            host=secrets["tiledb-mariadb"]["host"],
            user=secrets["tiledb-mariadb"]["user"],
            password=secrets["tiledb-mariadb"]["password"],
            autocommit=True
        )

        if connection.is_connected():
            print("✅ Connected to MariaDB!")
            cursor = connection.cursor()

        # Setting Timezone to UTC
        cursor.execute("SET time_zone = '+00:00'")

        # Select tiledb database
        cursor.execute("USE tiledb")
        
        # Query all daughterboard data with batch information
        print("\nFetching daughterboard data...")
        db_query = """
            SELECT d.serial_no, d.batch_id, d.db_status, d.burn_in,
                   d.kin_lot, d.pro_lot, d.gbt_lot,
                   d.ina_lot, d.ltm_lot, d.mos_lot, d.op4_lot, d.ok4_lot, d.ok1_lot,
                   d.mem_lot, d.sfp_lot, d.e_test, d.p_test, d.a0, d.a1, d.b0, d.b1
            FROM daughterboard d
            ORDER BY d.batch_id, d.serial_no
        """
        cursor.execute(db_query)
        db_rows = cursor.fetchall()
        db_columns = [desc[0] for desc in cursor.description]
        
        print(f"Retrieved {len(db_rows)} daughterboard records")
        
        # Convert to DataFrame
        df_daughterboards = pd.DataFrame(db_rows, columns=db_columns)
        print(f"Unique boards: {len(df_daughterboards)}")
        
        # Fetch benchtest information for each daughterboard
        print("Fetching benchtest information...")
        benchtest_query = """
            SELECT id, db_slot1, db_slot2, db_slot3, db_slot4
            FROM benchtest
            WHERE db_slot1 IS NOT NULL OR db_slot2 IS NOT NULL 
               OR db_slot3 IS NOT NULL OR db_slot4 IS NOT NULL
        """
        cursor.execute(benchtest_query)
        benchtest_rows = cursor.fetchall()
        benchtest_columns = [desc[0] for desc in cursor.description]
        df_benchtests = pd.DataFrame(benchtest_rows, columns=benchtest_columns)
        
        # Build mapping from serial_no to list of dbslot@benchtest_id
        serial_to_benchtests = {}
        for _, row in df_benchtests.iterrows():
            bt_id = int(row['id'])
            for slot_num in range(1, 5):
                slot_col = f'db_slot{slot_num}'
                serial = row[slot_col]
                if pd.notna(serial):
                    if serial not in serial_to_benchtests:
                        serial_to_benchtests[serial] = []
                    serial_to_benchtests[serial].append(f'dbslot{slot_num}@bt_{bt_id}')
        
        print(f"Found benchtest info for {len(serial_to_benchtests)} boards")
        
        # Decode serial numbers to get tag, batch, and position
        decoded = df_daughterboards['serial_no'].apply(decode_serial)
        df_daughterboards['tag'] = decoded.apply(lambda x: x['tag'])
        df_daughterboards['decoded_batch'] = decoded.apply(lambda x: x['batch'])
        df_daughterboards['position_in_batch'] = decoded.apply(lambda x: x['position'])
        
        # Filter out tags to ignore (currently only tag 90)
        tags_to_ignore = [90]
        df_daughterboards = df_daughterboards[~df_daughterboards['tag'].isin(tags_to_ignore)]
        print(f"After filtering tags {tags_to_ignore}: {len(df_daughterboards)} boards")
        
        # Sort by decoded batch and position
        df_daughterboards = df_daughterboards.sort_values(['decoded_batch', 'position_in_batch']).reset_index(drop=True)
        
        # Get batch information
        batch_query = """
            SELECT batch_id, COUNT(*) as board_count,
                   SUM(CASE WHEN db_status = 1 THEN 1 ELSE 0 END) as passed_count,
                   SUM(CASE WHEN db_status = 0 THEN 1 ELSE 0 END) as failed_count
            FROM daughterboard
            GROUP BY batch_id
            ORDER BY batch_id
        """
        cursor.execute(batch_query)
        batch_rows = cursor.fetchall()
        batch_columns = [desc[0] for desc in cursor.description]
        df_batches = pd.DataFrame(batch_rows, columns=batch_columns)
        
        # Convert numeric columns to proper types
        df_batches['board_count'] = pd.to_numeric(df_batches['board_count'])
        df_batches['passed_count'] = pd.to_numeric(df_batches['passed_count'])
        df_batches['failed_count'] = pd.to_numeric(df_batches['failed_count'])
        
        print(f"Found {len(df_batches)} batches")
        print(df_batches)
        
    except Error as e:
        print(f"❌ MariaDB Connection Failed: {e}")
        return

    ### ######## ###
    ### InfluxDB ###
    ### ######## ###
    
    influx_data = {}
    try:
        print("\n==================== InfluxDB Connection ====================")
        print(f"🔗 Connecting to InfluxDB at {secrets['tiledb-influxdb']['host']}:{secrets['tiledb-influxdb']['port']}...")
        client = InfluxDBClient(
            host=secrets["tiledb-influxdb"]["host"],
            port=secrets["tiledb-influxdb"]["port"],
            username=secrets["tiledb-influxdb"]["username"],
            password=secrets["tiledb-influxdb"]["password"]
        )
        client.ping()
        print("✅ Connected to InfluxDB!")
        
        client.switch_database("tiledb")
        
        # Define InfluxDB Tables
        VarTables = ["Link Status", "xADC", "ADC_Linearity", "CIS_Linearity", "CIS", "Integrator_Linearity"]
        TagTables = ["V"]
        
    except Exception as e:
        print(f"❌ InfluxDB Connection Failed: {e}")
        return

    ### ################# ###
    ### Production Plots ###
    ### ################# ###
    
    print("\n==================== Generating Production Plots ====================")
    
    # 1. Production Overview Plot (Individual Boards)
    print("Generating production overview plot...")
    fig_production_overview = go.Figure()
    
    colors = {1: '#00CC96', 0: '#EF553B', None: '#FECB52'}  # Pass=Green, Fail=Red, No Test=Yellow
    
    lot_columns = ['kin_lot', 'pro_lot', 'gbt_lot', 'ina_lot', 'ltm_lot', 'mos_lot', 
                   'op4_lot', 'ok4_lot', 'ok1_lot', 'mem_lot', 'sfp_lot']
    
    # Get unique decoded batches for x-axis
    unique_batches = sorted(df_daughterboards['decoded_batch'].unique())
    
    # Collect all shapes to add later
    shapes = []
    
    for idx, row in df_daughterboards.iterrows():
        status = row['db_status']
        e_test = row['e_test']
        p_test = row['p_test']
        
        # Determine color based on dbstatus, e_test, and p_test
        # Green if all are 1, Red if any is 0, Yellow if any is NULL
        if pd.isna(status) or pd.isna(e_test) or pd.isna(p_test):
            color = colors[None]  # Yellow for NULL
        elif status == 1 and e_test == 1 and p_test == 1:
            color = colors[1]  # Green for all pass
        else:
            color = colors[0]  # Red for any fail
        
        # Get shape based on burn_in value
        burn_in = row['burn_in']
        
        x_center = row['decoded_batch']
        y_bottom = row['position_in_batch']
        
        # Build hover text with all lot information
        hover_text = f"Serial No: {row['serial_no']}<br>"
        hover_text += f"Tag: {row['tag']}<br>"
        hover_text += f"Decoded Batch: {row['decoded_batch']}<br>"
        hover_text += f"Position in Batch: {row['position_in_batch']}<br>"
        hover_text += f"Batch ID: {row['batch_id']}<br>"
        hover_text += f"Burn In: {burn_in}<br>"
        hover_text += f"db_status: {status}<br>"
        hover_text += f"e_test: {int(e_test) if pd.notna(e_test) else 'N/A'}<br>"
        hover_text += f"p_test: {int(p_test) if pd.notna(p_test) else 'N/A'}<br>"
        
        # Add benchtest slot information
        serial = row['serial_no']
        if serial in serial_to_benchtests:
            hover_text += "<br>Benchtest Slots:<br>"
            for bt_slot in serial_to_benchtests[serial]:
                hover_text += f"  {bt_slot}<br>"
        
        hover_text += "<br>Component Lots:<br>"
        for lot_col in lot_columns:
            lot_value = row[lot_col]
            if pd.notna(lot_value):
                hover_text += f"  {lot_col}: {lot_value}<br>"
                # Add a0, b0, a1, b1 under sfp_lot
                if lot_col == 'sfp_lot':
                    hover_text += f"    a0: {row['a0']}<br>"
                    hover_text += f"    b0: {row['b0']}<br>"
                    hover_text += f"    a1: {row['a1']}<br>"
                    hover_text += f"    b1: {row['b1']}<br>"
        
        # Add invisible scatter for hover functionality and click events
        fig_production_overview.add_trace(go.Scatter(
            x=[x_center],
            y=[y_bottom + 0.5],
            mode='markers',
            marker=dict(size=0.1, opacity=0, color=color),
            hovertemplate=hover_text + '<extra></extra>',
            customdata=[hover_text],
            showlegend=False
        ))
        
        # Add shape based on burn_in
        if burn_in == 1:
            # Square: rectangle from (x-0.5, y) to (x+0.5, y+1)
            shapes.append(dict(
                type='rect',
                x0=x_center - 0.5,
                y0=y_bottom,
                x1=x_center + 0.5,
                y1=y_bottom + 1,
                fillcolor=color,
                line=dict(color='black', width=1)
            ))
        elif burn_in == 0:
            # Hexagon: 6 points centered at (x, y+0.5)
            # Hexagon points for a 1x1 cell
            cx, cy = x_center, y_bottom + 0.5
            hex_points = [
                [cx - 0.5, cy],           # left
                [cx - 0.25, cy + 0.433], # top-left
                [cx + 0.25, cy + 0.433], # top-right
                [cx + 0.5, cy],           # right
                [cx + 0.25, cy - 0.433], # bottom-right
                [cx - 0.25, cy - 0.433]  # bottom-left
            ]
            # Flatten for plotly
            hex_x = [p[0] for p in hex_points] + [hex_points[0][0]]
            hex_y = [p[1] for p in hex_points] + [hex_points[0][1]]
            
            shapes.append(dict(
                type='path',
                path=f'M {hex_x[0]},{hex_y[0]} ' + ' '.join([f'L {x},{y}' for x, y in zip(hex_x[1:], hex_y[1:])]) + ' Z',
                fillcolor=color,
                line=dict(color='black', width=1)
            ))
    
    fig_production_overview.update_layout(
        title=f"TileDaughterboard Production Overview ({timenow.strftime('%Y-%m-%d - %H:%M:%S')})",
        xaxis_title="Decoded Batch (from Serial No)",
        yaxis_title="Position in Batch (from Serial No)",
        height=700,
        showlegend=True,
        xaxis=dict(
            range=[-0.5, 15.5],  # Cover boundary conditions
            tickmode='linear',
            tick0=0,
            dtick=1
        ),
        yaxis=dict(
            range=[-0.5, 81.5],  # Cover boundary conditions
            tickmode='linear',
            tick0=0,
            dtick=5
        ),
        shapes=shapes
    )
    
    # Add custom legend for status
    fig_production_overview.add_trace(go.Scatter(
        x=[None], y=[None],
        mode='markers',
        marker=dict(size=20, color=colors[1], symbol='square'),
        name='Passed'
    ))
    fig_production_overview.add_trace(go.Scatter(
        x=[None], y=[None],
        mode='markers',
        marker=dict(size=20, color=colors[0], symbol='square'),
        name='Failed'
    ))
    fig_production_overview.add_trace(go.Scatter(
        x=[None], y=[None],
        mode='markers',
        marker=dict(size=20, color=colors[None], symbol='square'),
        name='No Test'
    ))
    
    # Add legend for burn_in shapes
    fig_production_overview.add_trace(go.Scatter(
        x=[None], y=[None],
        mode='markers',
        marker=dict(size=20, color='gray', symbol='hexagon'),
        name='Burn In: 0'
    ))
    fig_production_overview.add_trace(go.Scatter(
        x=[None], y=[None],
        mode='markers',
        marker=dict(size=20, color='gray', symbol='square'),
        name='Burn In: 1'
    ))
    
    # Add custom JavaScript for click-to-show modal
    custom_js = """
    <script>
    document.addEventListener('DOMContentLoaded', function() {
        // Create modal element
        var modal = document.createElement('div');
        modal.id = 'info-modal';
        modal.style.cssText = `
            display: none;
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
            z-index: 10000;
            max-width: 500px;
            max-height: 80vh;
            overflow-y: auto;
            font-family: Arial, sans-serif;
            font-size: 14px;
        `;
        
        // Create close button
        var closeBtn = document.createElement('button');
        closeBtn.innerHTML = '&times;';
        closeBtn.style.cssText = `
            position: absolute;
            top: 10px;
            right: 15px;
            font-size: 24px;
            cursor: pointer;
            background: none;
            border: none;
            color: #666;
        `;
        closeBtn.onclick = function() {
            modal.style.display = 'none';
            overlay.style.display = 'none';
        };
        
        // Create content div
        var content = document.createElement('div');
        content.id = 'modal-content';
        
        modal.appendChild(closeBtn);
        modal.appendChild(content);
        document.body.appendChild(modal);
        
        // Create overlay
        var overlay = document.createElement('div');
        overlay.id = 'modal-overlay';
        overlay.style.cssText = `
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.5);
            z-index: 9999;
        `;
        overlay.onclick = function() {
            modal.style.display = 'none';
            overlay.style.display = 'none';
        };
        document.body.appendChild(overlay);
        
        // Function to parse hover text and create tables
        function formatHoverText(hoverText) {
            var html = '';
            
            // Split by section headers
            var parts = hoverText.split(/<br>Benchtest Slots:|<br>Component Lots:/);
            
            // Part 0: Info section (before first header)
            var infoSection = parts[0] || '';
            var infoLines = infoSection.split('<br>');
            
            html += '<h3 style="margin-top: 0; margin-bottom: 10px; color: #333; border-bottom: 2px solid #00CC96; padding-bottom: 5px;">Info</h3>';
            html += '<table style="width: 100%; border-collapse: collapse; margin-bottom: 15px;">';
            for (var i = 0; i < infoLines.length; i++) {
                var line = infoLines[i].trim();
                if (line && line.includes(':')) {
                    var lineParts = line.split(':');
                    if (lineParts.length === 2) {
                        html += '<tr><td style="padding: 5px; border: 1px solid #ddd; font-weight: bold; background: #f5f5f5;">' + lineParts[0] + '</td><td style="padding: 5px; border: 1px solid #ddd;">' + lineParts[1] + '</td></tr>';
                    }
                }
            }
            html += '</table>';
            
            // Part 1: Status & Tests section (between Benchtest Slots and Component Lots)
            var statusSection = parts[1] || '';
            var statusLines = statusSection.split('<br>');
            
            html += '<h3 style="margin-top: 0; margin-bottom: 10px; color: #333; border-bottom: 2px solid #00CC96; padding-bottom: 5px;">Status & Tests</h3>';
            html += '<table style="width: 100%; border-collapse: collapse; margin-bottom: 15px;">';
            for (var i = 0; i < statusLines.length; i++) {
                var line = statusLines[i].trim();
                if (line && line.includes(':')) {
                    var lineParts = line.split(':');
                    if (lineParts.length === 2) {
                        html += '<tr><td style="padding: 5px; border: 1px solid #ddd; font-weight: bold; background: #f5f5f5;">' + lineParts[0] + '</td><td style="padding: 5px; border: 1px solid #ddd;">' + lineParts[1] + '</td></tr>';
                    }
                } else if (line && (line.includes('dbslot') || line.includes('bt_'))) {
                    html += '<tr><td colspan="2" style="padding: 5px; border: 1px solid #ddd; background: #fafafa;">' + line + '</td></tr>';
                }
            }
            html += '</table>';
            
            // Part 2: Component Lots section (after Component Lots)
            var lotsSection = parts[2] || '';
            var lotsLines = lotsSection.split('<br>');
            
            html += '<h3 style="margin-top: 0; margin-bottom: 10px; color: #333; border-bottom: 2px solid #00CC96; padding-bottom: 5px;">Component Lots</h3>';
            html += '<table style="width: 100%; border-collapse: collapse; margin-bottom: 15px;">';
            for (var i = 0; i < lotsLines.length; i++) {
                var line = lotsLines[i].trim();
                if (line && line.includes(':')) {
                    var lineParts = line.split(':');
                    if (lineParts.length === 2) {
                        if (lineParts[0].includes('a0') || lineParts[0].includes('b0') || lineParts[0].includes('a1') || lineParts[0].includes('b1')) {
                            html += '<tr><td style="padding: 5px 5px 5px 20px; border: 1px solid #ddd; font-weight: bold; background: #fafafa;">' + lineParts[0] + '</td><td style="padding: 5px; border: 1px solid #ddd;">' + lineParts[1] + '</td></tr>';
                        } else {
                            html += '<tr><td style="padding: 5px; border: 1px solid #ddd; font-weight: bold; background: #f5f5f5;">' + lineParts[0] + '</td><td style="padding: 5px; border: 1px solid #ddd;">' + lineParts[1] + '</td></tr>';
                        }
                    }
                }
            }
            html += '</table>';
            
            return html;
        }
        
        // Add click event listener to plot
        var plotDiv = document.getElementsByClassName('plotly-graph-div')[0];
        if (plotDiv) {
            plotDiv.on('plotly_click', function(data) {
                var point = data.points[0];
                if (point.data.customdata && point.data.customdata[0]) {
                    content.innerHTML = formatHoverText(point.data.customdata[0]);
                    modal.style.display = 'block';
                    overlay.style.display = 'block';
                }
            });
        }
    });
    </script>
    """
    
    fig_production_overview.write_html(
        output_dir + "production_overview.html",
        config={'displayModeBar': True, 'responsive': True},
        include_plotlyjs=True,
        full_html=True
    )
    
    # Read the generated HTML and inject custom JS
    with open(output_dir + "production_overview.html", 'r') as f:
        html_content = f.read()
    
    # Insert custom JS before closing body tag
    html_content = html_content.replace('</body>', custom_js + '</body>')
    
    # Write back
    with open(output_dir + "production_overview.html", 'w') as f:
        f.write(html_content)
    
    print("✅ Production overview plot saved with click-to-modal feature")
    
    # 4. Summary Dashboard
    print("Generating summary dashboard...")
    
    total_boards = len(df_daughterboards)
    total_passed = df_daughterboards['db_status'].sum()
    total_failed = total_boards - total_passed
    overall_yield = (total_passed / total_boards * 100) if total_boards > 0 else 0
    
    fig_summary = make_subplots(
        rows=1, cols=2,
        subplot_titles=["Overall Status", "Batch Distribution"],
        specs=[[{"type": "pie"}, {"type": "bar"}]]
    )
    
    # Overall Status Pie
    fig_summary.add_trace(
        go.Pie(labels=['Passed', 'Failed'], values=[total_passed, total_failed],
               marker=dict(colors=['#00CC96', '#EF553B'])),
        row=1, col=1
    )
    
    # Batch Distribution - use decoded_batch from serial parser
    batch_distribution = df_daughterboards['decoded_batch'].value_counts().sort_index()
    fig_summary.add_trace(
        go.Bar(x=batch_distribution.index, y=batch_distribution.values,
               marker_color='#636EFA'),
        row=1, col=2
    )
    
    fig_summary.update_layout(
        title=f"Production Summary Dashboard - Total Boards: {total_boards}, Yield: {overall_yield:.1f}%",
        height=400,
        showlegend=False
    )
    fig_summary.update_xaxes(title_text="Decoded Batch", row=1, col=2)
    fig_summary.update_yaxes(title_text="Board Count", row=1, col=2)
    
    fig_summary.write_html(output_dir + "summary_dashboard.html")
    print("✅ Summary dashboard saved")
    
    # Close connections
    cursor.close()
    connection.close()
    client.close()
    
    print(f"\n==================== Production Plots Complete ====================")
    print(f"All plots saved to: {output_dir}")
    print(f"Generated plots:")
    print(f"  - production_overview.html")
    print(f"  - summary_dashboard.html")


### ######### ###
### Executing ###
### ######### ###

# Load Config
config = load_yaml_conf("vars.yaml")
secrets = load_yaml_conf("../secrets/secrets.yaml")

# Execute main()
if __name__ == "__main__":
    production_plots()
