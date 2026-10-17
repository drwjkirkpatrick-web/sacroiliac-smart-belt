"""Pytest path bootstrap.

WHY: puts the project root (which contains the ``sibelt`` package) on
``sys.path`` so tests can ``import sibelt`` from a plain checkout without
installing anything.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
