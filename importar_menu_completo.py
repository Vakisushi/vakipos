from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import select

from desktop_app.database import create_database_backup, ensure_desktop_schema, session_scope
from desktop_app.models import Category, Product


@dataclass(frozen=True)
class MenuItem:
    category: str
    name: str
    price: float
    description: str = ""


ITEMS = [
    MenuItem(
        "Platillos",
        "Paquetellenes",
        150,
        "Medio sushi tradicional a elegir, media orden de boneless en salsa a elegir y media orden de papas.",
    ),
    MenuItem(
        "Platillos",
        "Boneless",
        130,
        "300 gramos de pollo bañados en salsa de tu elección, acompañados de pepino, zanahoria y ranch de la casa.",
    ),
    MenuItem(
        "Platillos",
        "Gohan",
        150,
        "Capa de arroz, queso crema, tampico y proteínas, coronado con aguacate y camarón; incluye soya y chipotle.",
    ),
    MenuItem(
        "Platillos",
        "Yakimeshi",
        140,
        "Arroz frito con zanahoria, calabaza y 3 proteínas, coronado con queso crema y aguacate.",
    ),
    MenuItem(
        "Platillos",
        "Papa Boneless",
        140,
        "300 g de papas fritas con 150 g de boneless en salsa a elegir, coronado con queso amarillo; incluye ranch.",
    ),
    MenuItem(
        "Platillos",
        "Banderilla sencilla",
        70,
        "Banderilla con bebida incluida: té de la casa o Jamaica. Coca-Cola o Coca-Cola Zero por $5 extra.",
    ),
    MenuItem(
        "Platillos",
        "Banderilla monchosa",
        100,
        "Banderilla con queso gratinado y tocino por arriba; incluye té de la casa o Jamaica. Coca-Cola o Coca-Cola Zero por $5 extra.",
    ),
]


TRADITIONALES = [
    ("Vaquiroll", "Queso crema, pepino, aguacate, tocino, pollo y carne."),
    ("Caliroll", "Queso crema, pepino, aguacate, camarón y surimi."),
    ("Cleoroll", "Queso crema, pepino, aguacate, res, camarón y tocino."),
    ("Cielo Mar y Tierra", "Queso crema, pepino, aguacate, camarón, pollo y carne."),
    ("Mar y Tierra", "Queso crema, pepino, aguacate, camarón y carne."),
    ("Cordon Blue", "Queso crema, pepino, aguacate, tocino y pollo."),
    ("Camarón Blue", "Queso crema, pepino, aguacate, tocino y camarón."),
    ("Güerito Roll", "Queso crema, pepino, aguacate, res, pollo, chile verde y chile caribe."),
]
for name, description in TRADITIONALES:
    ITEMS.append(MenuItem("Sushi Tradicional", name, 140, description))


ESPECIALES = [
    ("Quesoso", 170, 220, "Rollo tradicional a elegir con queso gratinado por encima, coronado con tocino."),
    ("Sonorense", 170, 220, "Rollo tradicional a elegir con guiso de carne, cebolla, chile verde y queso gratinado."),
    ("Avocado Roll", 170, 220, "Sushi tradicional a elegir con capa de aguacate por encima, coronado con ajonjolí."),
    ("Monchis Roll", 180, 230, "Sushi tradicional a elegir con cama de tampico arriba, cama de zanahoria y boneless."),
    ("Sushiboneless", 160, 190, "Sushi tradicional a elegir con 150 g de pollo arriba, bañado en salsa a elegir."),
]
for name, price_n, price_j, description in ESPECIALES:
    ITEMS.append(MenuItem("Sushi Especial", name, price_n, description))


LEGACY_SUSHI_VARIANTS = {
    f"{name} {size}"
    for name, *_ in (*TRADITIONALES, *ESPECIALES)
    for size in ("N", "J")
}


ITEMS.extend(
    [
        MenuItem(
            "Entradas",
            "Orden de aros",
            80,
            "Orden completa de aros de cebolla.",
        ),
        MenuItem("Extras", "Extra Pollo", 15),
        MenuItem("Extras", "Extra Res", 15),
        MenuItem("Extras", "Extra Camarón", 15),
        MenuItem("Extras", "Extra Tocino", 10),
        MenuItem("Extras", "Extra Aguacate", 15),
        MenuItem("Extras", "Extra Tampico", 15),
        MenuItem("Extras", "Extra Queso gratinado", 30),
        MenuItem("Bebidas", "Té de la casa 500 ml", 25),
        MenuItem("Bebidas", "Coca-Cola Zero", 30),
        MenuItem("Bebidas", "Jamaica", 25),
    ]
)


RETIRED_PRODUCTS = {
    "Edamames",
    "Media orden de aros",
    "Media orden de dedos de queso",
    "Orden de dedos de queso",
    "Coca-Cola 600 ml",
    "Refresco Lata",
}


def import_menu() -> tuple[int, int]:
    ensure_desktop_schema()
    created = 0
    updated = 0
    with session_scope() as session:
        categories = {row.name: row for row in session.exec(select(Category)).all()}
        existing_products = {
            row.name: row for row in session.exec(select(Product)).all()
        }
        needs_changes = any(
            item.name not in existing_products
            or existing_products[item.name].price != item.price
            or existing_products[item.name].description != (item.description or None)
            or categories.get(item.category) is None
            or existing_products[item.name].category_id != categories[item.category].id
            for item in ITEMS
        ) or any(
            product.is_active and product.name in LEGACY_SUSHI_VARIANTS
            for product in existing_products.values()
        ) or any(
            product.is_active and product.name in RETIRED_PRODUCTS
            for product in existing_products.values()
        )
        if not needs_changes:
            return 0, 0

        create_database_backup()
        for category_name in sorted({item.category for item in ITEMS}):
            if category_name not in categories:
                category = Category(name=category_name)
                session.add(category)
                session.flush()
                categories[category_name] = category

        for item in ITEMS:
            product = existing_products.get(item.name)
            if product is None:
                product = Product(
                    name=item.name,
                    price=item.price,
                    category_id=categories[item.category].id,
                    description=item.description or None,
                )
                created += 1
            else:
                new_description = item.description or None
                if (
                    product.price != item.price
                    or product.category_id != categories[item.category].id
                    or product.description != new_description
                    or not product.is_active
                ):
                    product.price = item.price
                    product.category_id = categories[item.category].id
                    product.description = new_description
                    product.is_active = True
                    updated += 1
            session.add(product)
        for legacy_name in LEGACY_SUSHI_VARIANTS:
            legacy = existing_products.get(legacy_name)
            if legacy is not None and legacy.is_active:
                legacy.is_active = False
                session.add(legacy)
        for retired_name in RETIRED_PRODUCTS:
            retired = existing_products.get(retired_name)
            if retired is not None and retired.is_active:
                retired.is_active = False
                session.add(retired)
    return created, updated


if __name__ == "__main__":
    new_count, updated_count = import_menu()
    print(f"Menú importado: {new_count} productos creados, {updated_count} actualizados.")
