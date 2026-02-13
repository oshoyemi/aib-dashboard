"""Generate AIB-Specific Symbotic Dashboard.

Pulls AIB data directly from BigQuery and generates a dedicated AIB dashboard.
"""

import pandas as pd
import json
from datetime import datetime
from pathlib import Path
from google.cloud import bigquery

DOWNLOADS = r"C:\Users\o0o01hq\Downloads"
AIB_DATA_FILE = Path(DOWNLOADS) / "symbotic_aib_data" / "aib_dashboard_data.csv"
OUTPUT_FILE = r"C:\Users\o0o01hq\OneDrive - Walmart Inc\Desktop\Codepuppy\aib_dashboard.html"
DAYS_BACK = 56  # ~8 weeks of data

print("="*70)
print("GENERATING AIB SYMBOTIC DASHBOARD FROM BIGQUERY")
print("="*70)

# Initialize BigQuery client
try:
    bq_client = bigquery.Client()
    print("\n[OK] Connected to BigQuery")
    USE_BIGQUERY = True
except Exception as e:
    print(f"\n[WARNING] Could not connect to BigQuery: {e}")
    print("[INFO] Falling back to local CSV file...")
    USE_BIGQUERY = False

df = None

# Fetch AIB data from BigQuery
if USE_BIGQUERY:
    print(f"\n[AIB] Querying BigQuery for AIB alarm data ({DAYS_BACK} days)...")
    aib_query = f"""
    SELECT 
        DC as SITE,
        CONCAT('AIB', EQUIPMENT_CELL) as CELLNAME,
        TIMESTAMP_START as ALARM_START,
        TIMESTAMP_END as ALARM_END,
        ALARM_TEXT as ALARMTEXT,
        ALARM_COMPONENT as COMPONENT,
        ALARM_DURATION_SECONDS / 60.0 as Duration_mins,
        ALARM_DURATION_SECONDS,
        DC,
        BUSINESS_DATE,
        EQUIPMENT_TYPE,
        BLOCKING as BLOCK,
        'AIB' as _source
    FROM `wmt-edw-sandbox.SYMBOTIC_DATA.snowflake_alarms`
    WHERE EQUIPMENT_TYPE = 'AIB'
    AND BUSINESS_DATE >= FORMAT_DATE('%Y-%m-%d', DATE_SUB(CURRENT_DATE(), INTERVAL {DAYS_BACK} DAY))
    ORDER BY TIMESTAMP_START DESC
    LIMIT 1500000
    """
    try:
        df = bq_client.query(aib_query).to_dataframe()
        df['Duration_mins'] = pd.to_numeric(df['Duration_mins'], errors='coerce').fillna(0)
        total_aib_downtime = df['Duration_mins'].sum()
        print(f"   [OK] Retrieved {len(df):,} AIB records from BigQuery")
        print(f"   AIB Total Downtime: {total_aib_downtime:,.1f} mins ({total_aib_downtime/60:,.1f} hours)")
        if len(df) > 0:
            print(f"   AIB Date Range: {df['ALARM_START'].min()} to {df['ALARM_START'].max()}")
            print(f"   AIB Sites: {', '.join(str(s) for s in df['SITE'].dropna().unique()[:10])}...")
    except Exception as e:
        print(f"   [ERROR] AIB BigQuery query failed: {e}")
        df = None

# Fallback to local CSV if BigQuery failed
if df is None or len(df) == 0:
    if not AIB_DATA_FILE.exists():
        print(f"\n[ERROR] AIB data file not found: {AIB_DATA_FILE}")
        print("Please ensure BigQuery connection works or export data first.")
        exit(1)
    
    file_size_mb = AIB_DATA_FILE.stat().st_size / (1024*1024)
    print(f"\n[FALLBACK] Loading AIB data from CSV: {AIB_DATA_FILE.name} ({file_size_mb:.1f} MB)")
    
    if file_size_mb > 200:
        print("Large file detected - loading up to 1,000,000 rows")
        df = pd.read_csv(AIB_DATA_FILE, nrows=1000000)
    else:
        df = pd.read_csv(AIB_DATA_FILE)
    print(f"Loaded {len(df):,} AIB records from CSV")

# Parse dates if not already done
if 'ALARM_START' in df.columns and df['ALARM_START'].dtype == 'object':
    df['ALARM_START'] = pd.to_datetime(df['ALARM_START'], errors='coerce')
if 'ALARM_END' in df.columns and df['ALARM_END'].dtype == 'object':
    df['ALARM_END'] = pd.to_datetime(df['ALARM_END'], errors='coerce')

# Use ALARM_DURATION_MINUTES if available
if 'ALARM_DURATION_MINUTES' in df.columns:
    df['Duration_mins'] = pd.to_numeric(df['ALARM_DURATION_MINUTES'], errors='coerce').fillna(0)
elif 'ALARM_DURATION_SECONDS' in df.columns:
    df['Duration_mins'] = pd.to_numeric(df['ALARM_DURATION_SECONDS'], errors='coerce').fillna(0) / 60
else:
    df['Duration_mins'] = 0

# Fix CELLNAME - prefix with 'AIB' if it's just a number
if 'CELLNAME' in df.columns:
    df['CELLNAME'] = df['CELLNAME'].apply(lambda x: f'AIB{x}' if str(x).isdigit() else str(x))

print(f"\nData Summary:")
print(f"  Date Range: {df['ALARM_START'].min()} to {df['ALARM_START'].max()}")
print(f"  Sites: {', '.join(df['SITE'].unique().tolist()[:10])}{'...' if len(df['SITE'].unique()) > 10 else ''}")
print(f"  Unique Cells: {df['CELLNAME'].nunique()}")
print(f"  Total Downtime: {df['Duration_mins'].sum():,.1f} mins ({df['Duration_mins'].sum()/60:,.1f} hours)")

