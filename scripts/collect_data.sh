#!/bin/bash

# Navigate to project directory
cd /Users/zmaros/Work/Projects/team_metrics

# Activate virtual environment
source venv/bin/activate

echo "=================================="
echo "Multi-Range Data Collection"
echo "=================================="
echo ""

# Collect multiple date ranges for comprehensive analysis
# Each range creates a separate cache file

# Short-term trend (30 days)
echo "📊 Collecting 30-day data..."
python collect_data.py --date-range 30d
if [ $? -ne 0 ]; then
    echo "⚠️  30-day collection failed"
fi
echo ""

# Standard range (90 days) - default for dashboard
echo "📊 Collecting 90-day data..."
python collect_data.py --date-range 90d
if [ $? -ne 0 ]; then
    echo "⚠️  90-day collection failed"
    exit 1  # Exit with error if default range fails
fi
echo ""

# Long-term trend (365 days)
echo "📊 Collecting 365-day data..."
python collect_data.py --date-range 365d
if [ $? -ne 0 ]; then
    echo "⚠️  365-day collection failed"
fi
echo ""

# Current quarter (optional - auto-detect)
CURRENT_QUARTER=$(date +"%m" | awk '{q=int(($1-1)/3)+1; print "Q"q"-"strftime("%Y")}')
echo "📊 Collecting current quarter ($CURRENT_QUARTER)..."
python collect_data.py --date-range "$CURRENT_QUARTER"
if [ $? -ne 0 ]; then
    echo "⚠️  Quarter collection failed"
fi
echo ""

echo "=================================="
echo "✅ Multi-range collection complete"
echo "=================================="

# Exit successfully if at least the default 90d range succeeded
exit 0
