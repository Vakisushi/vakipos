from sqlmodel import Session, select
from main import engine, Product, InventoryItem

def ajustar_inventario(nombre_producto, stock, min_stock):
    with Session(engine) as session:
        producto = session.exec(
            select(Product).where(Product.name == nombre_producto)
        ).first()

        if not producto:
            print("❌ No encontré el producto:", nombre_producto)
            return

        inv = session.exec(
            select(InventoryItem).where(InventoryItem.product_id == producto.id)
        ).first()

        if not inv:
            inv = InventoryItem(
                product_id=producto.id,
                stock=stock,
                min_stock=min_stock,
            )
            session.add(inv)
        else:
            inv.stock = stock
            inv.min_stock = min_stock

        session.commit()
        print(f"✅ Inventario actualizado para {nombre_producto}: stock={stock}, min={min_stock}")


if __name__ == "__main__":
    # EDITA ESTAS LÍNEAS CON TUS PRODUCTOS Y CANTIDADES
    ajustar_inventario("Sushi California", 0, 10)
    ajustar_inventario("Yakimeshi", 0, 5)
    ajustar_inventario("Refresco Lata", 0, 10)
    ajustar_inventario("Helado Frito", 0, 5)
    ajustar_inventario("Edamames", 0, 5)
