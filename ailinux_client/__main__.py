#!/usr/bin/env python3
"""
AILinux Client - Module Entry Point
====================================

Enables running with: python -m ailinux_client

Usage:
    python -m ailinux_client                 # Normal mode
    python -m ailinux_client --desktop       # Desktop mode (fullscreen panel)
    python -m ailinux_client --server URL    # Custom server
    python -m ailinux_client --local         # Local-only mode (Ollama)
"""

from .main import main

if __name__ == "__main__":
    main()
