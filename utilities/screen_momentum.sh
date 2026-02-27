#!/usr/bin/env bash
# ==============================================================================
# 🛡️ AUDIT & COMPLIANCE DOCUMENTATION
# ==============================================================================
# SCRIPT NAME    : screen_momentum.sh
# VERSION        : 2.7.0
# AUTHOR         : Matha Goram
# PROJECT        : AI/Quantum Tech Stock Momentum Tracker
# CLASSIFICATION : Financial Automation / Audit-Logged
#
# DESCRIPTION:
#   Orchestrates daily momentum screening. Ensures environment isolation,
#   executes Python analytical engine, and redirects all telemetry to a
#   standardized audit directory.
#
# AUDIT TRAIL:
#   2026-02-26 : 2.7.0 : Migrated logs to /Videos/quants/logs.
#                        Added Unicode/ANSI color telemetry reporting.
# ==============================================================================

# 🎨 Professional Color & Icon Definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

ICON_START="🚀"
ICON_VENV="🐍"
ICON_SUCCESS="✅"
ICON_ERROR="❌"
ICON_LOG="📂"

# 📍 Absolute Path Constants
BASE_DIR="/home/reza/PycharmProjects/quants"
PROJECT_DIR="$BASE_DIR/sharpe"
VENV_PATH="$BASE_DIR/.venv/bin/activate"

# 📂 Professional Log Hierarchy
LOG_DIR="/home/reza/Videos/quants/logs"
LOG_FILE="$LOG_DIR/screen_momentum_$(date +%Y-%m-%d).log"

# --- Initialization ---

# 🛠️ Audit Requirement: Ensure Log Directory Exists
if [ ! -d "$LOG_DIR" ]; then
    mkdir -p "$LOG_DIR"
fi

echo -e "${BLUE}${ICON_START} [$(date '+%Y-%m-%d %H:%M:%S')] AUDIT: Screen Process Initiated${NC}" | tee -a "$LOG_FILE"
echo -e "${BLUE}${ICON_LOG} AUDIT: Telemetry Stream: $LOG_FILE${NC}" | tee -a "$LOG_FILE"

# 📂 Navigate to Project Root
cd "$BASE_DIR" || {
    echo -e "${RED}${ICON_ERROR} AUDIT FAILURE: Root directory $BASE_DIR inaccessible.${NC}" | tee -a "$LOG_FILE"
    exit 1
}

# 🐍 Activation of Virtual Environment
if [ -f "$VENV_PATH" ]; then
    echo -e "${YELLOW}${ICON_VENV} AUDIT: Activating Python Virtual Environment...${NC}" | tee -a "$LOG_FILE"
    source "$VENV_PATH"
else
    echo -e "${RED}${ICON_ERROR} AUDIT FAILURE: Venv not found at $VENV_PATH${NC}" | tee -a "$LOG_FILE"
    exit 1
fi

# 🏃 Execution Phase
cd "$PROJECT_DIR" || exit 1
echo -e "${YELLOW}AUDIT: Launching Momentum Screening Engine...${NC}" | tee -a "$LOG_FILE"

# Execute Python and capture all Standard Output/Error
python3 ./screen_momentum.py >> "$LOG_FILE" 2>&1

# 🏁 Finalization & Exit Telemetry
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}${ICON_SUCCESS} AUDIT SUCCESS: Task completed (Code 0)${NC}" | tee -a "$LOG_FILE"
else
    echo -e "${RED}${ICON_ERROR} AUDIT FAILURE: Task exited with error (Code $EXIT_CODE)${NC}" | tee -a "$LOG_FILE"
fi

echo -e "${BLUE}================================================================${NC}" >> "$LOG_FILE"

exit $EXIT_CODE

