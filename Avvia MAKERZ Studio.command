#!/usr/bin/env bash
# MAKERZ Studio macOS launcher: opens the local workbench UI and starts the Node.js server.
DIR="$(cd "$(dirname "$0")" && pwd)"
echo "Starting MAKERZ Studio from: $DIR"
(sleep 1 && open "http://127.0.0.1:4173") &
node "$DIR/makerz-studio/server.mjs"
