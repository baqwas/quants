#!/bin/bash
# signal_generator.sh
#
# ==============================================================================
# Bash Script for Running signal_generator.py with Robust Error Handling
# ==============================================================================
# Features:
#   Logging of the script's execution time and status
#   Environment Setup to ensure the virtual environment and correct Python interpreter are used
#   Comprehensive Error Checking for the Python script's exit status
#   Runtime Protection to prevent running multiple instances concurrently

# --- Configuration ---
# Set the base directory where your Pycharm project resides
PROJECT_DIR="/home/reza/PycharmProjects/quants"

# Define the path to your virtual environment's Python interpreter
PYTHON_EXECUTABLE="$PROJECT_DIR/.venv/bin/python"

# Define the path to the Python script
PYTHON_SCRIPT="$PROJECT_DIR/momentum/signal_generator.py"

# Define a lock file path to prevent concurrent execution
LOCK_FILE="/tmp/signal_generator.lock"

# Define the log file path
LOG_FILE="$PROJECT_DIR/run_log_$(date +\%Y\%m\%d).txt"

# --- Functions ---

# Function to check for the existence of required files/directories
check_prerequisites() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - INFO: Checking prerequisites..." | tee -a "$LOG_FILE"

    if [ ! -d "$PROJECT_DIR" ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - ERROR: Project directory not found: $PROJECT_DIR" | tee -a "$LOG_FILE"
        return 1
    fi

    if [ ! -f "$PYTHON_EXECUTABLE" ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - ERROR: Python executable not found: $PYTHON_EXECUTABLE. Run 'python3 -m venv .venv' inside $PROJECT_DIR" | tee -a "$LOG_FILE"
        return 1
    fi

    if [ ! -f "$PYTHON_SCRIPT" ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - ERROR: Python script not found: $PYTHON_SCRIPT" | tee -a "$LOG_FILE"
        return 1
    fi

    # Change directory to the script's location so it can find config.toml and tickers.txt
    cd "$PROJECT_DIR/momentum" || { echo "$(date '+%Y-%m-%d %H:%M:%S') - FATAL: Failed to change directory." | tee -a "$LOG_FILE"; return 1; }

    echo "$(date '+%Y-%m-%d %H:%M:%S') - INFO: Prerequisites passed." | tee -a "$LOG_FILE"
    return 0
}

# --- Main Execution Block ---

# 1. Concurrency Check (Locking)
if [ -f "$LOCK_FILE" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - WARNING: Lock file found ($LOCK_FILE). Script is already running or failed to clean up. Exiting." | tee -a "$LOG_FILE"
    exit 1
fi

# Create lock file
touch "$LOCK_FILE"

# Ensure the lock file is removed upon exit (success, failure, or interruption)
trap "rm -f $LOCK_FILE; exit" INT TERM EXIT

# 2. Setup and Prerequisite Check
check_prerequisites
if [ $? -ne 0 ]; then
    rm -f "$LOCK_FILE" # Ensure lock is removed on fatal setup error
    exit 1
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') - INFO: Starting Python script execution..." | tee -a "$LOG_FILE"

# 3. Execute the Python Script
# The command's standard output and error are both logged to the file
"$PYTHON_EXECUTABLE" "$PYTHON_SCRIPT" >> "$LOG_FILE" 2>&1

# Capture the exit code of the Python script
PYTHON_EXIT_CODE=$?

# 4. Error Handling and Reporting
if [ $PYTHON_EXIT_CODE -eq 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - SUCCESS: Python script finished successfully (Exit Code 0)." | tee -a "$LOG_FILE"
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') - FAILURE: Python script exited with a non-zero status ($PYTHON_EXIT_CODE)." | tee -a "$LOG_FILE"
    # Optional: Add logic here to send a critical notification email
    # if the script fails (e.g., using 'mail' command or a Python helper).
fi

# 5. Cleanup
# The 'trap' command handles the lock file removal, but a final confirmation is good practice
rm -f "$LOCK_FILE"
echo "$(date '+%Y-%m-%d %H:%M:%S') - INFO: Lock file removed. Script finished." | tee -a "$LOG_FILE"

# Exit with the same code as the Python script
exit $PYTHON_EXIT_CODE