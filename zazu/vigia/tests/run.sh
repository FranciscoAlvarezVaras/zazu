#!/bin/sh
# Pruebas del vigía (casa falsa temporal; no toca datos reales). Uso: sh tests/run.sh
cd "$(dirname "$0")/.." && exec /usr/bin/python3 -W ignore -m unittest discover -s tests -v 2>&1 | tail -${1:-15}
