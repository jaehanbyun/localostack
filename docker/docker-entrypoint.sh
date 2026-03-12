#!/bin/bash
set -e

echo "Starting LocalOStack..."
exec uv run "$@"
