#!/bin/bash
#
###################################################################################
# SCRIPT: run_ibd_report.sh
# AUTHOR: AI Assistant (CORRECTED for User Permissions)
# DATE:   December 2025
#
# DESCRIPTION:
# A robust wrapper script to execute the IBD report Python script.
# It ensures the correct virtual environment is sourced, executes the Python
# script, and logs the outcome to facilitate reliable operation via cron.
#
# FIX: The LOG_FILE location has been moved from /var/log to the user's
# project directory, and all 'sudo' calls for logging have been removed
# to resolve Permission Denied errors.
#
###################################################################################

# --- CONFIGURATION ---

# Base directory of your project
PROJECT_DIR="/home/reza/PycharmProjects/quants/sharpe"

# Name of the virtual environment directory relative to the project directory
VENV_DIR="/home/reza/PycharmProjects/quants/.venv"

# Name of the Python script to run
PYTHON_SCRIPT="ibd_report.py"

# Log file for the bash execution status (MOVED to project directory to avoid permissions issues)
LOG_FILE="$PROJECT_DIR/ibd_report_cron.log"

# --- HELPER FUNCTIONS ---

log_message() {
    local TYPE="$1"
    local MESSAGE="$2"
    # Removed 'sudo' and 'tee'. Logging directly via append >>.
    echo "$(date '+%Y-%m-%d %H:%M:%S') - [$TYPE] - $MESSAGE" >> "$LOG_FILE"
}

# --- VALIDATION ---

if [ ! -d "$VENV_DIR" ]; then
    log_message "ERROR" "Virtual environment not found at: $VENV_DIR. Cannot proceed."
    exit 1
fi

if [ ! -f "$PROJECT_DIR/$PYTHON_SCRIPT" ]; then
    log_message "ERROR" "Python script not found at: $PROJECT_DIR/$PYTHON_SCRIPT. Cannot proceed."
    exit 1
fi

# Ensure the log file directory exists (no sudo needed as it's in the project folder)
mkdir -p "$(dirname "$LOG_FILE")"

# --- EXECUTION ---

log_message "INFO" "Starting IBD Report execution."

# 1. Change to the script directory (important for relative paths like config.toml)
cd "$PROJECT_DIR" || { log_message "ERROR" "Failed to change directory to $PROJECT_DIR"; exit 1; }

# 2. Activate the virtual environment
source "$VENV_DIR/bin/activate"

# Check if activation was successful (optional, as the next step will fail anyway if not)
if [ $? -ne 0 ]; then
    log_message "ERROR" "Failed to activate virtual environment. Check VENV_DIR path."
    exit 1
fi

log_message "INFO" "Virtual environment activated."

# 3. Execute the Python script
# We run the script using the activated python interpreter.
# stdout and stderr from the Python script are logged to the bash log file.
python "$PYTHON_SCRIPT" >> "$LOG_FILE" 2>&1
PYTHON_EXIT_CODE=$?

# 4. Deactivate the virtual environment
deactivate

# 5. Check and Log Final Status
if [ $PYTHON_EXIT_CODE -eq 0 ]; then
    log_message "SUCCESS" "IBD Report script completed successfully (Exit Code 0)."
else
    log_message "FAILURE" "IBD Report script failed (Exit Code $PYTHON_EXIT_CODE). Check $LOG_FILE for details."
fi

# --- CLEANUP ---
log_message "INFO" "Execution finished."
exit $PYTHON_EXIT_CODE