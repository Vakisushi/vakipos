from sqlmodel import Session, select
from passlib.hash import bcrypt

from main import engine, User


def main():
    with Session(engine) as session:
        admin = session.exec(
            select(User).where(User.username == "admin")
        ).first()

        if admin is None:
            # Si no existe, lo creamos
            admin = User(
                username="admin",
                full_name="Administrador",
                hashed_password=bcrypt.hash("admin"[:72]),
                is_admin=True,
            )
            session.add(admin)
            print("Usuario admin creado.")
        else:
            # Si ya existe, solo le arreglamos la contraseña
            admin.hashed_password = bcrypt.hash("admin"[:72])
            admin.is_admin = True
            session.add(admin)
            print("Usuario admin actualizado.")

        session.commit()
        print("Listo. Usuario = admin, contraseña = admin")


if __name__ == "__main__":
    main()
