"""Pytest configuration and shared fixtures."""

import sys
from pathlib import Path

# Add lambda directory to Python path for imports
lambda_dir = Path(__file__).parent.parent / "lambda"
sys.path.insert(0, str(lambda_dir))