# Calculate metrics
total_incidents = len(df)
total_downtime = df['Duration_mins'].sum()
avg_downtime = df['Duration_mins'].mean() if total_incidents > 0 else 0

# Get date range
min_date = df['ALARM_START'].min()
max_date = df['ALARM_START'].max()
date_range = f"{min_date.strftime('%B %d, %Y')} - {max_date.strftime('%B %d, %Y')}" if pd.notna(min_date) else "Unknown"
min_date_str = min_date.strftime('%Y-%m-%d') if pd.notna(min_date) else ''
max_date_str = max_date.strftime('%Y-%m-%d') if pd.notna(max_date) else ''

# Analyze by cell
if 'CELLNAME' in df.columns:
    cell_stats = df.groupby('CELLNAME').agg(
        Incidents=('CELLNAME', 'count'),
        Total_Duration=('Duration_mins', 'sum')
    ).sort_values('Incidents', ascending=False).head(15)
    print(f"\nTop 5 AIB Cells:")
    for cell, row in cell_stats.head(5).iterrows():
        print(f"  {cell}: {row['Incidents']:,} incidents, {row['Total_Duration']:,.1f} mins")

# Analyze by component
if 'COMPONENT' in df.columns:
    comp_stats = df['COMPONENT'].value_counts().head(15)
    print(f"\nTop 5 Components:")
    for comp, count in comp_stats.head(5).items():
        print(f"  {comp}: {count:,} incidents")

# Get unique values for filters
all_sites = sorted(df['SITE'].unique().tolist()) if 'SITE' in df.columns else []
all_cells = sorted(df['CELLNAME'].unique().tolist()) if 'CELLNAME' in df.columns else []

