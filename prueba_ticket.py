from escpos.printer import Win32Raw

PRINTER_NAME = "XP-58"   # <- este debe ser EXACTO como te salió en la lista

p = Win32Raw(PRINTER_NAME)

p.set(align="center", bold=True, width=2, height=2)
p.text("VAKI SUSHI\n")
p.set(align="left", bold=False)
p.text("Prueba XP-58 OK\n")
p.text("--------------------------\n")
p.text("TOTAL: $120\n\n")
p.cut()
p.close()
