### ################################### ###
### Summary Dashboard Plots Library ###
### Version 1.0.0 ###
### ################################### ###

### ############### ###
### Package Imports ###
### ############### ###

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

### ######### ###
### Functions ###
### ######### ###

def create_summary_dashboard(df_daughterboards, timenow, serial_to_benchtests=None):
    """
    Create the summary dashboard with multiple subplots showing production statistics.
    
    Args:
        df_daughterboards: DataFrame containing daughterboard data
        timenow: Current datetime for title timestamp
        serial_to_benchtests: Optional dictionary mapping serial numbers to benchtest slots
        
    Returns:
        fig: Plotly Figure object with subplots
    """
    # Use same color classification logic as production overview
    colors = {1: '#00CC96', 0: '#EF553B', None: '#FECB52', 'sfp_none': '#90EE90'}
    
    count_passed = 0
    count_failed = 0
    count_no_test = 0
    count_sfp_none = 0
    
    for idx, row in df_daughterboards.iterrows():
        status = row['db_status']
        e_test = row['e_test']
        p_test = row['p_test']
        serial = row['serial_no']
        
        # Determine color based on dbstatus, e_test, p_test, and sfp slots
        # Precedence: Failed (with benchtest) > No Test > Missing SFP Data > Passed
        has_benchtest = serial_to_benchtests and serial in serial_to_benchtests
        
        if (status == 0 or e_test == 0 or p_test == 0) and has_benchtest:
            count_failed += 1
        elif status == 0 and not has_benchtest:
            count_no_test += 1
        elif pd.isna(status) or pd.isna(e_test) or pd.isna(p_test):
            count_no_test += 1
        elif pd.isna(row['a0']) or pd.isna(row['a1']) or pd.isna(row['b0']) or pd.isna(row['b1']):
            count_sfp_none += 1
        elif status == 1 and e_test == 1 and p_test == 1:
            count_passed += 1
        else:
            count_failed += 1
    
    total_boards = len(df_daughterboards)
    # Yield calculation: failed/(passed+failed) - no_test does not contribute
    tested_boards = count_passed + count_failed
    yield_percentage = (count_failed / tested_boards * 100) if tested_boards > 0 else 0
    overall_yield = (count_passed / total_boards * 100) if total_boards > 0 else 0
    
    fig_summary = make_subplots(
        rows=5, cols=1,
        subplot_titles=["Overall Status", "Yield (Tested Boards)", "Cumulative Board Count (by Batch)", "Cumulative Board Count (by Time)", "Burn-In Timeline"],
        specs=[[{"type": "pie"}], [{"type": "pie"}], [{"type": "scatter"}], [{"type": "scatter"}], [{"type": "scatter"}]]
    )
    
    # Overall Status Pie - use same 4 categories as production overview
    fig_summary.add_trace(
        go.Pie(
            labels=['Passed', 'Failed', 'No Test', 'Missing SFP Data'],
            values=[count_passed, count_failed, count_no_test, count_sfp_none],
            marker=dict(colors=[colors[1], colors[0], colors[None], colors['sfp_none']])
        ),
        row=1, col=1
    )
    
    # Yield Pie Chart - only tested boards (passed + failed)
    fig_summary.add_trace(
        go.Pie(
            labels=['Passed', 'Failed'],
            values=[count_passed, count_failed],
            marker=dict(colors=[colors[1], colors[0]]),
            title=dict(text=f"Yield: {yield_percentage:.1f}% Failure Rate")
        ),
        row=2, col=1
    )
    
    # Cumulative Board Count by decoded batch
    batch_stats = calculate_batch_cumulative_stats(df_daughterboards, serial_to_benchtests)
    add_cumulative_batch_plot(fig_summary, batch_stats)
    
    # Cumulative Board Count by test_stop timestamp
    df_with_time, df_passed, df_failed, df_no_test = calculate_time_cumulative_stats(df_daughterboards, serial_to_benchtests)
    add_cumulative_time_plot(fig_summary, df_passed, df_failed, df_no_test)
    
    # Burn-In Timeline plot
    df_burnin = calculate_burnin_timeline(df_daughterboards)
    add_burnin_timeline_plot(fig_summary, df_burnin)
    
    # Calculate shared x-axis and y-axis ranges for time-based plots
    xaxis_range, yaxis_range = calculate_axis_ranges(df_with_time, df_burnin)
    
    # Update layout
    fig_summary.update_layout(
        title=dict(
            text=f"Production Summary Dashboard - Total Boards: {total_boards}, Yield: {overall_yield:.1f}% ({timenow.strftime('%Y-%m-%d - %H:%M:%S')})",
            font=dict(size=24)
        ),
        height=1600,
        showlegend=True,
        legend=dict(font=dict(size=14))
    )
    fig_summary.update_xaxes(title_text="Decoded Batch", row=3, col=1,
                             tickmode='linear', tick0=0, dtick=1,
                             title_font=dict(size=18), tickfont=dict(size=14))
    fig_summary.update_yaxes(title_text="Cumulative Board Count", row=3, col=1,
                             title_font=dict(size=18), tickfont=dict(size=14))
    fig_summary.update_xaxes(title_text="Test Passed Time", row=4, col=1, range=xaxis_range,
                             title_font=dict(size=18), tickfont=dict(size=14))
    fig_summary.update_yaxes(title_text="Cumulative Board Count", row=4, col=1, range=yaxis_range,
                             title_font=dict(size=18), tickfont=dict(size=14))
    fig_summary.update_xaxes(title_text="Burn-In Time", row=5, col=1, range=xaxis_range,
                             title_font=dict(size=18), tickfont=dict(size=14))
    fig_summary.update_yaxes(title_text="Cumulative Board Count", row=5, col=1, range=yaxis_range,
                             title_font=dict(size=18), tickfont=dict(size=14))
    
    return fig_summary


