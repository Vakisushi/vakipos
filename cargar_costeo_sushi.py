"""Carga el costeo completo de VAKI SUSHI (Costeo_Vaki_Sushi (1).pdf).

Modelo:
- Insumo: se compra. Costo = precio ticket (+IVA) / contenido / rendimiento * (1 + merma).
- Subreceta (preparación): se hace con insumos y/o otras subrecetas. Costo = suma / rendimiento.
- Producto (menú): usa insumos y subrecetas en la cantidad de su receta.

Es idempotente: vuelve a correrlo y reemplaza ingredientes, subrecetas y recetas de los
productos del costeo. Las existencias de los insumos existentes se conservan.

Uso:  python cargar_costeo_sushi.py
"""

from __future__ import annotations

from sqlmodel import select

from desktop_app.database import create_database_backup, ensure_desktop_schema, session_scope
from desktop_app.models import (
    Category,
    Ingredient,
    IngredientInventory,
    IngredientRecipe,
    Product,
    RecipeItem,
)
from desktop_app.services import product_recipe, recalculate_ingredient_costs, save_product

TOLERANCIA = 0.02

# ---------------------------------------------------------------------------
# 1. Insumos (hoja "Insumos" del PDF)
#    (nombre, unidad, precio ticket, contenido, lleva IVA, rendimiento, merma)
# ---------------------------------------------------------------------------
MERMA = 0.10
INSUMOS = [
    ("Aceite Ave Action Fry", "ml", 728, 20000, False, 1, MERMA),
    ("Té Jasmine", "g", 1746, 13607.77, False, 1, MERMA),
    ("Panko Kinchef", "g", 490, 9080, False, 1, MERMA),
    ("Salsa BBQ Kinchef", "g", 730, 15000, False, 1, MERMA),
    ("Soya Lucky", "ml", 435, 18927.05, False, 1, MERMA),
    ("Sriracha Kinchef", "ml", 908, 15120, False, 1, MERMA),
    ("Azúcar", "g", 22, 900, False, 1, MERMA),
    ("Arroz sushi Homai", "g", 602, 22700, False, 1, MERMA),
    ("Alga nori", "media hoja", 137, 100, False, 1, MERMA),
    ("Surimi", "g", 1080, 12000, False, 1, MERMA),
    ('Palillos de madera 8"', "par", 1840, 4000, True, 1, MERMA),
    ("Aderezo de mayonesa", "ml", 137.08, 3800, False, 1, MERMA),
    ("Consomé de pollo Knorr", "g", 110.48, 1000, False, 1, MERMA),
    ("Chipotle Member's Mark", "g", 200.51, 2800, False, 1, MERMA),
    ("Tocino", "g", 159, 1000, False, 1, MERMA),
    ("Botella ½ L", "pz", 93.06, 30, True, 1, MERMA),
    ("Tapa vaso soufflé 2 oz", "pz", 22.19, 100, True, 1, MERMA),
    ("Vaso soufflé 2 oz", "pz", 36.25, 100, True, 1, MERMA),
    ("Contenedor 9×9 con división", "pz", 144.84, 50, True, 1, MERMA),
    ("Contenedor hoagie", "pz", 136.50, 100, True, 1, MERMA),
    ("Guantes polietileno M", "pz", 36.08, 100, True, 1, MERMA),
    ("Bolsa camiseta grande", "g", 75, 1000, True, 1, MERMA),
    ("Media crema Lala", "ml", 17, 250, False, 1, MERMA),
    ("Pepino", "g", 15.90, 1000, False, 1, MERMA),
    ("Aguacate", "g", 39.90, 1000, False, 1, MERMA),
    ("Chile jalapeño", "g", 29.90, 1000, False, 1, MERMA),
    ("Limón", "g", 18.90, 1000, False, 1, MERMA),
    ("Zanahoria", "g", 16.90, 1000, False, 1, MERMA),
    ("Pechuga de pollo", "g", 57, 1000, False, 1, MERMA),
    ("Carne de res (diezmillo)", "g", 165, 1000, False, 1, MERMA),
    ("Chile serrano", "g", 29.93, 1000, False, 1, MERMA),
    ("Queso crema", "g", 298, 1900, False, 1, MERMA),
    ("Harina", "g", 20, 1000, False, 1, MERMA),
    ("Vinagre de manzana La Costeña", "ml", 54, 3700, False, 1, MERMA),
    ("Cebolla", "g", 20, 1000, False, 1, MERMA),
    ("Pimienta", "g", 33, 75, False, 1, MERMA),
    ("Sal con ajo", "g", 24, 130, False, 1, MERMA),
    ("Sal", "g", 10, 1000, False, 1, MERMA),
    ("Camarón", "g", 80, 1000, False, 0.8, MERMA),  # rendimiento 80% al pelar
    ("Queso chihuahua", "g", 105, 1000, False, 1, MERMA),
    ("Salsa búfalo", "ml", 210, 3700, False, 1, MERMA),
    ("Papas", "g", 97, 2200, False, 1, MERMA),
    ("Queso amarillo", "g", 48, 1000, False, 1, MERMA),
    ("Calabaza", "g", 25, 1000, False, 1, MERMA),
    ("Coca-Cola 600 ml", "pz", 17, 1, False, 1, 0),  # viene sellada, sin merma
    ("Chile (1 pz = $1)", "pz", 1, 1, False, 1, 0),  # chiles/chile verde: 1 pz = $1 de costo
]

