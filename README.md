# AIB Symbotic Dashboard

Interactive AIB downtime dashboard for Symbotic systems across all DCs.

## Features
- 📊 Top 15 AIB Cells by Incident Count (click to drill down)
- 🔧 Top 15 Components Pareto Analysis (click to drill down into alarm types)
- ⚠️ Top 10 Alarm Types
- 📅 Date range filtering
- 🏭 Site/DC multi-select filter
- 📦 Cell multi-select filter
- 📆 Walmart Week filter with insights
- 💾 Export to Excel

## Data
- Source: BigQuery (`SYMBOTIC_DATA.snowflake_alarms`)
- Auto-refreshed daily at 5:00 AM via Windows Task Scheduler
- Data is split into chunks for GitHub Pages compatibility

## Live Dashboard
Visit the GitHub Pages deployment to view the dashboard.

---
*Built with Code Puppy 🐶 | Walmart DC Engineering*
