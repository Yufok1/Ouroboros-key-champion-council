#!/bin/bash
echo "[MODEL] Launching Model Interface for champion_gen8"
echo

# Start server in background
python server.py &
SERVER_PID=$!
echo "Server PID: $SERVER_PID"

# Wait for server
sleep 2

echo "Server running at http://127.0.0.1:8766"
echo "Press Ctrl+C to stop"

# Keep running until interrupted
wait $SERVER_PID
