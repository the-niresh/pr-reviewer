"""Finding verification: static checks, then a Docker-only sandbox.

This package reads untrusted PR content and must never import the hosted
database, the control plane, or the operator CLI.
"""
