"""Developer and support-side command-line tools. Unlike runner/*, these are not shipped to the
end user's sandboxed runner install -- reviewer trace needs both the hosted Postgres connection
(pr_reviewer.db.client) and a local SQLite store path, which the shipped runner never holds both
of at once by design."""
