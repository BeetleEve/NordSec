"""Run this file in PyCharm to install, initialize and start local NordSec."""
import sys

# Windows consoles and IDE runners can otherwise use the legacy cp1251 codec.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, 'reconfigure'):
        stream.reconfigure(encoding='utf-8', errors='replace')

from scripts.run_local import main

if __name__ == '__main__':
    main()