# ---------------------------------------------------------------------------
# 2. Subrecetas (hoja "Subrecetas" y "Base fija de cada roll").
#    nombre: (unidad del resultado, rendimiento, [(componente, cantidad en su unidad)])
# ---------------------------------------------------------------------------
SUBRECETAS = {
    "Vinagre casero": ("ml", 4000, [("Vinagre de manzana La Costeña", 3700), ("Azúcar", 500)]),
    "Arroz preparado": ("g", 2050, [("Arroz sushi Homai", 1000), ("Vinagre casero", 200)]),
    "Aderezo chipotle": (
        "ml",
        1295,
        [
            ("Aderezo de mayonesa", 480),
            ("Consomé de pollo Knorr", 5),
            ("Media crema Lala", 480),
            ("Sriracha Kinchef", 80),
            ("Chipotle Member's Mark", 250),
            ("Sal", 1),
        ],
    ),
    "Ranch de la casa": (
        "ml",
        310,  # rendimiento medido en el PDF (suma de líquidos, limón da 60 ml de jugo)
        [
            ("Media crema Lala", 120),
            ("Aderezo de mayonesa", 120),
            ("Pimienta", 5),
            ("Sal con ajo", 5),
            ("Limón", 150),
        ],
    ),
    "Soya preparada": ("ml", 250, [("Soya Lucky", 100), ("Limón", 125)]),
    "Tampico": (
        "g",
        1575,
        [
            ("Surimi", 1000),
            ("Chile serrano", 100),
            ("Cebolla", 150),
            ("Media crema Lala", 125),
            ("Aderezo de mayonesa", 200),
        ],
    ),
    "Pollo boneless (crudo)": (
        "g",
        1000,
        [("Pechuga de pollo", 1000), ("Harina", 80), ("Aceite Ave Action Fry", 100)],
    ),
    "Papas fritas (100 g)": ("g", 100, [("Papas", 100), ("Aceite Ave Action Fry", 10)]),
    "Empanizado roll normal": (
        "pz",
        1,
        [("Panko Kinchef", 40), ("Harina", 20), ("Aceite Ave Action Fry", 30)],
    ),
    "Salsa de anguila": ("ml", 1000, [("Soya Lucky", 1000), ("Azúcar", 300)]),
    "Salsa cookie": ("ml", 100, [("Salsa búfalo", 50), ("Salsa BBQ Kinchef", 50)]),
    "Té de la casa (jazmín)": ("ml", 4000, [("Té Jasmine", 50), ("Azúcar", 400)]),
    "Relleno base normal": (
        "pz",
        1,
        [
            ("Arroz preparado", 250),
            ("Queso crema", 30),
            ("Aguacate", 30),
            ("Pepino", 20),
            ("Zanahoria", 30),
        ],
    ),
    "Relleno base jumbo": (
        "pz",
        1,
        [
            ("Arroz preparado", 400),
            ("Queso crema", 50),
            ("Aguacate", 60),
            ("Pepino", 40),
            ("Zanahoria", 30),
        ],
    ),
    "Bote de chipotle": (
        "pz",
        1,
        [("Aderezo chipotle", 60), ("Vaso soufflé 2 oz", 1), ("Tapa vaso soufflé 2 oz", 1)],
    ),
    "Bote de soya preparada": (
        "pz",
        1,
        [("Soya preparada", 60), ("Vaso soufflé 2 oz", 1), ("Tapa vaso soufflé 2 oz", 1)],
    ),
    "Bote de ranch": (
        "pz",
        1,
        [("Ranch de la casa", 60), ("Vaso soufflé 2 oz", 1), ("Tapa vaso soufflé 2 oz", 1)],
    ),
    # Base fija de cada roll: NO es un insumo, es una subreceta hecha con insumos.
    "Base fija roll normal": (
        "pz",
        1,
        [
            ("Relleno base normal", 1),
            ("Bote de chipotle", 1),
            ("Bote de soya preparada", 1),
            ("Contenedor 9×9 con división", 1),
            ('Palillos de madera 8"', 1),
        ],
    ),
    "Base fija roll jumbo": (
        "pz",
        1,
        [
            ("Relleno base jumbo", 1),
            ("Bote de chipotle", 1),
            ("Bote de soya preparada", 1),
            ("Contenedor 9×9 con división", 1),
            ('Palillos de madera 8"', 1),
        ],
    ),
}

