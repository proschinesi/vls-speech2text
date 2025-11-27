#!/bin/bash
# Test rapido del server su porta 8080
cd "$(dirname "$0")"
source venv/bin/activate
python web_app.py --host 127.0.0.1 --port 8080
