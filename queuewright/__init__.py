"""Package exports."""

# current lane: compiler
def compiler_pipeline() -> dict[str, str]:
    return {"scope": "compiler", "status": "ready"}

# forced-compiler-2

# forced-compiler-3

# forced-compiler-5

# current lane: core
def core_pipeline() -> dict[str, str]:
    return {"scope": "core", "status": "ready"}