# ---------------------------------------------------------------------------
# 3. Productos del menú
# ---------------------------------------------------------------------------
BASE_N = "Base fija roll normal"
BASE_J = "Base fija roll jumbo"
CHILE = "Chile (1 pz = $1)"
POLLO = "Pollo boneless (crudo)"
CARNE = "Carne de res (diezmillo)"
TOCINO = "Tocino"
CAMARON = "Camarón"
SURIMI = "Surimi"

# Sushi tradicional: (pollo, carne, tocino, camarón, surimi) en gramos, costo natural del PDF.
TRADICIONAL = {
    "Vaquiroll": {"N": ((50, 30, 30, 0, 0), 36.25), "J": ((80, 50, 50, 0, 0), 52.95)},
    "Caliroll": {"N": ((0, 0, 0, 70, 70), 36.77), "J": ((0, 0, 0, 120, 140), 56.72)},
    "Cleoroll": {"N": ((0, 30, 30, 50, 0), 38.33), "J": ((0, 50, 50, 80, 0), 56.28)},
    "Cielo Mar y Tierra": {"N": ((50, 30, 0, 50, 0), 36.51), "J": ((80, 50, 0, 80, 0), 53.01)},
    "Mar y Tierra": {"N": ((0, 40, 0, 70, 0), 37.10), "J": ((0, 70, 0, 120, 0), 55.56)},
    "Cordon Blue": {"N": ((70, 0, 40, 0, 0), 33.93), "J": ((120, 0, 70, 0, 0), 50.12)},
    "Camarón Blue": {"N": ((0, 0, 40, 70, 0), 36.83), "J": ((0, 0, 70, 120, 0), 55.10)},
    "Güerito Roll": {"N": ((70, 40, 0, 0, 0), 37.19), "J": ((120, 70, 0, 0, 0), 56.58)},
}
CHILES_GUERITO = {"N": 3, "J": 6}  # costo fijo de chiles del PDF
PRECIO_TRADICIONAL = {"N": 140, "J": 190}

# Rollo base "peor caso" (máximo costo) que se usa en especiales: Cleoroll N y Caliroll J.
PROTEINA_PEOR_N = [(CARNE, 30), (TOCINO, 30), (CAMARON, 50)]
PROTEINA_PEOR_J = [(SURIMI, 140), (CAMARON, 120)]

