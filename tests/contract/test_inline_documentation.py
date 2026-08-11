"""Static contract for meaningful public production-code documentation."""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

_APPLICATION_ROOT = Path(__file__).resolve().parents[2] / "app"
_VALIDATOR_DECORATORS = frozenset({"field_validator", "model_validator"})


def _decorator_name(decorator: ast.expr) -> str | None:
    """Return the terminal name of a decorator, unwrapping a call when necessary."""
    if isinstance(decorator, ast.Call):
        return _decorator_name(decorator.func)
    if isinstance(decorator, ast.Name):
        return decorator.id
    if isinstance(decorator, ast.Attribute):
        return decorator.attr
    return None


def _is_pydantic_validator(method: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Identify the narrow validator exemption whose model names document the invariant."""
    return any(
        _decorator_name(decorator) in _VALIDATOR_DECORATORS for decorator in method.decorator_list
    )


def _missing_documentation(path: Path) -> Iterable[str]:
    """Yield actionable path, line, and symbol descriptions for undocumented AST nodes."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    relative_path = path.relative_to(_APPLICATION_ROOT.parent)
    if not ast.get_docstring(tree):
        yield f"{relative_path}:1:module"

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            if not ast.get_docstring(node):
                yield f"{relative_path}:{node.lineno}:class {node.name}"
            for method in node.body:
                if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if method.name.startswith("_") or _is_pydantic_validator(method):
                    continue
                if not ast.get_docstring(method):
                    yield f"{relative_path}:{method.lineno}:method {node.name}.{method.name}"
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_") and not ast.get_docstring(node):
                yield f"{relative_path}:{node.lineno}:function {node.name}"


def test_production_symbols_have_meaningful_inline_documentation() -> None:
    """Require module, class, public function, and public method documentation in app code."""
    missing = [
        item
        for path in sorted(_APPLICATION_ROOT.rglob("*.py"))
        for item in _missing_documentation(path)
    ]

    assert not missing, "Missing production documentation:\n" + "\n".join(missing)
