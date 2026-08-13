#!/bin/bash

# Usage: ./benchtest_command_helper.sh <start> <end>

if [ $# -ne 2 ]; then
    echo "Usage: $0 <start> <end>"
    # exit 1
fi

START=$1
END=$2

for ((x=START; x<=END; x++)); do
    echo "Running with -b $x"
    python DBQ_Mk6.py -r "all" -b "$x"
done