#!/bin/bash
cd "$(dirname "$0")"

# Check if already running
if lsof -i :8501 -sTCP:LISTEN &>/dev/null; then
    echo "Dashboard is already running at http://localhost:8501"
    open http://localhost:8501
    exit 0
fi

# Start Streamlit detached so closing this window won't kill it
source .venv/bin/activate
echo "Starting Runway Pulse dashboard..."
nohup .venv/bin/python -m streamlit run dashboard/app.py --server.port 8501 &>/dev/null &
sleep 2
echo "Dashboard running at http://localhost:8501"
open http://localhost:8501
