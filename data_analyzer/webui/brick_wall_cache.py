"""HTML/JSON cache for the production brick wall (interactive hover + filters)."""

import json
from datetime import datetime
from html import escape
from pathlib import Path

from plot_cache import cache_banner_html, format_cache_stamp

BRICK_WALL_CACHE_DIR = Path('/var/www/html/drive/production_plots/production_brick_wall')
CACHE_VERSION = 3
LATEST_JSON_NAME = 'production_brick_wall_latest.json'
LATEST_HTML_NAME = 'production_brick_wall_latest.html'
MAX_BRICK_WALL_BATCH = 13


def get_brick_wall_cache_dir():
    return BRICK_WALL_CACHE_DIR


def _json_default(value):
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    return str(value)


def build_brick_wall_html(boards_by_batch, cached_at=None, brick_height=10):
    stamp = format_cache_stamp(cached_at)
    payload = {
        'boards_by_batch': boards_by_batch or {},
        'max_batch': MAX_BRICK_WALL_BATCH,
        'brick_height': brick_height,
    }
    data_json = json.dumps(payload, default=_json_default)
    data_json = data_json.replace('</', '<\\/')

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Production Brick Wall (Cached)</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f5f7fa;
      color: #333;
    }}
    .page-title {{ padding: 12px 16px 4px; font-size: 20px; font-weight: 700; }}
    .meta {{ padding: 0 16px 12px; color: #666; font-size: 12px; }}
    .brick-wall-section {{
      background: white; border-radius: 12px; padding: 15px; margin: 0 16px 16px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.05);
    }}
    .brick-wall-wrapper {{ display: flex; flex-direction: column; gap: 12px; }}
    .brick-wall-container {{
      display: flex; flex-direction: row; gap: 6px; padding: 5px;
      background: #f8f9fa; border-radius: 8px; overflow-x: auto; position: relative;
    }}
    .brick-wall-content {{ display: flex; flex-direction: row; gap: 6px; position: relative; }}
    .y-axis-column {{
      display: flex; flex-direction: column; min-width: 30px; font-size: 11px;
      color: #666; text-align: center;
    }}
    .y-axis-spacer {{ height: 22px; }}
    .y-axis-label {{
      display: flex; align-items: center; justify-content: center; position: relative;
    }}
    .batch-column {{
      display: flex; flex-direction: column; gap: 1px; align-items: center; min-width: 50px;
    }}
    .batch-label {{
      height: 22px; font-size: 11px; font-weight: 600; text-align: center; color: #444;
      display: flex; align-items: center; justify-content: center;
    }}
    .brick {{
      width: 48px; border-radius: 2px; position: relative; cursor: pointer;
      border: 1px solid rgba(0,0,0,0.1);
    }}
    .brick.empty {{ background: transparent; border: 1px dashed #e5e5e5; cursor: default; }}
    .brick.burned {{ box-shadow: inset 0 0 0 1px rgba(255,255,255,0.55); }}
    .brick.filtered-out {{ opacity: 0.18; filter: grayscale(0.7); }}
    .brick-emojis {{
      position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
      gap: 1px; font-size: 9px; line-height: 1; pointer-events: none;
    }}
    .legend {{
      display: flex; flex-wrap: wrap; gap: 12px 18px; font-size: 12px; color: #444; padding: 4px 2px;
    }}
    .legend-item {{ display: flex; align-items: center; gap: 8px; }}
    .swatch {{ width: 14px; height: 14px; border-radius: 3px; border: 1px solid rgba(0,0,0,0.12); }}
    .filters-section {{
      background: white; border-radius: 12px; padding: 14px 16px; margin: 0 16px 16px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.05);
    }}
    .filters-header {{
      display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 10px;
    }}
    .filters-title {{ font-size: 15px; font-weight: 700; }}
    .filters-actions {{ display: flex; gap: 8px; }}
    .filters-container {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .filter-btn, .filter-action-btn {{
      border: 1px solid #d7dbe0; background: #eef1f6; color: #555; border-radius: 6px;
      padding: 6px 10px; font-size: 12px; cursor: pointer;
    }}
    .filter-btn.active {{ background: #667eea; border-color: #667eea; color: #fff; }}
    .filter-subgroup {{
      border: 1px solid #e4e8ee; border-radius: 8px; padding: 8px; min-width: 140px;
    }}
    .filter-subgroup-title {{ font-size: 12px; font-weight: 700; margin-bottom: 6px; color: #555; }}
    .filter-subgroup-buttons {{ display: flex; flex-direction: column; gap: 6px; }}
    #tooltip {{
      position: absolute; z-index: 1000; display: none; min-width: 180px;
      background: rgba(30,30,30,0.95); color: #fff; border-radius: 8px;
      padding: 10px 12px; font-size: 12px; pointer-events: none;
      box-shadow: 0 4px 16px rgba(0,0,0,0.25);
    }}
    #tooltip.show {{ display: block; }}
    .tooltip-row {{ display: flex; gap: 8px; margin: 2px 0; }}
    .tooltip-label {{ color: #bbb; min-width: 70px; }}
    .brick.clicked {{
      animation: click-pulse 0.6s ease-out; z-index: 30;
    }}
    @keyframes click-pulse {{
      0% {{ transform: scale(1); box-shadow: 0 0 0 0 rgba(255, 152, 0, 1); }}
      50% {{ transform: scale(2.5); box-shadow: 0 0 0 20px rgba(255, 152, 0, 0.5); }}
      100% {{ transform: scale(1); box-shadow: 0 0 0 0 rgba(255, 152, 0, 0); }}
    }}
    .modal-overlay {{
      display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 2000;
    }}
    .modal {{
      display: none; position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
      background: white; padding: 20px; border-radius: 8px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.15); z-index: 2001;
      width: 1200px; max-width: 98vw; max-height: 90vh; overflow-y: auto;
      opacity: 0; animation: fade-in 0.3s ease-out forwards;
    }}
    .modal.closing {{ animation: fade-out 0.3s ease-out forwards; }}
    @keyframes fade-in {{
      from {{ opacity: 0; transform: translate(-50%, -50%) scale(0.95); }}
      to {{ opacity: 1; transform: translate(-50%, -50%) scale(1); }}
    }}
    @keyframes fade-out {{
      from {{ opacity: 1; transform: translate(-50%, -50%) scale(1); }}
      to {{ opacity: 0; transform: translate(-50%, -50%) scale(0.95); }}
    }}
    .modal-header {{
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #e1e5e9;
    }}
    .modal-title {{ font-size: 20px; font-weight: 600; color: #333; }}
    .modal-close {{
      background: none; border: none; font-size: 24px; cursor: pointer; color: #666; padding: 5px 10px;
    }}
    .modal-close:hover {{ color: #333; }}
    .modal-content {{
      font-size: 14px; line-height: 1.6; color: #333; display: flex; gap: 15px; flex-wrap: wrap;
    }}
    .modal-section {{
      padding: 10px; background: #f8f9fa; border-radius: 6px; margin-bottom: 8px;
      flex: 1; min-width: 250px;
    }}
    .modal-section-title {{ font-weight: 600; color: #666; margin-bottom: 10px; font-size: 13px; }}
    .modal-row {{ display: flex; justify-content: space-between; gap: 12px; margin: 4px 0; }}
    .modal-label {{ color: #888; }}
    .modal-value {{ color: #333; font-weight: 600; text-align: right; }}
    .modal-benchtest {{
      padding: 10px; background: #f8f9fa; border-radius: 6px; margin-bottom: 8px;
    }}
    .modal-benchtest-title {{ font-weight: 600; color: #333; margin-bottom: 5px; }}
    .modal-benchtest-header {{
      display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;
    }}
    .modal-comment {{
      padding: 8px; background: #f0f0f0; border-radius: 6px; margin-bottom: 6px; font-size: 13px;
    }}
    .modal-comments-section {{ flex: none; width: 100%; }}
    .modal-failed-test {{ color: #f44336; padding: 2px 0; }}
    .modal-failed-tests {{ margin-top: 8px; padding-left: 15px; }}
  </style>
</head>
<body>
  {cache_banner_html(stamp)}
  <div class="page-title">Production Brick Wall</div>
  <div class="meta">Interactive cached snapshot · Cached: {escape(stamp)}</div>

  <div class="brick-wall-section">
    <div class="brick-wall-wrapper">
      <div id="brick-wall-container" class="brick-wall-container"></div>
      <div class="legend" id="legend"></div>
    </div>
  </div>

  <div class="filters-section">
    <div class="filters-header">
      <div class="filters-title">Basic Information Filters</div>
      <div class="filters-actions">
        <button class="filter-action-btn" data-action="enable-all" data-group="basic">Enable All</button>
        <button class="filter-action-btn" data-action="disable-all" data-group="basic">Disable All</button>
      </div>
    </div>
    <div class="filters-container" id="basic-filters">
      <button class="filter-btn active" data-filter="passed-post-burn-in" data-group="basic">Passed Post-Burn-In</button>
      <button class="filter-btn active" data-filter="passed-pre-burn-in" data-group="basic">Passed Pre-Burn-In</button>
      <button class="filter-btn active" data-filter="failed" data-group="basic">Failed</button>
      <button class="filter-btn active" data-filter="no-test" data-group="basic">No Test</button>
      <button class="filter-btn active" data-filter="missing-sfp-data" data-group="basic">Missing SFP Data</button>
      <button class="filter-btn active" data-filter="not-burned-in" data-group="basic">Not Burned In</button>
    </div>
  </div>

  <div class="filters-section">
    <div class="filters-header">
      <div class="filters-title">Component Lots Filters</div>
      <div class="filters-actions">
        <button class="filter-action-btn" data-action="enable-all" data-group="component-lots">Enable All</button>
        <button class="filter-action-btn" data-action="disable-all" data-group="component-lots">Disable All</button>
      </div>
    </div>
    <div class="filters-container" id="component-lots-filters"></div>
  </div>

  <div class="filters-section">
    <div class="filters-header">
      <div class="filters-title">Benchtest Information</div>
      <div class="filters-actions">
        <button class="filter-action-btn" data-action="enable-all" data-group="benchtest">Enable All</button>
        <button class="filter-action-btn" data-action="disable-all" data-group="benchtest">Disable All</button>
      </div>
    </div>
    <div class="filters-container" id="benchtest-filters"></div>
  </div>

  <div id="tooltip"></div>

  <div class="modal-overlay" id="modal-overlay"></div>
  <div class="modal" id="modal">
    <div class="modal-header">
      <div class="modal-title" id="modal-title">Board Details</div>
      <button class="modal-close" id="modal-close">&times;</button>
    </div>
    <div class="modal-content" id="modal-content"></div>
  </div>

  <script>
    const CACHE_DATA = {data_json};
    const activeFilters = {{
      'passed-post-burn-in': true,
      'passed-pre-burn-in': true,
      'failed': true,
      'no-test': true,
      'missing-sfp-data': true,
      'not-burned-in': true,
    }};

    function boardColor(board) {{
      const status = board.db_status;
      const e_test = board.e_test;
      const p_test = board.p_test;
      const has_benchtest = board.has_benchtest;
      const has_sfp_data = board.a0 && board.a1 && board.b0 && board.b1;
      const has_post_burnin_test = board.has_post_burnin_test;
      if ((status === 0 || e_test === 0 || p_test === 0) && has_benchtest) return '#EF553B';
      if (status === 0 && !has_benchtest) return '#FECB52';
      if (status == null || e_test == null || p_test == null) return '#FECB52';
      if (!has_sfp_data) return '#90EE90';
      if (status === 1 && e_test === 1 && p_test === 1 && !has_post_burnin_test) return '#FF9800';
      if (status === 1 && e_test === 1 && p_test === 1 && has_post_burnin_test) return '#00CC96';
      return '#EF553B';
    }}

    function renderLegend() {{
      const items = [
        ['#00CC96', 'Passed post-burn-in'],
        ['#FF9800', 'Passed pre-burn-in'],
        ['#EF553B', 'Failed'],
        ['#FECB52', 'No test'],
        ['#90EE90', 'Missing SFP data'],
      ];
      document.getElementById('legend').innerHTML = items.map(([color, label]) =>
        `<div class="legend-item"><span class="swatch" style="background:${{color}}"></span>${{label}}</div>`
      ).join('') + `
        <div class="legend-item">📛 Not burned in</div>
        <div class="legend-item">📵 Missing SFP data</div>
      `;
    }}

    function renderWall() {{
      const container = document.getElementById('brick-wall-container');
      const tooltip = document.getElementById('tooltip');
      const boardsByBatch = CACHE_DATA.boards_by_batch || {{}};
      const brickHeight = CACHE_DATA.brick_height || 10;
      let maxPosition = 16;
      Object.values(boardsByBatch).forEach(boards => {{
        (boards || []).forEach(board => {{
          if (board.position && board.position > maxPosition) maxPosition = board.position;
        }});
      }});

      const content = document.createElement('div');
      content.className = 'brick-wall-content';

      const yAxis = document.createElement('div');
      yAxis.className = 'y-axis-column';
      yAxis.innerHTML = '<div class="y-axis-spacer"></div>';
      for (let pos = 0; pos <= maxPosition; pos += 1) {{
        const label = document.createElement('div');
        label.className = 'y-axis-label';
        label.style.height = (brickHeight + 1) + 'px';
        if (pos % 2 === 0) label.textContent = String(pos);
        yAxis.appendChild(label);
      }}
      content.appendChild(yAxis);

      for (let batchNum = 0; batchNum <= CACHE_DATA.max_batch; batchNum += 1) {{
        const boards = boardsByBatch[batchNum] || boardsByBatch[String(batchNum)] || [];
        const positionMap = {{}};
        boards.forEach(board => {{ positionMap[board.position] = board; }});
        const column = document.createElement('div');
        column.className = 'batch-column';
        column.innerHTML = `<div class="batch-label">B${{batchNum}}</div>`;
        for (let pos = 0; pos <= maxPosition; pos += 1) {{
          const board = positionMap[pos];
          const brick = document.createElement('div');
          brick.className = 'brick';
          brick.style.height = brickHeight + 'px';
          if (!board) {{
            brick.classList.add('empty');
            column.appendChild(brick);
            continue;
          }}
          brick.dataset.serial = board.serial_no;
          brick._boardData = board;
          brick.style.background = boardColor(board);
          if (board.burn_in_stop) brick.classList.add('burned');
          const emojis = document.createElement('div');
          emojis.className = 'brick-emojis';
          const hasSfp = board.a0 && board.a1 && board.b0 && board.b1;
          if (!hasSfp) emojis.appendChild(document.createTextNode('📵'));
          if (!board.burn_in_stop) emojis.appendChild(document.createTextNode('📛'));
          if (emojis.childNodes.length) brick.appendChild(emojis);

          brick.addEventListener('mouseenter', (e) => {{
            const statusText = board.db_status === 1 ? 'Passed' : (board.db_status === 0 ? 'Failed' : 'Unknown');
            const burnedText = board.burn_in === 1 || board.burn_in_stop ? 'Yes' : 'No';
            const eTestText = board.e_test === 1 ? 'Passed' : (board.e_test === 0 ? 'Failed' : 'Unknown');
            const pTestText = board.p_test === 1 ? 'Passed' : (board.p_test === 0 ? 'Failed' : 'Unknown');
            tooltip.innerHTML = `
              <div class="tooltip-row"><span class="tooltip-label">Serial:</span>${{board.serial_no}}</div>
              <div class="tooltip-row"><span class="tooltip-label">Tag:</span>${{board.tag}}</div>
              <div class="tooltip-row"><span class="tooltip-label">Batch:</span>${{board.batch}}</div>
              <div class="tooltip-row"><span class="tooltip-label">Position:</span>${{board.position}}</div>
              <div class="tooltip-row"><span class="tooltip-label">Status:</span>${{statusText}}</div>
              <div class="tooltip-row"><span class="tooltip-label">E-Test:</span>${{eTestText}}</div>
              <div class="tooltip-row"><span class="tooltip-label">P-Test:</span>${{pTestText}}</div>
              <div class="tooltip-row"><span class="tooltip-label">Burned:</span>${{burnedText}}</div>
              <div class="tooltip-row"><span class="tooltip-label">SFP Data:</span>${{hasSfp ? 'Yes' : 'No'}}</div>
            `;
            tooltip.classList.add('show');
            tooltip.style.left = (e.pageX + 12) + 'px';
            tooltip.style.top = (e.pageY + 12) + 'px';
          }});
          brick.addEventListener('mousemove', (e) => {{
            tooltip.style.left = (e.pageX + 12) + 'px';
            tooltip.style.top = (e.pageY + 12) + 'px';
          }});
          brick.addEventListener('mouseleave', () => tooltip.classList.remove('show'));
          brick.addEventListener('click', () => {{
            brick.classList.add('clicked');
            setTimeout(() => brick.classList.remove('clicked'), 600);
            tooltip.classList.remove('show');
            showModal(board);
          }});
          column.appendChild(brick);
        }}
        content.appendChild(column);
      }}

      container.innerHTML = '';
      container.appendChild(content);
    }}

    function showModal(board) {{
      const modal = document.getElementById('modal');
      const modalOverlay = document.getElementById('modal-overlay');
      const modalTitle = document.getElementById('modal-title');
      const modalContent = document.getElementById('modal-content');
      modalTitle.textContent = `Board ${{board.serial_no}}`;

      let html = '';
      html += '<div class="modal-section">';
      html += '<div class="modal-section-title">Basic Information</div>';
      html += '<div class="modal-row"><span class="modal-label">Serial No:</span><span class="modal-value">' + board.serial_no + '</span></div>';
      html += '<div class="modal-row"><span class="modal-label">Tag:</span><span class="modal-value">' + board.tag + '</span></div>';
      html += '<div class="modal-row"><span class="modal-label">Batch:</span><span class="modal-value">' + board.batch + '</span></div>';
      html += '<div class="modal-row"><span class="modal-label">Position:</span><span class="modal-value">' + board.position + '</span></div>';

      const statusText = board.db_status === 1 ? 'Passed' : (board.db_status === 0 ? 'Failed' : 'Unknown');
      const statusColor = board.db_status === 1 ? '#4caf50' : (board.db_status === 0 ? '#f44336' : '#9e9e9e');
      html += '<div class="modal-row"><span class="modal-label">Status:</span><span class="modal-value" style="color: ' + statusColor + '">' + statusText + '</span></div>';

      const eTestText = board.e_test === 1 ? 'Passed' : (board.e_test === 0 ? 'Failed' : 'Unknown');
      const eTestColor = board.e_test === 1 ? '#4caf50' : (board.e_test === 0 ? '#f44336' : '#9e9e9e');
      html += '<div class="modal-row"><span class="modal-label">E-Test:</span><span class="modal-value" style="color: ' + eTestColor + '">' + eTestText + '</span></div>';

      const pTestText = board.p_test === 1 ? 'Passed' : (board.p_test === 0 ? 'Failed' : 'Unknown');
      const pTestColor = board.p_test === 1 ? '#4caf50' : (board.p_test === 0 ? '#f44336' : '#9e9e9e');
      html += '<div class="modal-row"><span class="modal-label">P-Test:</span><span class="modal-value" style="color: ' + pTestColor + '">' + pTestText + '</span></div>';

      const burnedText = board.burn_in === 1 || board.burn_in_stop ? 'Yes' : 'No';
      const burnedColor = (board.burn_in === 1 || board.burn_in_stop) ? '#4caf50' : '#f44336';
      html += '<div class="modal-row"><span class="modal-label">Burned:</span><span class="modal-value" style="color: ' + burnedColor + '">' + burnedText + '</span></div>';

      const burnInStart = board.burn_in_start || 'N/A';
      const burnInStartColor = burnInStart === 'N/A' ? '#f44336' : '#666';
      html += '<div class="modal-row"><span class="modal-label">Burn-in Start:</span><span class="modal-value" style="color: ' + burnInStartColor + '">' + burnInStart + '</span></div>';

      const burnInStop = board.burn_in_stop || 'N/A';
      const burnInStopColor = burnInStop === 'N/A' ? '#f44336' : '#666';
      html += '<div class="modal-row"><span class="modal-label">Burn-in Stop:</span><span class="modal-value" style="color: ' + burnInStopColor + '">' + burnInStop + '</span></div>';
      html += '</div>';

      html += '<div class="modal-section">';
      html += '<div class="modal-section-title">Component Lots</div>';
      html += '<div class="modal-row"><span class="modal-label">KIN Lot:</span><span class="modal-value">' + (board.kin_lot || 'N/A') + '</span></div>';
      html += '<div class="modal-row"><span class="modal-label">PRO Lot:</span><span class="modal-value">' + (board.pro_lot || 'N/A') + '</span></div>';
      html += '<div class="modal-row"><span class="modal-label">GBT Lot:</span><span class="modal-value">' + (board.gbt_lot || 'N/A') + '</span></div>';
      html += '<div class="modal-row"><span class="modal-label">INA Lot:</span><span class="modal-value">' + (board.ina_lot || 'N/A') + '</span></div>';
      html += '<div class="modal-row"><span class="modal-label">LTM Lot:</span><span class="modal-value">' + (board.ltm_lot || 'N/A') + '</span></div>';
      html += '<div class="modal-row"><span class="modal-label">MOS Lot:</span><span class="modal-value">' + (board.mos_lot || 'N/A') + '</span></div>';
      html += '<div class="modal-row"><span class="modal-label">OP4 Lot:</span><span class="modal-value">' + (board.op4_lot || 'N/A') + '</span></div>';
      html += '<div class="modal-row"><span class="modal-label">OK4 Lot:</span><span class="modal-value">' + (board.ok4_lot || 'N/A') + '</span></div>';
      html += '<div class="modal-row"><span class="modal-label">OK1 Lot:</span><span class="modal-value">' + (board.ok1_lot || 'N/A') + '</span></div>';
      html += '<div class="modal-row"><span class="modal-label">MEM Lot:</span><span class="modal-value">' + (board.mem_lot || 'N/A') + '</span></div>';

      const sfpLot = board.sfp_lot || 'N/A';
      html += '<div class="modal-row"><span class="modal-label">SFP Lot:</span><span class="modal-value" style="color: ' + (sfpLot === 'N/A' ? '#f44336' : '#666') + '">' + sfpLot + '</span></div>';
      const sfpA0 = board.a0 || 'N/A';
      html += '<div class="modal-row"><span class="modal-label">SFP A0:</span><span class="modal-value" style="color: ' + (sfpA0 === 'N/A' ? '#f44336' : '#666') + '">' + sfpA0 + '</span></div>';
      const sfpB0 = board.b0 || 'N/A';
      html += '<div class="modal-row"><span class="modal-label">SFP B0:</span><span class="modal-value" style="color: ' + (sfpB0 === 'N/A' ? '#f44336' : '#666') + '">' + sfpB0 + '</span></div>';
      const sfpA1 = board.a1 || 'N/A';
      html += '<div class="modal-row"><span class="modal-label">SFP A1:</span><span class="modal-value" style="color: ' + (sfpA1 === 'N/A' ? '#f44336' : '#666') + '">' + sfpA1 + '</span></div>';
      const sfpB1 = board.b1 || 'N/A';
      html += '<div class="modal-row"><span class="modal-label">SFP B1:</span><span class="modal-value" style="color: ' + (sfpB1 === 'N/A' ? '#f44336' : '#666') + '">' + sfpB1 + '</span></div>';
      html += '</div>';

      if (board.benchtests && board.benchtests.length > 0) {{
        html += '<div class="modal-section">';
        html += '<div class="modal-section-title">Benchtest Information</div>';
        board.benchtests.forEach(bt => {{
          html += '<div class="modal-benchtest">';
          const benchtestUrl = 'https://piro-atlas-lab.fysik.su.se/drive/benchtests/benchtest_id_' + bt.benchtest_id + '/DB_' + board.serial_no + '/';
          html += '<div class="modal-benchtest-header">';
          html += '<div class="modal-benchtest-title"><a href="' + benchtestUrl + '" target="_blank" style="color: #0066cc; text-decoration: none;">Benchtest ' + bt.benchtest_id + ' ' + (bt.benchtest_slot || '') + '</a></div>';
          html += '</div>';
          html += '<div class="modal-row"><span class="modal-label">Test OP:</span><span class="modal-value">' + (bt.test_op || 'N/A') + '</span></div>';
          if (bt.test_stop) {{
            html += '<div class="modal-row"><span class="modal-label">Test Date:</span><span class="modal-value">' + String(bt.test_stop).split(' ')[0] + '</span></div>';
          }}
          let burnedStatus = 'N/A';
          if (bt.test_stop && board.burn_in_stop) {{
            burnedStatus = new Date(bt.test_stop) > new Date(board.burn_in_stop) ? 'burned' : 'not burned';
          }} else if (board.burn_in_stop) {{
            burnedStatus = 'not burned';
          }}
          if (burnedStatus !== 'N/A') {{
            const color = burnedStatus === 'burned' ? '#4caf50' : '#f44336';
            html += '<div class="modal-row"><span class="modal-label">Burned:</span><span class="modal-value" style="color: ' + color + '">' + burnedStatus + '</span></div>';
          }}
          const testPassText = bt.test_pass === 1 ? 'Passed' : (bt.test_pass === 0 ? 'Failed' : (bt.test_pass === -1 ? 'Ignored' : 'Unknown'));
          const testPassColor = bt.test_pass === 1 ? '#4caf50' : (bt.test_pass === 0 ? '#f44336' : (bt.test_pass === -1 ? '#ff9800' : '#9e9e9e'));
          html += '<div class="modal-row"><span class="modal-label">Test Pass:</span><span class="modal-value" style="color: ' + testPassColor + '">' + testPassText + '</span></div>';
          if (bt.failed_tests && bt.failed_tests.length > 0) {{
            html += '<div class="modal-failed-tests">';
            bt.failed_tests.forEach(failedTest => {{
              const testPlotUrl = 'https://piro-atlas-lab.fysik.su.se/drive/benchtests/benchtest_id_' + bt.benchtest_id + '/DB_' + board.serial_no + '/DBSNo_' + board.serial_no + '_PPrGTH_' + failedTest + '.html';
              html += '<div class="modal-failed-test"><a href="' + testPlotUrl + '" target="_blank" style="color: #f44336; text-decoration: none;">- ' + failedTest + '</a></div>';
            }});
            html += '</div>';
          }}
          html += '</div>';
        }});
        html += '</div>';
      }}

      if (board.comments && board.comments.length > 0) {{
        html += '<div class="modal-section modal-comments-section">';
        html += '<div class="modal-section-title">Comments</div>';
        board.comments.forEach(comment => {{
          const tstamp = comment.tstamp || 'N/A';
          const op = comment.op || 'N/A';
          const note = comment.note || '';
          if (comment.is_benchtest_comment) {{
            html += '<div class="modal-comment">' + tstamp + ' (' + op + ', md' + (comment.md || '?') + '@bt' + (comment.bt || '?') + '): ' + note + '</div>';
          }} else {{
            html += '<div class="modal-comment">' + tstamp + ' (' + op + '): ' + note + '</div>';
          }}
        }});
        html += '</div>';
      }}

      modalContent.innerHTML = html;
      modal.style.display = 'block';
      modalOverlay.style.display = 'block';
    }}

    function closeModal() {{
      const modal = document.getElementById('modal');
      const modalOverlay = document.getElementById('modal-overlay');
      modal.classList.add('closing');
      setTimeout(() => {{
        modal.style.display = 'none';
        modalOverlay.style.display = 'none';
        modal.classList.remove('closing');
      }}, 300);
    }}

    function populateLotFilters() {{
      const container = document.getElementById('component-lots-filters');
      const lotTypes = [
        {{ key: 'kin_lot', label: 'KIN Lot' }},
        {{ key: 'pro_lot', label: 'PRO Lot' }},
        {{ key: 'gbt_lot', label: 'GBT Lot' }},
        {{ key: 'ina_lot', label: 'INA Lot' }},
        {{ key: 'ltm_lot', label: 'LTM Lot' }},
        {{ key: 'mos_lot', label: 'MOS Lot' }},
        {{ key: 'op4_lot', label: 'OP4 Lot' }},
        {{ key: 'ok4_lot', label: 'OK4 Lot' }},
        {{ key: 'ok1_lot', label: 'OK1 Lot' }},
        {{ key: 'mem_lot', label: 'MEM Lot' }},
        {{ key: 'sfp_lot', label: 'SFP Lot' }},
      ];
      const values = {{}};
      lotTypes.forEach(item => {{ values[item.key] = new Set(); }});
      Object.values(CACHE_DATA.boards_by_batch || {{}}).forEach(boards => {{
        (boards || []).forEach(board => {{
          lotTypes.forEach(item => {{
            if (board[item.key]) values[item.key].add(board[item.key]);
          }});
        }});
      }});
      container.innerHTML = '';
      lotTypes.forEach(item => {{
        const sorted = Array.from(values[item.key]).sort();
        if (!sorted.length) return;
        const subgroup = document.createElement('div');
        subgroup.className = 'filter-subgroup';
        subgroup.innerHTML = `<div class="filter-subgroup-title">${{item.label}}</div>`;
        const buttons = document.createElement('div');
        buttons.className = 'filter-subgroup-buttons';
        sorted.forEach(value => {{
          const key = `${{item.key}}_${{value}}`;
          const btn = document.createElement('button');
          btn.className = 'filter-btn active';
          btn.dataset.filter = key;
          btn.dataset.group = 'component-lots';
          btn.textContent = value;
          buttons.appendChild(btn);
          activeFilters[key] = true;
        }});
        subgroup.appendChild(buttons);
        container.appendChild(subgroup);
      }});
    }}

    function populateBenchtestFilters() {{
      const container = document.getElementById('benchtest-filters');
      const counts = new Set();
      const slots = new Set();
      Object.values(CACHE_DATA.boards_by_batch || {{}}).forEach(boards => {{
        (boards || []).forEach(board => {{
          if (board.benchtests && board.benchtests.length) {{
            counts.add(board.benchtests.length);
            board.benchtests.forEach(bt => {{
              if (bt.benchtest_slot) slots.add(bt.benchtest_slot);
            }});
          }}
        }});
      }});
      container.innerHTML = '';
      if (counts.size) {{
        const subgroup = document.createElement('div');
        subgroup.className = 'filter-subgroup';
        subgroup.innerHTML = '<div class="filter-subgroup-title"># Benchtests</div>';
        const buttons = document.createElement('div');
        buttons.className = 'filter-subgroup-buttons';
        Array.from(counts).sort((a, b) => a - b).forEach(count => {{
          const key = `num_benchtests_${{count}}`;
          const btn = document.createElement('button');
          btn.className = 'filter-btn active';
          btn.dataset.filter = key;
          btn.dataset.group = 'benchtest';
          btn.textContent = String(count);
          buttons.appendChild(btn);
          activeFilters[key] = true;
        }});
        subgroup.appendChild(buttons);
        container.appendChild(subgroup);
      }}
      if (slots.size) {{
        const subgroup = document.createElement('div');
        subgroup.className = 'filter-subgroup';
        subgroup.innerHTML = '<div class="filter-subgroup-title">MD Position</div>';
        const buttons = document.createElement('div');
        buttons.className = 'filter-subgroup-buttons';
        Array.from(slots).sort().forEach(slot => {{
          const key = `md_position_${{slot}}`;
          const btn = document.createElement('button');
          btn.className = 'filter-btn active';
          btn.dataset.filter = key;
          btn.dataset.group = 'benchtest';
          btn.textContent = slot;
          buttons.appendChild(btn);
          activeFilters[key] = true;
        }});
        subgroup.appendChild(buttons);
        container.appendChild(subgroup);
      }}
    }}

    function applyFilters() {{
      document.querySelectorAll('#brick-wall-container .brick').forEach(brick => {{
        const board = brick._boardData;
        if (!board) return;
        const status = board.db_status;
        const e_test = board.e_test;
        const p_test = board.p_test;
        const has_benchtest = board.has_benchtest;
        const has_sfp_data = board.a0 && board.a1 && board.b0 && board.b1;
        const has_post_burnin_test = board.has_post_burnin_test;

        const basicKeys = ['passed-post-burn-in', 'passed-pre-burn-in', 'failed', 'no-test', 'missing-sfp-data', 'not-burned-in'];
        const hasBasic = basicKeys.some(key => activeFilters[key]);
        const hasLots = Object.keys(activeFilters).some(key =>
          key.includes('_') && !key.startsWith('num_benchtests_') && !key.startsWith('md_position_') && activeFilters[key]
        );
        const hasBench = Object.keys(activeFilters).some(key =>
          (key.startsWith('num_benchtests_') || key.startsWith('md_position_')) && activeFilters[key]
        );
        if (!hasBasic && !hasLots && !hasBench) {{
          brick.classList.add('filtered-out');
          return;
        }}

        let matchesBasic = !hasBasic;
        if (hasBasic) {{
          if (activeFilters['passed-post-burn-in'] && status === 1 && e_test === 1 && p_test === 1 && has_post_burnin_test) matchesBasic = true;
          if (activeFilters['passed-pre-burn-in'] && status === 1 && e_test === 1 && p_test === 1 && !has_post_burnin_test) matchesBasic = true;
          if (activeFilters['failed'] && (status === 0 || e_test === 0 || p_test === 0)) matchesBasic = true;
          if (activeFilters['no-test'] && (status == null || e_test == null || p_test == null)) matchesBasic = true;
          if (activeFilters['missing-sfp-data'] && !has_sfp_data) matchesBasic = true;
          if (activeFilters['not-burned-in'] && !board.burn_in_stop) matchesBasic = true;
        }}

        let matchesLots = !hasLots;
        if (hasLots) {{
          matchesLots = Object.keys(activeFilters).some(key => {{
            if (!activeFilters[key]) return false;
            const match = key.match(/^((?:kin|pro|gbt|ina|ltm|mos|op4|ok4|ok1|mem|sfp)_lot)_(.+)$/);
            if (!match) return false;
            return String(board[match[1]] || '') === match[2];
          }});
        }}

        let matchesBench = !hasBench;
        if (hasBench) {{
          const count = (board.benchtests || []).length;
          const countMatch = activeFilters[`num_benchtests_${{count}}`];
          const slotMatch = (board.benchtests || []).some(bt => activeFilters[`md_position_${{bt.benchtest_slot}}`]);
          matchesBench = Boolean(countMatch || slotMatch);
        }}

        if (matchesBasic && matchesLots && matchesBench) brick.classList.remove('filtered-out');
        else brick.classList.add('filtered-out');
      }});
    }}

    function attachFilterListeners() {{
      document.querySelectorAll('.filter-btn').forEach(btn => {{
        btn.addEventListener('click', () => {{
          const filter = btn.dataset.filter;
          activeFilters[filter] = !activeFilters[filter];
          btn.classList.toggle('active', activeFilters[filter]);
          applyFilters();
        }});
        btn.addEventListener('dblclick', () => {{
          const group = btn.dataset.group;
          document.querySelectorAll(`.filter-btn[data-group="${{group}}"]`).forEach(other => {{
            const key = other.dataset.filter;
            activeFilters[key] = other === btn;
            other.classList.toggle('active', other === btn);
          }});
          applyFilters();
        }});
      }});
      document.querySelectorAll('.filter-action-btn').forEach(btn => {{
        btn.addEventListener('click', () => {{
          const enabled = btn.dataset.action === 'enable-all';
          const group = btn.dataset.group;
          document.querySelectorAll(`.filter-btn[data-group="${{group}}"]`).forEach(filterBtn => {{
            activeFilters[filterBtn.dataset.filter] = enabled;
            filterBtn.classList.toggle('active', enabled);
          }});
          applyFilters();
        }});
      }});
    }}

    renderLegend();
    renderWall();
    populateLotFilters();
    populateBenchtestFilters();
    attachFilterListeners();
    applyFilters();

    document.getElementById('modal-close').addEventListener('click', closeModal);
    document.getElementById('modal-overlay').addEventListener('click', closeModal);
    document.addEventListener('keydown', (e) => {{
      if (e.key === 'Escape') closeModal();
    }});
  </script>
</body>
</html>
'''


def save_brick_wall_cache(boards_by_batch, cached_at=None):
    BRICK_WALL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    moment = cached_at or datetime.now()
    if isinstance(moment, str):
        cached_at_text = moment
        stamp_for_name = datetime.now()
    else:
        cached_at_text = moment.strftime('%Y-%m-%d %H:%M:%S')
        stamp_for_name = moment

    for path in BRICK_WALL_CACHE_DIR.glob('production_brick_wall_*'):
        try:
            path.unlink()
        except OSError as exc:
            print(f'Error clearing brick wall cache {path}: {exc}')

    payload = {
        'version': CACHE_VERSION,
        'cached_at': cached_at_text,
        'success': True,
        'boards_by_batch': boards_by_batch,
    }
    json_text = json.dumps(payload, default=_json_default)
    html_text = build_brick_wall_html(boards_by_batch, cached_at=cached_at_text)

    stamped = stamp_for_name.strftime('%Y%m%dT%H%M%S')
    stamped_json = BRICK_WALL_CACHE_DIR / f'production_brick_wall_{stamped}.json'
    stamped_html = BRICK_WALL_CACHE_DIR / f'production_brick_wall_{stamped}.html'
    latest_json = BRICK_WALL_CACHE_DIR / LATEST_JSON_NAME
    latest_html = BRICK_WALL_CACHE_DIR / LATEST_HTML_NAME

    stamped_json.write_text(json_text, encoding='utf-8')
    stamped_html.write_text(html_text, encoding='utf-8')
    latest_json.write_text(json_text, encoding='utf-8')
    latest_html.write_text(html_text, encoding='utf-8')

    return {
        'cache_dir': str(BRICK_WALL_CACHE_DIR),
        'cached_at': cached_at_text,
        'json': stamped_json.name,
        'html': stamped_html.name,
        'latest_json': latest_json.name,
        'latest_html': latest_html.name,
    }


def load_brick_wall_cache():
    latest_json = BRICK_WALL_CACHE_DIR / LATEST_JSON_NAME
    if not latest_json.exists():
        return None
    try:
        payload = json.loads(latest_json.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        print(f'Error reading brick wall cache {latest_json}: {exc}')
        return None
    if payload.get('version') not in (1, 2, CACHE_VERSION):
        return None
    if not payload.get('boards_by_batch'):
        return None
    return payload
