"""
Vercel entry point — imports the Flask app from the parent directory.
Place this file at:  api/index.py   (relative to your project root)
"""
import sys, os

# Make the project root importable so `from app import app` works
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

# Vercel looks for a variable called `app` (WSGI callable)
# Nothing else needed here.
