"""Script de inicialización (Bootstrap) para ISC ATS Backend.

Sincroniza el catálogo de permisos RBAC, crea y configura los roles del sistema
(Administrador con todos los permisos, Talento Humano, Comercial, Proyecto, Marketing,
candidate) y asegura la creación del usuario administrador inicial.

Uso:
    python -m scripts.bootstrap --email admin@isc.local --password MiClaveSegura123!
    O con uv:
    uv run python -m scripts.bootstrap --email admin@isc.local --password MiClaveSegura123!
"""

import argparse
import asyncio
import sys

from app.core.database import async_session_factory
from app.modules.auth.application.bootstrap_service import (
    BootstrapError,
    bootstrap_admin,
)


async def run_bootstrap(email: str, password: str) -> None:
    print(f"[*] Iniciando bootstrap del sistema ISC ATS para: {email}")
    try:
        async with async_session_factory() as session:
            result = await bootstrap_admin(session, email, password)
            await session.commit()

            print("\n[+] Bootstrap completado con éxito:")
            print(f"  - Usuario Administrador ID: {result.user_id}")
            print(f"  - Usuario creado nuevo: {'Sí' if result.user_created else 'No (ya existía)'}")
            print(f"  - Permisos sincronizados en catálogo: {result.permissions_synced}")
            print(f"  - Permisos asignados al Administrador: {result.grants}")
            print("  - Roles iniciales asegurados: Administrador, Talento Humano, Comercial, Proyecto, Marketing, candidate")
    except BootstrapError as exc:
        print(f"\n[!] Error de Bootstrap: {exc}", file=sys.stderr)
        print("    Asegúrate de haber corrido primero las migraciones con: alembic upgrade head", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"\n[!] Error inesperado durante el bootstrap: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap ISC ATS RBAC and Admin User")
    parser.add_argument(
        "--email",
        default="admin@isc.com",
        help="Correo electrónico del administrador (default: admin@isc.com)",
    )
    parser.add_argument(
        "--password",
        default="Admin123*!",
        help="Contraseña para el administrador (default: Admin123*!)",
    )
    args = parser.parse_args()

    asyncio.run(run_bootstrap(args.email, args.password))


if __name__ == "__main__":
    main()
