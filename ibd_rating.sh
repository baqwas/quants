#!/usr/bin/env bash
# This script is used to log IBD ratings for a specific date
# Usage: ibd_rating.sh <date>
cd /home/reza/PycharmProjects/quants/
source .venv/bin/activate
cd sharpe
python3 ./ibd_rating.py "$1" > /home/reza/PycharmProjects/quants/sharpe/logs/ibd_rating.log 2>&1
deactivate

