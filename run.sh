#!/usr/bin/env bash
# OCR Tool - Linux/macOS run script
# Usage: ./run.sh input_file.png [output_file.md]

set -e

if [ -z "$1" ]; then
    echo "Usage: ./run.sh input_file [output_file]"
    echo "Example: ./run.sh page_1.png output/page_1.md"
    exit 1
fi

# Load .env if it exists and DATALAB_API_KEY is not set
if [ -z "$DATALAB_API_KEY" ] && [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Use venv python if it exists, otherwise system python
if [ -f "venv/bin/python" ]; then
    PYTHON=venv/bin/python
else
    PYTHON=python3
fi

$PYTHON api.py "$@"
