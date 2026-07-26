#!/bin/bash
if pkill -f "streamlit run dashboard/app.py"; then
    echo "Dashboard stopped."
else
    echo "Dashboard was not running."
fi
