from sqlmodel import Session, select
from main import engine, User


def main():
    with Session(engine) as session:
        admin = session.exec(
            select(User).where(User.username == "admin")
        ).first()

        if admin is None:
            admin = User(
                username="admin",
                full_name="Administrador",
                hashed_password="admin",  # texto plano
                is_admin=True,
            )
            session.add(admin)
            print("Usuario admin creado.")
        else:
            admin.hashed_password = "admin"
            admin.is_admin = True
            session.add(admin)
            print("Usuario admin actualizado.")

        session.commit()
        print("LISTO: usuario = admin, contraseña = admin")


if __name__ == "__main__":
    main()
