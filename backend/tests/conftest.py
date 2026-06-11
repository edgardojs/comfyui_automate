"""Shared test configuration and fixtures.

Sets up environment variables and database fixtures for all tests.
"""

import os

# Disable rate limiting in tests by default
# Individual rate limiter tests will re-enable it as needed
os.environ.setdefault("RATE_LIMIT_DISABLED", "1")