"""Punto de entrada principal de Vaki Sushi POS.

Este archivo existe para que el botón ▶ de VS Code abra siempre la aplicación
de escritorio. La versión web anterior se conserva en ``legacy_web_main.py``.
"""

from desktop_app.database import ensure_desktop_schema
from desktop_app.ui import run
from importar_menu_completo import import_menu


def main() -> int:
    ensure_desktop_schema()
    import_menu()
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
