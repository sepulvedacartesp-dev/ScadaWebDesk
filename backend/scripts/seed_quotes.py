import asyncio
import os
import uuid
from datetime import date
from decimal import Decimal

import asyncpg
from dotenv import load_dotenv


CATALOG_SEED = [
    {
        "slug": "containers",
        "nombre": "Contenedores modulares",
        "descripcion": "Servicios base para despliegue de contenedores inteligentes.",
        "items": [
            {
                "label": "Contenedor principal",
                "valor_uf": Decimal("3.16"),
                "nota": "Incluye habilitacion y despliegue inicial.",
                "orden": 1,
            },
            {
                "label": "Contenedor adicional",
                "valor_uf": Decimal("0.76"),
                "nota": "Se aplica a partir del segundo contenedor.",
                "orden": 2,
            },
        ],
    },
    {
        "slug": "nexbox",
        "nombre": "Modulos NexBox",
        "descripcion": "Expansion inalambrica de 8 canales.",
        "items": [
            {
                "label": "NexBox 8 canales",
                "valor_uf": Decimal("1.00"),
                "nota": "Compatible con instalaciones existentes.",
                "orden": 1,
            }
        ],
    },
    {
        "slug": "internet",
        "nombre": "Servicios de conectividad",
        "descripcion": "Provision de enlace dedicado y soporte basico.",
        "items": [
            {
                "label": "Suministro de internet en sitio",
                "valor_uf": Decimal("1.50"),
                "nota": "Incluye gestion y soporte basico del enlace.",
                "orden": 1,
            }
        ],
    },
    {
        "slug": "support",
        "nombre": "Planes de soporte",
        "descripcion": "Cobertura de soporte recurrente segun requerimientos.",
        "items": [
            {
                "label": "Soporte basico",
                "valor_uf": Decimal("0.00"),
                "nota": "Hasta 1 requerimiento o llamada al mes.",
                "orden": 1,
            },
            {
                "label": "Soporte Plus",
                "valor_uf": Decimal("2.00"),
                "nota": "Hasta 4 requerimientos o llamadas al mes.",
                "orden": 2,
            },
        ],
    },
]

CLIENTS_SEED = [
    {
        "empresa_id": "demo",
        "nombre": "Cliente Demo SurNex",
        "rut": "76.543.210-3",
        "contacto": "Juan Perez",
        "correo": "juan.perez@example.com",
        "telefono": "+56 9 1234 5678",
        "notas": "Cliente de demostracion para pruebas internas.",
    }
]


async def seed_catalog(conn: asyncpg.Connection) -> None:
    for entry in CATALOG_SEED:
        catalog = await conn.fetchrow(
            "SELECT id FROM quote_catalog WHERE slug = $1",
            entry["slug"],
        )
        if catalog:
            catalog_id = catalog["id"]
            print(f"Catalogo '{entry['slug']}' ya existe, omitiendo creacion.")
        else:
            catalog_id = uuid.uuid4()
            await conn.execute(
                """
                INSERT INTO quote_catalog (id, slug, nombre, descripcion, tipo)
                VALUES ($1, $2, $3, $4, 'service')
                """,
                catalog_id,
                entry["slug"],
                entry["nombre"],
                entry.get("descripcion"),
            )
            print(f"Catalogo '{entry['slug']}' creado.")

        for item in entry["items"]:
            existing_item = await conn.fetchrow(
                """
                SELECT id FROM quote_catalog_items
                WHERE catalog_id = $1 AND label = $2 AND valid_to IS NULL
                """,
                catalog_id,
                item["label"],
            )
            if existing_item:
                print(f"  Item '{item['label']}' ya existe, omitiendo.")
                continue

            item_id = uuid.uuid4()
            await conn.execute(
                """
                INSERT INTO quote_catalog_items (
                    id, catalog_id, label, valor_uf, nota, orden, valid_from
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                item_id,
                catalog_id,
                item["label"],
                item["valor_uf"],
                item.get("nota"),
                item.get("orden", 0),
                date.today(),
            )
            print(f"  Item '{item['label']}' creado.")


async def seed_clients(conn: asyncpg.Connection) -> None:
    for client in CLIENTS_SEED:
        exists = await conn.fetchrow(
            """
            SELECT id FROM clients
            WHERE empresa_id = $1 AND rut = $2
            """,
            client["empresa_id"],
            client["rut"],
        )
        if exists:
            print(f"Cliente {client['rut']} ya existe, omitiendo.")
            continue

        client_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO clients (
                id, empresa_id, nombre, rut, contacto, correo, telefono, notas
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            client_id,
            client["empresa_id"],
            client["nombre"],
            client["rut"],
            client.get("contacto"),
            client.get("correo"),
            client.get("telefono"),
            client.get("notas"),
        )
        print(f"Cliente {client['rut']} creado.")


async def main() -> None:
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL no esta definido. Configura tus variables de entorno.")

    conn = await asyncpg.connect(database_url)
    try:
        await seed_catalog(conn)
        await seed_clients(conn)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
