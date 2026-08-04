### ################################### ###
### Production Overview Plots Library ###
### Version 1.0.0 ###
### ################################### ###

### ############### ###
### Package Imports ###
### ############### ###

import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

### ######### ###
### Functions ###
### ######### ###

def create_production_overview_plot(df_daughterboards, serial_to_benchtests, timenow, get_failed_tests_func=None, serial_to_benchtest_test_stop=None, serial_to_benchtest_test_op=None, serial_to_has_post_burnin_test=None, serial_to_ignored_benchtests=None, serial_to_ignored_benchtest_test_stop=None, serial_to_ignored_benchtest_test_op=None):
    """
    Create the production overview plot showing individual boards with status colors and shapes.
    
    Args:
        df_daughterboards: DataFrame containing daughterboard data
        serial_to_benchtests: Dictionary mapping serial numbers to benchtest slots
        timenow: Current datetime for title timestamp
        get_failed_tests_func: Optional function to get failed tests for a serial/benchtest
        serial_to_benchtest_test_stop: Optional dictionary mapping serial numbers to dict of benchtest_slot -> test_stop
        serial_to_benchtest_test_op: Optional dictionary mapping serial numbers to dict of benchtest_slot -> test_op
        serial_to_has_post_burnin_test: Optional dictionary mapping serial numbers to bool indicating post-burn-in test
        serial_to_ignored_benchtests: Optional dictionary mapping serial numbers to ignored benchtest slots (test_pass = -1)
        serial_to_ignored_benchtest_test_stop: Optional dictionary mapping serial numbers to dict of ignored benchtest_slot -> test_stop
        serial_to_ignored_benchtest_test_op: Optional dictionary mapping serial numbers to dict of ignored benchtest_slot -> test_op
        
    Returns:
        fig: Plotly Figure object
    """
    fig_production_overview = go.Figure()
    
    colors = {1: '#00CC96', 0: '#EF553B', None: '#FECB52', 'sfp_none': '#90EE90'}  # Pass=Green, Fail=Red, No Test=Yellow, SFP None=Light Green
    
    lot_columns = ['kin_lot', 'pro_lot', 'gbt_lot', 'ina_lot', 'ltm_lot', 'mos_lot', 
                   'op4_lot', 'ok4_lot', 'ok1_lot', 'mem_lot', 'sfp_lot']
    
    # Get unique decoded batches for x-axis
    unique_batches = sorted(df_daughterboards['decoded_batch'].unique())
    
    # Collect all shapes to add later
    shapes = []
    
    # Counters for legend statistics
    count_passed = 0
    count_failed = 0
    count_no_test = 0
    count_sfp_none = 0
    count_not_burned = 0
    count_burned_no_post = 0
    count_burned_post = 0
    
    for idx, row in df_daughterboards.iterrows():
        status = row['db_status']
        e_test = row['e_test']
        p_test = row['p_test']
        serial = row['serial_no']
        
        # Determine color based on dbstatus, e_test, p_test, and sfp slots
        # Precedence: Failed (with benchtest) > No Test > Missing SFP Data > Passed
        has_benchtest = serial in serial_to_benchtests
        
        if (status == 0 or e_test == 0 or p_test == 0) and has_benchtest:
            color = colors[0]  # Red for fail with benchtest (highest priority)
            count_failed += 1
        elif status == 0 and not has_benchtest:
            color = colors[None]  # Yellow for db_status=0 with no benchtest (No Test)
            count_no_test += 1
        elif pd.isna(status) or pd.isna(e_test) or pd.isna(p_test):
            color = colors[None]  # Yellow for NULL (No Test)
            count_no_test += 1
        elif pd.isna(row['a0']) or pd.isna(row['a1']) or pd.isna(row['b0']) or pd.isna(row['b1']):
            color = colors['sfp_none']  # Light green for missing SFP data
            count_sfp_none += 1
        elif status == 1 and e_test == 1 and p_test == 1:
            color = colors[1]  # Green for all pass
            count_passed += 1
        else:
            color = colors[0]  # Red for any other fail
            count_failed += 1
        
        # Get shape based on burn-in status and post-burn-in testing
        burn_in_stop = row['burn_in_stop']
        
        # Determine shape based on burn-in status
        if pd.isna(burn_in_stop):
            # Not burned in
            shape = 'pentagon'
            count_not_burned += 1
        else:
            # Burned in - check if has post-burn-in test
            if serial_to_has_post_burnin_test and serial in serial_to_has_post_burnin_test:
                if serial_to_has_post_burnin_test[serial]:
                    # Has post-burn-in test
                    shape = 'square'
                    count_burned_post += 1
                else:
                    # No post-burn-in test
                    shape = 'hexagon'
                    count_burned_no_post += 1
            else:
                # Default to hexagon if no info
                shape = 'hexagon'
                count_burned_no_post += 1
        
        x_center = row['decoded_batch']
        y_bottom = row['position_in_batch']
        
        # Build hover text with all lot information
        hover_text = f"Serial No: {row['serial_no']}<br>"
        hover_text += f"Tag: {row['tag']}<br>"
        hover_text += f"Decoded Batch: {row['decoded_batch']}<br>"
        hover_text += f"Position in Batch: {row['position_in_batch']}<br>"
        hover_text += f"Batch ID: {row['batch_id']}<br>"
        hover_text += f"Burn In Stop: {row['burn_in_stop'] if pd.notna(row['burn_in_stop']) else 'NULL'}<br>"
        hover_text += f"db_status: {status}<br>"
        hover_text += f"e_test: {int(e_test) if pd.notna(e_test) else 'N/A'}<br>"
        hover_text += f"p_test: {int(p_test) if pd.notna(p_test) else 'N/A'}<br>"
        
        # Add benchtest slot information
        serial = row['serial_no']
        burn_in_stop = row['burn_in_stop']
        if serial in serial_to_benchtests:
            hover_text += "<br>Benchtest Slots:<br>"
            for bt_slot in serial_to_benchtests[serial]:
                hover_text += f"  • {bt_slot}"
                
                # Get test_stop and test_op values
                test_stop = None
                test_op = None
                if serial_to_benchtest_test_stop and serial in serial_to_benchtest_test_stop:
                    if bt_slot in serial_to_benchtest_test_stop[serial]:
                        test_stop = serial_to_benchtest_test_stop[serial][bt_slot]
                if serial_to_benchtest_test_op and serial in serial_to_benchtest_test_op:
                    if bt_slot in serial_to_benchtest_test_op[serial]:
                        test_op = serial_to_benchtest_test_op[serial][bt_slot]
                
                # Format as: (op: "test_op" date: YYYY-MM-DD)
                if pd.notna(test_op) or pd.notna(test_stop):
                    hover_text += " ("
                    if pd.notna(test_op):
                        hover_text += f'op: "{test_op}"'
                    if pd.notna(test_stop):
                        # Extract date part (YYYY-MM-DD) from timestamp
                        test_date = str(test_stop).split()[0] if pd.notna(test_stop) else 'N/A'
                        if pd.notna(test_op):
                            hover_text += " "
                        hover_text += f"date: {test_date}"
                    hover_text += ")"
                
                # Check if burned in before this benchtest (burn_in_stop < test_stop)
                if pd.notna(burn_in_stop) and pd.notna(test_stop):
                    if burn_in_stop < test_stop:
                        hover_text += " (burned)"
                    else:
                        hover_text += " (not burned)"
                elif pd.notna(burn_in_stop):
                    # Board was burned in but this test has no test_stop
                    hover_text += " (not burned)"
                elif pd.isna(burn_in_stop):
                    # Board was never burned in
                    hover_text += " (not burned)"
                
                hover_text += "<br>"
                # Check for failed tests if function is provided
                if get_failed_tests_func:
                    failed_tests = get_failed_tests_func(serial, bt_slot)
                    if failed_tests:
                        for failed_test in failed_tests:
                            hover_text += f"    - {failed_test}<br>"
        
        # Add ignored benchtest slot information (test_pass = -1)
        if serial_to_ignored_benchtests and serial in serial_to_ignored_benchtests:
            hover_text += "<br>Ignored Benchtest Slots:<br>"
            for bt_slot in serial_to_ignored_benchtests[serial]:
                hover_text += f"  • {bt_slot}"
                
                # Get test_stop and test_op values
                test_stop = None
                test_op = None
                if serial_to_ignored_benchtest_test_stop and serial in serial_to_ignored_benchtest_test_stop:
                    if bt_slot in serial_to_ignored_benchtest_test_stop[serial]:
                        test_stop = serial_to_ignored_benchtest_test_stop[serial][bt_slot]
                if serial_to_ignored_benchtest_test_op and serial in serial_to_ignored_benchtest_test_op:
                    if bt_slot in serial_to_ignored_benchtest_test_op[serial]:
                        test_op = serial_to_ignored_benchtest_test_op[serial][bt_slot]
                
                # Format as: (op: "test_op" date: YYYY-MM-DD)
                if pd.notna(test_op) or pd.notna(test_stop):
                    hover_text += " ("
                    if pd.notna(test_op):
                        hover_text += f'op: "{test_op}"'
                    if pd.notna(test_stop):
                        # Extract date part (YYYY-MM-DD) from timestamp
                        test_date = str(test_stop).split()[0] if pd.notna(test_stop) else 'N/A'
                        if pd.notna(test_op):
                            hover_text += " "
                        hover_text += f"date: {test_date}"
                    hover_text += ")"
                
                hover_text += "<br>"
        
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
        
        # Add shape based on burn-in status and post-burn-in testing
        if shape == 'pentagon':
            # Pentagon: 5 points centered at (x, y+0.5)
            cx, cy = x_center, y_bottom + 0.5
            pentagon_points = [
                [cx, cy + 0.5],           # top
                [cx + 0.5, cy + 0.15],    # top-right
                [cx + 0.35, cy - 0.4],    # bottom-right
                [cx - 0.35, cy - 0.4],    # bottom-left
                [cx - 0.5, cy + 0.15]     # top-left
            ]
            shapes.append(dict(
                type='path',
                path='M ' + ' L '.join([f'{p[0]},{p[1]}' for p in pentagon_points]) + ' Z',
                fillcolor=color,
                line=dict(color='black', width=1)
            ))
        elif shape == 'hexagon':
            # Hexagon: 6 points centered at (x, y+0.5)
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
        elif shape == 'square':
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
    
    # Calculate total boards for legend
    total_boards = len(df_daughterboards)
    
    fig_production_overview.update_layout(
        title=dict(
            text=f"TileDaughterboard Production Overview ({timenow.strftime('%Y-%m-%d - %H:%M:%S')})",
            font=dict(size=24)
        ),
        xaxis=dict(
            title=dict(text="Decoded Batch (from Serial No)", font=dict(size=18)),
            range=[-0.5, 15.5],  # Cover boundary conditions
            tickmode='linear',
            tick0=0,
            dtick=1,
            tickfont=dict(size=14)
        ),
        yaxis=dict(
            title=dict(text="Position in Batch (from Serial No)", font=dict(size=18)),
            range=[-0.5, 81.5],  # Cover boundary conditions
            tickmode='linear',
            tick0=0,
            dtick=5,
            tickfont=dict(size=14)
        ),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.25,
            xanchor="center",
            x=0.5,
            font=dict(size=14)
        ),
        shapes=shapes,
        margin=dict(b=220)  # Bottom margin for legend
    )
    
    # Add custom legend for status
    fig_production_overview.add_trace(go.Scatter(
        x=[None], y=[None],
        mode='markers',
        marker=dict(size=20, color=colors[1], symbol='square'),
        name=f'Passed ({count_passed}/{total_boards})'
    ))
    fig_production_overview.add_trace(go.Scatter(
        x=[None], y=[None],
        mode='markers',
        marker=dict(size=20, color=colors[0], symbol='square'),
        name=f'Failed ({count_failed}/{total_boards})'
    ))
    fig_production_overview.add_trace(go.Scatter(
        x=[None], y=[None],
        mode='markers',
        marker=dict(size=20, color=colors[None], symbol='square'),
        name=f'No Test ({count_no_test}/{total_boards})'
    ))
    fig_production_overview.add_trace(go.Scatter(
        x=[None], y=[None],
        mode='markers',
        marker=dict(size=20, color=colors['sfp_none'], symbol='square'),
        name=f'Missing SFP Data ({count_sfp_none}/{total_boards})'
    ))
    
    # Add legend for burn-in status shapes
    fig_production_overview.add_trace(go.Scatter(
        x=[None], y=[None],
        mode='markers',
        marker=dict(size=20, color='gray', symbol='pentagon'),
        name=f'Not Burned In ({count_not_burned}/{total_boards})'
    ))
    fig_production_overview.add_trace(go.Scatter(
        x=[None], y=[None],
        mode='markers',
        marker=dict(size=20, color='gray', symbol='hexagon'),
        name=f'Burned In (No Post-Burn-In Test) ({count_burned_no_post}/{total_boards})'
    ))
    fig_production_overview.add_trace(go.Scatter(
        x=[None], y=[None],
        mode='markers',
        marker=dict(size=20, color='gray', symbol='square'),
        name=f'Burned In (With Post-Burn-In Test) ({count_burned_post}/{total_boards})'
    ))
    
    return fig_production_overview


