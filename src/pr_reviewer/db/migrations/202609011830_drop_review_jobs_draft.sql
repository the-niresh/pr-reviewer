-- Opened drafts are ignored in github/lifecycle.py and never enqueue a
-- review_jobs row. The draft boolean added in 202608302200_pr_lifecycle.sql
-- had no writer in src/. A column that cannot be set is dead schema.
-- This file drops it. The applied 202608302200 file is left unchanged.

alter table review_jobs drop column if exists draft;
