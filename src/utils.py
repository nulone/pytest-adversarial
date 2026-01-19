import ast


def extract_functions(source_code: str) -> list[str]:
    """Extract function names from Python source code.

    Args:
        source_code: Python source code as a string

    Returns:
        List of function names found in the code (excluding __magic__ methods)
    """
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return []

    functions = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Filter out __magic__ methods
            if not (node.name.startswith("__") and node.name.endswith("__")):
                functions.append(node.name)

    return functions