def get_custom_javascript():
    """
    Return custom JavaScript for click-to-show modal functionality.
    
    Returns:
        str: JavaScript code as string
    """
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
            var parts = hoverText.split(/<br>Benchtest Slots:|<br>Ignored Benchtest Slots:|<br>Component Lots:/);
            
            // Part 0: Info section (before first header)
            var infoSection = parts[0] || '';
            var infoLines = infoSection.split('<br>');
            
            // Extract serial number from info section for URL construction
            var serialNumber = '';
            for (var i = 0; i < infoLines.length; i++) {
                var line = infoLines[i].trim();
                if (line && line.includes('Serial No:')) {
                    var serialMatch = line.match(/Serial No:\s*(\d+)/);
                    if (serialMatch) {
                        serialNumber = serialMatch[1];
                    }
                }
            }
            
            html += '<h3 style="margin-top: 0; margin-bottom: 10px; color: #333; border-bottom: 2px solid #00CC96; padding-bottom: 5px;">Info</h3>';
            html += '<table style="width: 100%; border-collapse: collapse; margin-bottom: 15px;">';
            for (var i = 0; i < infoLines.length; i++) {
                var line = infoLines[i].trim();
                if (line && line.includes(':')) {
                    // Split only on first colon to handle datetime values that contain colons
                    var colonIndex = line.indexOf(':');
                    if (colonIndex > 0) {
                        var key = line.substring(0, colonIndex).trim();
                        var value = line.substring(colonIndex + 1).trim();
                        html += '<tr><td style="padding: 5px; border: 1px solid #ddd; font-weight: bold; background: #f5f5f5;">' + key + '</td><td style="padding: 5px; border: 1px solid #ddd;">' + value + '</td></tr>';
                    }
                }
            }
            html += '</table>';
            
            // Part 1: Status & Tests section (between Benchtest Slots and Component Lots)
            var statusSection = parts[1] || '';
            var statusLines = statusSection.split('<br>');
            
            html += '<h3 style="margin-top: 0; margin-bottom: 10px; color: #333; border-bottom: 2px solid #00CC96; padding-bottom: 5px;">Status & Tests</h3>';
            html += '<table style="width: 100%; border-collapse: collapse; margin-bottom: 15px;">';
            
            // Track current benchtest ID for failed test links
            var currentBenchtestId = '';
            
            for (var i = 0; i < statusLines.length; i++) {
                var line = statusLines[i].trim();
                if (line && (line.includes('dbslot') || line.includes('bt_'))) {
                    // Create hyperlink for benchtest slots and track benchtest ID
                    var benchtestMatch = line.match(/bt_(\d+)/);
                    if (benchtestMatch) {
                        currentBenchtestId = benchtestMatch[1];
                        var benchtestUrl = 'https://piro-atlas-lab.fysik.su.se/drive/benchtests/benchtest_id_' + currentBenchtestId + '/DB_' + serialNumber + '/';
                        html += '<tr><td colspan="2" style="padding: 5px; border: 1px solid #ddd; background: #fafafa;"><a href="' + benchtestUrl + '" target="_blank" style="color: #0066cc; text-decoration: none;">' + line + '</a></td></tr>';
                    } else {
                        html += '<tr><td colspan="2" style="padding: 5px; border: 1px solid #ddd; background: #fafafa;">' + line + '</td></tr>';
                    }
                } else if (line && line.includes('-')) {
                    // Handle failed test lines (indented with dash) with hyperlink
                    var testName = line.replace(/^-/, '').trim();
                    if (currentBenchtestId && serialNumber) {
                        var testUrl = 'https://piro-atlas-lab.fysik.su.se/drive/benchtests/benchtest_id_' + currentBenchtestId + '/DB_' + serialNumber + '/DBSNo_' + serialNumber + '_PPrGTH_' + testName + '.html';
                        html += '<tr><td colspan="2" style="padding: 5px 5px 5px 20px; border: 1px solid #ddd; background: #ffe6e6;"><a href="' + testUrl + '" target="_blank" style="color: #cc0000; text-decoration: none;">' + line + '</a></td></tr>';
                    } else {
                        html += '<tr><td colspan="2" style="padding: 5px 5px 5px 20px; border: 1px solid #ddd; background: #ffe6e6; color: #cc0000;">' + line + '</td></tr>';
                    }
                } else if (line && line.includes(':')) {
                    // Split only on first colon to handle datetime values that contain colons
                    var colonIndex = line.indexOf(':');
                    if (colonIndex > 0) {
                        var key = line.substring(0, colonIndex).trim();
                        var value = line.substring(colonIndex + 1).trim();
                        html += '<tr><td style="padding: 5px; border: 1px solid #ddd; font-weight: bold; background: #f5f5f5;">' + key + '</td><td style="padding: 5px; border: 1px solid #ddd;">' + value + '</td></tr>';
                    }
                }
            }
            html += '</table>';
            
            // Part 2: Ignored Benchtest Slots section (between Ignored Benchtest Slots and Component Lots)
            var ignoredSection = parts[2] || '';
            
            // Check if parts[2] is actually the Component Lots section (no ignored benchtests)
            if (ignoredSection.includes('Component Lots') || ignoredSection.includes('kin_lot')) {
                ignoredSection = '';
            }
            
            var ignoredLines = ignoredSection.split('<br>');
            
            // Check if there are any non-empty lines that contain benchtest info
            var hasIgnoredBenchtests = false;
            for (var i = 0; i < ignoredLines.length; i++) {
                var line = ignoredLines[i].trim();
                // Skip empty lines and bullet points
                if (!line || line === '•' || line === '• ') {
                    continue;
                }
                if (line && (line.includes('dbslot') || line.includes('bt_'))) {
                    hasIgnoredBenchtests = true;
                    break;
                }
            }
            
            if (hasIgnoredBenchtests) {
                html += '<h3 style="margin-top: 0; margin-bottom: 10px; color: #333; border-bottom: 2px solid #FF6B6B; padding-bottom: 5px;">Ignored Benchtest Slots</h3>';
                html += '<table style="width: 100%; border-collapse: collapse; margin-bottom: 15px;">';
                
                for (var i = 0; i < ignoredLines.length; i++) {
                    var line = ignoredLines[i].trim();
                    // Skip empty lines and bullet points
                    if (!line || line === '•' || line === '• ') {
                        continue;
                    }
                    
                    // Check if this is a benchtest slot line (contains dbslot and bt_)
                    if (line.includes('dbslot') && line.includes('bt_')) {
                        // Parse benchtest slot line: • dbslotx@bt_y (op: "test_op" date: YYYY-MM-DD)
                        var benchtestMatch = line.match(/dbslot\d+@bt_\d+/);
                        if (benchtestMatch) {
                            var benchtestSlot = benchtestMatch[0];
                            var benchtestIdMatch = benchtestSlot.match(/bt_(\d+)/);
                            if (benchtestIdMatch) {
                                var benchtestId = benchtestIdMatch[1];
                                var benchtestUrl = 'https://piro-atlas-lab.fysik.su.se/drive/benchtests/benchtest_id_' + benchtestId + '/DB_' + serialNumber + '/';
                                html += '<tr><td colspan="2" style="padding: 5px; border: 1px solid #ddd; background: #fafafa;"><a href="' + benchtestUrl + '" target="_blank" style="color: #0066cc; text-decoration: none;">' + line + '</a></td></tr>';
                            } else {
                                html += '<tr><td colspan="2" style="padding: 5px; border: 1px solid #ddd; background: #fafafa;">' + line + '</td></tr>';
                            }
                        } else {
                            html += '<tr><td colspan="2" style="padding: 5px; border: 1px solid #ddd; background: #fafafa;">' + line + '</td></tr>';
                        }
                    }
                }
                html += '</table>';
            }
            
            // Part 3: Component Lots section (after Component Lots)
            var lotsSection = parts[2] || '';
            
            // If parts[2] was actually ignored benchtests, then Component Lots is in parts[3]
            if (hasIgnoredBenchtests) {
                lotsSection = parts[3] || '';
            }
            
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
    return custom_js


def save_production_overview_with_modal(fig, output_dir):
    """
    Save the production overview plot with custom JavaScript for modal functionality.
    
    Args:
        fig: Plotly Figure object
        output_dir: Directory path to save the HTML file
    """
    custom_js = get_custom_javascript()
    
    fig.write_html(
        output_dir + "production_overview.html",
        config={'displayModeBar': True, 'responsive': True},
        include_plotlyjs=True,
        full_html=True
    )
    
    # Read the generated HTML and inject custom JS
    with open(output_dir + "production_overview.html", 'r') as f:
        html_content = f.read()
    
    # Add responsive CSS to make plot fill window height
    responsive_css = """
    <style>
    html, body {
        margin: 0;
        padding: 0;
        height: 100%;
        overflow: hidden;
    }
    .plotly-graph-div {
        height: 100vh !important;
        width: 100vw !important;
    }
    </style>
    """
    
    # Insert responsive CSS after head tag
    html_content = html_content.replace('<head>', '<head>' + responsive_css)
    
    # Insert custom JS before closing body tag
    html_content = html_content.replace('</body>', custom_js + '</body>')
    
    # Write back
    with open(output_dir + "production_overview.html", 'w') as f:
        f.write(html_content)
