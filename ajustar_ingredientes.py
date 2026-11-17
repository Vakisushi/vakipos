from sqlmodel import Session, select
from main import engine, Ingredient, IngredientInventory

def ajustar_ingrediente(nombre_ingrediente, stock, min_stock):
    """
    Ajusta el inventario de UN ingrediente.
    - nombre_ingrediente: tiene que coincidir con el nombre en la BD
    - stock: cantidad actual que tienes (en la unidad definida, g, ml, pz, etc.)
    - min_stock: mínimo que quieres para que NO marque 'BAJO'
    """
    with Session(engine) as session:
        ing = session.exec(
            select(Ingredient).where(Ingredient.name == nombre_ingrediente)
        ).first()

        if not ing:
            print(f"❌ No encontré el ingrediente: {nombre_ingrediente}")
            return

        inv = session.exec(
            select(IngredientInventory).where(IngredientInventory.ingredient_id == ing.id)
        ).first()

        if not inv:
            inv = IngredientInventory(
                ingredient_id=ing.id,
                stock=stock,
                min_stock=min_stock,
            )
            session.add(inv)
        else:
            inv.stock = stock
            inv.min_stock = min_stock

        session.commit()
        print(f"✅ Inventario actualizado: {nombre_ingrediente} -> stock={stock}, min={min_stock}")


if __name__ == "__main__":
    # 🔴 EDITA ESTAS LÍNEAS CON TUS CANTIDADES REALES 🔴

    # Ejemplos:
    ajustar_ingrediente("Arroz para sushi", 10000, 3000)      # 10 kg de arroz, mínimo 3 kg
    ajustar_ingrediente("Alga nori", 200, 50)                  # 200 hojas, mínimo 50
    ajustar_ingrediente("Pepino", 5000, 1000)                  # 5 kg pepino, mínimo 1 kg
    ajustar_ingrediente("Surimi", 3000, 800)                   # 3 kg surimi
    ajustar_ingrediente("Aceite para freír", 8000, 2000)       # 8 litros (si lo manejas en ml)
    ajustar_ingrediente("Base helado", 2000, 400)
    ajustar_ingrediente("Refresco lata surtido", 72, 24)
    ajustar_ingrediente("Edamame congelado", 4000, 800)
