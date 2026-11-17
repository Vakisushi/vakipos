# print_agent.py
# Print Agent para Windows (XP-58 / 58mm)
# Endpoints:
#   GET  /health
#   GET  /printers
#   POST /print        { "printer": "...", "text": "..." }
#   POST /print/comanda { "printer": "...", "text": "..." }
#   POST /print/cliente { "printer": "...", "text": "..." }

from __future__ import annotations

import argparse
import sys
from typing import Optional, List, Dict, Any

from flask import Flask, request, jsonify
from flask_cors import CORS

try:
    import win32print
except ImportError:
    win32print = None


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9123

app = Flask(__name__)
# CORS abierto para que puedas llamar desde tu web (vakisushi.com) hacia localhost
CORS(app, resources={r"/*": {"origins": "*"}})


def _ensure_windows():
    if win32print is None:
        raise RuntimeError(
            "Falta pywin32. Instala en tu venv:\n"
            "  pip install pywin32 flask flask-cors"
        )


def list_printers() -> List[str]:
    _ensure_windows()
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    printers = win32print.EnumPrinters(flags)
    names = []
    for p in printers:
        # p[2] suele ser el nombre
        if len(p) >= 3 and p[2]:
            names.append(p[2])
    return sorted(set(names))


def get_default_printer() -> Optional[str]:
    _ensure_windows()
    try:
        return win32print.GetDefaultPrinter()
    except Exception:
        return None


def _escpos_bytes(text: str) -> bytes:
    """
    Convierte texto a bytes para impresoras térmicas ESC/POS.
    Incluye init + salto final + corte.
    """
    # Init
    data = b"\x1b\x40"
    # Texto (cp437 suele funcionar bien para cajas registradoras; si falla, cambia a utf-8 sin errores)
    try:
        payload = text.encode("cp437", errors="replace")
    except Exception:
        payload = text.encode("utf-8", errors="replace")

    # Saltos finales
    data += payload + b"\n\n\n"
    # Corte (muchas 58mm soportan este)
    data += b"\x1d\x56\x00"
    return data


def print_raw(printer_name: str, raw: bytes) -> None:
    _ensure_windows()
    hPrinter = win32print.OpenPrinter(printer_name)
    try:
        job = win32print.StartDocPrinter(hPrinter, 1, ("VakiPOS Ticket", None, "RAW"))
        try:
            win32print.StartPagePrinter(hPrinter)
            win32print.WritePrinter(hPrinter, raw)
            win32print.EndPagePrinter(hPrinter)
        finally:
            win32print.EndDocPrinter(hPrinter)
    finally:
        win32print.ClosePrinter(hPrinter)


def normalize_58mm(text: str) -> str:
    """
    Ajustes simples para 58mm (32 chars aprox).
    No te lo complico: solo normaliza saltos.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


@app.get("/health")
def health():
    return jsonify({"ok": True, "agent": "print_agent", "port": DEFAULT_PORT})


@app.get("/printers")
def printers():
    try:
        ps = list_printers()
        return jsonify({"ok": True, "printers": ps, "default": get_default_printer()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def _handle_print(kind: str):
    """
    kind: 'comanda' | 'cliente' | 'generic'
    """
    try:
        payload: Dict[str, Any] = request.get_json(force=True, silent=False) or {}
    except Exception:
        payload = {}

    printer = (payload.get("printer") or "").strip()
    text = payload.get("text") or ""

    if not printer:
        # Si no mandas printer, usa default
        printer = get_default_printer() or ""

    if not printer:
        return jsonify({"ok": False, "error": "No se detectó impresora. Usa GET /printers y manda 'printer'."}), 400

    # Decoración por tipo
    text = normalize_58mm(str(text))

    if kind == "comanda":
        header = "**** COMANDA COCINA ****\n"
        text = header + text
    elif kind == "cliente":
        header = "**** TICKET CLIENTE ****\n"
        text = header + text

    try:
        raw = _escpos_bytes(text)
        print_raw(printer, raw)
        return jsonify({"ok": True, "printed_to": printer, "kind": kind})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "printer": printer}), 500


@app.post("/print")
def print_generic():
    return _handle_print("generic")


@app.post("/print/comanda")
def print_comanda():
    return _handle_print("comanda")


@app.post("/print/cliente")
def print_cliente():
    return _handle_print("cliente")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    print(f"✅ Print Agent corriendo en http://{args.host}:{args.port}")
    # OJO: no uses debug en producción
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
