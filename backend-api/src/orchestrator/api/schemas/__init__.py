"""Pydantic schemas — the API contract itself (AD-3).

These models are the single source of `contracts/openapi.json` and, through it, of the
TypeScript types in web-client. Nothing here imports the database or a use case.
"""
