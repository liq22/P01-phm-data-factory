#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/../docker/iotdb"
docker compose down
