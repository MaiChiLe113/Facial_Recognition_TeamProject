"""Import every module in a package so their @register_* decorators run.

Each module is imported on its own: one that fails (syntax error, missing library) is recorded
and skipped, and the others still load.
"""
import importlib
import logging
import pkgutil

log = logging.getLogger("hawkeye")


def import_all(package_name):
    """Import package_name.* (modules and sub-packages, not names starting with "_").
    Return {module_name: error_text} for the ones that failed."""
    errors = {}
    package = importlib.import_module(package_name)
    for info in pkgutil.iter_modules(package.__path__):
        if info.name.startswith("_"):
            continue
        full = f"{package_name}.{info.name}"
        try:
            importlib.import_module(full)
        except Exception as e:  # noqa: BLE001 - any import failure must not stop the others
            errors[full] = f"{type(e).__name__}: {e}"
            log.warning("Could not import %s: %s", full, errors[full])
    return errors
