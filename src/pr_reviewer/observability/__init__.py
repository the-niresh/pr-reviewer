"""Cross-store trace reconstruction (Runtime Task 5A). Never imports pr_reviewer.db or
pr_reviewer.control_plane: this package is pure merge/redaction logic over data its callers
already fetched, not a third place that talks to Neon or the local SQLite file itself.
"""
