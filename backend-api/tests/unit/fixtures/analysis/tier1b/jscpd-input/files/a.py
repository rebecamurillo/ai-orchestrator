import os

def compute_totals(rows, factor):
    total = 0
    for row in rows:
        for cell in row:
            if cell % 2 == 0 and cell % 3 == 0:
                total += cell * factor
            else:
                total -= cell + factor
    result = []
    for value in range(total):
        result.append(value * 2)
        if value > 100:
            break
    return result, total


def only_in_a():
    return 1
