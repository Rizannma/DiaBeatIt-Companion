#!/usr/bin/env python
"""Debug path resolution."""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

current_file = os.path.abspath(__file__)
current_dir = os.path.dirname(current_file)
project_root = os.path.dirname(current_dir)
backend_dir = os.path.join(project_root, 'backend')

print(f"Current file: {current_file}")
print(f"Current dir: {current_dir}")
print(f"Project root: {project_root}")
print(f"Backend dir (calculated): {backend_dir}")
print(f"Backend dir exists: {os.path.isdir(backend_dir)}")

if os.path.isdir(backend_dir):
    print(f"\nFiles in backend folder:")
    for filename in os.listdir(backend_dir):
        print(f"  - {filename}")
