"""One module per use case: the business rules, written against ports and nothing else.

A use case takes the ports it needs, decides, and commits. It imports no framework and no
driver (AD-2), which is what lets the same code run over the in-memory fakes in
`tests/unit/fakes/` and over the adapters `main.py` wires.
"""
