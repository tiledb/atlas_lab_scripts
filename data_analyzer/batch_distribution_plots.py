### ################################### ###
### Batch Distribution Plots Library ###
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

def create_batch_distribution_dashboard(df_daughterboards, timenow):
    """
    Create a dashboard showing distribution of daughterboards and batches across component lots.
    
    Args:
        df_daughterboards: DataFrame containing daughterboard data
        timenow: Current datetime for title timestamp
        
    Returns:
        fig: Plotly Figure object with subplots
    """
    # Component lot columns
    lot_columns = ['kin_lot', 'pro_lot', 'gbt_lot', 'ina_lot', 'ltm_lot', 'mos_lot', 
                   'op4_lot', 'ok4_lot', 'ok1_lot', 'mem_lot', 'sfp_lot']
    
    lot_names = ['Kintex', 'ProASIC', 'GBT', 'INA', 'LTM', 'MOSFET', 
                 'OP4', 'OK4', 'OK1', 'Memory', 'SFP']
    
    fig = make_subplots(
        rows=len(lot_columns), cols=2,
        subplot_titles=[f"{lot_names[i]} - Daughterboard Count" if col == 0 else f"{lot_names[i]} - Batch Distribution" 
                       for i in range(len(lot_columns)) for col in range(2)],
        specs=[[{"type": "bar"}, {"type": "bar"}] for _ in range(len(lot_columns))],
        vertical_spacing=0.04
    )
    
    for idx, (lot_col, lot_name) in enumerate(zip(lot_columns, lot_names)):
        row = idx + 1
        
        # Daughterboard count per lot value with hover text showing serial numbers
        lot_counts = df_daughterboards[lot_col].value_counts().sort_index()
        hover_texts = []
        for lot_value in lot_counts.index:
            boards_in_lot = df_daughterboards[df_daughterboards[lot_col] == lot_value]['serial_no'].tolist()
            boards_in_lot_str = [str(board) for board in boards_in_lot]
            hover_text = f"{lot_name} Lot: {lot_value}<br>Count: {len(boards_in_lot)}<br>Serial Numbers:<br>" + "<br>".join(boards_in_lot_str)
            hover_texts.append(hover_text)
        
        fig.add_trace(
            go.Bar(
                x=lot_counts.index.astype(str),
                y=lot_counts.values,
                name=f"{lot_name} Count",
                marker_color='#00CC96',
                showlegend=False,
                text=lot_counts.values,
                textposition='outside',
                hovertext=hover_texts
            ),
            row=row, col=1
        )
        
        # Batch distribution per lot value with hover text showing serial numbers
        for batch in sorted(df_daughterboards['decoded_batch'].unique()):
            batch_data = df_daughterboards[df_daughterboards['decoded_batch'] == batch]
            lot_batch_counts = batch_data[lot_col].value_counts().sort_index()
            
            hover_texts_batch = []
            for lot_value in lot_batch_counts.index:
                boards_in_lot_batch = batch_data[batch_data[lot_col] == lot_value]['serial_no'].tolist()
                boards_in_lot_batch_str = [str(board) for board in boards_in_lot_batch]
                hover_text = f"{lot_name} Lot: {lot_value}<br>Batch: {batch}<br>Count: {len(boards_in_lot_batch)}<br>Serial Numbers:<br>" + "<br>".join(boards_in_lot_batch_str)
                hover_texts_batch.append(hover_text)
            
            fig.add_trace(
                go.Bar(
                    x=lot_batch_counts.index.astype(str),
                    y=lot_batch_counts.values,
                    name=f"Batch {batch}",
                    showlegend=(row == 1),  # Only show legend for first plot
                    hovertext=hover_texts_batch
                ),
                row=row, col=2
            )
        
        fig.update_xaxes(title_text=lot_name, row=row, col=1, tickfont=dict(size=10))
        fig.update_yaxes(title_text="Count", row=row, col=1, tickfont=dict(size=10))
        fig.update_xaxes(title_text=lot_name, row=row, col=2, tickfont=dict(size=10))
        fig.update_yaxes(title_text="Count", row=row, col=2, tickfont=dict(size=10))
    
    fig.update_layout(
        title=dict(
            text=f"Production Batch Distribution - Component Lots ({timenow.strftime('%Y-%m-%d - %H:%M:%S')})",
            font=dict(size=24)
        ),
        height=300 * len(lot_columns),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.01,
            xanchor="center",
            x=0.5,
            font=dict(size=12)
        ),
        margin=dict(b=150, l=50, r=50, t=80)
    )
    
    return fig
