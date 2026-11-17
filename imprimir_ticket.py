from escpos.printer import Win32Raw
from datetime import datetime

PRINTER_NAME = "XP-58"

def imprimir_ticket(orden_id, productos, total):
    p = Win32Raw(PRINTER_NAME)

    # Encabezado
    p.set(align="center", bold=True, width=2, height=2)
    p.text("VAKI SUSHI\n")
    p.set(align="center", bold=False)
    p.text("Gracias por su compra\n")
    p.text("------------------------------\n")

    # Fecha y folio
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
    p.text(f"Folio: {orden_id}\n")
    p.text(f"Fecha: {fecha}\n")
    p.text("------------------------------\n")

    # Productos
    for nombre, precio in productos:
        linea = f"{nombre[:20]:20} ${precio:>6.2f}\n"
        p.text(linea)

    p.text("------------------------------\n")

    # Total
    p.set(bold=True)
    p.text(f"TOTAL: ${total:.2f}\n")
    p.set(bold=False)

    p.text("\n")
    p.text("¡Buen provecho!\n\n")

    p.cut()
    p.close()