ESPECIALES = {
    # nombre: {tamaño: (precio, receta, costo máx del PDF)}
    "Quesoso": {
        "N": (170, [(BASE_N, 1), ("Queso chihuahua", 100), ("Media crema Lala", 30), (TOCINO, 30)] + PROTEINA_PEOR_N, 57.37),
        "J": (220, [(BASE_J, 1), ("Queso chihuahua", 125), ("Media crema Lala", 37.5), (TOCINO, 37.5)] + PROTEINA_PEOR_J, 80.52),
    },
    "Sonorense": {
        "N": (170, [(BASE_N, 1), ("Queso chihuahua", 50), ("Media crema Lala", 30), (CARNE, 100), ("Cebolla", 50), (CHILE, 2)] + PROTEINA_PEOR_N, 67.60),
        "J": (220, [(BASE_J, 1), ("Queso chihuahua", 62.5), ("Media crema Lala", 37.5), (CARNE, 125), ("Cebolla", 62.5), (CHILE, 2.5)] + PROTEINA_PEOR_J, 93.30),
    },
    "Avocado Roll": {
        "N": (170, [(BASE_N, 1), ("Aguacate", 100), ("Queso crema", 5)] + PROTEINA_PEOR_N, 43.58),
        "J": (220, [(BASE_J, 1), ("Aguacate", 125), ("Queso crema", 6.25)] + PROTEINA_PEOR_J, 63.28),
    },
    "Monchis Roll": {
        "N": (180, [(BASE_N, 1), ("Tampico", 100), ("Zanahoria", 90), (POLLO, 150), ("Salsa búfalo", 150), ("Bote de ranch", 1)] + PROTEINA_PEOR_N, 72.11),
        "J": (230, [(BASE_J, 1), ("Tampico", 125), ("Zanahoria", 112.5), (POLLO, 187.5), ("Salsa búfalo", 187.5), ("Bote de ranch", 1)] + PROTEINA_PEOR_J, 97.78),
    },
    "Sushiboneless": {
        "N": (160, [(BASE_N, 1), (POLLO, 150), ("Salsa búfalo", 150), ("Bote de ranch", 1)] + PROTEINA_PEOR_N, 62.64),
        "J": (190, [(BASE_J, 1), (POLLO, 187.5), ("Salsa búfalo", 187.5), ("Bote de ranch", 1)] + PROTEINA_PEOR_J, 85.93),
    },
}

PLATILLOS = {
    "Paquetellenes": (
        150,
        [
            ("Relleno base normal", 0.5),  # medio roll tradicional (solo ingredientes)
            (CARNE, 15),
            (TOCINO, 15),
            (CAMARON, 25),
            (POLLO, 100),
            ("Salsa búfalo", 75),
            ("Papas fritas (100 g)", 100),
            ("Bote de chipotle", 1),
            ("Bote de soya preparada", 1),
            ("Bote de ranch", 1),
            ("Contenedor 9×9 con división", 1),
            ('Palillos de madera 8"', 1),
        ],
        45.99,
    ),
    "Boneless": (
        130,
        [
            (POLLO, 300),
            ("Salsa búfalo", 150),
            ("Zanahoria", 150),
            ("Pepino", 150),
            ("Bote de ranch", 1),
            ("Contenedor 9×9 con división", 1),
        ],
        43.69,
    ),
    "Gohan": (
        150,
        [
            ("Arroz preparado", 200),
            ("Queso crema", 150),
            ("Tampico", 200),
            (CARNE, 50),  # 3 proteínas × 50 g, peor caso: carne, tocino, camarón
            (TOCINO, 50),
            (CAMARON, 70),  # 50 g de proteína + 20 g de camarón de corona
            ("Aguacate", 30),
            ("Bote de chipotle", 1),
            ("Bote de soya preparada", 1),
            ("Contenedor 9×9 con división", 1),
            ('Palillos de madera 8"', 1),
        ],
        82.26,
    ),
    "Yakimeshi": (
        140,
        [
            ("Arroz preparado", 200),
            ("Zanahoria", 30),
            ("Calabaza", 30),
            (CARNE, 50),
            (TOCINO, 50),
            (CAMARON, 50),
            ("Queso crema", 50),
            ("Aguacate", 30),
            ("Aceite Ave Action Fry", 15),
            ("Soya preparada", 80),
            ("Limón", 50),
            ("Bote de chipotle", 1),
            ("Bote de soya preparada", 1),
            ("Contenedor 9×9 con división", 1),
            ('Palillos de madera 8"', 1),
        ],
        51.86,
    ),
    "Papa Boneless": (
        140,
        [
            ("Papas fritas (100 g)", 300),
            (POLLO, 150),
            ("Salsa búfalo", 150),
            ("Queso amarillo", 60),
            ("Bote de ranch", 1),
            ("Contenedor 9×9 con división", 1),
        ],
        46.92,
    ),
}