# Calculate Walmart week
def get_walmart_week(date_str):
    if pd.isna(date_str):
        return None
    try:
        if isinstance(date_str, str):
            date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        else:
            date = date_str
        fy_start = datetime(2025, 2, 1)
        days_diff = (date.replace(tzinfo=None) - fy_start).days
        week_num = (days_diff // 7) + 1
        if week_num > 52:
            return f"W{week_num - 52:02d}"
        return f"W{week_num:02d}"
    except:
        return None

df['WM_WEEK'] = df['ALARM_START'].apply(get_walmart_week)
all_wm_weeks = sorted([w for w in df['WM_WEEK'].unique() if w], reverse=True)
print(f"\nWalmart Weeks: {', '.join(all_wm_weeks)}")

# Prepare raw data for JavaScript
print("\nPreparing data for dashboard...")
raw_incidents = []
for _, row in df.iterrows():
    incident = {
        'site': str(row.get('SITE', '')),
        'cell': str(row.get('CELLNAME', '')),
        'component': str(row.get('COMPONENT', '')),
        'alarm_text': str(row.get('ALARMTEXT', ''))[:200],
        'alarm_start': row['ALARM_START'].isoformat() if pd.notna(row.get('ALARM_START')) else None,
        'duration_mins': float(row['Duration_mins']) if pd.notna(row.get('Duration_mins')) else 0,
        'wm_week': row.get('WM_WEEK', None),
        'blocking': bool(row.get('BLOCKING', False)) if pd.notna(row.get('BLOCKING')) else False,
        'starving': bool(row.get('STARVING', False)) if pd.notna(row.get('STARVING')) else False,
        'driveway': str(row.get('EQUIPMENT_DRIVEWAY', '')) if pd.notna(row.get('EQUIPMENT_DRIVEWAY')) else ''
    }
    raw_incidents.append(incident)

print(f"Embedded {len(raw_incidents):,} incidents")

# Generate timestamp
generated_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# Create HTML
print("\nGenerating AIB Dashboard HTML...")

html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AIB Symbotic Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <script src="https://cdn.sheetjs.com/xlsx-0.20.1/package/dist/xlsx.full.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #e8f4fc 0%, #c3dff0 100%);
            padding: 20px;
            color: #262730;
        }}
        .container {{
            max-width: 1600px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 10px 40px rgba(0,113,206,0.15);
            padding: 30px;
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 4px solid #0071CE;
            background: linear-gradient(135deg, #0071CE 0%, #004a8c 100%);
            margin: -30px -30px 30px -30px;
            padding: 30px;
            border-radius: 10px 10px 0 0;
            color: white;
        }}
        .header h1 {{
            font-size: 2.5rem;
            margin-bottom: 10px;
        }}
        .header .subtitle {{
            opacity: 0.9;
            font-size: 1.1rem;
        }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }}
        .metric-card {{
            background: linear-gradient(135deg, #0071CE 0%, #005299 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .metric-card.blocking {{
            background: linear-gradient(135deg, #ea1100 0%, #b80d00 100%);
        }}
        .metric-card.starving {{
            background: linear-gradient(135deg, #FFC220 0%, #cc9a1a 100%);
            color: #333;
        }}
        .metric-label {{
            font-size: 0.85rem;
            opacity: 0.9;
            margin-bottom: 8px;
        }}
        .metric-value {{
            font-size: 2rem;
            font-weight: bold;
        }}
        .filters-section {{
            background: #f0f7ff;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 30px;
            border: 2px solid #0071CE;
        }}
        .filters-section h3 {{
            color: #0071CE;
            margin-bottom: 15px;
        }}
        .filter-row {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 15px;
        }}
        .filter-group {{
            display: flex;
            flex-direction: column;
        }}
        .filter-group label {{
            font-weight: 600;
            margin-bottom: 5px;
            color: #333;
            font-size: 0.9rem;
        }}
        .filter-group select, .filter-group input {{
            padding: 10px;
            border: 1px solid #0071CE;
            border-radius: 5px;
            font-size: 0.95rem;
        }}
        .btn {{
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
        }}
        .btn-primary {{
            background: #0071CE;
            color: white;
        }}
        .btn-primary:hover {{
            background: #005a9c;
            transform: translateY(-2px);
        }}
        .chart-section {{
            margin-bottom: 30px;
        }}
        .chart-section h2 {{
            color: #0071CE;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #e0e0e0;
        }}
        .chart-container {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            margin-bottom: 20px;
        }}
        .insights-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .insight-card {{
            background: #f8fbff;
            border-radius: 10px;
            padding: 20px;
            border: 2px solid #0071CE;
        }}
        .insight-card h3 {{
            color: #0071CE;
            margin-bottom: 15px;
            font-size: 1.1rem;
        }}
        .insight-card.blocking {{
            border-color: #ea1100;
            background: #fff8f8;
        }}
        .insight-card.blocking h3 {{
            color: #ea1100;
        }}
        .insight-card.starving {{
            border-color: #FFC220;
            background: #fffdf5;
        }}
        .insight-card.starving h3 {{
            color: #996b00;
        }}
        .alarm-item {{
            padding: 10px;
            margin-bottom: 8px;
            background: white;
            border-radius: 6px;
            border-left: 4px solid #0071CE;
            font-size: 0.9rem;
        }}
        .alarm-item.blocking {{
            border-left-color: #ea1100;
        }}
        .alarm-item.starving {{
            border-left-color: #FFC220;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background: #0071CE;
            color: white;
        }}
        tr:hover {{ background: #f5f9ff; }}
        .update-info {{
            text-align: center;
            color: #666;
            font-size: 0.9rem;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #eee;
        }}
        .filter-status {{
            margin-top: 10px;
            padding: 10px;
            background: #d4edda;
            border-radius: 5px;
            color: #155724;
            font-weight: 600;
            text-align: center;
        }}
        .recommendation {{
            padding: 12px;
            margin-bottom: 10px;
            border-radius: 8px;
            border-left: 4px solid #2a8703;
            background: #f0fff0;
        }}
        .recommendation.high {{
            border-left-color: #ea1100;
            background: #fff5f5;
        }}
        .recommendation.medium {{
            border-left-color: #FFC220;
            background: #fffbf0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔷 AIB Symbotic Dashboard</h1>
            <div class="subtitle">
                Generated: {generated_time} | Data Range: {date_range}<br>
                {len(all_sites)} Sites | {len(all_cells)} Cells | {total_incidents:,} Total Alarms
            </div>
        </div>

        <div class="filters-section">
            <h3>🔍 Filter Dashboard</h3>
            <div class="filter-row">
                <div class="filter-group">
                    <label for="wmWeekFilter">Walmart Week:</label>
                    <select id="wmWeekFilter">
                        <option value="ALL">All Weeks</option>
                        {chr(10).join([f'<option value="{wk}">{wk}</option>' for wk in all_wm_weeks])}
                    </select>
                </div>
                <div class="filter-group">
                    <label for="siteFilter">Site/DC:</label>
                    <select id="siteFilter" multiple size="5">
                        <option value="ALL" selected>All Sites</option>
                        {chr(10).join([f'<option value="{site}">{site}</option>' for site in all_sites])}
                    </select>
                </div>
                <div class="filter-group">
                    <label for="cellFilter">Cell:</label>
                    <select id="cellFilter" multiple size="5">
                        <option value="ALL" selected>All Cells</option>
                        {chr(10).join([f'<option value="{cell}">{cell}</option>' for cell in all_cells])}
                    </select>
                </div>
                <div class="filter-group">
                    <label for="alarmTypeFilter">Alarm Type:</label>
                    <select id="alarmTypeFilter">
                        <option value="ALL" selected>All Alarms</option>
                        <option value="BLOCKING">Blocking Only</option>
                        <option value="STARVING">Starving Only</option>
                    </select>
                </div>
            </div>
            <div class="filter-row" style="margin-top: 10px;">
                <div class="filter-group">
                    <label for="startDate">📅 Start Date:</label>
                    <input type="date" id="startDate" value="{min_date_str}">
                </div>
                <div class="filter-group">
                    <label for="endDate">📅 End Date:</label>
                    <input type="date" id="endDate" value="{max_date_str}">
                </div>
            </div>
            <button class="btn btn-primary" onclick="applyFilters()">Apply Filters</button>
            <button class="btn" style="background: #6c757d; color: white; margin-left: 10px;" onclick="resetFilters()">Reset</button>
            <div id="filterStatus" class="filter-status" style="display: none;"></div>
        </div>

        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-label">Total AIB Alarms</div>
                <div class="metric-value" id="metricTotal">{total_incidents:,}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Total Downtime (hrs)</div>
                <div class="metric-value" id="metricDowntime">{total_downtime/60:,.1f}</div>
            </div>
            <div class="metric-card blocking">
                <div class="metric-label">Blocking Alarms</div>
                <div class="metric-value" id="metricBlocking">{df['BLOCKING'].sum() if 'BLOCKING' in df.columns else 0:,}</div>
            </div>
            <div class="metric-card starving">
                <div class="metric-label">Starving Alarms</div>
                <div class="metric-value" id="metricStarving">{df['STARVING'].sum() if 'STARVING' in df.columns else 0:,}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Avg Duration (mins)</div>
                <div class="metric-value" id="metricAvg">{avg_downtime:.2f}</div>
            </div>
        </div>

        <!-- Weekly Insights Section -->
        <div class="chart-section" id="weeklyInsightsSection" style="display: none;">
            <h2>💡 Weekly Insights & Recommendations</h2>
            <div id="weeklyInsightsInfo" style="margin-bottom: 15px; padding: 12px; background: #e7f3ff; border-radius: 6px; border-left: 4px solid #0071CE;">
                <strong>Analyzing:</strong> <span id="insightsWeekLabel">-</span> | <span id="insightsSiteLabel">All Sites</span>
            </div>
            
            <div class="insights-grid">
                <div class="insight-card">
                    <h3>🚨 Top 3 Loss Alarms (by Downtime)</h3>
                    <div id="topLossAlarms"></div>
                </div>
                <div class="insight-card blocking">
                    <h3>⛔ Top 3 Blocking Alarms</h3>
                    <div id="topBlockingAlarms"></div>
                </div>
                <div class="insight-card starving">
                    <h3>📉 Top 3 Starving Alarms</h3>
                    <div id="topStarvingAlarms"></div>
                </div>
            </div>
            
            <div class="insights-grid">
                <div class="insight-card">
                    <h3>🏭 Most Impacted Cell: <span id="mostImpactedCell">-</span></h3>
                    <div id="mostImpactedCellAlarms"></div>
                </div>
                <div class="insight-card" style="border-color: #2a8703;">
                    <h3 style="color: #2a8703;">✅ Recommendations</h3>
                    <div id="weeklyRecommendations"></div>
                </div>
            </div>
        </div>

        <div class="chart-section">
            <h2>📊 Top 15 AIB Cells by Incident Count <span style="font-size: 0.7em; color: #666; font-weight: normal;">— Click a bar to drill down</span></h2>
            <div id="cellFilterBadge" style="display: none; margin-bottom: 10px; padding: 8px 15px; background: #e7f3ff; border-radius: 20px; border: 2px solid #0071CE; display: inline-flex; align-items: center; gap: 10px;">
                <span>🔍 Filtering by: <strong id="cellFilterLabel"></strong></span>
                <button onclick="clearCellSelection()" style="background: #ea1100; color: white; border: none; border-radius: 50%; width: 22px; height: 22px; cursor: pointer; font-weight: bold; font-size: 0.8rem;">✕</button>
            </div>
            <div class="chart-container" style="height: 400px;">
                <canvas id="cellChart"></canvas>
            </div>
        </div>

        <div class="chart-section">
            <h2>🔧 Top 15 Components (Pareto Analysis) <span id="compChartCellLabel" style="font-size: 0.7em; color: #0071CE;"></span> <span style="font-size: 0.7em; color: #666; font-weight: normal;">— Click a bar to drill down</span></h2>
            <div id="compFilterBadge" style="display: none; margin-bottom: 10px; padding: 8px 15px; background: #fff3e0; border-radius: 20px; border: 2px solid #FF6900; display: inline-flex; align-items: center; gap: 10px;">
                <span>🔧 Filtering by component: <strong id="compFilterLabel"></strong></span>
                <button onclick="clearComponentSelection()" style="background: #ea1100; color: white; border: none; border-radius: 50%; width: 22px; height: 22px; cursor: pointer; font-weight: bold; font-size: 0.8rem;">✕</button>
            </div>
            <div class="chart-container" style="height: 400px;">
                <canvas id="componentChart"></canvas>
            </div>
        </div>

        <div class="chart-section">
            <h2>⚠️ Top 10 Alarm Types <span id="alarmChartCellLabel" style="font-size: 0.7em; color: #0071CE;"></span> <span id="alarmChartCompLabel" style="font-size: 0.7em; color: #FF6900;"></span></h2>
            <div class="chart-container" style="height: 350px;">
                <canvas id="alarmChart"></canvas>
            </div>
        </div>

        <div class="chart-section">
            <h2>📋 Detailed Cell Statistics</h2>
            <div class="chart-container">
                <table id="cellTable">
                    <thead>
                        <tr>
                            <th>Rank</th>
                            <th>Cell</th>
                            <th>Incidents</th>
                            <th>Downtime (mins)</th>
                            <th>Blocking</th>
                            <th>Starving</th>
                            <th>Avg Duration</th>
                        </tr>
                    </thead>
                    <tbody id="cellTableBody"></tbody>
                </table>
            </div>
        </div>

        <div class="update-info">
            AIB Dashboard generated from BigQuery: wmt-edw-sandbox.SYMBOTIC_DATA.snowflake_alarms<br>
            {len(df):,} AIB alarms analyzed | Built with Code Puppy 🐶
        </div>
    </div>

    <script>
        const rawIncidents = {json.dumps(raw_incidents)};
        
        let cellChart = null;
        let componentChart = null;
        let alarmChart = null;
        let selectedCell = null;
        let selectedComponent = null;
        let lastFilteredData = null;
        
        // Calculate cumulative percentages for Pareto
        function calculateCumulativePercentages(values) {{
            const total = values.reduce((sum, val) => sum + val, 0);
            if (total === 0) return values.map(() => 0);
            let cumSum = 0;
            return values.map(val => {{
                cumSum += val;
                return (cumSum / total) * 100;
            }});
        }}
        
        // Handle cell bar click — drill down into components + alarm types
        function onCellBarClick(event, elements) {{
            if (!elements || elements.length === 0) return;
            const idx = elements[0].index;
            const clickedCell = cellChart.data.labels[idx];
            
            // Toggle: if same cell clicked again, clear selection
            if (selectedCell === clickedCell) {{
                clearCellSelection();
                return;
            }}
            
            selectedCell = clickedCell;
            // Clear component selection when switching cells
            clearComponentSelection();
            
            const data = lastFilteredData || rawIncidents;
            const cellData = data.filter(inc => inc.cell === selectedCell);
            
            // Highlight selected bar
            const colors = cellChart.data.labels.map(label =>
                label === selectedCell ? '#FFC220' : '#0071CE'
            );
            cellChart.data.datasets[0].backgroundColor = colors;
            cellChart.update();
            
            // Update components chart for selected cell
            updateComponentsForCell(cellData);
            updateAlarmsForCell(cellData);
            
            // Show badge
            document.getElementById('cellFilterBadge').style.display = 'inline-flex';
            document.getElementById('cellFilterLabel').textContent = selectedCell;
            document.getElementById('compChartCellLabel').textContent = '\u2014 ' + selectedCell;
            document.getElementById('alarmChartCellLabel').textContent = '\u2014 ' + selectedCell;
        }}
        
        function clearCellSelection() {{
            selectedCell = null;
            const data = lastFilteredData || rawIncidents;
            
            // Reset bar colors
            if (cellChart) {{
                cellChart.data.datasets[0].backgroundColor = '#0071CE';
                cellChart.update();
            }}
            
            // Also clear component selection when cell changes
            clearComponentSelection();
            
            // Reset components + alarms to full data
            updateComponentsForCell(data);
            updateAlarmsForCell(data);
            
            // Hide badge
            document.getElementById('cellFilterBadge').style.display = 'none';
            document.getElementById('compChartCellLabel').textContent = '';
            document.getElementById('alarmChartCellLabel').textContent = '';
        }}
        
        function updateComponentsForCell(data) {{
            const compCounts = {{}};
            data.forEach(inc => {{
                compCounts[inc.component] = (compCounts[inc.component] || 0) + 1;
            }});
            const sortedComps = Object.entries(compCounts).sort((a, b) => b[1] - a[1]).slice(0, 15);
            const compValues = sortedComps.map(c => c[1]);
            const cumulativePcts = calculateCumulativePercentages(compValues);
            
            if (componentChart) {{
                componentChart.data.labels = sortedComps.map(c => c[0]);
                componentChart.data.datasets[0].data = compValues;
                componentChart.data.datasets[1].data = cumulativePcts;
                // Preserve component highlight if selected
                if (selectedComponent) {{
                    componentChart.data.datasets[0].backgroundColor = sortedComps.map(c =>
                        c[0] === selectedComponent ? '#FFC220' : '#0071CE'
                    );
                }} else {{
                    componentChart.data.datasets[0].backgroundColor = '#0071CE';
                }}
                componentChart.update();
            }}
        }}
        
        function updateAlarmsForCell(data) {{
            // If a component is selected, further filter by component
            const filteredData = selectedComponent
                ? data.filter(inc => inc.component === selectedComponent)
                : data;
            
            const alarmCounts = {{}};
            filteredData.forEach(inc => {{
                const text = inc.alarm_text.length > 50 ? inc.alarm_text.substring(0, 50) + '...' : inc.alarm_text;
                alarmCounts[text] = (alarmCounts[text] || 0) + 1;
            }});
            const sortedAlarms = Object.entries(alarmCounts).sort((a, b) => b[1] - a[1]).slice(0, 10);
            
            if (alarmChart) {{
                alarmChart.data.labels = sortedAlarms.map(a => a[0]);
                alarmChart.data.datasets[0].data = sortedAlarms.map(a => a[1]);
                alarmChart.update();
            }}
        }}
        
        // Handle component bar click — drill down into alarm types
        function onComponentBarClick(event, elements) {{
            if (!elements || elements.length === 0) return;
            // Only respond to clicks on the bar dataset (index 0), not the cumulative % line (index 1)
            if (elements[0].datasetIndex !== 0) return;
            
            const idx = elements[0].index;
            const clickedComp = componentChart.data.labels[idx];
            
            // Toggle: if same component clicked again, clear selection
            if (selectedComponent === clickedComp) {{
                clearComponentSelection();
                return;
            }}
            
            selectedComponent = clickedComp;
            
            // Highlight selected bar on component chart
            const colors = componentChart.data.labels.map(label =>
                label === selectedComponent ? '#FFC220' : '#0071CE'
            );
            componentChart.data.datasets[0].backgroundColor = colors;
            componentChart.update();
            
       // Get the current working data (respects cell selection + filters)
            const data = lastFilteredData || rawIncidents;
            const drillData = selectedCell ? data.filter(inc => inc.cell === selectedCell) : data;
            updateAlarmsForCell(drillData);
            
            // Show badge + labels
            document.getElementById('compFilterBadge').style.display = 'inline-flex';
            document.getElementById('compFilterLabel').textContent = selectedComponent;
            document.getElementById('alarmChartCompLabel').textContent = '\u2014 ' + selectedComponent;
        }}
        
        function clearComponentSelection() {{
            selectedComponent = null;
            
            // Reset component bar colors
            if (componentChart) {{
                componentChart.data.datasets[0].backgroundColor = '#0071CE';
                componentChart.update();
            }}
            
            // Refresh alarms with full data (respecting cell selection)
            const data = lastFilteredData || rawIncidents;
            const drillData = selectedCell ? data.filter(inc => inc.cell === selectedCell) : data;
            updateAlarmsForCell(drillData);
            
            // Hide badge + labels
            document.getElementById('compFilterBadge').style.display = 'none';
            document.getElementById('alarmChartCompLabel').textContent = '';
        }}
        
        // Get previous Walmart week
        function getPreviousWeek(weekStr) {{
            if (!weekStr || weekStr === 'ALL') return null;
            const weekNum = parseInt(weekStr.replace('W', ''));
            if (weekNum <= 1) return 'W52';
            return 'W' + String(weekNum - 1).padStart(2, '0');
        }}
        
        // Apply filters
        function applyFilters() {{
            const selectedWeek = document.getElementById('wmWeekFilter').value;
            const siteSelect = document.getElementById('siteFilter');
            const selectedSites = Array.from(siteSelect.selectedOptions).map(opt => opt.value);
            const cellSelect = document.getElementById('cellFilter');
            const selectedCells = Array.from(cellSelect.selectedOptions).map(opt => opt.value);
            const alarmType = document.getElementById('alarmTypeFilter').value;
            const startDate = document.getElementById('startDate').value;
            const endDate = document.getElementById('endDate').value;
            
            let filtered = rawIncidents.filter(inc => {{
                if (selectedWeek !== 'ALL' && inc.wm_week !== selectedWeek) return false;
                if (!selectedSites.includes('ALL') && !selectedSites.includes(inc.site)) return false;
                if (!selectedCells.includes('ALL') && !selectedCells.includes(inc.cell)) return false;
                if (alarmType === 'BLOCKING' && !inc.blocking) return false;
                if (alarmType === 'STARVING' && !inc.starving) return false;
                if (startDate && inc.alarm_start) {{
                    const incDate = inc.alarm_start.substring(0, 10);
                    if (incDate < startDate) return false;
                }}
                if (endDate && inc.alarm_start) {{
                    const incDate = inc.alarm_start.substring(0, 10);
                    if (incDate > endDate) return false;
                }}
                return true;
            }});
            
            // Update metrics
            const totalIncidents = filtered.length;
            const totalDowntime = filtered.reduce((sum, inc) => sum + inc.duration_mins, 0);
            const blockingCount = filtered.filter(inc => inc.blocking).length;
            const starvingCount = filtered.filter(inc => inc.starving).length;
            const avgDowntime = totalIncidents > 0 ? totalDowntime / totalIncidents : 0;
            
            document.getElementById('metricTotal').textContent = totalIncidents.toLocaleString();
            document.getElementById('metricDowntime').textContent = (totalDowntime / 60).toFixed(1);
            document.getElementById('metricBlocking').textContent = blockingCount.toLocaleString();
            document.getElementById('metricStarving').textContent = starvingCount.toLocaleString();
            document.getElementById('metricAvg').textContent = avgDowntime.toFixed(2);
            
            // Update charts
            updateCharts(filtered);
            updateTable(filtered);
            
            // Update insights if week selected
            if (selectedWeek !== 'ALL') {{
                updateWeeklyInsights(filtered, selectedWeek, selectedSites);
            }} else {{
                document.getElementById('weeklyInsightsSection').style.display = 'none';
            }}
            
            // Show status
            const status = document.getElementById('filterStatus');
            status.style.display = 'block';
            status.textContent = `Showing ${{totalIncidents.toLocaleString()}} alarms | ${{(totalDowntime/60).toFixed(1)}} hours downtime | ${{blockingCount.toLocaleString()}} blocking | ${{starvingCount.toLocaleString()}} starving`;
        }}
        
        // Reset filters
        function resetFilters() {{
            document.getElementById('wmWeekFilter').value = 'ALL';
            document.getElementById('alarmTypeFilter').value = 'ALL';
            document.getElementById('startDate').value = '{min_date_str}';
            document.getElementById('endDate').value = '{max_date_str}';
            Array.from(document.getElementById('siteFilter').options).forEach(opt => opt.selected = opt.value === 'ALL');
            Array.from(document.getElementById('cellFilter').options).forEach(opt => opt.selected = opt.value === 'ALL');
            clearCellSelection();
            
            document.getElementById('metricTotal').textContent = '{total_incidents:,}';
            document.getElementById('metricDowntime').textContent = '{total_downtime/60:,.1f}';
            document.getElementById('metricBlocking').textContent = '{df["BLOCKING"].sum() if "BLOCKING" in df.columns else 0:,}';
            document.getElementById('metricStarving').textContent = '{df["STARVING"].sum() if "STARVING" in df.columns else 0:,}';
            document.getElementById('metricAvg').textContent = '{avg_downtime:.2f}';
            
            document.getElementById('weeklyInsightsSection').style.display = 'none';
            document.getElementById('filterStatus').style.display = 'none';
            
            updateCharts(rawIncidents);
            updateTable(rawIncidents);
        }}
        
        // Update charts
        function updateCharts(data) {{
            lastFilteredData = data;
            
            // Cell chart
            const cellCounts = {{}};
            data.forEach(inc => {{
                cellCounts[inc.cell] = (cellCounts[inc.cell] || 0) + 1;
            }});
            const sortedCells = Object.entries(cellCounts).sort((a, b) => b[1] - a[1]).slice(0, 15);
            
            if (cellChart) {{
                cellChart.data.labels = sortedCells.map(c => c[0]);
                cellChart.data.datasets[0].data = sortedCells.map(c => c[1]);
                // Preserve highlight if a cell is selected
                if (selectedCell) {{
                    cellChart.data.datasets[0].backgroundColor = sortedCells.map(c =>
                        c[0] === selectedCell ? '#FFC220' : '#0071CE'
                    );
                }} else {{
                    cellChart.data.datasets[0].backgroundColor = '#0071CE';
                }}
                cellChart.update();
            }}
            
            // If a cell is selected, only update components/alarms for that cell
            const drillData = selectedCell ? data.filter(inc => inc.cell === selectedCell) : data;
            updateComponentsForCell(drillData);
            updateAlarmsForCell(drillData);
        }}
        
        // Update table
        function updateTable(data) {{
            const cellStats = {{}};
            data.forEach(inc => {{
                if (!cellStats[inc.cell]) {{
                    cellStats[inc.cell] = {{ count: 0, downtime: 0, blocking: 0, starving: 0 }};
                }}
                cellStats[inc.cell].count++;
                cellStats[inc.cell].downtime += inc.duration_mins;
                if (inc.blocking) cellStats[inc.cell].blocking++;
                if (inc.starving) cellStats[inc.cell].starving++;
            }});
            
            const sorted = Object.entries(cellStats).sort((a, b) => b[1].count - a[1].count).slice(0, 20);
            
            const tbody = document.getElementById('cellTableBody');
            tbody.innerHTML = sorted.map((item, idx) => {{
                const [cell, stats] = item;
                const avg = stats.count > 0 ? (stats.downtime / stats.count).toFixed(2) : '0.00';
                return `
                    <tr>
                        <td><strong>${{idx + 1}}</strong></td>
                        <td>${{cell}}</td>
                        <td>${{stats.count.toLocaleString()}}</td>
                        <td>${{stats.downtime.toFixed(1)}}</td>
                        <td style="color: #ea1100;">${{stats.blocking.toLocaleString()}}</td>
                        <td style="color: #996b00;">${{stats.starving.toLocaleString()}}</td>
                        <td>${{avg}}</td>
                    </tr>
                `;
            }}).join('');
        }}
        
        // Update weekly insights
        function updateWeeklyInsights(data, selectedWeek, selectedSites) {{
            const section = document.getElementById('weeklyInsightsSection');
            section.style.display = 'block';
            
            document.getElementById('insightsWeekLabel').textContent = selectedWeek;
            document.getElementById('insightsSiteLabel').textContent = selectedSites.includes('ALL') ? 'All Sites' : selectedSites.join(', ');
            
            // Top 3 Loss Alarms
            const alarmDowntime = {{}};
            data.forEach(inc => {{
                if (!alarmDowntime[inc.alarm_text]) {{
                    alarmDowntime[inc.alarm_text] = {{ downtime: 0, count: 0 }};
                }}
                alarmDowntime[inc.alarm_text].downtime += inc.duration_mins;
                alarmDowntime[inc.alarm_text].count++;
            }});
            const topLoss = Object.entries(alarmDowntime).sort((a, b) => b[1].downtime - a[1].downtime).slice(0, 3);
            document.getElementById('topLossAlarms').innerHTML = topLoss.map((item, idx) => {{
                const [alarm, stats] = item;
                const display = alarm.length > 50 ? alarm.substring(0, 50) + '...' : alarm;
                return `<div class="alarm-item"><strong>#${{idx+1}}</strong> ${{display}}<br><small>${{stats.downtime.toFixed(0)}} mins | ${{stats.count}} occurrences</small></div>`;
            }}).join('');
            
            // Top 3 Blocking
            const blockingData = data.filter(inc => inc.blocking);
            const blockingAlarms = {{}};
            blockingData.forEach(inc => {{
                blockingAlarms[inc.alarm_text] = (blockingAlarms[inc.alarm_text] || 0) + 1;
            }});
            const topBlocking = Object.entries(blockingAlarms).sort((a, b) => b[1] - a[1]).slice(0, 3);
            document.getElementById('topBlockingAlarms').innerHTML = topBlocking.map((item, idx) => {{
                const [alarm, count] = item;
                const display = alarm.length > 50 ? alarm.substring(0, 50) + '...' : alarm;
                return `<div class="alarm-item blocking"><strong>#${{idx+1}}</strong> ${{display}}<br><small>${{count}} blocking alarms</small></div>`;
            }}).join('') || '<p style="color: #888;">No blocking alarms</p>';
            
            // Top 3 Starving
            const starvingData = data.filter(inc => inc.starving);
            const starvingAlarms = {{}};
            starvingData.forEach(inc => {{
                starvingAlarms[inc.alarm_text] = (starvingAlarms[inc.alarm_text] || 0) + 1;
            }});
            const topStarving = Object.entries(starvingAlarms).sort((a, b) => b[1] - a[1]).slice(0, 3);
            document.getElementById('topStarvingAlarms').innerHTML = topStarving.map((item, idx) => {{
                const [alarm, count] = item;
                const display = alarm.length > 50 ? alarm.substring(0, 50) + '...' : alarm;
                return `<div class="alarm-item starving"><strong>#${{idx+1}}</strong> ${{display}}<br><small>${{count}} starving alarms</small></div>`;
            }}).join('') || '<p style="color: #888;">No starving alarms</p>';
            
            // Most impacted cell
            const cellDowntime = {{}};
            data.forEach(inc => {{
                if (!cellDowntime[inc.cell]) {{
                    cellDowntime[inc.cell] = {{ downtime: 0, count: 0, topAlarm: {{}} }};
                }}
                cellDowntime[inc.cell].downtime += inc.duration_mins;
                cellDowntime[inc.cell].count++;
                cellDowntime[inc.cell].topAlarm[inc.alarm_text] = (cellDowntime[inc.cell].topAlarm[inc.alarm_text] || 0) + 1;
            }});
            const sortedCells = Object.entries(cellDowntime).sort((a, b) => b[1].downtime - a[1].downtime);
            
            if (sortedCells.length > 0) {{
                const [cellName, cellData] = sortedCells[0];
                document.getElementById('mostImpactedCell').textContent = `${{cellName}} (${{cellData.downtime.toFixed(0)}} mins)`;
                const cellTopAlarms = Object.entries(cellData.topAlarm).sort((a, b) => b[1] - a[1]).slice(0, 3);
                document.getElementById('mostImpactedCellAlarms').innerHTML = cellTopAlarms.map((item, idx) => {{
                    const [alarm, count] = item;
                    const display = alarm.length > 45 ? alarm.substring(0, 45) + '...' : alarm;
                    return `<div class="alarm-item"><strong>#${{idx+1}}</strong> ${{display}} <small>(${{count}}x)</small></div>`;
                }}).join('');
            }}
            
            // Recommendations
            const recommendations = [];
            if (topLoss.length > 0) {{
                const [alarm, stats] = topLoss[0];
                const short = alarm.length > 35 ? alarm.substring(0, 35) + '...' : alarm;
                recommendations.push(`<div class="recommendation high">🚨 <strong>Fix:</strong> "${{short}}" - ${{stats.downtime.toFixed(0)}} mins lost</div>`);
            }}
            if (sortedCells.length > 0) {{
                const [cellName, cellData] = sortedCells[0];
                recommendations.push(`<div class="recommendation high">🏭 <strong>Focus:</strong> ${{cellName}} needs attention (${{cellData.count}} alarms)</div>`);
            }}
            if (topBlocking.length > 0) {{
                recommendations.push(`<div class="recommendation medium">⛔ <strong>Blocking:</strong> ${{blockingData.length}} blocking alarms impacting flow</div>`);
            }}
            if (topStarving.length > 0) {{
                recommendations.push(`<div class="recommendation medium">📉 <strong>Starving:</strong> ${{starvingData.length}} starving alarms - check upstream</div>`);
            }}
            document.getElementById('weeklyRecommendations').innerHTML = recommendations.join('');
        }}
        
        // Initialize charts
        function initCharts() {{
            // Cell chart
            const cellCounts = {{}};
            rawIncidents.forEach(inc => {{
                cellCounts[inc.cell] = (cellCounts[inc.cell] || 0) + 1;
            }});
            const sortedCells = Object.entries(cellCounts).sort((a, b) => b[1] - a[1]).slice(0, 15);
            
            cellChart = new Chart(document.getElementById('cellChart'), {{
                type: 'bar',
                data: {{
                    labels: sortedCells.map(c => c[0]),
                    datasets: [{{
                        label: 'Incidents',
                        data: sortedCells.map(c => c[1]),
                        backgroundColor: '#0071CE',
                        borderColor: '#005299',
                        borderWidth: 1
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{ legend: {{ display: false }} }},
                    scales: {{ y: {{ beginAtZero: true }} }},
                    onClick: onCellBarClick,
                    onHover: (event, elements) => {{
                        event.native.target.style.cursor = elements.length ? 'pointer' : 'default';
                    }}
                }}
            }});
            
            // Component chart (Pareto)
            const compCounts = {{}};
            rawIncidents.forEach(inc => {{
                compCounts[inc.component] = (compCounts[inc.component] || 0) + 1;
            }});
            const sortedComps = Object.entries(compCounts).sort((a, b) => b[1] - a[1]).slice(0, 15);
            const compValues = sortedComps.map(c => c[1]);
            const cumulativePcts = calculateCumulativePercentages(compValues);
            
            componentChart = new Chart(document.getElementById('componentChart'), {{
                type: 'bar',
                data: {{
                    labels: sortedComps.map(c => c[0]),
                    datasets: [{{
                        label: 'Incidents',
                        data: compValues,
                        backgroundColor: '#0071CE',
                        borderWidth: 1,
                        yAxisID: 'y'
                    }}, {{
                        label: 'Cumulative %',
                        data: cumulativePcts,
                        type: 'line',
                        borderColor: '#FF6900',
                        borderWidth: 3,
                        pointRadius: 4,
                        fill: false,
                        yAxisID: 'y1'
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {{
                        y: {{ beginAtZero: true, position: 'left' }},
                        y1: {{ beginAtZero: true, position: 'right', max: 100, grid: {{ drawOnChartArea: false }} }}
                    }},
                    onClick: onComponentBarClick,
                    onHover: (event, elements) => {{
                        event.native.target.style.cursor = elements.length ? 'pointer' : 'default';
                    }}
                }}
            }});
            
            // Alarm chart
            const alarmCounts = {{}};
            rawIncidents.forEach(inc => {{
                const text = inc.alarm_text.length > 50 ? inc.alarm_text.substring(0, 50) + '...' : inc.alarm_text;
                alarmCounts[text] = (alarmCounts[text] || 0) + 1;
            }});
            const sortedAlarms = Object.entries(alarmCounts).sort((a, b) => b[1] - a[1]).slice(0, 10);
            
            alarmChart = new Chart(document.getElementById('alarmChart'), {{
                type: 'bar',
                data: {{
                    labels: sortedAlarms.map(a => a[0]),
                    datasets: [{{
                        label: 'Occurrences',
                        data: sortedAlarms.map(a => a[1]),
                        backgroundColor: '#FFC220',
                        borderWidth: 1
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    indexAxis: 'y',
                    plugins: {{ legend: {{ display: false }} }}
                }}
            }});
            
            // Initialize table
            updateTable(rawIncidents);
        }}
        
        // Event listeners
        document.getElementById('wmWeekFilter').addEventListener('change', applyFilters);
        document.getElementById('alarmTypeFilter').addEventListener('change', applyFilters);
        
        // Init
        initCharts();
        
        // Auto-reload at 5:05 AM daily to pick up fresh BigQuery data
        function scheduleAutoReload() {{
            const now = new Date();
            const target = new Date();
            target.setHours(5, 5, 0, 0);
            if (target <= now) target.setDate(target.getDate() + 1);
            const msUntilReload = target - now;
            console.log('[AIB Dashboard] Auto-reload scheduled in ' + Math.round(msUntilReload / 60000) + ' minutes (5:05 AM)');
            setTimeout(() => location.reload(), msUntilReload);
        }}
        scheduleAutoReload();
    </script>
</body>
</html>
'''

# Write HTML file
print(f"Writing dashboard to {OUTPUT_FILE}...")
with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write(html_content)

print("\n" + "="*70)
print("AIB DASHBOARD GENERATED!")
print("="*70)
print(f"\nSaved to: {OUTPUT_FILE}")
print(f"\nDashboard Statistics:")
print(f"  - Total AIB Alarms: {total_incidents:,}")
print(f"  - Total Downtime: {total_downtime:,.1f} mins ({total_downtime/60:,.1f} hours)")
print(f"  - Sites: {len(all_sites)}")
print(f"  - Cells: {len(all_cells)}")
print(f"  - Walmart Weeks: {', '.join(all_wm_weeks)}")
print(f"  - Date Range: {date_range}")
print("="*70)