def calculate_batch_cumulative_stats(df_daughterboards, serial_to_benchtests=None):
    """
    Calculate cumulative statistics by decoded batch.
    
    Args:
        df_daughterboards: DataFrame containing daughterboard data
        serial_to_benchtests: Optional dictionary mapping serial numbers to benchtest slots
        
    Returns:
        batch_stats: DataFrame with batch statistics
    """
    # Classify each board as passed, failed, or no_test
    df_sorted = df_daughterboards.copy()
    df_sorted['classification'] = 'no_test'
    
    for idx, row in df_sorted.iterrows():
        status = row['db_status']
        e_test = row['e_test']
        p_test = row['p_test']
        serial = row['serial_no']
        
        has_benchtest = serial_to_benchtests and serial in serial_to_benchtests
        
        if (status == 0 or e_test == 0 or p_test == 0) and has_benchtest:
            df_sorted.at[idx, 'classification'] = 'failed'
        elif status == 0 and not has_benchtest:
            df_sorted.at[idx, 'classification'] = 'no_test'
        elif pd.isna(status) or pd.isna(e_test) or pd.isna(p_test):
            df_sorted.at[idx, 'classification'] = 'no_test'
        elif pd.isna(row['a0']) or pd.isna(row['a1']) or pd.isna(row['b0']) or pd.isna(row['b1']):
            df_sorted.at[idx, 'classification'] = 'no_test'
        elif status == 1 and e_test == 1 and p_test == 1:
            df_sorted.at[idx, 'classification'] = 'passed'
        else:
            df_sorted.at[idx, 'classification'] = 'failed'
    
    # Group by batch and classification
    batch_stats = df_sorted.groupby(['decoded_batch', 'classification']).size().unstack(fill_value=0)
    
    # Ensure all columns exist
    for col in ['passed', 'failed', 'no_test']:
        if col not in batch_stats.columns:
            batch_stats[col] = 0
    
    # Calculate cumulative counts
    batch_stats['cumulative_passed'] = batch_stats['passed'].cumsum()
    batch_stats['cumulative_failed'] = batch_stats['failed'].cumsum()
    batch_stats['cumulative_no_test'] = batch_stats['no_test'].cumsum()
    
    batch_stats = batch_stats.reset_index()
    
    return batch_stats


