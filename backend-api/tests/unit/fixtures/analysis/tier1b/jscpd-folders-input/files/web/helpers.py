import os
import json

WIDTH = 20


def render_report(entries, width):
    lines = []
    for entry in entries:
        name = str(entry["name"]).ljust(width)
        amount = "{:>10.2f}".format(entry["amount"])
        if entry.get("flag"):
            lines.append(name + amount + " *")
        else:
            lines.append(name + amount)
    header = "=" * (width + 10)
    footer = "-" * (width + 10)
    return "\n".join([header, *lines, footer])
