"""The multi-repository initiative: its `epics.yaml`, and the DAG that file describes.

Beside `use_cases/dispatch_initiative.py` rather than inside `templates/lists.py` on
purpose. `lists.py` answers a *planner's* question — what a `for_each` expands over, inside
one Run, on one repository — and its `epics.yaml` schema is the one an `initiative` Template
loops over. This package answers a *dispatcher's* question: which repository each epic
belongs to, which epics wait for which, and whether the whole graph can be turned into Runs
at all. The two files share a basename and nothing else, so sharing a parser would make
every rule one of them adds a rule the other has to tolerate.
"""