def add_cumulative_batch_plot(fig_summary, batch_stats):
    """
    Add cumulative board count by batch plot to the figure.
    
    Args:
        fig_summary: Plotly Figure object to add traces to
        batch_stats: DataFrame with batch statistics
    """
    # Create hover text for passed
    hover_text_passed = [
        f"Batch: {batch}<br>" +
        f"Passed in batch: {passed}<br>" +
        f"Cumulative Passed: {cum}"
        for batch, passed, cum in zip(
            batch_stats['decoded_batch'],
            batch_stats['passed'],
            batch_stats['cumulative_passed']
        )
    ]
    
    # Create hover text for failed
    hover_text_failed = [
        f"Batch: {batch}<br>" +
        f"Failed in batch: {failed}<br>" +
        f"Cumulative Failed: {cum}"
        for batch, failed, cum in zip(
            batch_stats['decoded_batch'],
            batch_stats['failed'],
            batch_stats['cumulative_failed']
        )
    ]
    
    # Create hover text for no_test
    hover_text_no_test = [
        f"Batch: {batch}<br>" +
        f"No Test in batch: {no_test}<br>" +
        f"Cumulative No Test: {cum}"
        for batch, no_test, cum in zip(
            batch_stats['decoded_batch'],
            batch_stats['no_test'],
            batch_stats['cumulative_no_test']
        )
    ]
    
    fig_summary.add_trace(
        go.Scatter(x=batch_stats['decoded_batch'], y=batch_stats['cumulative_passed'],
                   mode='lines+markers', name='Cumulative Passed (by Batch)',
                   line=dict(color='#00CC96', width=2),
                   marker=dict(size=6),
                   hovertemplate='%{text}<extra></extra>',
                   text=hover_text_passed),
        row=3, col=1
    )
    fig_summary.add_trace(
        go.Scatter(x=batch_stats['decoded_batch'], y=batch_stats['cumulative_failed'],
                   mode='lines+markers', name='Cumulative Failed (by Batch)',
                   line=dict(color='#EF553B', width=2),
                   marker=dict(size=6),
                   hovertemplate='%{text}<extra></extra>',
                   text=hover_text_failed),
        row=3, col=1
    )
    fig_summary.add_trace(
        go.Scatter(x=batch_stats['decoded_batch'], y=batch_stats['cumulative_no_test'],
                   mode='lines+markers', name='Cumulative No Test (by Batch)',
                   line=dict(color='#FECB52', width=2),
                   marker=dict(size=6),
                   hovertemplate='%{text}<extra></extra>',
                   text=hover_text_no_test),
        row=3, col=1
    )


def calculate_time_cumulative_stats(df_daughterboards, serial_to_benchtests=None):
    """
    Calculate cumulative statistics by test_stop timestamp.
    
    Args:
        df_daughterboards: DataFrame containing daughterboard data
        serial_to_benchtests: Optional dictionary mapping serial numbers to benchtest slots
        
    Returns:
        tuple: (df_with_time, df_passed, df_failed, df_no_test) DataFrames
    """
    # Classify each board as passed, failed, or no_test
    df_sorted = df_daughterboards.copy()
    df_sorted['classification'] = 'no_test'
    
    for idx, row in df_sorted.iterrows():
        status = row['db_status']
        e_test = row['e_test']
        p_test = row['p_test']
        serial = row['serial_no']
        
        has_benchtest = serial_to_benchtests and serial in serial_to_benchtests
        
        if (status == 0 or e_test == 0 or p_test == 0) and has_benchtest:
            df_sorted.at[idx, 'classification'] = 'failed'
        elif status == 0 and not has_benchtest:
            df_sorted.at[idx, 'classification'] = 'no_test'
        elif pd.isna(status) or pd.isna(e_test) or pd.isna(p_test):
            df_sorted.at[idx, 'classification'] = 'no_test'
        elif pd.isna(row['a0']) or pd.isna(row['a1']) or pd.isna(row['b0']) or pd.isna(row['b1']):
            df_sorted.at[idx, 'classification'] = 'no_test'
        elif status == 1 and e_test == 1 and p_test == 1:
            df_sorted.at[idx, 'classification'] = 'passed'
        else:
            df_sorted.at[idx, 'classification'] = 'failed'
    
    # Filter boards that have test_stop timestamps
    df_with_time = df_sorted[df_sorted['test_stop'].notna()].copy()
    df_with_time = df_with_time.sort_values('test_stop').reset_index(drop=True)
    
    # Calculate cumulative counts
    df_with_time['cumulative_passed'] = (df_with_time['classification'] == 'passed').cumsum()
    df_with_time['cumulative_failed'] = (df_with_time['classification'] == 'failed').cumsum()
    df_with_time['cumulative_no_test'] = (df_with_time['classification'] == 'no_test').cumsum()
    
    # Split by classification
    df_passed = df_with_time[df_with_time['classification'] == 'passed']
    df_failed = df_with_time[df_with_time['classification'] == 'failed']
    df_no_test = df_with_time[df_with_time['classification'] == 'no_test']
    
    return df_with_time, df_passed, df_failed, df_no_test


