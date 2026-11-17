# whatsapp_low_stock_notifier.py

from sqlmodel import Session, select
from datetime import datetime
import os
import requests

# IMPORTA ESTO DESDE TU ARCHIVO PRINCIPAL
# OJO: cambia "main" por el nombre real de tu archivo FastAPI
from main import engine, IngredientInventory, Ingredient

# ---------- 1. Construir el texto de faltantes ----------

def build_low_stock_text() -> str:
    with Session(engine) as db:
        low_inventory = db.exec(
            select(IngredientInventory).where(
                IngredientInventory.stock <= IngredientInventory.min_stock
            )
        ).all()

        if not low_inventory:
            return "Todo en orden, no hay ingredientes por debajo del mínimo."

        lines = []
        lines.append("⚠ FALTANTES / INGREDIENTES BAJOS:")
        lines.append(f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        lines.append("")

        for item in low_inventory:
            lines.append(
                f"- {item.ingredient.name}: {item.stock} {item.ingredient.unit} "
                f"(mínimo {item.min_stock})"
            )

        return "\n".join(lines)


# ---------- 2. Enviar mensaje por WhatsApp (Cloud API de Meta) ----------

def send_whatsapp_message(text: str):
    """
    Necesitas tener:
      - un número de WhatsApp Business configurado
      - un token de acceso (WHATSAPP_TOKEN)
      - el 'phone_number_id' (WHATSAPP_PHONE_ID)
      - el número destino (WHATSAPP_TO, en formato internacional, ej: 5216621234567)
    """

    token = os.environ.get("WHATSAPP_TOKEN")
    phone_id = os.environ.get("WHATSAPP_PHONE_ID")
    to_number = os.environ.get("WHATSAPP_TO")

    if not token or not phone_id or not to_number:
        print("⚠ Faltan variables de entorno WHATSAPP_TOKEN / WHATSAPP_PHONE_ID / WHATSAPP_TO")
        return

    url = f"https://graph.facebook.com/v20.0/{phone_id}/messages"

    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {
            "body": text
        }
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    resp = requests.post(url, json=payload, headers=headers)
    print("Status:", resp.status_code)
    print("Respuesta:", resp.text)


# ---------- 3. Punto de entrada: lo que se ejecuta cuando corras el script ----------

if __name__ == "__main__":
    text = build_low_stock_text()

    # Si quieres, puedes NO enviar nada cuando todo está bien:
    if "Todo en orden, no hay ingredientes" in text:
        print("Inventario bien, no se envía WhatsApp.")
    else:
        send_whatsapp_message(text)
