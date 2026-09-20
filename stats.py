"""
Alias wrapper to run check_jobs.py
"""
import runpy

if __name__ == "__main__":
    runpy.run_module("check_jobs", run_name="__main__")
