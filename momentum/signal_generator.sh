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
#   V2.2.0: Added loop to process all files matching 'tickers_*.txt'

# --- Configuration ---
# Set the base directory where your Pycharm project resides
PROJECT_DIR="/home/reza/PycharmProjects/quants"

# Define the path to your virtual environment's Python interpreter
PYTHON_EXECUTABLE="$PROJECT_DIR/.venv/bin/python"

# Define the path to the Python script
PYTHON_SCRIPT="$PROJECT_DIR/momentum/signal_generator.py"

# Define the config file name
CONFIG_FILENAME="config.toml"

# Define a lock file path to prevent concurrent execution
LOCK_FILE="/tmp/signal_generator.lock"

# Define the log file path
LOG_FILE="$PROJECT_DIR/run_log_$(date +\%Y\%m\%d).txt"

# Initialize overall exit code to success (0)
OVERALL_EXIT_CODE=0

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

    # Change directory to the script's location so it can find config.toml and the tickers files
    cd "$PROJECT_DIR/momentum" || { echo "$(date '+%Y-%m-%d %H:%M:%S') - FATAL: Failed to change directory." | tee -a "$LOG_FILE"; return 1; }

    # Check for the required config file
    if [ ! -f "$CONFIG_FILENAME" ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - CRITICAL ERROR: Configuration file not found: $CONFIG_FILENAME in $(pwd)" | tee -a "$LOG_FILE"
        return 1
    fi

    # Check for at least one ticker file matching the pattern
    shopt -s nullglob # Ensure the check works correctly if no files are found
    TICKER_FILES=(tickers_*.txt)
    shopt -u nullglob

    if [ ${#TICKER_FILES[@]} -eq 0 ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - CRITICAL ERROR: No ticker list files found matching 'tickers_*.txt' in $(pwd)" | tee -a "$LOG_FILE"
        return 1
    fi

    echo "$(date '+%Y-%m-%d %H:%M:%S') - INFO: Prerequisites passed. Found ${#TICKER_FILES[@]} ticker list(s) to process." | tee -a "$LOG_FILE"
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

# 3. Execute the Python Script for all ticker files
shopt -s nullglob # Ensure the loop doesn't run if no files are found
for ticker_file in tickers_*.txt; do
    echo "$(date '+%Y-%m-%d %H:%M:%S') - INFO: Starting Python script execution for: $ticker_file..." | tee -a "$LOG_FILE"
    echo "INFO: Python output for $ticker_file is logged to: $LOG_FILE"

    # Execute the Python Script, passing the filename using -t option
    # Note: Because the directory was changed in check_prerequisites, the relative filename works.
    "$PYTHON_EXECUTABLE" "$PYTHON_SCRIPT" -t "$ticker_file" >> "$LOG_FILE" 2>&1

    PYTHON_EXIT_CODE=$?

    # 4. Error Handling and Reporting
    if [ $PYTHON_EXIT_CODE -eq 0 ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - SUCCESS: Python script finished successfully for $ticker_file (Exit Code 0)." | tee -a "$LOG_FILE"
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S') - FAILURE: Python script exited with a non-zero status ($PYTHON_EXIT_CODE) for $ticker_file. Check log for details." | tee -a "$LOG_FILE"
        # Set the overall exit code to failure if any single run fails
        OVERALL_EXIT_CODE=1
    fi
done
shopt -u nullglob

# 5. Cleanup
rm -f "$LOCK_FILE"
if [ "$OVERALL_EXIT_CODE" -eq 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - INFO: All ticker lists processed successfully. Lock file removed. Script finished." | tee -a "$LOG_FILE"
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') - FAILURE: One or more ticker lists failed to process. Lock file removed. Script finished." | tee -a "$LOG_FILE"
fi

# Exit with the overall consolidated status
exit $OVERALL_EXIT_CODE