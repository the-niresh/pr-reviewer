"""Local retrieval: chunk source, embed it, store generations in pgvector.

This package reads the user's source tree and writes vectors to the runner's
local Postgres. It must not import the hosted database, the control plane, or
the operator CLI.
"""
