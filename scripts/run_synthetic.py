"""Backward-compatible alias for run_analysis.py."""
import runpy, sys
from pathlib import Path
sys.argv[0] = str(Path(__file__).with_name("run_analysis.py"))
runpy.run_path(sys.argv[0], run_name="__main__")
