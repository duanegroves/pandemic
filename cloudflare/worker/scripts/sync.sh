#!/bin/sh
# Prepare the Worker for dev/deploy without duplicating source in git:
#   src/pandemic/  <- engine, data, server/{__init__,rooms,meta}.py from ../../src/pandemic
#   public/        <- built frontend (web/dist)
# Build the frontend first: (cd web && npm ci && npm run build)
set -e
cd "$(dirname "$0")/.."
SRC=../../src/pandemic
DIST=../../web/dist
if [ ! -f "$DIST/index.html" ]; then
  echo "missing $DIST/index.html: run 'cd web && npm ci && npm run build' first" >&2
  exit 1
fi
rm -rf src/pandemic public
mkdir -p src/pandemic/server public
cp $SRC/__init__.py src/pandemic/
cp -R $SRC/engine $SRC/data src/pandemic/
cp $SRC/server/__init__.py $SRC/server/rooms.py $SRC/server/meta.py src/pandemic/server/
find src/pandemic -name __pycache__ -prune -exec rm -rf {} +
cp -R $DIST/. public/
