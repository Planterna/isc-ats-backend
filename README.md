# ISC ATS — Applicant Tracking System (Backend)

Backend de alto rendimiento para el **Sistema de Seguimiento de Candidatos (ATS)** de ISC, construido con **FastAPI**, **PostgreSQL** (con Screaming Architecture mediante esquemas dedicados y pgvector), **MinIO**, **Redis / Arq** y **Google Gemini AI**.

---

## 📋 Tabla de Contenidos

1. [Arquitectura y Módulos](#-arquitectura-y-módulos)
2. [Requisitos Previos](#-requisitos-previos)
3. [Variables de Entorno](#-variables-de-entorno)
4. [Instalación y Puesta en Marcha](#-instalación-y-puesta-en-marcha)
5. [Base de Datos y Migraciones (Alembic)](#-base-de-datos-y-migraciones-alembic)
6. [Bootstrap Inicial (Roles, Permisos y Admin)](#-bootstrap-inicial-roles-permisos-y-admin)
7. [Ejecución del Servidor y Worker](#-ejecución-del-servidor-y-worker)
8. [Documentación Interactiva (Swagger / OpenAPI)](#-documentación-interactiva-swagger--openapi)
9. [Flujo de Trabajo del Sistema](#-flujo-de-trabajo-del-sistema)
10. [Pruebas Automatizadas y Calidad](#-pruebas-automatizadas-y-calidad)
11. [Despliegue en Producción](#-despliegue-en-producción)

---

## 🏛 Arquitectura y Módulos

El proyecto sigue los principios de **Screaming Architecture** y diseño guiado por el dominio (DDD). La base de datos de PostgreSQL está particionada lógicamente en **7 esquemas (Bounded Contexts)** independientes:

```
app/
├── core/                   # Configuración global, seguridad, DB, rate limiting y colas
├── modules/
│   ├── auth/               # Esquema `auth`: Usuarios, roles RBAC, JWT, denylist, consentimientos
│   ├── org/                # Esquema `org`: Departamentos, empresas cliente (espejo TMR), parámetros, procesos y etapas
│   ├── recruitment/        # Esquema `recruitment`: Vacantes, candidatos, postulaciones, entrevistas, notas
│   ├── talent/             # Esquema `talent`: Banco de talentos global y filtros
│   ├── comms/              # Esquema `comms`: Notificaciones internas y logs de correos (SMTP/Resend)
│   ├── storage/            # Esquema `storage`: Metadatos de archivos MinIO/S3 y control de cuotas
│   └── ai/                 # Esquema `ai`: Extracción de CVs con Gemini, scoring, generación de banners y Word
├── shared/                 # Modelos base, repositorios genéricos y mixins
├── templates/              # Plantillas DOCX y recursos de diseño para banners
├── api_router.py           # Agregador de todos los sub-routers de la API
├── main.py                 # Punto de entrada de la aplicación FastAPI
└── worker.py               # Worker de tareas en segundo plano (Arq)
```

### Roles Predefinidos en el Sistema
- **Administrador**: Acceso total a todos los módulos y configuración global.
- **Talento Humano (TH)**: Gestión integral del pipeline de selección, vacantes, candidatos, etapas y banco de talentos.
- **Comercial**: Gestión y seguimiento de vacantes asociadas a clientes específicos.
- **Proyecto**: Supervisión operativa de vacantes y perfiles técnicos.
- **Marketing**: Consulta de suscriptores y métricas para campañas.
- **candidate**: Permisos mínimos restringidos para el portal de autoservicio del candidato.

---

## ⚙️ Requisitos Previos

Asegúrate de contar con los siguientes componentes en tu entorno:

- **Python**: Versión `3.12` o superior.
- **Gestor de Paquetes**: Se recomienda [uv](https://docs.astral.sh/uv/) (o alternativamente `pip` con `venv`).
- **PostgreSQL**: Versión 15 o superior con la extensión `vector` habilitada (`CREATE EXTENSION IF NOT EXISTS vector;`).
- **MinIO**: Servidor local o remoto para almacenamiento de objetos (CVs, fotos, documentos).
- **Redis**: Versión 7+ (requerido para el Worker en producción; opcional en desarrollo local con `QUEUE_BACKEND=inline`).

---

## 🔐 Variables de Entorno

Crea tu archivo `.env` copiando la plantilla proporcionada:

```bash
cp .env.example .env
```

### Configuración Principal

| Variable | Descripción | Valor por Defecto |
| :--- | :--- | :--- |
| `ENVIRONMENT` | Entorno de ejecución (`development`, `production`, `testing`) | `development` |
| `DATABASE_URL` | Conexión async a PostgreSQL (`postgresql+asyncpg://...`) | `postgresql+asyncpg://postgres:postgres@localhost:5432/isc_ats` |
| `MINIO_ENDPOINT` | Host y puerto del servidor MinIO | `localhost:9000` |
| `MINIO_ACCESS_KEY` | Llave de acceso de MinIO | `minioadmin` |
| `MINIO_SECRET_KEY` | Clave secreta de MinIO | `minioadmin` |
| `MINIO_BUCKET` | Nombre del bucket para almacenar CVs | `candidates-cvs` |
| `JWT_SECRET_KEY` | Secreto criptográfico para firma de tokens JWT | *(Definir clave segura en prod)* |
| `QUEUE_BACKEND` | `inline` para tareas en el mismo hilo (dev) o `arq` para Redis (prod) | `inline` |
| `REDIS_URL` | Conexión a Redis para Arq y lista de revocación de tokens | `redis://localhost:6379/0` |
| `GEMINI_API_KEY` | API Key de Google Gemini para procesamiento de IA | `""` |
| `EMAIL_PROVIDER` | Proveedor de correos: `smtp` (Gmail) o `resend` | `smtp` |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | Credenciales de correo saliente | `""` |
| `MEETINGS_PROVIDER` | `disabled` o `graph` (para crear enlaces de Microsoft Teams) | `disabled` |

---

## 🚀 Instalación y Puesta en Marcha

### Opción A: Con `uv` (Recomendado)

```bash
# 1. Instalar dependencias
uv sync

# 2. Activar el entorno virtual generado
# En Windows (PowerShell):
.venv\Scripts\Activate.ps1
# En Linux / macOS:
source .venv/bin/activate
```

### Opción B: Con Python `venv` y `pip` tradicional

```bash
# 1. Crear el entorno virtual
python -m venv .venv

# 2. Activar el entorno
# En Windows:
.venv\Scripts\activate
# En Linux / macOS:
source .venv/bin/activate

# 3. Instalar dependencias del proyecto
pip install -e .
pip install ruff pytest pytest-asyncio httpx
```

---

## 🗄 Base de Datos y Migraciones (Alembic)

1. **Crear la base de datos en PostgreSQL**:
   ```sql
   CREATE DATABASE isc_ats;
   \c isc_ats;
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

2. **Ejecutar las migraciones**:
   Alembic creará automáticamente los 7 esquemas (`auth`, `org`, `recruitment`, `talent`, `comms`, `storage`, `ai`) y todas las tablas estructuradas:
   ```bash
   uv run alembic upgrade head
   # O con venv activo:
   alembic upgrade head
   ```

3. **Crear una nueva migración** (tras modificar o añadir modelos SQLAlchemy):
   ```bash
   uv run alembic revision --autogenerate -m "descripcion_del_cambio"
   ```

---

## 👑 Bootstrap Inicial (Roles, Permisos y Admin)

El sistema incluye un script idempotente que sincroniza el catálogo de permisos, asegura todos los roles estándar y crea tu primer usuario Administrador:

```bash
# Con uv:
uv run python -m scripts.bootstrap --email admin@isc.com --password MiClaveSegura123!

# O con Python normal:
python -m scripts.bootstrap --email admin@isc.com --password MiClaveSegura123!
```

> [!NOTE]
> Este comando es completamente seguro de volver a ejecutar en cualquier momento para sincronizar nuevos permisos del catálogo sin alterar los datos existentes.

---

## 🖥 Ejecución del Servidor y Worker

### 1. Servidor API (FastAPI)
Inicia la API con recarga automática:
```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
La API estará lista y escuchando en: `http://localhost:8000`.

### 2. Worker de Tareas en Segundo Plano (Arq)
En producción (o en desarrollo si tienes `QUEUE_BACKEND=arq` y Redis corriendo):
```bash
uv run arq app.worker.WorkerSettings
```
El worker procesará de forma asíncrona:
- Análisis de CVs y cálculo de afinidad (*match scoring*) con Gemini.
- Extracción de datos del perfil del candidato.
- Envío de correos (verificación, restablecimiento de contraseña, notificaciones de rechazo o cambio de etapa).
- Creación de reuniones virtuales en Microsoft Teams.

### 3. Puesta en marcha completa con Docker Compose (Recomendado)

El proyecto incluye un archivo `docker-compose.yml` que orquesta todos los servicios necesarios: PostgreSQL 16 con `pgvector`, MinIO, Redis, la API FastAPI (con sincronización y migraciones automáticas) y el Worker Arq.

```bash
# 1. Levantar todos los servicios en segundo plano:
docker compose up -d --build

# 2. Ver logs en tiempo real:
docker compose logs -f backend
docker compose logs -f worker

# 3. Ejecutar el bootstrap para crear el usuario administrador:
docker compose exec backend uv run python -m scripts.bootstrap --email admin@isc.com --password MiClaveSegura123!

# 4. Detener los servicios:
docker compose down
```

> [!TIP]
> **Modo Híbrido (Infraestructura en Docker, Backend en Local):**  
> Si prefieres depurar Uvicorn en tu máquina local, puedes levantar únicamente las bases de datos y servicios auxiliares con:
> ```bash
> docker compose up -d db minio redis
> ```
> Y luego ejecutar el backend en local con `uv run uvicorn app.main:app --reload`.

---

## 📖 Documentación Interactiva (Swagger / OpenAPI)

FastAPI genera automáticamente la documentación interactiva y el esquema OpenAPI:

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **OpenAPI JSON**: [http://localhost:8000/api/v1/openapi.json](http://localhost:8000/api/v1/openapi.json)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## 🔄 Flujo de Trabajo del Sistema

### 1. Autenticación y Autorización
- Iniciar sesión en `POST /api/v1/auth/login` enviando `email` y `password`.
- La respuesta retorna un `access_token` JWT y una cookie con el `refresh_token`.
- Enviar el token en las peticiones autenticadas:
  `Authorization: Bearer <access_token>`.
- Al cambiar contraseña o hacer logout (`POST /api/v1/auth/logout`), el token previo queda revocado inmediatamente en la lista de denegación (`denylist`).

### 2. Configuración del Proceso de Selección
- Definir parámetros en `/api/v1/org/parameters` (tipos de contrato, modalidades, niveles educativos).
- Configurar procesos y sus etapas en `/api/v1/org/processes` y `/api/v1/org/process-stages`.

### 3. Publicación de Vacantes
- Crear una solicitud de vacante en `POST /api/v1/recruitment/vacancies`.
- Pasar a estado publicado (`published`) cuando la vacante esté aprobada.
- Generar póster/banner publicitario automáticamente con `POST /api/v1/ai/vacancy-promo-images`.

### 4. Postulación y Procesamiento con IA
- El candidato sube su CV en `POST /api/v1/storage/files/upload`.
- Al registrar su postulación en `POST /api/v1/recruitment/applications`, se encola la tarea `analyze_application`.
- Gemini evalúa el CV frente a los requisitos de la vacante, genera una justificación técnica y asigna un puntaje de compatibilidad (`match_score` de 0 a 100).
- Convertir directamente una hoja de vida en formato Word estandarizado corporativo mediante `POST /api/v1/ai/direct-cv-converter`.

### 5. Entrevistas y Agendamiento
- **Modo A (Directo)**: El reclutador agenda directamente fecha, hora y entrevistadores en `POST /api/v1/recruitment/interviews`.
- **Modo B (Selección de Slots)**: Se generan franjas de disponibilidad (`/interviews/available-slots`) y se envía un enlace al candidato para que seleccione el horario que mejor le convenga.
- Si `MEETINGS_PROVIDER=graph`, se genera automáticamente el enlace de Microsoft Teams y se envía la invitación por correo.

---

## 🧪 Pruebas Automatizadas y Calidad

El proyecto cuenta con una amplia suite de pruebas unitarias y de integración que validan seguridad, flujos de selección y guardas HTTP:

```bash
# Ejecutar toda la suite de pruebas
uv run pytest

# Ejecutar un módulo de pruebas específico
uv run pytest tests/test_auth_login.py

# Ejecutar con salida detallada
uv run pytest -v

# Linter y verificación de código
uv run ruff check .

# Formateo de código
uv run ruff format .
```

---

## 🚢 Despliegue en Producción

Para consultar los lineamientos detallados de despliegue en Dokploy o entornos de contenedores, revisa el archivo [DEPLOY.md](DEPLOY.md).

**Puntos clave para producción:**
1. Cambiar obligatoriamente `JWT_SECRET_KEY`, `MINIO_ACCESS_KEY` y `MINIO_SECRET_KEY` (la aplicación rehusará arrancar con los valores por defecto).
2. Activar `QUEUE_BACKEND=arq` y configurar `REDIS_URL`.
3. Orden estricto de despliegue:
   1. Iniciar **Redis**.
   2. Desplegar el **Backend** (ejecuta migraciones con `entrypoint.prod.sh`).
   3. Iniciar el **Worker** con el comando `arq app.worker.WorkerSettings`.
