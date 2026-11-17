from fastapi import FastAPI, Depends, Request, Form 
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
print(">>> CARGANDO MAIN:", __file__)
from fastapi import FastAPI, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
from sqlmodel import (
    SQLModel,
    Field,
    Session,
    create_engine,
    select,
    Relationship,
    delete,
)
from typing import Optional, List, Dict
from jinja2 import Template
from datetime import datetime
from sqlalchemy import func
import uuid
import os
import json
import sys
import subprocess

# ---------------------------------------------------------
# CONFIGURACIÓN BD
# ---------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'sushi_pos.db')}"
engine = create_engine(DATABASE_URL, echo=False)


app = FastAPI(title="Sushi POS")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# MODELOS
# ---------------------------------------------------------


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    full_name: str
    hashed_password: str  # contraseña tal cual (por ahora)
    is_admin: bool = Field(default=False)


class Category(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    products: List["Product"] = Relationship(back_populates="category")
    # NUEVO: ingredientes asignados a esta categoría
    ingredient_links: List["IngredientCategory"] = Relationship(back_populates="category")


class Product(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    price: float
    category_id: int = Field(foreign_key="category.id")
    category: Optional[Category] = Relationship(back_populates="products")
    recipe_items: List["RecipeItem"] = Relationship(back_populates="product")


class Ingredient(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    unit: str = Field(default="pz")  # g, ml, pz, etc.
    stocks: List["IngredientInventory"] = Relationship(back_populates="ingredient")
    recipes: List["RecipeItem"] = Relationship(back_populates="ingredient")
    # NUEVO: categorías donde se usa este ingrediente
    category_links: List["IngredientCategory"] = Relationship(back_populates="ingredient")


class IngredientInventory(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    ingredient_id: int = Field(foreign_key="ingredient.id")
    ingredient: Optional[Ingredient] = Relationship(back_populates="stocks")
    stock: float = Field(default=0)  # existencias
    min_stock: float = Field(default=0)  # mínimo antes de marcar "bajo"


class IngredientCategory(SQLModel, table=True):
    """Asocia un ingrediente con una o varias categorías (Sushis, Entradas, etc.)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    ingredient_id: int = Field(foreign_key="ingredient.id")
    category_id: int = Field(foreign_key="category.id")

    ingredient: Optional[Ingredient] = Relationship(back_populates="category_links")
    category: Optional[Category] = Relationship(back_populates="ingredient_links")


class RecipeItem(SQLModel, table=True):
    """Relación producto-ingrediente (receta): cuánto ingrediente usa 1 unidad del producto."""
    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id")
    ingredient_id: int = Field(foreign_key="ingredient.id")
    quantity_per_unit: float  # ej: 100 g de arroz por roll

    product: Optional[Product] = Relationship(back_populates="recipe_items")
    ingredient: Optional[Ingredient] = Relationship(back_populates="recipes")


class Order(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    # Tipo de pedido
    order_type: str  # "COMEDOR", "LLEVAR", "APP", etc.
    table_number: Optional[str] = None
    customer_name: Optional[str] = None
    delivery_platform: Optional[str] = None  # "RAPPI", "DIDI", "UBER", None

    # NUEVO: estado de pago
    is_paid: bool = Field(default=False)
    payment_method: Optional[str] = None  # "EFECTIVO", "TRANSFERENCIA", "TARJETA"

    items: List["OrderItem"] = Relationship(back_populates="order")



class OrderItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id")
    product_id: int = Field(foreign_key="product.id")
    quantity: int
    unit_price: float
    order: Optional[Order] = Relationship(back_populates="items")
    product: Optional[Product] = Relationship()


class CashClose(SQLModel, table=True):
    """Cierre de caja: quién cerró, cuándo, cuánto había y diferencia."""
    id: Optional[int] = Field(default=None, primary_key=True)
    closed_at: datetime = Field(default_factory=datetime.utcnow)
    user_id: int = Field(foreign_key="user.id")
    total_sales: float
    reported_cash: float
    difference: float  # reported_cash - total_sales


# ---------------------------------------------------------
# SESIONES / LOGIN SIMPLE EN MEMORIA
# ---------------------------------------------------------

sessions: Dict[str, int] = {}  # token -> user_id


def get_session():
    with Session(engine) as session:
        yield session


def get_current_user(request: Request, db: Session = Depends(get_session)) -> Optional[User]:
    token = request.cookies.get("session_id")
    if not token:
        return None
    user_id = sessions.get(token)
    if not user_id:
        return None
    user = db.get(User, user_id)
    return user


# ---------------------------------------------------------
# INICIALIZACIÓN BD + DATOS DEMO
# ---------------------------------------------------------


def create_db_and_seed():
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        # usuario admin por defecto
        admin = session.exec(select(User).where(User.username == "admin")).first()
        if not admin:
            admin = User(
                username="admin",
                full_name="Administrador",
                hashed_password="admin",  # texto plano
                is_admin=True,
            )
            session.add(admin)

        # categorías básicas
        if not session.exec(select(Category)).first():
            categorias = [
                "Entradas",
                "Platillos",
                "Sushis",
                "Bebidas",
                "Postres",
            ]
            for c in categorias:
                cat = Category(name=c)
                session.add(cat)
            session.commit()

            # productos demo
            productos_demo = [
                ("Edamames", 60, "Entradas"),
                ("Yakimeshi", 90, "Platillos"),
                ("Sushi California", 110, "Sushis"),
                ("Refresco Lata", 25, "Bebidas"),
                ("Helado Frito", 65, "Postres"),
            ]
            for nombre, precio, cat_nombre in productos_demo:
                cat = session.exec(select(Category).where(Category.name == cat_nombre)).first()
                if cat:
                    p = Product(name=nombre, price=precio, category_id=cat.id)
                    session.add(p)
            session.commit()

        # ingredientes demo
        if not session.exec(select(Ingredient)).first():
            ingredientes_demo = [
                ("Arroz para sushi", "g", 5000, 1000),
                ("Alga nori", "pz", 100, 20),
                ("Pepino", "g", 2000, 500),
                ("Surimi", "g", 2000, 500),
                ("Aceite para freír", "ml", 5000, 1000),
                ("Base helado", "g", 1000, 200),
                ("Refresco lata surtido", "pz", 48, 12),
                ("Edamame congelado", "g", 3000, 500),
            ]
            for nombre, unidad, stock, min_stock in ingredientes_demo:
                ing = Ingredient(name=nombre, unit=unidad)
                session.add(ing)
                session.flush()
                inv = IngredientInventory(
                    ingredient_id=ing.id,
                    stock=stock,
                    min_stock=min_stock,
                )
                session.add(inv)
            session.commit()

        # recetas demo por producto
        if not session.exec(select(RecipeItem)).first():
            recetas = {
                "Sushi California": [
                    ("Arroz para sushi", 120.0),
                    ("Alga nori", 1.0),
                    ("Pepino", 30.0),
                    ("Surimi", 40.0),
                ],
                "Yakimeshi": [
                    ("Arroz para sushi", 150.0),
                    ("Aceite para freír", 10.0),
                    ("Surimi", 30.0),
                ],
                "Edamames": [
                    ("Edamame congelado", 100.0),
                ],
                "Refresco Lata": [
                    ("Refresco lata surtido", 1.0),
                ],
                "Helado Frito": [
                    ("Base helado", 80.0),
                    ("Aceite para freír", 10.0),
                ],
            }

            for prod_name, lista_ings in recetas.items():
                producto = session.exec(
                    select(Product).where(Product.name == prod_name)
                ).first()
                if not producto:
                    continue
                for ing_name, qty in lista_ings:
                    ing = session.exec(
                        select(Ingredient).where(Ingredient.name == ing_name)
                    ).first()
                    if not ing:
                        continue
                    r = RecipeItem(
                        product_id=producto.id,
                        ingredient_id=ing.id,
                        quantity_per_unit=qty,
                    )
                    session.add(r)
            session.commit()

        # Vincular ingredientes con categorías (inicialmente todos con todas)
        if not session.exec(select(IngredientCategory)).first():
            all_ingredients = session.exec(select(Ingredient)).all()
            all_categories = session.exec(select(Category)).all()
            for ing in all_ingredients:
                for cat in all_categories:
                    link = IngredientCategory(ingredient_id=ing.id, category_id=cat.id)
                    session.add(link)
            session.commit()


@app.on_event("startup")
def on_startup():
    create_db_and_seed()


# ---------------------------------------------------------
# PLANTILLAS HTML
# ---------------------------------------------------------

LOGIN_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Sushi POS - Login</title>
    <style>
        body { font-family: Arial, sans-serif; background:#f5f5f5; display:flex; align-items:center; justify-content:center; height:100vh; margin:0; }
        .card { background:white; padding:20px; border-radius:10px; box-shadow:0 2px 8px rgba(0,0,0,0.1); width:320px; }
        input, select { width:100%; padding:8px; margin:6px 0; box-sizing:border-box; }
        button { width:100%; padding:10px; margin-top:10px; cursor:pointer; }
        .error { color:red; }
    </style>
</head>
<body>
<div class="card">
    <h2>Login Sushi POS</h2>
    {% if error %}
    <p class="error">{{ error }}</p>
    {% endif %}
    <form method="post" action="/login">
        <label>Usuario</label>
        <input type="text" name="username" required>
        <label>Contraseña</label>
        <input type="password" name="password" required>
        <button type="submit">Entrar</button>
    </form>
</div>
</body>
</html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Sushi POS - Menú principal</title>
    <style>
        body { font-family: Arial, sans-serif; margin:0; background:#f5f5f5; }
        header { background:#222; color:white; padding:10px 20px; display:flex; justify-content:space-between; align-items:center; }
        .user { font-size:0.9rem; }
        .container { padding:20px; display:flex; flex-wrap:wrap; gap:20px; justify-content:center; }
        .card { width:220px; height:130px; background:white; border-radius:12px; box-shadow:0 2px 8px rgba(0,0,0,0.15); display:flex; flex-direction:column; justify-content:center; align-items:center; text-align:center; text-decoration:none; color:#222; }
        .card:hover { box-shadow:0 4px 14px rgba(0,0,0,0.25); transform:translateY(-2px); }
        .card-title { font-size:1.1rem; font-weight:bold; margin-bottom:6px; }
        .card-desc { font-size:0.85rem; color:#555; }
        .tag { font-size:0.7rem; padding:2px 6px; border-radius:8px; background:#eee; margin-top:6px; }
    </style>
</head>
<body>
<header>
    <div><strong>Sushi POS</strong> – Menú principal</div>
    <div class="user">
        Usuario: {{ user.full_name }} ({{ user.username }}) |
        <a href="/logout" style="color:#fff;">Salir</a>
    </div>
</header>

<div class="container">
    <a class="card" href="/pos">
        <div class="card-title">Nuevo pedido</div>
        <div class="card-desc">Tomar pedido de comedor, para llevar o delivery.</div>
        <div class="tag">Módulo POS</div>
    </a>
    <a class="card" href="/orders/list">
        <div class="card-title">Pedidos recientes</div>
        <div class="card-desc">Ver últimos pedidos capturados.</div>
        <div class="tag">Historial</div>
    </a>
    <a class="card" href="/inventario">
        <div class="card-title">Inventario</div>
        <div class="card-desc">Ver ingredientes y faltantes.</div>
        <div class="tag">Módulo inventario</div>
    </a>
    <a class="card" href="/ingredientes">
        <div class="card-title">Ingredientes</div>
        <div class="card-desc">Crear/editar ingredientes por categoría.</div>
        <div class="tag">Nuevo</div>
    </a>
    <a class="card" href="/bot/panel">
        <div class="card-title">Bot & Automatización</div>
        <div class="card-desc">Texto para WhatsApp y automatización futura.</div>
        <div class="tag">Bot</div>
    </a>
    <a class="card" href="/caja/cierre">
        <div class="card-title">Cierre de caja</div>
        <div class="card-desc">Registrar efectivo y diferencia.</div>
        <div class="tag">Caja</div>
    </a>
    <a class="card" href="/reportes">
        <div class="card-title">Reportes (demo)</div>
        <div class="card-desc">Ventas totales simples.</div>
        <div class="tag">Reportes</div>
    </a>
</div>
</body>
</html>
"""
ORDERS_LIST_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Pedidos Recientes</title>
    <style>
        body { font-family: Arial; background:#f5f5f5; padding:20px; }
        h1 { text-align:center; }
        table { width:100%; border-collapse:collapse; margin-top:20px; background:white; }
        th, td { padding:12px; border:1px solid #ccc; text-align:left; }
        th { background:#333; color:white; }
        tr:nth-child(even) { background:#f2f2f2; }
        a.btn { 
            padding:8px 12px; 
            background:#008CBA; 
            color:white; 
            text-decoration:none; 
            border-radius:5px; 
        }
        a.btn:hover { background:#006f98; }
    </style>
</head>
<body>

<h1>Pedidos Recientes</h1>

<table>
    <tr>
        <th>ID</th>
        <th>Tipo</th>
        <th>Mesa</th>
        <th>Cliente</th>
        <th>Plataforma</th>
        <th>Total</th>
        <th>Estado</th>
        <th>Acciones</th>
    </tr>

    {% for order in orders %}
    <tr>
        <td>{{ order.id }}</td>
        <td>{{ order.order_type }}</td>

        <td>
            {% if order.order_type == "COMEDOR" %}
                {{ order.table_number or "-" }}
            {% else %}-{% endif %}
        </td>

        <td>
            {% if order.order_type == "PARA LLEVAR" %}
                {{ order.customer_name or "-" }}
            {% else %}-{% endif %}
        </td>

        <td>
            {% if order.order_type == "PLATAFORMA" %}
                {{ order.delivery_platform or "-" }}
            {% else %}-{% endif %}
        </td>

        <td>${{ "%.2f"|format(order.total) }}</td>

        <td>
            {% if order.is_paid %}
                ✔ Pagado
            {% else %}
                ❌ Pendiente
            {% endif %}
        </td>

        <td>
            <a class="btn" href="/orders/{{ order.id }}">Ver</a>
            {% if not order.is_paid %}
            <a class="btn" href="/orders/{{ order.id }}/pay">Pagar</a>
            {% endif %}
        </td>
    </tr>
    {% endfor %}

</table>

<p style="text-align:center;">
    <a class="btn" href="/menu">Volver</a>
</p>

</body>
</html>
"""


ORDER_DETAIL_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Detalle del Pedido</title>
</head>
<body>

<h1>Pedido #{{ order.id }}</h1>

<p><b>Tipo:</b> {{ order.order_type }}</p>

{% if order.order_type == "COMEDOR" %}
<p><b>Mesa:</b> {{ order.table_number }}</p>
{% endif %}

{% if order.order_type == "LLEVAR" %}
<p><b>Cliente:</b> {{ order.customer_name }}</p>
{% endif %}

{% if order.order_type == "APP" %}
<p><b>Plataforma:</b> {{ order.delivery_platform }}</p>
{% endif %}

<h3>Productos:</h3>
<ul>
{% for item in items %}
    <li>{{ item.quantity }} x {{ item.product.name }} – ${{ "%.2f"|format(item.unit_price) }}</li>
{% endfor %}
</ul>

<h3>Total: ${{ "%.2f"|format(total) }}</h3>

{% if not order.is_paid %}
<p><a href="/orders/{{ order.id }}/pay">Pagar ahora</a></p>
{% else %}
<p style="color:green;"><b>✔ YA PAGADO</b></p>
{% endif %}

<p><a href="/orders/list">Volver</a></p>

</body>
</html>

<a class="btn btn-ghost" href="/orders/{{ order.id }}/tickets">🧾 Tickets / Imprimir</a>

"""



ORDER_PAY_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Pagar Pedido</title>
</head>
<body>

<h1>Pagar Pedido #{{ order.id }}</h1>

<h3>Total: ${{ "%.2f"|format(total) }}</h3>

<form method="post">
    <label>Método de pago:</label><br><br>

    <input type="radio" name="payment_method" value="EFECTIVO" required> Efectivo<br>
    <input type="radio" name="payment_method" value="TRANSFERENCIA"> Transferencia<br>
    <input type="radio" name="payment_method" value="TARJETA"> Tarjeta<br><br>

    <button type="submit">Confirmar Pago</button>
</form>

<p><a href="/orders/{{ order.id }}">Cancelar</a></p>

</body>
</html>
"""



POS_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Sushi POS – Nuevo pedido</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: #f3f4f6;
            color: #111827;
        }
        a { text-decoration: none; color: inherit; }

        .page {
            display: flex;
            min-height: 100vh;
        }

        /* Sidebar */
        .sidebar {
            width: 240px;
            background: #111827;
            color: #f9fafb;
            padding: 20px 16px;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }
        .sidebar h1 {
            font-size: 20px;
            font-weight: 700;
            margin-bottom: 8px;
        }
        .sidebar small {
            color: #9ca3af;
        }
        .sidebar-section-title {
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: .08em;
            color: #9ca3af;
            margin-top: 12px;
            margin-bottom: 4px;
        }
        .cat-list {
            display: flex;
            flex-direction: column;
            gap: 6px;
        }
        .cat-btn {
            padding: 8px 10px;
            border-radius: 8px;
            border: none;
            background: transparent;
            color: #e5e7eb;
            text-align: left;
            font-size: 14px;
            cursor: pointer;
        }
        .cat-btn:hover {
            background: #1f2937;
        }
        .cat-btn.active {
            background: #f97316;
            color: #111827;
            font-weight: 600;
        }

        .sidebar-footer {
            margin-top: auto;
            font-size: 12px;
            color: #6b7280;
        }

        /* Main content */
        .content {
            flex: 1;
            padding: 20px 24px 32px;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        .content-er {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .content-header h2 {
            font-size: 22px;
        }
        .pill {
            display:inline-flex;
            align-items:center;
            justify-content:center;
            padding: 4px 10px;
            border-radius: 999px;
            font-size: 12px;
            background: #e5e7eb;
            color: #4b5563;
            margin-left:4px;
        }

        .layout-main {
            display: grid;
            grid-template-columns: minmax(0, 2fr) minmax(280px, 1fr);
            gap: 20px;
            align-items: flex-start;
        }

        .card {
            background: white;
            border-radius: 12px;
            padding: 16px 18px;
            box-shadow: 0 10px 25px rgba(0,0,0,.04);
        }
        .card h3 {
            font-size: 16px;
            margin-bottom: 10px;
        }

        /* Category sections & products */
        .category-section {
            display: none; /* se muestra via JS */
        }
        .category-title {
            font-size: 15px;
            font-weight: 600;
            margin-bottom: 10px;
        }
        .product-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
            gap: 12px;
        }
        .product-card {
            border-radius: 10px;
            border: 1px solid #e5e7eb;
            padding: 10px 10px 12px;
            background: #f9fafb;
        }
        .product-header {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            margin-bottom: 6px;
        }
        .product-name {
            font-weight: 600;
            font-size: 14px;
        }
        .product-price {
            font-weight: 600;
            color: #16a34a;
            font-size: 14px;
        }
        .product-body {
            display: grid;
            grid-template-columns: 70px 1fr;
            column-gap: 8px;
            row-gap: 6px;
            align-items: center;
            font-size: 12px;
        }
        .product-body label {
            font-size: 12px;
            color: #6b7280;
        }
        .product-body input[type="number"],
        .product-body select,
        .product-body input[type="text"] {
            width: 100%;
            padding: 4px 6px;
            border-radius: 6px;
            border: 1px solid #d1d5db;
            font-size: 12px;
        }
        .product-body input[type="text"] {
            grid-column: 1 / span 2;
        }
        .product-footer {
            margin-top: 8px;
            text-align: right;
        }
        .btn-add-to-cart {
            padding: 5px 10px;
            border-radius: 999px;
            border: none;
            cursor: pointer;
            background: #0ea5e9;
            color: #0f172a;
            font-weight: 600;
            font-size: 12px;
        }
        .btn-add-to-cart:hover {
            background: #0284c7;
        }

        .summary-section h4 {
            font-size: 14px;
            margin-bottom: 4px;
        }
        .summary-section pre {
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
            font-size: 12px;
            background: #0f172a;
            color: #e5e7eb;
            padding: 8px;
            border-radius: 8px;
            white-space: pre-wrap;
        }
        .summary-section ul {
            margin-left: 16px;
            font-size: 13px;
        }
        .summary-section li {
            margin-bottom: 2px;
        }

        .footer-actions {
            display: flex;
            justify-content: flex-end;
            margin-top: 12px;
        }
        .btn-primary {
            padding: 8px 16px;
            border-radius: 999px;
            border: none;
            cursor: pointer;
            background: #f97316;
            color: #111827;
            font-weight: 600;
            font-size: 14px;
        }
        .btn-primary:hover {
            background: #ea580c;
        }

        .btn-link {
            padding: 4px 10px;
            border-radius:999px;
            background:#f97316;
            color:#111827;
            font-size:12px;
            font-weight:600;
            margin-left:6px;
            text-decoration:none;
        }
        .btn-link:hover {
            background:#ea580c;
        }

        @media (max-width: 960px) {
            .page {
                flex-direction: column;
            }
            .sidebar {
                width: 100%;
                flex-direction: row;
                overflow-x: auto;
            }
            .sidebar h1, .sidebar small, .sidebar-footer {
                display: none;
            }
            .layout-main {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
<div class="page">
    <!-- Sidebar de categorías -->
    <aside class="sidebar">
        <div>
            <h1>Vaki Sushi POS</h1>
            <small>Nuevo pedido</small>

            <div class="sidebar-section-title">Categorías</div>
            <div class="cat-list">
                {% for cat in categories %}
                <button type="button"
                        class="cat-btn{% if loop.first %} active{% endif %}"
                        data-cat-button="{{ cat.name }}">
                    {{ cat.name }}
                </button>
                {% endfor %}
            </div>
        </div>

        <div class="sidebar-footer">
            Usuario actual: {{ user.full_name }}<br>
            {{ now }}
        </div>
    </aside>

    <!-- Contenido principal -->
    <main class="content">
        <div class="content-header">
            <div>
                <h2>Nuevo pedido</h2>
                <div class="pill">Selecciona productos y agrégalos a la comanda.</div>
            </div>
            <div>
                <a href="/menu" class="pill">← Menú principal</a>
                <a href="/ingredientes" class="pill">Ingredientes</a>
            </div>
        </div>

        {% if alert_message %}
        <div style="background:#fef3c7;border:1px solid #fbbf24;color:#92400e;padding:8px 10px;border-radius:8px;font-size:13px;margin-bottom:10px;">
            {{ alert_message }}
        </div>
        {% endif %}

        <form method="post" action="/orders/create">

            <!-- NUEVO: datos generales del pedido -->
            <div class="card" style="margin-bottom:16px;">
                <h3>Datos del pedido</h3>
                <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin-top:8px;font-size:13px;">
                    <div>
                        <label>Tipo de pedido</label>
                        <select name="order_type">
                            <option value="COMEDOR">Comedor (mesa)</option>
                            <option value="LLEVAR">Para llevar</option>
                            <option value="APP">Plataforma / App</option>
                        </select>
                    </div>
                    <div>
                        <label>Referencia</label>
                        <input type="text"
                               name="reference"
                               placeholder="Mesa 4, Kevin, 662..., etc.">
                    </div>
                    <div>
                        <label>Plataforma (si aplica)</label>
                        <select name="delivery_platform">
                            <option value="">Sin plataforma</option>
                            <option value="RAPPI">Rappi</option>
                            <option value="DIDI">DiDi</option>
                            <option value="UBER">Uber Eats</option>
                            <option value="OTRA">Otra</option>
                        </select>
                    </div>
                </div>
            </div>

            <div class="layout-main">
                <!-- Productos -->
                <section class="card">
                    {% for cat in categories %}
                    <div class="category-section"
                         data-cat-section="{{ cat.name }}"
                         {% if loop.first %}style="display:block"{% endif %}>
                        <div class="category-title">
                            {{ cat.name }}
                            {% if cat.name == 'Sushis' %}
                                <a class="btn-link" href="/productos/nuevo?category=Sushis">+ Agregar sushi</a>
                            {% elif cat.name == 'Bebidas' %}
                                <a class="btn-link" href="/productos/nuevo?category=Bebidas">+ Agregar bebida</a>
                            {% elif cat.name == 'Entradas' %}
                                <a class="btn-link" href="/productos/nuevo?category=Entradas">+ Agregar entrada</a>
                            {% elif cat.name == 'Platillos' %}
                                <a class="btn-link" href="/productos/nuevo?category=Platillos">+ Agregar platillo</a>
                            {% elif cat.name == 'Postres' %}
                                <a class="btn-link" href="/productos/nuevo?category=Postres">+ Agregar postre</a>
                            {% endif %}
                        </div>
                        <div class="product-grid">
                            {% for p in cat.products %}
                            <div class="product-card"
                                 data-product-id="{{ p.id }}"
                                 data-product-name="{{ p.name }}"
                                 data-product-price="{{ '%.2f'|format(p.price) }}">
                                <div class="product-header">
                                    <span class="product-name">{{ p.name }}</span>
                                    <span class="product-price">${{ '%.2f'|format(p.price) }}</span>
                                </div>
                                <div class="product-body">
                                    <label for="qty_{{ p.id }}">Cant.</label>
                                    <input type="number"
                                           id="qty_{{ p.id }}"
                                           name="qty_{{ p.id }}"
                                           min="0" step="1" value="0">

                                    {% if cat.name|lower == 'sushis' %}
                                        <label for="alga_{{ p.id }}">Alga</label>
                                        <select id="alga_{{ p.id }}" name="alga_{{ p.id }}">
                                            <option value="N/A">Alga (N/A)</option>
                                            <option value="con alga">Con alga</option>
                                            <option value="sin alga">Sin alga</option>
                                        </select>

                                        <label for="emp_{{ p.id }}">Empanizado</label>
                                        <select id="emp_{{ p.id }}" name="emp_{{ p.id }}">
                                            <option value="N/A">Empanizado (N/A)</option>
                                            <option value="empanizado">Empanizado</option>
                                            <option value="natural">Natural</option>
                                        </select>

                                        <input type="text"
                                               name="nota_{{ p.id }}"
                                               placeholder="Notas (sin pepino, poco picante, etc.)">

                                    {% elif cat.name|lower == 'bebidas' %}
                                        <!-- Bebidas: sin notas ni alga/empanizado -->
                                        <input type="hidden" name="alga_{{ p.id }}" value="N/A">
                                        <input type="hidden" name="emp_{{ p.id }}" value="N/A">
                                        <label></label><div></div>
                                        <label></label><div></div>

                                    {% else %}
                                        <!-- Entradas / Platillos / Postres: solo notas -->
                                        <input type="hidden" name="alga_{{ p.id }}" value="N/A">
                                        <input type="hidden" name="emp_{{ p.id }}" value="N/A">
                                        <label></label><div></div>
                                        <label></label><div></div>

                                        <input type="text"
                                               name="nota_{{ p.id }}"
                                               placeholder="Notas (sin pepino, poco picante, etc.)">
                                    {% endif %}
                                </div>
                                <div class="product-footer">
                                    <button type="button" class="btn-add-to-cart">Agregar a comanda</button>
                                </div>
                            </div>
                            {% endfor %}
                        </div>
                    </div>
                    {% endfor %}
                </section>

                <!-- Comanda actual / cocina / inventario -->
                <aside class="card summary-section">
                    <h3>Comanda actual</h3>
                    <p style="font-size:13px; color:#6b7280; margin-bottom:8px;">
                        Agrega productos desde la izquierda. Aquí se muestra lo que se enviará a cocina.
                    </p>

                    <div id="cart-box">
                        <p id="cart-empty" style="font-size:13px; color:#9ca3af;">
                            No hay productos en la comanda actual.
                        </p>
                        <ul id="cart-list" style="max-height:160px; overflow-y:auto; margin-left:16px; font-size:13px;"></ul>
                        <p style="font-size:13px; margin-top:6px;">
                            Total estimado: <strong id="cart-total">$0.00</strong>
                        </p>
                    </div>

                    {% if kitchen %}
                        <h3 style="margin-top:14px;">Último pedido (cocina)</h3>
                        <pre>{{ kitchen }}</pre>
                    {% else %}
                        <h3 style="margin-top:14px;">Último pedido</h3>
                        <p style="font-size:13px;color:#6b7280;">Aquí aparecerá la última venta generada.</p>
                    {% endif %}

                    <h3 style="margin-top:14px;">Ingredientes con inventario bajo</h3>
                    {% if low_inventory %}
                        <ul>
                        {% for item in low_inventory %}
                            <li>{{ item.ingredient.name }} ({{ item.stock }} {{ item.ingredient.unit }})</li>
                        {% endfor %}
                        </ul>
                    {% else %}
                        <p>Todo bien por ahora.</p>
                    {% endif %}
                </aside>
            </div>

            <!-- carrito serializado -->
            <input type="hidden" name="cart_json" id="cart_json">

            <div class="footer-actions">
                <button type="button" id="btn-create-order" class="btn-primary">Crear pedido</button>
            </div>
        </form>
    </main>
</div>

<script>
    // ----- Cambiar de categoría -----
    const catButtons = document.querySelectorAll('[data-cat-button]');
    const catSections = document.querySelectorAll('[data-cat-section]');

    function showCategory(catName) {
        catSections.forEach(sec => {
            sec.style.display = (sec.dataset.catSection === catName) ? 'block' : 'none';
        });
    }

    catButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const cat = btn.dataset.catButton;
            catButtons.forEach(b => b.classList.toggle('active', b === btn));
            showCategory(cat);
        });
    });

    if (catButtons.length) {
        const active = document.querySelector('.cat-btn.active') || catButtons[0];
        active.click();
    }

    // ----- Carrito / comanda actual -----
    const cart = [];

    function updateCartUI() {
        const list = document.getElementById('cart-list');
        const emptyMsg = document.getElementById('cart-empty');
        const totalSpan = document.getElementById('cart-total');

        list.innerHTML = '';

        if (!cart.length) {
            emptyMsg.style.display = 'block';
            totalSpan.textContent = '$0.00';
            return;
        }

        emptyMsg.style.display = 'none';

        let total = 0;

        cart.forEach(item => {
            const li = document.createElement('li');
            let line = item.qty + ' x ' + item.name + ' - $' + (item.price * item.qty).toFixed(2);

            const extras = [];
            if (item.alga && item.alga !== 'N/A') extras.push(item.alga);
            if (item.emp && item.emp !== 'N/A') extras.push(item.emp);
            if (item.nota) extras.push(item.nota);

            if (extras.length) {
                line += ' (' + extras.join(' / ') + ')';
            }

            li.textContent = line;
            list.appendChild(li);

            total += item.price * item.qty;
        });

        totalSpan.textContent = '$' + total.toFixed(2);
    }

    document.querySelectorAll('.btn-add-to-cart').forEach(btn => {
        btn.addEventListener('click', () => {
            const card = btn.closest('.product-card');
            const productId = parseInt(card.dataset.productId, 10);
            const name = card.dataset.productName;
            const price = parseFloat(card.dataset.productPrice);

            const qtyInput = card.querySelector('input[id^="qty_"]');
            const qty = parseInt(qtyInput.value || '0', 10);

            if (!qty || qty <= 0) {
                alert('Indica una cantidad mayor a 0.');
                return;
            }

            const algaSel = card.querySelector('select[id^="alga_"]');
            const empSel = card.querySelector('select[id^="emp_"]');
            const notaInput = card.querySelector('input[name^="nota_"]');

            const alga = algaSel ? algaSel.value : 'N/A';
            const emp = empSel ? empSel.value : 'N/A';
            const nota = notaInput ? notaInput.value.trim() : '';

            cart.push({
                product_id: productId,
                name: name,
                price: price,
                qty: qty,
                alga: alga,
                emp: emp,
                nota: nota
            });

            updateCartUI();

            // reset rápidos
            qtyInput.value = 0;
            if (notaInput) notaInput.value = '';
        });
    });

    const btnCreate = document.getElementById('btn-create-order');
    if (btnCreate) {
        btnCreate.addEventListener('click', () => {
            if (!cart.length) {
                alert('No hay productos en la comanda.');
                return;
            }
            const hidden = document.getElementById('cart_json');
            hidden.value = JSON.stringify(cart);
            btnCreate.closest('form').submit();
        });
    }
</script>
</body>
</html>
"""

# ---------------------- NUEVO PRODUCTO ---------------------


PRODUCT_NEW_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Nuevo producto</title>
    <style>
        body { font-family: Arial, sans-serif; margin:0; background:#f5f5f5; }
        header { background:#111827; color:white; padding:10px 20px; display:flex; justify-content:space-between; align-items:center; }
        a { color:#e5e7eb; text-decoration:none; }
        .container { max-width:800px; margin:20px auto; padding:16px; }
        .card { background:white; padding:16px; border-radius:10px; box-shadow:0 2px 8px rgba(0,0,0,0.1); }
        label { display:block; margin:8px 0 4px; font-size:14px; }
        input[type=text], input[type=number], select {
            width:100%; padding:6px 8px; box-sizing:border-box; border-radius:6px; border:1px solid #d1d5db;
        }
        button {
            margin-top:12px; padding:8px 14px; border-radius:999px; border:none;
            background:#f97316; color:#111827; font-weight:600; cursor:pointer;
        }
        button:hover { background:#ea580c; }
        table { width:100%; border-collapse:collapse; margin-top:12px; }
        th, td { padding:4px 6px; font-size:13px; }
        th { text-align:left; background:#f3f4f6; }
        .small { font-size:12px; color:#6b7280; }
    </style>
</head>
<body>
<header>
    <div><strong>Sushi POS</strong> – Nuevo producto ({{ category.name }})</div>
    <div>
        <a href="/pos">POS</a> |
        <a href="/menu">Menú principal</a>
    </div>
</header>

<div class="container">
    <div class="card">
        <h2>Crear producto en categoría {{ category.name }}</h2>
        <form method="post" action="/productos/nuevo">
            <input type="hidden" name="category_id" value="{{ category.id }}">

            <label>Nombre del producto</label>
            <input type="text" name="name" required>

            <label>Precio</label>
            <input type="number" name="price" step="0.01" min="0" required>

            <p class="small">
                Ahora define qué ingredientes usa este producto y cuánto de cada uno por unidad.
                Estos ingredientes se descontarán automáticamente del inventario cada vez que vendas este producto.
            </p>

            <table>
                <tr>
                    <th>Usar</th>
                    <th>Ingrediente</th>
                    <th>Cantidad por unidad</th>
                </tr>
                {% for ing in ingredients %}
                <tr>
                    <td><input type="checkbox" name="ing_ids" value="{{ ing.id }}"></td>
                    <td>{{ ing.name }} ({{ ing.unit }})</td>
                    <td><input type="number" step="0.01" min="0" name="qty_{{ ing.id }}" value="0"></td>
                </tr>
                {% endfor %}
            </table>

            <button type="submit">Crear producto</button>
        </form>
    </div>
</div>
</body>
</html>
"""

TICKETS_PAGE_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Tickets pedido #{{ order.id }}</title>
  <style>
    body { font-family: system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; margin:0; background:#f3f4f6; color:#111827; }
    header { background:#111827; color:#f9fafb; padding:12px 20px; display:flex; justify-content:space-between; align-items:center; }
    header a { color:#e5e7eb; text-decoration:none; margin-left:12px; font-size:13px; }
    .page { padding:18px 20px; max-width:1100px; margin:0 auto; }
    .card { background:#fff; border-radius:14px; padding:16px 18px; box-shadow:0 10px 25px rgba(0,0,0,.05); margin-bottom:16px; }
    .row { display:flex; gap:10px; flex-wrap:wrap; align-items:center; justify-content:space-between; }
    .btn { display:inline-flex; align-items:center; justify-content:center; padding:10px 16px; border-radius:999px; border:0; cursor:pointer; font-weight:800; font-size:13px; }
    .btn-green { background:#16a34a; color:#fff; }
    .btn-green:hover { background:#15803d; }
    .btn-blue { background:#0ea5e9; color:#0f172a; }
    .btn-blue:hover { background:#0284c7; }
    .btn-gray { background:#e5e7eb; color:#111827; }
    .btn-gray:hover { background:#d1d5db; }
    pre { background:#0f172a; color:#e5e7eb; padding:12px; border-radius:12px; overflow:auto; white-space:pre-wrap; }
    .msg { padding:10px 12px; border-radius:12px; margin-bottom:12px; font-weight:700; }
    .ok { background:#dcfce7; color:#166534; }
    .bad { background:#fee2e2; color:#991b1b; }
  </style>
</head>
<body>
<header>
  <div><b>Vaki Sushi POS</b> – Tickets pedido #{{ order.id }}</div>
  <div>
    <a href="/menu">Menú</a>
    <a href="/orders/list">Pedidos</a>
    <a href="/pos">Nuevo pedido</a>
  </div>
</header>

<div class="page">

  {% if message %}
    <div class="msg {{ 'ok' if success else 'bad' }}">{{ message }}</div>
  {% endif %}

  <div class="card">
    <div class="row">
      <div>
        <div style="font-size:18px;font-weight:900;">Impresión rápida</div>
        <div style="color:#6b7280;font-size:13px;">Imprime en: <b>{{ printer }}</b></div>
      </div>
      <div style="display:flex; gap:10px; flex-wrap:wrap;">
        <a class="btn btn-gray" href="/orders/{{ order.id }}">← Volver al pedido</a>
        <a class="btn btn-blue" href="/print/cliente/{{ order.id }}">Imprimir Cliente</a>
        <a class="btn btn-green" href="/print/cocina/{{ order.id }}">Imprimir Cocina</a>
      </div>
    </div>
  </div>

  <div class="card">
    <h3 style="margin:0 0 10px 0;">Ticket Cliente</h3>
    <pre>{{ ticket_text }}</pre>
  </div>

  <div class="card">
    <h3 style="margin:0 0 10px 0;">Comanda Cocina</h3>
    <pre>{{ kitchen_text }}</pre>
  </div>

</div>
</body>
</html>
"""

# ---------------------- GESTIÓN DE INGREDIENTES ------------

INGREDIENT_LIST_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Ingredientes</title>
    <style>
        body { font-family: Arial, sans-serif; margin:0; background:#f5f5f5; }
        header { background:#111827; color:white; padding:10px 20px; display:flex; justify-content:space-between; align-items:center; }
        a { color:#e5e7eb; text-decoration:none; }
        .container { max-width:900px; margin:20px auto; padding:16px; }
        .card { background:white; padding:16px; border-radius:10px; box-shadow:0 2px 8px rgba(0,0,0,0.1); }
        table { width:100%; border-collapse:collapse; margin-top:10px; font-size:14px; }
        th, td { border-bottom:1px solid #e5e7eb; padding:6px 8px; text-align:left; }
        th { background:#f3f4f6; }
        .top-row { display:flex; justify-content:space-between; align-items:center; }
        .btn { display:inline-block; padding:6px 12px; border-radius:999px; background:#f97316; color:#111827; font-weight:600; text-decoration:none; font-size:13px; }
        .btn:hover { background:#ea580c; }
        .small-link { color:#111827; text-decoration:none; font-size:13px; }
    </style>
</head>
<body>
<header>
    <div><strong>Sushi POS</strong> – Ingredientes</div>
    <div>
        <a href="/pos">POS</a> |
        <a href="/menu">Menú principal</a> |
        <a href="/logout">Salir</a>
    </div>
</header>

<div class="container">
    <div class="card">
        <div class="top-row">
            <h2>Ingredientes</h2>
            <a class="btn" href="/ingredientes/nuevo">+ Agregar ingrediente</a>
        </div>
        <p style="font-size:13px;color:#6b7280;">
            Aquí controlas qué categorías usan cada ingrediente. El stock sigue siendo único por ingrediente.
        </p>
        <table>
            <tr>
                <th>Ingrediente</th>
                <th>Unidad</th>
                <th>Categorías donde se usa</th>
                <th></th>
            </tr>
            {% for ing in ingredients %}
            <tr>
                <td>{{ ing.name }}</td>
                <td>{{ ing.unit }}</td>
                <td>
                    {% set cats = ing_cats.get(ing.id, []) %}
                    {% if cats %}
                        {{ ", ".join(cats) }}
                    {% else %}
                        <span style="color:#9ca3af;">(ninguna categoría)</span>
                    {% endif %}
                </td>
                <td><a class="small-link" href="/ingredientes/editar/{{ ing.id }}">Editar</a></td>
            </tr>
            {% endfor %}
        </table>
    </div>
</div>
</body>
</html>
"""

INGREDIENT_FORM_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>{{ 'Editar ingrediente' if ingredient else 'Nuevo ingrediente' }}</title>
    <style>
        body { font-family: Arial, sans-serif; margin:0; background:#f5f5f5; }
        header { background:#111827; color:white; padding:10px 20px; display:flex; justify-content:space-between; align-items:center; }
        a { color:#e5e7eb; text-decoration:none; }
        .container { max-width:600px; margin:20px auto; padding:16px; }
        .card { background:white; padding:16px; border-radius:10px; box-shadow:0 2px 8px rgba(0,0,0,0.1); }
        label { display:block; margin:8px 0 4px; font-size:14px; }
        input[type=text] { width:100%; padding:6px 8px; box-sizing:border-box; border-radius:6px; border:1px solid #d1d5db; }
        .cats { display:flex; flex-wrap:wrap; gap:8px; margin-top:6px; }
        .chk { font-size:13px; background:#f9fafb; border-radius:999px; padding:4px 10px; border:1px solid #e5e7eb; }
        button {
            margin-top:12px; padding:8px 14px; border-radius:999px; border:none;
            background:#f97316; color:#111827; font-weight:600; cursor:pointer;
        }
        button:hover { background:#ea580c; }
        .help { font-size:12px; color:#6b7280; margin-top:6px; }
    </style>
</head>
<body>
<header>
    <div><strong>Sushi POS</strong> – {{ 'Editar ingrediente' if ingredient else 'Nuevo ingrediente' }}</div>
    <div>
        <a href="/ingredientes">Ingredientes</a> |
        <a href="/pos">POS</a> |
        <a href="/menu">Menú principal</a>
    </div>
</header>

<div class="container">
    <div class="card">
        <h2>{{ 'Editar ingrediente' if ingredient else 'Nuevo ingrediente' }}</h2>
        <form method="post" action="{{ form_action }}">
            <label>Nombre del ingrediente</label>
            <input type="text" name="name" value="{{ ingredient.name if ingredient else '' }}" required>

            <label>Unidad (g, ml, pz, etc.)</label>
            <input type="text" name="unit" value="{{ ingredient.unit if ingredient else '' }}" placeholder="g, ml, pz">

            <label>Usar este ingrediente en las siguientes categorías:</label>
            <div class="cats">
                {% for cat in categories %}
                <label class="chk">
                    <input type="checkbox"
                           name="cat_ids"
                           value="{{ cat.id }}"
                           {% if cat.id in selected_ids %}checked{% endif %}>
                    {{ cat.name }}
                </label>
                {% endfor %}
            </div>
            <p class="help">
                Ejemplo: queso amarillo líquido marcado en “Platillos” y “Postres” se usará tanto en papas fritas
                como en nachos con queso, compartiendo el mismo stock.
            </p>

            <button type="submit">{{ 'Guardar cambios' if ingredient else 'Crear ingrediente' }}</button>
        </form>
    </div>
</div>
</body>
</html>
"""

def calcular_total_ventas(db: Session) -> float:
    total = db.exec(
        select(func.coalesce(func.sum(OrderItem.quantity * OrderItem.unit_price), 0))
    ).one()
    return float(total or 0)

# ---------------------- RUTAS DE INGREDIENTES ----------------------


@app.get("/ingredientes", response_class=HTMLResponse)
def ingredientes_list(
    request: Request,
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    ingredientes = db.exec(select(Ingredient).order_by(Ingredient.name)).all()
    categorias = db.exec(select(Category)).all()

    # mapa: ingrediente_id -> [nombres_de_categorias]
    ing_cats: Dict[int, List[str]] = {}
    links = db.exec(select(IngredientCategory)).all()
    cats_by_id = {c.id: c for c in categorias}

    for ln in links:
        if ln.ingredient_id not in ing_cats:
            ing_cats[ln.ingredient_id] = []
        cat = cats_by_id.get(ln.category_id)
        if cat:
            ing_cats[ln.ingredient_id].append(cat.name)

    return render_template_string(
        INGREDIENT_LIST_HTML,
        ingredients=ingredientes,
        ing_cats=ing_cats,
    )


@app.get("/ingredientes/nuevo", response_class=HTMLResponse)
def ingredientes_nuevo_get(
    request: Request,
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    categories = db.exec(select(Category).order_by(Category.name)).all()

    return render_template_string(
        INGREDIENT_FORM_HTML,
        ingredient=None,
        categories=categories,
        selected_ids=[],
        form_action="/ingredientes/nuevo",
    )


@app.post("/ingredientes/nuevo", response_class=HTMLResponse)
async def ingredientes_nuevo_post(
    request: Request,
    name: str = Form(...),
    unit: str = Form("pz"),
    cat_ids: Optional[List[int]] = Form(None),
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    if cat_ids is None:
        cat_ids = []

    # crear ingrediente
    ing = Ingredient(name=name, unit=unit)
    db.add(ing)
    db.commit()
    db.refresh(ing)

    # crear inventario base en 0
    inv = IngredientInventory(
        ingredient_id=ing.id,
        stock=0.0,
        min_stock=0.0,
    )
    db.add(inv)

    # vínculos ingrediente–categoría
    for cid in cat_ids:
        link = IngredientCategory(ingredient_id=ing.id, category_id=int(cid))
        db.add(link)

    db.commit()

    return RedirectResponse(url="/ingredientes", status_code=302)


@app.get("/ingredientes/editar/{ing_id}", response_class=HTMLResponse)
def ingredientes_editar_get(
    ing_id: int,
    request: Request,
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    ingredient = db.get(Ingredient, ing_id)
    if not ingredient:
        return HTMLResponse("Ingrediente no encontrado", status_code=404)

    categories = db.exec(select(Category).order_by(Category.name)).all()
    links = db.exec(
        select(IngredientCategory).where(IngredientCategory.ingredient_id == ing_id)
    ).all()
    selected_ids = [ln.category_id for ln in links]

    return render_template_string(
        INGREDIENT_FORM_HTML,
        ingredient=ingredient,
        categories=categories,
        selected_ids=selected_ids,
        form_action=f"/ingredientes/editar/{ing_id}",
    )


@app.post("/ingredientes/editar/{ing_id}", response_class=HTMLResponse)
async def ingredientes_editar_post(
    ing_id: int,
    request: Request,
    name: str = Form(...),
    unit: str = Form("pz"),
    cat_ids: Optional[List[int]] = Form(None),
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    ingredient = db.get(Ingredient, ing_id)
    if not ingredient:
        return HTMLResponse("Ingrediente no encontrado", status_code=404)

    if cat_ids is None:
        cat_ids = []

    # actualizar nombre y unidad
    ingredient.name = name
    ingredient.unit = unit

    # actualizar vínculos con categorías
    existing_links = db.exec(
        select(IngredientCategory).where(IngredientCategory.ingredient_id == ing_id)
    ).all()
    existing_cat_ids = {ln.category_id for ln in existing_links}
    new_cat_ids = {int(cid) for cid in cat_ids}

    # borrar los que ya no están seleccionados
    for ln in existing_links:
        if ln.category_id not in new_cat_ids:
            db.delete(ln)

    # agregar los nuevos
    for cid in new_cat_ids:
        if cid not in existing_cat_ids:
            db.add(IngredientCategory(ingredient_id=ing_id, category_id=cid))

    db.commit()

    return RedirectResponse(url="/ingredientes", status_code=302)


CIERRE_CAJA_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Sushi POS - Cierre de caja</title>
    <style>
        body { font-family: Arial, sans-serif; margin:0; background:#f5f5f5; }
        header { background:#222; color:white; padding:10px 20px; display:flex; justify-content:space-between; align-items:center; }
        .user { font-size:0.9rem; }
        .container { padding:20px; max-width:600px; margin:0 auto; }
        .box { background:white; padding:15px; border-radius:10px; box-shadow:0 2px 8px rgba(0,0,0,0.1); margin-bottom:15px; }
        label { display:block; margin:6px 0; }
        input[type=number] { width:100%; padding:6px; box-sizing:border-box; }
        button { padding:8px 12px; margin-top:8px; cursor:pointer; }
        .ok { color:green; }
        .bad { color:red; }
        .small { font-size:0.85rem; color:#555; }
    </style>
</head>
<body>
<header>
    <div><strong>Sushi POS</strong> – Cierre de caja</div>
    <div class="user">
        Usuario: {{ user.full_name }} ({{ user.username }}) |
        <a href="/menu" style="color:#fff;">Menú principal</a> |
        <a href="/logout" style="color:#fff;">Salir</a>
    </div>
</header>

<div class="container">
    <div class="box">
        <h2>Resumen de ventas</h2>
        <p>Total de ventas acumuladas (todas las órdenes registradas): <strong>${{ "%.2f"|format(total_ventas) }}</strong></p>
        <p class="small">Más adelante se puede separar por día / turno / desde último cierre.</p>
    </div>

    <div class="box">
        <h2>Registrar cierre de caja</h2>
        {% if closed %}
            {% if difference|round(2) == 0 %}
                <p class="ok">✅ Cierre registrado sin diferencia.</p>
            {% elif difference > 0 %}
                <p class="bad">⚠ Sobra dinero: ${{ "%.2f"|format(difference) }}</p>
            {% else %}
                <p class="bad">⚠ Falta dinero: ${{ "%.2f"|format(difference|abs) }}</p>
            {% endif %}
        {% endif %}
        <form method="post" action="/caja/cierre">
            <label>Efectivo contado en caja (dinero físico):</label>
            <input type="number" step="0.01" name="reported_cash" required>
            <button type="submit">Guardar cierre</button>
        </form>
    </div>

    <div class="box">
        <h3>Último cierre registrado</h3>
        {% if last_close %}
            <p>Fecha/hora: {{ last_close.closed_at }}</p>
            <p>Ventas acumuladas en ese momento: ${{ "%.2f"|format(last_close.total_sales) }}</p>
            <p>Efectivo contado: ${{ "%.2f"|format(last_close.reported_cash) }}</p>
            {% if last_close.difference|round(2) == 0 %}
                <p class="ok">Diferencia: $0.00 (cuadró perfecto)</p>
            {% elif last_close.difference > 0 %}
                <p class="bad">Diferencia (sobró): ${{ "%.2f"|format(last_close.difference) }}</p>
            {% else %}
                <p class="bad">Diferencia (faltó): ${{ "%.2f"|format(last_close.difference|abs) }}</p>
            {% endif %}
        {% else %}
            <p>Todavía no hay cierres registrados.</p>
        {% endif %}
    </div>
</div>
</body>
</html>
"""


def render_template_string(template_str: str, **context):
    return HTMLResponse(content=Template(template_str).render(**context))


# ---------------------------------------------------------
# LOGIN / MENÚ
# ---------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def root(request: Request, db: Session = Depends(get_session)):
    user = get_current_user(request, db)
    if user:
        return RedirectResponse(url="/menu", status_code=302)
    return render_template_string(LOGIN_HTML, error=None)


@app.get("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("session_id")
    return response


@app.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_session),
):
    user = db.exec(select(User).where(User.username == username)).first()
    if not user or user.hashed_password != password:
        return render_template_string(LOGIN_HTML, error="Usuario o contraseña incorrectos")
    token = str(uuid.uuid4())
    sessions[token] = user.id
    response = RedirectResponse(url="/menu", status_code=302)
    response.set_cookie("session_id", token, httponly=True)
    return response


@app.get("/menu", response_class=HTMLResponse)
def menu(
    request: Request,
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)
    return render_template_string(DASHBOARD_HTML, user=user)


# ---------------------------------------------------------
# POS / PEDIDOS
# ---------------------------------------------------------


@app.get("/pos", response_class=HTMLResponse)
def pos(
    request: Request,
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    categories = db.exec(select(Category).order_by(Category.name)).all()
    for c in categories:
        c.products

    low_inventory = db.exec(
        select(IngredientInventory).where(IngredientInventory.stock <= IngredientInventory.min_stock)
    ).all()

    return render_template_string(
        POS_HTML,
        user=user,
        categories=categories,
        last_order=None,
        last_total=0.0,
        ticket=None,
        kitchen=None,
        low_inventory=low_inventory,
        alert_message=None,
        now=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )


def build_ticket(order: Order, items: List[OrderItem], total: float, options_by_item: Dict[int, str]) -> str:
    lines = []
    lines.append("------ SUSHI POS ------")
    lines.append(f"Pedido #{order.id}")
    lines.append(f"Tipo: {order.order_type}")
    if order.order_type == "COMEDOR":
        lines.append(f"Mesa: {order.table_number}")
    else:
        if order.customer_name:
            lines.append(f"Cliente: {order.customer_name}")
    if order.delivery_platform:
        lines.append(f"Plataforma: {order.delivery_platform}")
    lines.append("-----------------------")
    for it in items:
        lines.append(f"{it.quantity} x {it.product.name}  ${it.unit_price:.2f}")
        extra = options_by_item.get(it.id)
        if extra:
            lines.append(f"   -> {extra}")
    lines.append("-----------------------")
    lines.append(f"TOTAL: ${total:.2f}")
    lines.append("Gracias por su compra")
    return "\n".join(lines)


def build_kitchen_ticket(order: Order, items: List[OrderItem], options_by_item: Dict[int, str]) -> str:
    lines = []
    lines.append("**** COMANDA COCINA ****")
    lines.append(f"Pedido #{order.id} - {order.order_type}")
    if order.order_type == "COMEDOR":
        lines.append(f"Mesa: {order.table_number}")
    else:
        if order.customer_name:
            lines.append(f"Cliente: {order.customer_name}")
    if order.delivery_platform:
        lines.append(f"Plataforma: {order.delivery_platform}")
    lines.append("------------------------")
    for it in items:
        lines.append(f"{it.quantity} x {it.product.name}")
        extra = options_by_item.get(it.id)
        if extra:
            lines.append(f"   -> {extra}")
    lines.append("------------------------")
    lines.append("FIN COMANDA")
    return "\n".join(lines)



def write_ticket_files(order: Order, ticket: str, kitchen: str):
    tickets_dir = os.path.join(BASE_DIR, "tickets_cliente")
    kitchen_dir = os.path.join(BASE_DIR, "comandas_cocina")
    os.makedirs(tickets_dir, exist_ok=True)
    os.makedirs(kitchen_dir, exist_ok=True)
    with open(os.path.join(tickets_dir, f"ticket_{order.id}.txt"), "w", encoding="utf-8") as f:
        f.write(ticket)
    with open(os.path.join(kitchen_dir, f"comanda_{order.id}.txt"), "w", encoding="utf-8") as f:
        f.write(kitchen)



@app.post("/orders/create", response_class=HTMLResponse)
async def create_order(
    request: Request,
    order_type: str = Form("COMEDOR"),
    reference: str = Form(""),
    delivery_platform: str = Form(""),
    db: Session = Depends(get_session),
):

    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    form = await request.form()
    cart_json = form.get("cart_json", "[]")

    try:
        cart_items = json.loads(cart_json)
    except json.JSONDecodeError:
        cart_items = []

    # cargar categorías e inventario para poder re-renderizar POS si hay errores
    categories = db.exec(select(Category).order_by(Category.name)).all()
    for c in categories:
        c.products
    low_inventory = db.exec(
        select(IngredientInventory).where(IngredientInventory.stock <= IngredientInventory.min_stock)
    ).all()

    if not cart_items:
        return render_template_string(
            POS_HTML,
            user=user,
            categories=categories,
            last_order=None,
            last_total=0.0,
            ticket=None,
            kitchen=None,
            low_inventory=low_inventory,
            alert_message="No agregaste ningún producto a la comanda.",
            now=datetime.now().strftime("%d/%m/%Y %H:%M"),
        )

    # -------- Verificar inventario --------
    shortages: Dict[str, bool] = {}

    for item in cart_items:
        try:
            product_id = int(item.get("product_id"))
            qty = int(item.get("qty", 0))
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue

        product = db.get(Product, product_id)
        if not product:
            continue

        alga_opt = (item.get("alga") or "").lower()
        nota_opt = (item.get("nota") or "").lower()

        skip_alga = (alga_opt == "sin alga")
        skip_pepino = ("sin pepino" in nota_opt)

        receta = db.exec(
            select(RecipeItem).where(RecipeItem.product_id == product.id)
        ).all()

        for r in receta:
            ing = db.get(Ingredient, r.ingredient_id)
            if not ing:
                continue

            name_lower = ing.name.lower()
            if skip_alga and "alga" in name_lower:
                continue
            if skip_pepino and "pepino" in name_lower:
                continue

            consumo = qty * r.quantity_per_unit
            inv = db.exec(
                select(IngredientInventory).where(
                    IngredientInventory.ingredient_id == ing.id
                )
            ).first()
            available = inv.stock if inv else 0
            if consumo > available:
                shortages[ing.name] = True

    if shortages:
        if len(shortages) == 1:
            nombre = list(shortages.keys())[0]
            alert_message = f"⚠ Cuidado: ya no tenemos suficiente {nombre} para este pedido."
        else:
            nombres = ", ".join(shortages.keys())
            alert_message = f"⚠ Cuidado: faltan ingredientes para este pedido: {nombres}."

        return render_template_string(
            POS_HTML,
            user=user,
            categories=categories,
            last_order=None,
            last_total=0.0,
            ticket=None,
            kitchen=None,
            low_inventory=low_inventory,
            alert_message=alert_message,
            now=datetime.now().strftime("%d/%m/%Y %H:%M"),
        )

    # -------- Crear orden y descontar inventario --------
    order = Order(
        order_type=order_type,
        table_number=reference if order_type == "COMEDOR" else None,
        customer_name=reference if order_type != "COMEDOR" else None,
        delivery_platform=delivery_platform or None,
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    items: List[OrderItem] = []
    total = 0.0
    options_by_item: Dict[int, str] = {}

    for item in cart_items:
        try:
            product_id = int(item.get("product_id"))
            qty = int(item.get("qty", 0))
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue

        product = db.get(Product, product_id)
        if not product:
            continue

        alga = (item.get("alga") or "").strip()
        emp = (item.get("emp") or "").strip()
        nota = (item.get("nota") or "").strip()

        extras = []
        if alga and alga != "N/A":
            extras.append(alga)
        if emp and emp != "N/A":
            extras.append(emp)
        if nota:
            extras.append(nota)
        options_text = " / ".join(extras) if extras else ""

        alga_opt = alga.lower()
        nota_opt = nota.lower()
        skip_alga = (alga_opt == "sin alga")
        skip_pepino = ("sin pepino" in nota_opt)

        it = OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=qty,
            unit_price=product.price,
        )
        db.add(it)
        db.flush()  # para obtener it.id

        items.append(it)
        total += qty * product.price

        if options_text:
            options_by_item[it.id] = options_text

        # descontar inventario por receta
        receta = db.exec(
            select(RecipeItem).where(RecipeItem.product_id == product.id)
        ).all()
        for r in receta:
            ing = db.get(Ingredient, r.ingredient_id)
            if not ing:
                continue

            name_lower = ing.name.lower()
            if skip_alga and "alga" in name_lower:
                continue
            if skip_pepino and "pepino" in name_lower:
                continue

            consumo = qty * r.quantity_per_unit
            inv = db.exec(
                select(IngredientInventory).where(
                    IngredientInventory.ingredient_id == ing.id
                )
            ).first()
            if inv:
                inv.stock = max(inv.stock - consumo, 0)

    db.commit()

    # refrescar productos de cada item
    for it in items:
        db.refresh(it)
        db.refresh(it.product)

    ticket = build_ticket(order, items, total, options_by_item)
    kitchen = build_kitchen_ticket(order, items, options_by_item)
    write_ticket_files(order, ticket, kitchen)

    low_inventory = db.exec(
        select(IngredientInventory).where(IngredientInventory.stock <= IngredientInventory.min_stock)
    ).all()

    return render_template_string(
        POS_HTML,
        user=user,
        categories=categories,
        last_order=order,
        last_total=total,
        ticket=ticket,
        kitchen=kitchen,
        low_inventory=low_inventory,
        alert_message=None,
        now=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )



# ---------------------------------------------------------
# CREAR PRODUCTOS (USA RECETAS)
# ---------------------------------------------------------


@app.get("/productos/nuevo", response_class=HTMLResponse)
def productos_nuevo_get(
    request: Request,
    category: str,
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    cat = db.exec(select(Category).where(Category.name == category)).first()
    if not cat:
        return HTMLResponse("Categoría no encontrada", status_code=404)

    # Ingredientes ligados a esta categoría
    links = db.exec(
        select(IngredientCategory).where(IngredientCategory.category_id == cat.id)
    ).all()
    ing_ids = [ln.ingredient_id for ln in links]

    if ing_ids:
        ingredients = db.exec(
            select(Ingredient).where(Ingredient.id.in_(ing_ids)).order_by(Ingredient.name)
        ).all()
    else:
        ingredients = db.exec(select(Ingredient).order_by(Ingredient.name)).all()

    return render_template_string(
        PRODUCT_NEW_HTML,
        category=cat,
        ingredients=ingredients,
    )


@app.post("/productos/nuevo", response_class=HTMLResponse)
async def productos_nuevo_post(
    request: Request,
    category_id: int = Form(...),
    name: str = Form(...),
    price: float = Form(...),
    ing_ids: Optional[List[int]] = Form(None),
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    if ing_ids is None:
        ing_ids = []

    product = Product(
        name=name,
        price=price,
        category_id=category_id,
    )
    db.add(product)
    db.commit()
    db.refresh(product)

    form = await request.form()
    for ing_id in ing_ids:
        qty_str = form.get(f"qty_{ing_id}", "0")
        try:
            qty = float(qty_str)
        except ValueError:
            qty = 0.0
        if qty <= 0:
            continue

        r = RecipeItem(
            product_id=product.id,
            ingredient_id=int(ing_id),
            quantity_per_unit=qty,
        )
        db.add(r)

    db.commit()

    return RedirectResponse(url="/pos", status_code=302)

# RUTAS DE PEDIDOS (LISTA, DETALLE, PAGO)

@app.get("/orders/list", response_class=HTMLResponse)
def orders_list(
    request: Request,
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    orders = db.exec(
        select(Order).order_by(Order.id.desc()).limit(50)
    ).all()

    totals = {}
    for o in orders:
        items = db.exec(
            select(OrderItem).where(OrderItem.order_id == o.id)
        ).all()

        total = 0.0
        for it in items:
            total += float(it.quantity or 0) * float(it.unit_price or 0)

        totals[o.id] = total

    return render_template_string(
        ORDERS_LIST_HTML,
        user=user,
        orders=orders,
        totals=totals,
    )


@app.get("/orders/{order_id}", response_class=HTMLResponse)
def order_detail(
    request: Request,
    order_id: int,
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    order = db.get(Order, order_id)
    if not order:
        return HTMLResponse("Pedido no encontrado", status_code=404)

    items = db.exec(
        select(OrderItem).where(OrderItem.order_id == order.id)
    ).all()

    for it in items:
        db.refresh(it)
        db.refresh(it.product)

    total = sum(it.quantity * it.unit_price for it in items)

    html = Template(ORDER_DETAIL_HTML).render(
        user=user,
        order=order,
        items=items,
        total=total,
    )
    return HTMLResponse(html)


@app.get("/orders/{order_id}/pay", response_class=HTMLResponse)
def order_pay_form(
    request: Request,
    order_id: int,
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    order = db.get(Order, order_id)
    if not order:
        return HTMLResponse("Pedido no encontrado", status_code=404)

    items = db.exec(
        select(OrderItem).where(OrderItem.order_id == order.id)
    ).all()

    for it in items:
        db.refresh(it)
        db.refresh(it.product)

    total = sum(it.quantity * it.unit_price for it in items)

    html = Template(ORDER_PAY_HTML).render(
        user=user,
        order=order,
        items=items,
        total=total,
    )
    return HTMLResponse(html)


@app.post("/orders/{order_id}/pay", response_class=HTMLResponse)
def order_pay(
    request: Request,
    order_id: int,
    payment_method: str = Form(...),
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    order = db.get(Order, order_id)
    if not order:
        return HTMLResponse("Pedido no encontrado", status_code=404)

    # Si ya estaba pagado
    if getattr(order, "is_paid", False):
        return HTMLResponse("Este pedido ya estaba marcado como pagado.")

    # Validamos método de pago
    if payment_method not in ["EFECTIVO", "TRANSFERENCIA", "TARJETA"]:
        return HTMLResponse("Método de pago no válido.", status_code=400)

    order.is_paid = True
    order.payment_method = payment_method
    db.add(order)
    db.commit()
    db.refresh(order)

    return RedirectResponse(url=f"/orders/{order.id}", status_code=302)


# ----------------- INVENTARIO (INGREDIENTES) -----------------

INVENTARIO_HTML = """
<!DOCTYPE html>
<html lang="es">
  <head>
    <meta charset="UTF-8" />
    <title>Inventario</title>
    <style>
      body { font-family: Arial, sans-serif; background: #f4f4f4; margin: 0; padding: 0; }
      .container {
        width: 90%%; max-width: 1100px; background: white; margin: 30px auto;
        padding: 25px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1);
      }
      h1 { margin-top: 0; color: #333; }

      table { width: 100%%; border-collapse: collapse; margin-top: 20px; }
      th, td { padding: 12px; border-bottom: 1px solid #ddd; text-align: left; }

      th { background: #fafafa; color: #444; font-weight: bold; }

      .top-buttons { display: flex; justify-content: flex-end; gap: 12px; margin-bottom: 15px; }

      .btn {
        background: #ff7f27; color: white; padding: 10px 18px; border-radius: 8px;
        text-decoration: none; font-weight: bold; transition: 0.15s; display: inline-block;
      }
      .btn:hover { background: #e86e1f; }

      .btn-gray {
        background: #5a5a5a;
      }
      .btn-gray:hover { background: #444; }

    </style>
  </head>

  <body>
    <div class="container">
      
      <div class="top-buttons">
        <!-- 🔙 NUEVO BOTÓN -->
        <a href="/menu" class="btn btn-gray">Volver al menú principal</a>

        <!-- 🛠 BOTÓN EXISTENTE -->
        <a href="/inventario/editar/login" class="btn">Editar stock</a>
      </div>

      <h1>Inventario de ingredientes</h1>
      <p>Vista general del almacén. Para modificar cantidades usa el botón "Editar stock".</p>

      <table>
        <tr>
          <th>INGREDIENTE</th>
          <th>STOCK</th>
          <th>MÍNIMO</th>
          <th>UNIDAD</th>
        </tr>

        {% for item in items %}
        <tr>
          <td>{{ item.ingredient.name }}</td>
          <td>{{ item.stock }}</td>
          <td>{{ item.min_stock }}</td>
          <td>{{ item.ingredient.unit }}</td>
        </tr>
        {% endfor %}

      </table>

    </div>
  </body>
</html>
"""


INVENTARIO_EDIT_LOGIN_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Editar stock - Autorización</title>
    <style>
        body { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
               margin:0; background:#f3f4f6; display:flex; justify-content:center; align-items:center; height:100vh; }
        .card {
            background:white; padding:20px 22px; border-radius:12px;
            box-shadow:0 15px 35px rgba(0,0,0,.12); width:320px;
        }
        h2 { margin:0 0 8px 0; font-size:18px; }
        p { margin:4px 0 10px 0; font-size:13px; color:#6b7280; }
        label { display:block; margin:6px 0 3px; font-size:13px; }
        input[type=text], input[type=password] {
            width:100%; padding:6px 8px; border-radius:8px; border:1px solid #d1d5db;
            font-size:13px; box-sizing:border-box;
        }
        button {
            margin-top:12px; width:100%; padding:8px 0; border-radius:999px; border:none;
            background:#f97316; color:#111827; font-weight:600; cursor:pointer; font-size:14px;
        }
        button:hover { background:#ea580c; }
        .error { color:#b91c1c; font-size:12px; margin-top:6px; }
        .link-back { font-size:12px; margin-top:10px; text-align:center; }
        .link-back a { color:#4b5563; text-decoration:none; }
    </style>
</head>
<body>
<div class="card">
    <h2>Autorización de stock</h2>
    <p>Solo personal autorizado puede modificar existencias.</p>
    {% if error %}
        <div class="error">{{ error }}</div>
    {% endif %}
    <form method="post" action="/inventario/editar/login">
        <label>Usuario especial</label>
        <input type="text" name="edit_user" placeholder="Usuario" required>

        <label>Contraseña especial</label>
        <input type="password" name="edit_pass" placeholder="Contraseña" required>

        <button type="submit">Continuar</button>
    </form>
    <div class="link-back">
        <a href="/inventario">← Volver a inventario</a>
    </div>
</div>
</body>
</html>
"""

INVENTARIO_EDIT_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Editar stock - Inventario</title>
    <style>
        body { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin:0; background:#f3f4f6; }
        header { background:#111827; color:white; padding:10px 20px; display:flex; justify-content:space-between; align-items:center; }
        a { color:#e5e7eb; text-decoration:none; }
        .user { font-size:0.85rem; }
        .page { padding:20px; max-width:1000px; margin:0 auto; }
        .card {
            background:white; padding:16px 18px; border-radius:12px;
            box-shadow:0 10px 25px rgba(0,0,0,.05);
        }
        h2 { margin:0 0 6px 0; }
        .subtitle { font-size:13px; color:#6b7280; margin-bottom:12px; }
        table { width:100%; border-collapse:collapse; font-size:13px; margin-top:8px; }
        th, td { padding:8px 10px; border-bottom:1px solid #e5e7eb; text-align:left; }
        th { background:#f9fafb; font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:#6b7280; }
        input[type=number], select {
            width:100%; padding:4px 6px; border-radius:6px; border:1px solid #d1d5db;
            font-size:12px; box-sizing:border-box;
        }
        .footer-actions {
            display:flex; justify-content:flex-end; margin-top:12px;
        }
        .btn-primary {
            padding:8px 16px; border-radius:999px; border:none;
            background:#16a34a; color:white; font-weight:600; font-size:14px; cursor:pointer;
        }
        .btn-primary:hover { background:#15803d; }
        .pill-info {
            display:inline-flex; align-items:center; justify-content:center;
            padding:2px 8px; border-radius:999px; font-size:11px;
            background:#dbeafe; color:#1d4ed8; font-weight:600;
        }
        .top-row {
            display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;
        }
        .btn-secondary {
            padding:6px 12px; border-radius:999px; border:none;
            background:#6b7280; color:white; font-size:13px; font-weight:600; cursor:pointer;
            text-decoration:none;
        }
        .btn-secondary:hover { background:#4b5563; }
        .msg { font-size:13px; margin-bottom:8px; }
        .msg-ok { color:#166534; }
        .col-delete { text-align:center; width:70px; }
    </style>
</head>
<body>
<header>
    <div><strong>Sushi POS</strong> – Editar stock</div>
    <div class="user">
        Usuario: {{ user.full_name }} ({{ user.username }}) |
        <a href="/inventario">Inventario</a> |
        <a href="/menu">Menú principal</a>
    </div>
</header>

<div class="page">
    <div class="card">
        <div class="top-row">
            <div>
                <h2>Modificar existencias</h2>
                <div class="subtitle">
                    Ajusta stock, mínimo y unidad. Cambios se guardan para todos los módulos.
                </div>
            </div>
            <div>
                <!-- Botón claro para volver -->
                <a class="btn-secondary" href="/inventario">Volver a inventario</a>
            </div>
        </div>

        {% if saved %}
            <div class="msg msg-ok">✅ Cambios guardados correctamente.</div>
        {% endif %}

        <div class="msg">
            <span class="pill-info">Modo protegido</span>
            Solo accesible con usuario especial de Vaki Sushi.
        </div>

        <form method="post" action="/inventario/editar">
            <table>
                <tr>
                    <th>Ingrediente</th>
                    <th>Stock</th>
                    <th>Mínimo</th>
                    <th>Unidad</th>
                    <th class="col-delete">Borrar</th>
                </tr>
                {% for i in items %}
                <tr>
                    <td>{{ i.ingredient.name }}</td>
                    <td>
                        <input type="number"
                               step="0.01"
                               name="stock_{{ i.id }}"
                               value="{{ i.stock }}">
                    </td>
                    <td>
                        <input type="number"
                               step="0.01"
                               name="min_{{ i.id }}"
                               value="{{ i.min_stock }}">
                    </td>
                    <td>
                        <select name="unit_{{ i.id }}">
                            <option value="gr" {% if i.ingredient.unit == 'gr' %}selected{% endif %}>gr</option>
                            <option value="pz" {% if i.ingredient.unit == 'pz' %}selected{% endif %}>pz</option>
                            <option value="ml" {% if i.ingredient.unit == 'ml' %}selected{% endif %}>ml</option>
                        </select>
                    </td>
                    <td class="col-delete">
                        <input type="checkbox" name="delete_{{ i.id }}">
                    </td>
                </tr>
                {% endfor %}
            </table>

            <div class="footer-actions">
                <button type="submit" class="btn-primary">Guardar cambios</button>
            </div>
        </form>
    </div>
</div>
</body>
</html>
"""

# --------- RUTAS INVENTARIO LIMPIAS (CON BORRAR FUNCIONAL) ---------


@app.get("/inventario", response_class=HTMLResponse)
def inventario(
    request: Request,
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    items = db.exec(select(IngredientInventory).order_by(IngredientInventory.id)).all()
    return render_template_string(INVENTARIO_HTML, items=items, user=user)


@app.get("/inventario/editar/login", response_class=HTMLResponse)
def inventario_editar_login_get(
    request: Request,
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    return render_template_string(
        INVENTARIO_EDIT_LOGIN_HTML,
        error=None,
    )


@app.post("/inventario/editar/login", response_class=HTMLResponse)
def inventario_editar_login_post(
    request: Request,
    edit_user: str = Form(...),
    edit_pass: str = Form(...),
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    # Credenciales especiales que tú definiste
    if edit_user == "vakicen" and edit_pass == "vakiedits":
        response = RedirectResponse(url="/inventario/editar", status_code=302)
        # Cookie simple para saber que ya pasó por el login especial
        response.set_cookie("stock_edit_ok", "1", httponly=True)
        return response

    # Si falla, volvemos a mostrar el login con error
    return render_template_string(
        INVENTARIO_EDIT_LOGIN_HTML,
        error="Usuario o contraseña de stock incorrectos.",
    )


@app.get("/inventario/editar", response_class=HTMLResponse)
def inventario_editar_get(
    request: Request,
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    # verifica cookie de permiso
    if request.cookies.get("stock_edit_ok") != "1":
        return RedirectResponse(url="/inventario/editar/login", status_code=302)

    items = db.exec(select(IngredientInventory).order_by(IngredientInventory.id)).all()
    return render_template_string(INVENTARIO_EDIT_HTML, items=items, user=user, saved=False)


@app.post("/inventario/editar", response_class=HTMLResponse)
async def inventario_editar_post(
    request: Request,
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    # Revisa de nuevo que venga del login especial
    if request.cookies.get("stock_edit_ok") != "1":
        return RedirectResponse(url="/inventario/editar/login", status_code=302)

    form = await request.form()

    items = db.exec(select(IngredientInventory).order_by(IngredientInventory.id)).all()

    for inv in items:
        # ¿Lo marcaron para borrar?
        if form.get(f"delete_{inv.id}"):
            # Borrar recetas que usen este ingrediente
            recetas = db.exec(
                select(RecipeItem).where(RecipeItem.ingredient_id == inv.ingredient_id)
            ).all()
            for r in recetas:
                db.delete(r)

            # Borrar vínculos con categorías
            links = db.exec(
                select(IngredientCategory).where(IngredientCategory.ingredient_id == inv.ingredient_id)
            ).all()
            for ln in links:
                db.delete(ln)

            # Borrar inventario e ingrediente
            ing = inv.ingredient
            db.delete(inv)
            if ing:
                db.delete(ing)
            continue

        # Si no se borró, actualizar stock / mínimo / unidad
        stock_val = form.get(f"stock_{inv.id}", str(inv.stock)).replace(",", ".")
        min_val = form.get(f"min_{inv.id}", str(inv.min_stock)).replace(",", ".")
        unit_val = form.get(f"unit_{inv.id}", inv.ingredient.unit)

        try:
            inv.stock = float(stock_val)
        except ValueError:
            pass

        try:
            inv.min_stock = float(min_val)
        except ValueError:
            pass

        inv.ingredient.unit = unit_val

    db.commit()

    # Volvemos a cargar la lista actualizada para mostrar "guardado ok"
    items = db.exec(select(IngredientInventory).order_by(IngredientInventory.id)).all()
    return render_template_string(INVENTARIO_EDIT_HTML, items=items, user=user, saved=True)

# --- IMPRESION ---
PRINTER_NAME = "XP-58"  # cámbialo si tu Windows lo muestra distinto

def get_ticket_paths(order_id: int):
    tickets_dir = os.path.join(BASE_DIR, "tickets_cliente")
    kitchen_dir = os.path.join(BASE_DIR, "comandas_cocina")
    ticket_path = os.path.join(tickets_dir, f"ticket_{order_id}.txt")
    kitchen_path = os.path.join(kitchen_dir, f"comanda_{order_id}.txt")
    return ticket_path, kitchen_path

def run_print_agent(file_path: str):
    """
    Llama a print_agent.py para imprimir el .txt en la impresora térmica.
    """
    agent_path = os.path.join(BASE_DIR, "print_agent.py")
    if not os.path.exists(agent_path):
        raise RuntimeError(f"No existe print_agent.py en: {agent_path}")

    if not os.path.exists(file_path):
        raise RuntimeError(f"No existe el archivo a imprimir: {file_path}")

    # Ejecuta con el mismo python del venv
    cmd = [sys.executable, agent_path, "--printer", PRINTER_NAME, "--file", file_path]
    p = subprocess.run(cmd, capture_output=True, text=True)

    if p.returncode != 0:
        raise RuntimeError(f"print_agent falló:\nSTDOUT:\n{p.stdout}\nSTDERR:\n{p.stderr}")
    return p.stdout.strip()

@app.get("/orders/{order_id}/tickets", response_class=HTMLResponse)
def tickets_page(
    request: Request,
    order_id: int,
    msg: str = "",
    ok: int = 1,
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    order = db.get(Order, order_id)
    if not order:
        return HTMLResponse("Pedido no encontrado", status_code=404)

    ticket_path, kitchen_path = get_ticket_paths(order_id)

    # Si no existen los .txt aún (pedido viejo), los regeneramos
    items = db.exec(select(OrderItem).where(OrderItem.order_id == order.id)).all()
    for it in items:
        db.refresh(it)
        db.refresh(it.product)

    total = sum(it.quantity * it.unit_price for it in items)
    options_by_item = {}  # aquí podrías reconstruir extras si los guardas en DB; si no, se queda vacío.

    # Generar texto actual (y guardarlo) si falta
    if not os.path.exists(ticket_path) or not os.path.exists(kitchen_path):
        ticket = build_ticket(order, items, total, options_by_item)
        kitchen = build_kitchen_ticket(order, items, options_by_item)
        write_ticket_files(order, ticket, kitchen)

    # Leer para mostrar
    with open(ticket_path, "r", encoding="utf-8") as f:
        ticket_text = f.read()
    with open(kitchen_path, "r", encoding="utf-8") as f:
        kitchen_text = f.read()

    return render_template_string(
        TICKETS_PAGE_HTML,
        user=user,
        order=order,
        ticket_text=ticket_text,
        kitchen_text=kitchen_text,
        printer=PRINTER_NAME,
        message=msg if msg else None,
        success=True if ok == 1 else False,
    )


@app.get("/print/cliente/{order_id}", response_class=HTMLResponse)
def print_cliente(
    request: Request,
    order_id: int,
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    ticket_path, _ = get_ticket_paths(order_id)

    try:
        out = run_print_agent(ticket_path)
        return RedirectResponse(url=f"/orders/{order_id}/tickets?msg=✅+Impreso+cliente+OK&ok=1", status_code=302)
    except Exception as e:
        return RedirectResponse(url=f"/orders/{order_id}/tickets?msg=❌+Error:+{str(e).replace(' ', '+')}&ok=0", status_code=302)


@app.get("/print/cocina/{order_id}", response_class=HTMLResponse)
def print_cocina(
    request: Request,
    order_id: int,
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    _, kitchen_path = get_ticket_paths(order_id)

    try:
        out = run_print_agent(kitchen_path)
        return RedirectResponse(url=f"/orders/{order_id}/tickets?msg=✅+Impreso+cocina+OK&ok=1", status_code=302)
    except Exception as e:
        return RedirectResponse(url=f"/orders/{order_id}/tickets?msg=❌+Error:+{str(e).replace(' ', '+')}&ok=0", status_code=302)

# ---------------------------------------------------------
# BOT / AUTOMATIZACIÓN
# ---------------------------------------------------------


@app.get("/bot/panel", response_class=HTMLResponse)
def bot_panel(
    request: Request,
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    low_inventory = db.exec(
        select(IngredientInventory).where(IngredientInventory.stock <= IngredientInventory.min_stock)
    ).all()

    text_lines = []
    if not low_inventory:
        text_lines.append("Todo en orden, no hay ingredientes por debajo del mínimo.")
    else:
        text_lines.append("⚠ FALTANTES / INGREDIENTES BAJOS:")
        for item in low_inventory:
            text_lines.append(
                f"- {item.ingredient.name}: {item.stock} {item.ingredient.unit} (mínimo {item.min_stock})"
            )

    text_for_whatsapp = "\n".join(text_lines)

    html = "<h2>Bot & Automatización</h2>"
    html += '<a href="/menu">⬅ Volver al menú</a><br><br>'
    html += "<p>Este texto lo puedes copiar y pegar en WhatsApp por ahora. Más adelante se conectará a la API.</p>"
    html += "<textarea style='width:100%;height:200px;'>" + text_for_whatsapp + "</textarea>"
    html += "<p>También está disponible como endpoint para un bot en: <code>/bot/low_stock_text</code></p>"
    return HTMLResponse(html)


@app.get("/bot/low_stock_text", response_class=PlainTextResponse)
def bot_low_stock_text(db: Session = Depends(get_session)):
    low_inventory = db.exec(
        select(IngredientInventory).where(IngredientInventory.stock <= IngredientInventory.min_stock)
    ).all()
    if not low_inventory:
        return "Todo en orden, no hay ingredientes por debajo del mínimo."
    lines = ["FALTANTES / INGREDIENTES BAJOS:"]
    for item in low_inventory:
        lines.append(
            f"- {item.ingredient.name}: {item.stock} {item.ingredient.unit} (mínimo {item.min_stock})"
        )
    return "\n".join(lines)


# ---------------------------------------------------------
# UTILIDAD: TOTAL VENTAS
# ---------------------------------------------------------


def calcular_total_ventas(db: Session) -> float:
    # Solo suma pedidos ya cobrados
    orders = db.exec(select(Order).where(Order.is_paid == True)).all()
    total = 0.0
    for o in orders:
        items = db.exec(select(OrderItem).where(OrderItem.order_id == o.id)).all()
        for it in items:
            total += it.quantity * it.unit_price
    return total


# ---------------------------------------------------------
# REPORTES SIMPLES
# ---------------------------------------------------------


@app.get("/reportes", response_class=HTMLResponse)
def reportes(
    request: Request,
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    total_ventas = calcular_total_ventas(db)

    html = "<h2>Reportes (demo)</h2>"
    html += '<a href="/menu">⬅ Volver al menú</a><br><br>'
    html += f"<p>Total de ventas acumuladas (muy simple): <strong>${total_ventas:.2f}</strong></p>"
    html += "<p>Más adelante se puede hacer por día, por mes, por producto, etc.</p>"
    return HTMLResponse(html)


# ---------------------------------------------------------
# CIERRE DE CAJA
# ---------------------------------------------------------


@app.get("/caja/cierre", response_class=HTMLResponse)
def caja_cierre(
    request: Request,
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    total_ventas = calcular_total_ventas(db)
    last_close = db.exec(select(CashClose).order_by(CashClose.id.desc())).first()

    return render_template_string(
        CIERRE_CAJA_HTML,
        user=user,
        total_ventas=total_ventas,
        last_close=last_close,
        closed=False,
        difference=0.0,
    )


@app.post("/caja/cierre", response_class=HTMLResponse)
def caja_cierre_post(
    request: Request,
    reported_cash: float = Form(...),
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    total_ventas = calcular_total_ventas(db)
    difference = reported_cash - total_ventas

    close = CashClose(
        user_id=user.id,
        total_sales=total_ventas,
        reported_cash=reported_cash,
        difference=difference,
    )
    db.add(close)
    db.commit()
    db.refresh(close)

    return render_template_string(
        CIERRE_CAJA_HTML,
        user=user,
        total_ventas=total_ventas,
        last_close=close,
        closed=True,
        difference=difference,
    )
