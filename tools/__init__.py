# Intentionally (almost) empty: makes tools/ a *regular* package so it cannot
# be shadowed by an unrelated top-level `tools` package elsewhere on sys.path
# (regular packages beat PEP 420 namespace portions regardless of path order).
# Keep it import-side-effect free — every client stays runnable as a script.
