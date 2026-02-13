"""Auto-refresh AIB Dashboard with fresh BigQuery data.

This script:
1. Queries BigQuery for latest AIB alarm data
2. Saves to CSV
3. Generates the AIB dashboard

Scheduled to run via Windows Task Scheduler.
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

LOG_FILE = Path(r"C:\Users\o0o01hq\OneDrive - Walmart Inc\Desktop\Codepuppy\aib_refresh_log.txt")
DATA_DIR = Path(r"C:\Users\o0o01hq\Downloads\symbotic_aib_data")
DATA_FILE = DATA_DIR / "aib_dashboard_data.csv"
DASHBOARD_SCRIPT = Path(r"C:\Users\o0o01hq\OneDrive - Walmart Inc\Desktop\Codepuppy\refresh_aib_dashboard.py")

def log(message):
    """Log message to file and console."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_msg = f"[{timestamp}] {message}"
    print(log_msg)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_msg + '\n')

def refresh_bigquery_data():
    """Query BigQuery for fresh AIB data using bq CLI."""
    log("Querying BigQuery for fresh AIB data (4 Walmart weeks)...")
    
    # Ensure data directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # BigQuery query - 35 days to ensure 4+ complete Walmart weeks
    # Uses MOD sampling to get ~25% of rows spanning full date range
    query = '''
    SELECT
        SITE,
        EQUIPMENT_CELL as CELLNAME,
        ALARM_COMPONENT as COMPONENT,
        ALARM_TEXT as ALARMTEXT,
        TIMESTAMP_START as ALARM_START,
        TIMESTAMP_END as ALARM_END,
        ALARM_DURATION_SECONDS,
        ROUND(ALARM_DURATION_SECONDS/60, 2) as ALARM_DURATION_MINUTES,
        DC,
        BUSINESS_DATE,
        EQUIPMENT_TYPE,
        BLOCKING,
        STARVING,
        EQUIPMENT_DRIVEWAY
    FROM `wmt-edw-sandbox.SYMBOTIC_DATA.snowflake_alarms`
    WHERE EQUIPMENT_TYPE = 'AIB'
      AND TIMESTAMP_START >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 35 DAY)
      AND MOD(ABS(FARM_FINGERPRINT(CAST(TIMESTAMP_START AS STRING))), 4) = 0
    ORDER BY TIMESTAMP_START DESC
    LIMIT 1500000
    '''
    
    # Run bq query and export to CSV
    # ~25% sampled data to capture 4+ Walmart weeks of AIB data
    cmd = [
        'bq', 'query',
        '--use_legacy_sql=false',
        '--format=csv',
        '--max_rows=1500000',
        query
    ]
    
    try:
        log("Running BQ query...")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )
        
        if result.returncode == 0:
            # Save to CSV
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                f.write(result.stdout)
            
            # Count rows
            row_count = len(result.stdout.strip().split('\n')) - 1  # minus header
            log(f"BigQuery data saved: {row_count:,} rows")
            return True
        else:
            log(f"BQ query failed: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        log("BQ query timed out after 10 minutes")
        return False
    except Exception as e:
        log(f"BQ query error: {str(e)}")
        return False

def generate_dashboard():
    """Run the dashboard generation script."""
    log("Generating AIB dashboard...")
    
    try:
        result = subprocess.run(
            [sys.executable, str(DASHBOARD_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            cwd=DASHBOARD_SCRIPT.parent
        )
        
        if result.returncode == 0:
            log("Dashboard generated successfully")
            # Log last few lines of output
            output_lines = result.stdout.strip().split('\n')[-5:]
            for line in output_lines:
                log(f"  {line}")
            return True
        else:
            log(f"Dashboard generation failed: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        log("Dashboard generation timed out")
        return False
    except Exception as e:
        log(f"Dashboard generation error: {str(e)}")
        return False

def main():
    """Main refresh workflow."""
    log("="*60)
    log("AIB DASHBOARD AUTO-REFRESH STARTED")
    log("="*60)
    
    # Check if data file exists and is recent (within 6 hours)
    # If BQ refresh fails, we can still use existing data
    bq_success = refresh_bigquery_data()
    
    if not bq_success:
        if DATA_FILE.exists():
            file_age_hours = (datetime.now().timestamp() - DATA_FILE.stat().st_mtime) / 3600
            log(f"Using existing data file (age: {file_age_hours:.1f} hours)")
        else:
            log("ERROR: No data file available. Cannot generate dashboard.")
            return
    
    # Generate dashboard
    dash_success = generate_dashboard()
    
    if dash_success:
        log("AIB DASHBOARD REFRESH COMPLETE!")
    else:
        log("Dashboard refresh completed with errors")
    
    log("="*60 + "\n")

if __name__ == '__main__':
    main()