def add_cumulative_time_plot(fig_summary, df_passed, df_failed, df_no_test):
    """
    Add cumulative board count by time plot to the figure.
    
    Args:
        fig_summary: Plotly Figure object to add traces to
        df_passed: DataFrame with passed boards
        df_failed: DataFrame with failed boards
        df_no_test: DataFrame with no_test boards
    """
    fig_summary.add_trace(
        go.Scatter(x=df_passed['test_stop'], y=df_passed['cumulative_passed'],
                   mode='lines+markers', name='Cumulative Passed (by Time)',
                   line=dict(color='#00CC96', width=2),
                   marker=dict(color='#00CC96', size=6),
                   hovertemplate='%{text}<extra></extra>',
                   text=[f"Serial: {s}<br>Test Stop: {t}<br>Cumulative Passed: {c}"
                         for s, t, c in zip(df_passed['serial_no'], df_passed['test_stop'], df_passed['cumulative_passed'])]),
        row=4, col=1
    )
    fig_summary.add_trace(
        go.Scatter(x=df_failed['test_stop'], y=df_failed['cumulative_failed'],
                   mode='lines+markers', name='Cumulative Failed (by Time)',
                   line=dict(color='#EF553B', width=2),
                   marker=dict(color='#EF553B', size=6),
                   hovertemplate='%{text}<extra></extra>',
                   text=[f"Serial: {s}<br>Test Stop: {t}<br>Cumulative Failed: {c}"
                         for s, t, c in zip(df_failed['serial_no'], df_failed['test_stop'], df_failed['cumulative_failed'])]),
        row=4, col=1
    )
    fig_summary.add_trace(
        go.Scatter(x=df_no_test['test_stop'], y=df_no_test['cumulative_no_test'],
                   mode='lines+markers', name='Cumulative No Test (by Time)',
                   line=dict(color='#FECB52', width=2),
                   marker=dict(color='#FECB52', size=6),
                   hovertemplate='%{text}<extra></extra>',
                   text=[f"Serial: {s}<br>Test Stop: {t}<br>Cumulative No Test: {c}"
                         for s, t, c in zip(df_no_test['serial_no'], df_no_test['test_stop'], df_no_test['cumulative_no_test'])]),
        row=4, col=1
    )


