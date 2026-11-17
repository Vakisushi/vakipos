from sqlmodel import Session, select
from main import engine, User

def crear_usuario(username, full_name, password, is_admin=False):
    with Session(engine) as session:
        existente = session.exec(
            select(User).where(User.username == username)
        ).first()

        if existente:
            print("❌ El usuario ya existe:", username)
            return

        nuevo = User(
            username=username,
            full_name=full_name,
            hashed_password=password,
            is_admin=is_admin,
        )

        session.add(nuevo)
        session.commit()
        print("✅ Usuario creado con ID:", nuevo.id)


if __name__ == "__main__":
    # Aquí editas los valores
    crear_usuario(
        username="cajero1",
        full_name="Cajero 1",
        password="1234",
        is_admin=False,
    )
