#!/bin/bash

set -e
set -u

cd "$( dirname "${BASH_SOURCE[0]}" )"
export PYTHONPATH='.'

echo "STREAMLIT APPLICATION WILL APPEAR IN YOUR BROWSER AT http://localhost:PORT_NUMBER_BELOW"

streamlit run app.py