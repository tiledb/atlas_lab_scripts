"""JSON/HTML cache for production summary plots."""

import json
from datetime import datetime
from html import escape
from pathlib import Path

from plot_cache import cache_banner_html, format_cache_stamp

PRODUCTION_SUMMARY_CACHE_DIR = Path('/var/www/html/drive/production_plots/production_summary')
CACHE_VERSION = 1
LATEST_JSON_NAME = 'production_summary_latest.json'
LATEST_HTML_NAME = 'production_summary_latest.html'


def _json_default(value):
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    return str(value)


def build_production_summary_html(summary, cached_at=None):
    try:
        import plotly.graph_objects as go
        from plotly.io import to_html
    except ImportError as exc:
        print(f'Plotly not available for production summary HTML export: {exc}')
        return None

    stamp = format_cache_stamp(cached_at or summary.get('cached_at') or summary.get('timestamp'))
    colors = summary.get('colors') or {}
    figures_html = []

    def _pie_html(fig, div_id, include_js):
        fig.update_layout(
            autosize=True,
            height=380,
            margin=dict(t=50, r=10, b=10, l=10),
            legend=dict(orientation='h', yanchor='top', y=-0.08, x=0.5, xanchor='center'),
            showlegend=True,
        )
        return to_html(
            fig,
            include_plotlyjs='cdn' if include_js else False,
            full_html=False,
            div_id=div_id,
            config={'responsive': True, 'displayModeBar': False},
            default_width='100%',
            default_height=380,
        )

    # Yield pie
    yield_data = summary.get('yield_after_burnin') or {}
    fig = go.Figure(data=[go.Pie(
        labels=['Passed', 'Failed'],
        values=[yield_data.get('passed', 0), yield_data.get('failed', 0)],
        marker=dict(colors=[colors.get('passed', '#00CC96'), colors.get('failed', '#EF553B')]),
        hole=0.35,
        domain=dict(x=[0.05, 0.95], y=[0.18, 1.0]),
    )])
    fig.update_layout(
        title=f"Yield after Burn-In (Failure Rate: {summary.get('yield_failure_rate', 0)}%)",
    )
    figures_html.append(('pie', _pie_html(fig, 'summary-yield-pie', True)))

    # Burn-in status pie
    burnin = summary.get('burnin_status') or {}
    fig = go.Figure(data=[go.Pie(
        labels=['Burned In', 'Not Burned In'],
        values=[burnin.get('burned_in', 0), burnin.get('not_burned_in', 0)],
        marker=dict(colors=[colors.get('burned_in', '#4caf50'), colors.get('not_burned_in', '#f44336')]),
        hole=0.35,
        domain=dict(x=[0.05, 0.95], y=[0.18, 1.0]),
    )])
    fig.update_layout(title='Burn-In Status')
    figures_html.append(('pie', _pie_html(fig, 'summary-burnin-pie', False)))

    # Total produced pie
    produced = summary.get('total_produced') or {}
    fig = go.Figure(data=[go.Pie(
        labels=['Passed after Burn-In', 'Failed after Burn-In', 'No Test / Untested', 'Not Yet Produced'],
        values=[
            produced.get('passed_after_burnin', 0),
            produced.get('failed_after_burnin', 0),
            produced.get('no_test_or_untested', 0),
            produced.get('not_yet_produced', 0),
        ],
        marker=dict(colors=[
            colors.get('passed', '#00CC96'),
            colors.get('failed', '#EF553B'),
            colors.get('no_test', '#FECB52'),
            colors.get('not_yet_produced', '#B6B6B6'),
        ]),
        hole=0.35,
        domain=dict(x=[0.05, 0.95], y=[0.18, 1.0]),
    )])
    fig.update_layout(
        title=(
            f"Total Produced vs Expected "
            f"({produced.get('produced', 0)} / {produced.get('expected', 0)})"
        ),
    )
    figures_html.append(('pie', _pie_html(fig, 'summary-produced-pie', False)))

    def _line_html(fig, div_id):
        return to_html(
            fig,
            include_plotlyjs=False,
            full_html=False,
            div_id=div_id,
            config={'responsive': True, 'displayModeBar': False},
            default_width='100%',
            default_height=420,
        )

    # Cumulative by batch
    by_batch = summary.get('cumulative_by_batch') or {}
    batches = by_batch.get('batches') or []
    fig = go.Figure()
    if batches:
        fig.add_trace(go.Scatter(
            x=batches, y=by_batch.get('passed') or [], mode='lines+markers',
            name='Passed', line=dict(color=colors.get('passed', '#00CC96')),
        ))
        fig.add_trace(go.Scatter(
            x=batches, y=by_batch.get('failed') or [], mode='lines+markers',
            name='Failed', line=dict(color=colors.get('failed', '#EF553B')),
        ))
        fig.add_trace(go.Scatter(
            x=batches, y=by_batch.get('no_test') or [], mode='lines+markers',
            name='No Test', line=dict(color=colors.get('no_test', '#FECB52')),
        ))
        expected = (summary.get('schedule') or {}).get('expected_by_batch') or {}
        if expected.get('batches') and expected.get('cumulative'):
            fig.add_trace(go.Scatter(
                x=expected['batches'], y=expected['cumulative'], mode='lines+markers',
                name='Expected Produced', line=dict(color=colors.get('expected_produced', '#636EFA'), dash='dash'),
            ))
    fig.update_layout(
        title='Cumulative Board Count (by Batch)',
        height=420,
        autosize=True,
        margin=dict(t=60, r=20, b=60, l=50),
        xaxis_title='Batch',
        yaxis_title='Cumulative Boards',
        legend=dict(orientation='h', y=-0.25),
    )
    figures_html.append(('wide', _line_html(fig, 'summary-batch-line')))

    # Cumulative by time
    by_time = summary.get('cumulative_by_time') or {}
    fig = go.Figure()
    for key, label, color_key in (
        ('passed', 'Passed', 'passed'),
        ('failed', 'Failed', 'failed'),
        ('no_test', 'No Test', 'no_test'),
    ):
        points = by_time.get(key) or []
        if not points:
            continue
        fig.add_trace(go.Scatter(
            x=[point.get('x') for point in points],
            y=[point.get('y') for point in points],
            mode='lines+markers',
            name=label,
            line=dict(color=colors.get(color_key, '#00CC96')),
            text=[point.get('serial') for point in points],
            hovertemplate='%{x}<br>%{y}<br>Serial: %{text}<extra></extra>',
        ))
    fig.update_layout(
        title='Cumulative Board Count (by Time)',
        height=420,
        autosize=True,
        margin=dict(t=60, r=20, b=60, l=50),
        xaxis_title='Time',
        yaxis_title='Cumulative Boards',
        legend=dict(orientation='h', y=-0.25),
    )
    figures_html.append(('wide', _line_html(fig, 'summary-time-line')))

    # Burn-in timeline
    timeline = summary.get('burnin_timeline') or []
    fig = go.Figure()
    if timeline:
        fig.add_trace(go.Scatter(
            x=[item.get('burn_in_center') for item in timeline],
            y=[item.get('y_pos') for item in timeline],
            mode='markers',
            name='Burned In',
            marker=dict(color=colors.get('burnin_timeline', '#AB63FA'), size=8),
            error_x=dict(
                type='data',
                array=[item.get('error_plus_ms', 0) for item in timeline],
                arrayminus=[item.get('error_minus_ms', 0) for item in timeline],
                symmetric=False,
                color=colors.get('burnin_timeline', '#AB63FA'),
                thickness=3,
                width=8,
            ),
            text=[
                (
                    f"Serial: {item.get('serial')}<br>Batch: {item.get('batch')}<br>"
                    f"Start: {item.get('burn_in_start')}<br>Stop: {item.get('burn_in_stop')}"
                )
                for item in timeline
            ],
            hovertemplate='%{text}<extra></extra>',
        ))
    expected_burnin = ((summary.get('schedule') or {}).get('expected_burnin_timeline') or [])
    if expected_burnin:
        fig.add_trace(go.Scatter(
            x=[item.get('burn_in_center') for item in expected_burnin],
            y=[item.get('y_pos') for item in expected_burnin],
            mode='markers',
            name='Expected Burned In',
            marker=dict(color=colors.get('expected_burnin', '#FF6692'), size=8, symbol='diamond'),
            error_x=dict(
                type='data',
                array=[item.get('error_plus_ms', 0) for item in expected_burnin],
                arrayminus=[item.get('error_minus_ms', 0) for item in expected_burnin],
                symmetric=False,
                color=colors.get('expected_burnin', '#FF6692'),
                thickness=3,
                width=8,
            ),
        ))
    fig.update_layout(
        title='Burn-In Timeline',
        height=420,
        autosize=True,
        margin=dict(t=60, r=20, b=60, l=50),
        xaxis_title='Burn-In Time',
        yaxis_title='Cumulative Board Count',
        legend=dict(orientation='h', y=-0.25),
    )
    figures_html.append(('wide', _line_html(fig, 'summary-burnin-timeline')))

    pie_cards = ''.join(
        f'<div class="chart-card pie-card">{chunk}</div>'
        for kind, chunk in figures_html if kind == 'pie'
    )
    wide_cards = ''.join(
        f'<div class="chart-card wide-card">{chunk}</div>'
        for kind, chunk in figures_html if kind == 'wide'
    )
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Production Summary (Cached)</title>
  <style>
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f5f7fa;
      color: #333;
    }}
    .page-title {{ padding: 12px 16px 4px; font-size: 20px; font-weight: 700; }}
    .meta {{ padding: 0 16px 12px; color: #666; font-size: 12px; }}
    .stats {{
      display: flex; flex-wrap: wrap; gap: 10px; padding: 0 16px 12px;
    }}
    .stat {{
      background: white; border: 1px solid #e4e8ee; border-radius: 8px;
      padding: 8px 12px; font-size: 13px;
    }}
    .charts {{
      display: flex; flex-direction: column; gap: 14px; padding: 0 16px 24px;
    }}
    .pies-row {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
      align-items: stretch;
    }}
    @media (max-width: 1100px) {{
      .pies-row {{ grid-template-columns: 1fr; }}
    }}
    .chart-card {{
      background: white; border-radius: 12px; padding: 8px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.05);
      position: relative;
      overflow: hidden;
      min-width: 0;
    }}
    .pie-card {{
      min-height: 420px;
      height: 420px;
    }}
    .wide-card {{
      min-height: 460px;
    }}
    .chart-card .js-plotly-plot,
    .chart-card .plot-container,
    .chart-card .svg-container {{
      width: 100% !important;
      max-width: 100%;
    }}
    .pie-card .js-plotly-plot,
    .pie-card .plot-container {{
      height: 400px !important;
    }}
  </style>
