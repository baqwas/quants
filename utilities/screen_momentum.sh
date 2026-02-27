#!/usr/bin/env bash
# ==============================================================================
# 🛡️ AUDIT & COMPLIANCE DOCUMENTATION
# ==============================================================================
# SCRIPT NAME    : screen_momentum.sh
# VERSION        : 3.1.0
# AUTHOR         : Matha Goram
# PROJECT        : AI/Quantum Tech Stock Momentum Tracker
# AUDIT CLASS    : SEC-FIN-LOG-01 (Automated Market Analysis)
#
# DESCRIPTION:
#   Orchestrates the daily tech-stock momentum screening engine. Manages
#   environment integrity and centralizes execution logs in the Videos hierarchy.
#
# AUDIT TRAIL:
#   2026-02-26 : 3.1.0 : Finalized path /home/reza/Videos/quants/logs.
#                        Implemented ANSI colors and Unicode status icons.
# ==============================================================================

# 🎨 Color and Icon Definitions
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

# 📂 Standardized Audit Log Hierarchy
LOG_DIR="/home/reza/Videos/quants/logs"
LOG_FILE="$LOG_DIR/screen_momentum_$(date +%Y-%m-%d).log"

# --- Initialization ---

# 🛠️ Audit: Ensure Log Directory Integrity
mkdir -p "$LOG_DIR"

echo -e "${BLUE}${ICON_START} [$(date '+%Y-%m-%d %H:%M:%S')] AUDIT: Execution Initialized${NC}" | tee -a "$LOG_FILE"
echo -e "${BLUE}${ICON_LOG} AUDIT: Writing telemetry to: $LOG_FILE${NC}" | tee -a "$LOG_FILE"

# 📂 Navigate to Workspace
cd "$BASE_DIR" || {
    echo -e "${RED}${ICON_ERROR} AUDIT ERROR: Directory $BASE_DIR unreachable.${NC}" | tee -a "$LOG_FILE"
    exit 1
}

# 🐍 Activation of Project Virtual Environment
if [ -f "$VENV_PATH" ]; then
    echo -e "${YELLOW}${ICON_VENV} AUDIT: Activating Virtual Environment...${NC}" | tee -a "$LOG_FILE"
    source "$VENV_PATH"
else
    echo -e "${RED}${ICON_ERROR} AUDIT ERROR: Activation failed at $VENV_PATH${NC}" | tee -a "$LOG_FILE"
    exit 1
fi

# 🏃 Execution Phase
cd "$PROJECT_DIR" || exit 1
echo -e "${YELLOW}AUDIT: Launching Python Momentum Engine...${NC}" | tee -a "$LOG_FILE"

# Redirection of both Standard Out and Standard Error to Audit Log
python3 ./screen_momentum.py >> "$LOG_FILE" 2>&1

# 🏁 Closure & Status Reporting
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}${ICON_SUCCESS} AUDIT SUCCESS: Task completed (Exit Code 0)${NC}" | tee -a "$LOG_FILE"
else
    echo -e "${RED}${ICON_ERROR} AUDIT FAILURE: Task exited with error (Code $EXIT_CODE)${NC}" | tee -a "$LOG_FILE"
fi

echo -e "${BLUE}================================================================${NC}" >> "$LOG_FILE"

exit $EXIT_CODE