EXTRAS = {
    "Extra Pollo": (15, [(POLLO, 30)], 2.05),
    "Extra Res": (15, [(CARNE, 30)], 5.45),
    "Extra Camarón": (15, [(CAMARON, 30)], 3.30),
    "Extra Tocino": (10, [(TOCINO, 30)], 5.25),
    "Extra Aguacate": (15, [("Aguacate", 30)], 1.32),
    "Extra Tampico": (15, [("Tampico", 50)], 3.90),
}

BEBIDAS = {
    "Té de la casa 500 ml": (25, [("Té de la casa (jazmín)", 500), ("Botella ½ L", 1)], 6.18),
    "Coca-Cola 600 ml": (30, [("Coca-Cola 600 ml", 1)], 17.00),
}

# Nombres del importador anterior que se reemplazan por la versión con tamaño.
SUSTITUIDOS = [
    "Quesoso", "Sonorense", "Avocado Roll", "Monchis Roll", "Sushiboneless",
    *TRADICIONAL.keys(),
]

# Ingredientes de cargas anteriores que ya no existen en el costeo.
OBSOLETOS = [
    "Base roll Normal", "Base roll Jumbo", "Chiles Güerito Normal", "Chiles Güerito Jumbo",
    "Pollo boneless", "Carne (res)",
]


def _borrar_ingrediente(session, ingrediente: Ingredient) -> None:
    for model, column in (
        (RecipeItem, RecipeItem.ingredient_id),
        (IngredientInventory, IngredientInventory.ingredient_id),
    ):
        for row in session.exec(select(model).where(column == ingrediente.id)).all():
            session.delete(row)
    for row in session.exec(
        select(IngredientRecipe).where(
            (IngredientRecipe.parent_ingredient_id == ingrediente.id)
            | (IngredientRecipe.component_ingredient_id == ingrediente.id)
        )
    ).all():
        session.delete(row)
    session.delete(ingrediente)


def _ingrediente(session, nombre: str, unidad: str, *, kind: str, price=None, iva=False,
                 contents=None, yield_rate=1.0, waste=0.0, yield_qty=None) -> int:
    ing = session.exec(select(Ingredient).where(Ingredient.name == nombre)).first()
    if ing is None:
        ing = Ingredient(name=nombre)
        session.add(ing)
        session.flush()
    ing.unit = unidad
    ing.kind = kind
    ing.purchase_price = price
    ing.purchase_iva = iva
    ing.purchase_contents = contents
    ing.yield_rate = yield_rate
    ing.waste_rate = waste
    ing.yield_quantity = yield_qty
    session.add(ing)
    if kind == "insumo":
        inv = session.exec(
            select(IngredientInventory).where(IngredientInventory.ingredient_id == ing.id)
        ).first()
        if inv is None:
            session.add(IngredientInventory(ingredient_id=ing.id, stock=0, min_stock=0))
    return ing.id


def _categoria(session, nombre: str) -> int:
    cat = session.exec(select(Category).where(Category.name == nombre)).first()
    if cat is None:
        cat = Category(name=nombre)
        session.add(cat)
        session.flush()
    return cat.id


def _receta_producto(ids: dict[str, int], lineas) -> dict[int, tuple[float, str]]:
    """Convierte [(nombre, cantidad)] en {id: (cantidad, unidad)}; suma repetidos."""
    receta: dict[int, float] = {}
    for nombre, cantidad in lineas:
        if cantidad:
            receta[ids[nombre]] = receta.get(ids[nombre], 0) + cantidad
    return {ing_id: (cant, UNIDADES[ing_id]) for ing_id, cant in receta.items()}


UNIDADES: dict[int, str] = {}


def _costo_producto(session, product_id: int) -> float:
    total = 0.0
    for line in product_recipe(session, product_id):
        ingrediente = session.get(Ingredient, line.ingredient_id)
        total += line.quantity * ingrediente.unit_cost
    return total