</head>
<body>
  {cache_banner_html(stamp)}
  <div class="page-title">Production Summary</div>
  <div class="meta">Cached Plotly snapshot · Cached: {escape(stamp)}</div>
  <div class="stats">
    <div class="stat"><strong>Total boards:</strong> {summary.get('total_boards', 0)}</div>
    <div class="stat"><strong>Post-burn-in pass rate:</strong> {summary.get('post_burnin_pass_rate', 0)}%</div>
    <div class="stat"><strong>Yield failure rate:</strong> {summary.get('yield_failure_rate', 0)}%</div>
    <div class="stat"><strong>Source timestamp:</strong> {escape(str(summary.get('timestamp') or ''))} UTC</div>
  </div>
  <div class="charts">
    <div class="pies-row">
      {pie_cards}
    </div>
    {wide_cards}
  </div>
</body>
</html>
'''


def save_production_summary_cache(summary, cached_at=None):
    PRODUCTION_SUMMARY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    moment = cached_at or datetime.now()
    if isinstance(moment, str):
        cached_at_text = moment
        stamp_for_name = datetime.now()
    else:
        cached_at_text = moment.strftime('%Y-%m-%d %H:%M:%S')
        stamp_for_name = moment

    for path in PRODUCTION_SUMMARY_CACHE_DIR.glob('production_summary_*'):
        try:
            path.unlink()
        except OSError as exc:
            print(f'Error clearing production summary cache {path}: {exc}')

    payload = dict(summary or {})
    payload['version'] = CACHE_VERSION
    payload['cached_at'] = cached_at_text
    payload['success'] = True

    json_text = json.dumps(payload, default=_json_default)
    html_text = build_production_summary_html(payload, cached_at=cached_at_text)

    stamped = stamp_for_name.strftime('%Y%m%dT%H%M%S')
    stamped_json = PRODUCTION_SUMMARY_CACHE_DIR / f'production_summary_{stamped}.json'
    stamped_html = PRODUCTION_SUMMARY_CACHE_DIR / f'production_summary_{stamped}.html'
    latest_json = PRODUCTION_SUMMARY_CACHE_DIR / LATEST_JSON_NAME
    latest_html = PRODUCTION_SUMMARY_CACHE_DIR / LATEST_HTML_NAME

    stamped_json.write_text(json_text, encoding='utf-8')
    latest_json.write_text(json_text, encoding='utf-8')
    if html_text:
        stamped_html.write_text(html_text, encoding='utf-8')
        latest_html.write_text(html_text, encoding='utf-8')

    return {
        'cache_dir': str(PRODUCTION_SUMMARY_CACHE_DIR),
        'cached_at': cached_at_text,
        'json': stamped_json.name,
        'html': stamped_html.name if html_text else None,
        'latest_json': latest_json.name,
        'latest_html': latest_html.name if html_text else None,
    }


def load_production_summary_cache():
    latest_json = PRODUCTION_SUMMARY_CACHE_DIR / LATEST_JSON_NAME
    if not latest_json.exists():
        return None
    try:
        payload = json.loads(latest_json.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        print(f'Error reading production summary cache {latest_json}: {exc}')
        return None
    if payload.get('version') != CACHE_VERSION:
        return None
    if not payload.get('success'):
        return None
    return payload
