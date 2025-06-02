#!/bin/bash

# Function to start the application
start_app() {
    echo "🚀 Starting application..."
    source venv/bin/activate
    python -m autrade.main
}

# Function to stop the application
stop_app() {
    echo "🛑 Stopping application..."
    pkill -f "python -m autrade.main" || true
}

# Initial start
start_app