def cargar() -> list[str]:
    ensure_desktop_schema()
    create_database_backup()
    advertencias: list[str] = []
    esperados: dict[str, float] = {}

    with session_scope() as session:
        # Limpieza de cargas anteriores que no eran insumos reales.
        for nombre in OBSOLETOS:
            ing = session.exec(select(Ingredient).where(Ingredient.name == nombre)).first()
            if ing is not None:
                _borrar_ingrediente(session, ing)
        session.flush()

        # Insumos
        ids: dict[str, int] = {}
        for nombre, unidad, precio, contenido, iva, rendimiento, merma in INSUMOS:
            ids[nombre] = _ingrediente(
                session, nombre, unidad, kind="insumo", price=precio, iva=iva,
                contents=contenido, yield_rate=rendimiento, waste=merma,
            )

        # Subrecetas: se crean primero para poder referenciarlas entre sí.
        for nombre, (unidad, rendimiento, _) in SUBRECETAS.items():
            ids[nombre] = _ingrediente(
                session, nombre, unidad, kind="preparacion", yield_qty=rendimiento
            )
        for nombre, (_, _, componentes) in SUBRECETAS.items():
            for row in session.exec(
                select(IngredientRecipe).where(IngredientRecipe.parent_ingredient_id == ids[nombre])
            ).all():
                session.delete(row)
            session.flush()
            for comp_nombre, cantidad in componentes:
                session.add(IngredientRecipe(
                    parent_ingredient_id=ids[nombre],
                    component_ingredient_id=ids[comp_nombre],
                    quantity=cantidad,
                ))
        session.flush()

        for ing in session.exec(select(Ingredient)).all():
            UNIDADES[ing.id] = ing.unit
        recalculate_ingredient_costs(session)
        session.flush()

        # Categorías
        cat_trad = _categoria(session, "Sushi Tradicional")
        cat_esp = _categoria(session, "Sushi Especial")
        cat_plat = _categoria(session, "Platillos")
        cat_ext = _categoria(session, "Extras")
        cat_beb = _categoria(session, "Bebidas")

        def guardar(nombre: str, precio: float, categoria: int, lineas, esperado=None):
            existente = session.exec(select(Product).where(Product.name == nombre)).first()
            pid = save_product(
                session,
                existente.id if existente else None,
                nombre,
                precio,
                categoria,
                _receta_producto(ids, lineas),
                "",
            )
            session.flush()
            if esperado is not None:
                esperados[nombre] = esperado
                costo = _costo_producto(session, pid)
                if abs(costo - esperado) > TOLERANCIA:
                    advertencias.append(f"{nombre}: calculado ${costo:.2f}, PDF ${esperado:.2f}")

        # Sushi tradicional Normal y Jumbo
        for roll, tamanos in TRADICIONAL.items():
            for tam, nombre_tam in (("N", "Normal"), ("J", "Jumbo")):
                (pollo, carne, tocino, camaron, surimi), natural = tamanos[tam]
                base = BASE_N if tam == "N" else BASE_J
                lineas = [
                    (base, 1),
                    (POLLO, pollo),
                    (CARNE, carne),
                    (TOCINO, tocino),
                    (CAMARON, camaron),
                    (SURIMI, surimi),
                ]
                if roll == "Güerito Roll":
                    lineas.append((CHILE, CHILES_GUERITO[tam]))
                guardar(f"{roll} {nombre_tam}", PRECIO_TRADICIONAL[tam], cat_trad, lineas, natural)

        # Sushi especial Normal y Jumbo
        for roll, tamanos in ESPECIALES.items():
            for tam, nombre_tam in (("N", "Normal"), ("J", "Jumbo")):
                precio, lineas, maximo = tamanos[tam]
                guardar(f"{roll} {nombre_tam}", precio, cat_esp, lineas, maximo)

        for nombre, (precio, lineas, maximo) in PLATILLOS.items():
            guardar(nombre, precio, cat_plat, lineas, maximo)
        for nombre, (precio, lineas, costo) in EXTRAS.items():
            guardar(nombre, precio, cat_ext, lineas, costo)
        for nombre, (precio, lineas, costo) in BEBIDAS.items():
            guardar(nombre, precio, cat_beb, lineas, costo)

        for producto in session.exec(
            select(Product).where(Product.name.in_(SUSTITUIDOS))
        ).all():
            producto.is_active = False
            session.add(producto)

    return advertencias


if __name__ == "__main__":
    avisos = cargar()
    print("Costeo VAKI SUSHI cargado: insumos, subrecetas y productos del PDF.")
    if avisos:
        print("Diferencias contra el PDF:")
        for aviso in avisos:
            print(" -", aviso)
    else:
        print(f"Todos los costos cuadran con el PDF (±${TOLERANCIA:.2f}).")
