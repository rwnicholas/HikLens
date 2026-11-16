#!/usr/bin/env bash
# Quick launcher for Hikvision CCTV Stream Viewer
cd "$(dirname "$0")"
python3 cam_viewer.py "$@"
