"""Command-line tools that build the application to inspect it, never to serve it.

This package sits above `main` in the AD-2 layering: it may import the composition root,
and nothing in the application imports it. `pyproject.toml` declares that position rather
than leaving it to convention.
"""
