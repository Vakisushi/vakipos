from desktop_app.database import ensure_desktop_schema
from desktop_app.ui import run
from importar_menu_completo import import_menu


if __name__ == "__main__":
    ensure_desktop_schema()
    import_menu()
    raise SystemExit(run())
