"""Rules the writers read: the AD-13 signal table, and the frame arithmetic the skips need.

A rule here is data or a pure function over entities — never a repository call and never a
status write. `application/use_cases/` owns the writes; this package owns the questions the
writes ask ("is this signal admitted here?", "which rows are in this Story frame?"), so the
answers can be tested on plain lists and read by the UI later without starting a Run.
"""