def calculate_burnin_timeline(df_daughterboards):
    """
    Calculate burn-in timeline statistics.
    
    Args:
        df_daughterboards: DataFrame containing daughterboard data
        
    Returns:
        df_burnin: DataFrame with burn-in timeline data
    """
    # Filter boards that have burn_in_start and burn_in_stop
    df_burnin = df_daughterboards[
        df_daughterboards['burn_in_start'].notna() & 
        df_daughterboards['burn_in_stop'].notna()
    ].copy()
    
    if len(df_burnin) > 0:
        # Calculate center point using timedelta arithmetic
        df_burnin['burn_in_center'] = df_burnin['burn_in_start'] + (df_burnin['burn_in_stop'] - df_burnin['burn_in_start']) / 2
        
        # Calculate error bar values (distance from center to start/stop) in milliseconds
        df_burnin['error_minus'] = (df_burnin['burn_in_center'] - df_burnin['burn_in_start']).dt.total_seconds() * 1000
        df_burnin['error_plus'] = (df_burnin['burn_in_stop'] - df_burnin['burn_in_center']).dt.total_seconds() * 1000
        
        # Assign y-axis values as cumulative board count
        df_burnin = df_burnin.sort_values('burn_in_center')
        df_burnin['y_pos'] = range(1, len(df_burnin) + 1)
    else:
        df_burnin = pd.DataFrame(columns=['burn_in_center', 'y_pos', 'error_minus', 'error_plus'])
    
    return df_burnin


def add_burnin_timeline_plot(fig_summary, df_burnin):
    """
    Add burn-in timeline plot to the figure.
    
    Args:
        fig_summary: Plotly Figure object to add traces to
        df_burnin: DataFrame with burn-in timeline data
    """
    if len(df_burnin) > 0:
        # Create hover text
        hover_burnin = [
            f"Serial: {serial}<br>" +
            f"Batch: {batch}<br>" +
            f"Burn In Start: {start}<br>" +
            f"Burn In Stop: {stop}<br>" +
            f"Center: {center}"
            for serial, batch, start, stop, center in zip(
                df_burnin['serial_no'],
                df_burnin['decoded_batch'],
                df_burnin['burn_in_start'],
                df_burnin['burn_in_stop'],
                df_burnin['burn_in_center']
            )
        ]
        
        # Add scatter plot with error bars
        fig_summary.add_trace(
            go.Scatter(
                x=df_burnin['burn_in_center'],
                y=df_burnin['y_pos'],
                mode='markers',
                name='Burn-In Period',
                marker=dict(color='#AB63FA', size=8),
                error_x=dict(
                    array=df_burnin['error_plus'],
                    arrayminus=df_burnin['error_minus'],
                    symmetric=False,
                    color='#AB63FA',
                    thickness=4,
                    width=10
                ),
                hovertemplate='%{text}<extra></extra>',
                text=hover_burnin
            ),
            row=5, col=1
        )


def calculate_axis_ranges(df_with_time, df_burnin):
    """
    Calculate shared x-axis and y-axis ranges for time-based plots.
    
    Args:
        df_with_time: DataFrame with time-based data
        df_burnin: DataFrame with burn-in data
        
    Returns:
        tuple: (xaxis_range, yaxis_range) or (None, None) if no data
    """
    # Calculate shared x-axis range
    all_times = []
    if len(df_with_time) > 0:
        all_times.extend(df_with_time['test_stop'].dropna().tolist())
    if len(df_burnin) > 0:
        all_times.extend(df_burnin['burn_in_start'].dropna().tolist())
        all_times.extend(df_burnin['burn_in_stop'].dropna().tolist())
    
    if all_times:
        min_time = min(all_times)
        max_time = max(all_times)
        # Add some padding
        time_padding = (max_time - min_time) * 0.05
        xaxis_range = [min_time - time_padding, max_time + time_padding]
    else:
        xaxis_range = None
    
    # Calculate shared y-axis range
    all_y_values = []
    if len(df_with_time) > 0:
        all_y_values.extend(df_with_time['cumulative_passed'].tolist())
        all_y_values.extend(df_with_time['cumulative_failed'].tolist())
        all_y_values.extend(df_with_time['cumulative_no_test'].tolist())
    if len(df_burnin) > 0:
        all_y_values.extend(df_burnin['y_pos'].tolist())
    
    if all_y_values:
        min_y = min(all_y_values)
        max_y = max(all_y_values)
        yaxis_range = [min_y - 1, max_y + 1]
    else:
        yaxis_range = None
    
    return xaxis_range, yaxis_range
