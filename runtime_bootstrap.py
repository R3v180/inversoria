"""
Carga fiable de módulos locales tras hot-reload de Streamlit (evita KeyError 'i18n'
e instancias de DatabaseManager sin métodos nuevos).
"""
import importlib
import importlib.util
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))


def ensure_i18n_module():
    """Importa i18n.py por ruta absoluta y lo registra en sys.modules."""
    mod = sys.modules.get("i18n")
    if mod is not None and hasattr(mod, "_") and hasattr(mod, "TRANSLATIONS"):
        return mod
    path = os.path.join(_ROOT, "i18n.py")
    spec = importlib.util.spec_from_file_location("i18n", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"No se pudo cargar i18n desde {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["i18n"] = mod
    spec.loader.exec_module(mod)
    return mod


def ensure_database_manager_class():
    """Devuelve la clase DatabaseManager actualizada (reload si hace falta)."""
    import database_manager as dm

    if hasattr(dm.DatabaseManager, "get_cost_basis"):
        return dm.DatabaseManager
    dm = importlib.reload(dm)
    if not hasattr(dm.DatabaseManager, "get_cost_basis"):
        raise AttributeError(
            "database_manager.DatabaseManager no define get_cost_basis; "
            "revisa que el archivo en disco esté actualizado."
        )
    return dm.DatabaseManager


def new_database_manager():
    cls = ensure_database_manager_class()
    return cls()
