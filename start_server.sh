#!/bin/bash
cd /home/hitech/projects/app2nix
source .venv/bin/activate
echo "Starting app2nix server..."
echo "Access from network: http://$(hostname -I | awk '{print $1}'):8000"
exec uvicorn server:app --host 0.0.0.0 --port 8000
