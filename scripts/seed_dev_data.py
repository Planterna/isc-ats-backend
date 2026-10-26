"""Seed the database with realistic development and testing data.

This script populates:
  - System parameters (stage names, vacancy names)
  - Profile templates & template items
  - Client companies, departments, contacts
  - Hiring processes & ordered pipeline stages
  - Job vacancies (active, paused, draft)
  - Staff recruiter user (rrhh@isc.com) with Talento Humano role
  - Candidate users & detailed candidate profiles
  - Consents (terms_privacy, marketing) & roles for candidates
  - Applications distributed across stages with salary expectations
  - Interviewer availability & sample interviews
  - Talent pool entries

Safe to re-run — uses get-or-create patterns so it won't duplicate rows.

Usage:
    python -m scripts.seed_dev_data
    # Or in Docker:
    docker compose exec backend uv run python -m scripts.seed_dev_data
"""

import asyncio
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
import app.models_registry  # noqa: F401 — registers all models on Base.metadata
from app.core.security import hash_password
from app.modules.auth.infrastructure.models import (
    CONSENT_MARKETING,
    CONSENT_TERMS_PRIVACY,
    Consent,
    Role,
    User,
    UserRole,
)
from app.modules.org.infrastructure.models import (
    ClientCompany,
    Contact,
    Department,
    Parameter,
    Process,
    ProcessStage,
    ProfileTemplate,
    ProfileTemplateItem,
)
from app.modules.recruitment.infrastructure.application_models import Application
from app.modules.recruitment.infrastructure.candidate_models import Candidate
from app.modules.recruitment.infrastructure.interview_models import (
    Interview,
    InterviewerAvailability,
)
from app.modules.recruitment.infrastructure.models import Vacancy
from app.modules.talent.infrastructure.models import TalentPool


# ── Helpers ───────────────────────────────────────────────────────────────────


async def get_or_create_param(
    session: AsyncSession, *, type_: str, code: str, name: str, user_id: int = 1
) -> Parameter:
    stmt = select(Parameter).where(Parameter.type == type_, Parameter.code == code)
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        return existing
    param = Parameter(type=type_, code=code, name=name, created_by=user_id)
    session.add(param)
    await session.flush()
    return param


async def get_or_create_company(
    session: AsyncSession, name: str, legal_name: str | None = None, user_id: int = 1
) -> ClientCompany:
    stmt = select(ClientCompany).where(
        ClientCompany.name == name, ClientCompany.is_active.is_(True)
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        return existing
    company = ClientCompany(name=name, legal_name=legal_name, created_by=user_id)
    session.add(company)
    await session.flush()
    return company


async def get_or_create_department(
    session: AsyncSession, name: str, user_id: int = 1
) -> Department:
    stmt = select(Department).where(
        Department.name == name, Department.is_active.is_(True)
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        return existing
    dept = Department(name=name, created_by=user_id)
    session.add(dept)
    await session.flush()
    return dept


async def get_or_create_contact(
    session: AsyncSession,
    *,
    first_name: str,
    last_name: str,
    email: str,
    company_id: int,
    user_id: int = 1,
) -> Contact:
    stmt = select(Contact).where(Contact.email == email, Contact.is_active.is_(True))
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        return existing
    contact = Contact(
        first_name=first_name,
        last_name=last_name,
        email=email,
        client_company_id=company_id,
        created_by=user_id,
    )
    session.add(contact)
    await session.flush()
    return contact


async def get_or_create_process(
    session: AsyncSession,
    *,
    name: str,
    company_id: int,
    dept_id: int,
    user_id: int = 1,
) -> Process:
    stmt = select(Process).where(
        Process.name == name,
        Process.client_company_id == company_id,
        Process.is_active.is_(True),
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        return existing
    process = Process(
        name=name,
        client_company_id=company_id,
        department_id=dept_id,
        created_by=user_id,
    )
    session.add(process)
    await session.flush()
    return process


async def get_or_create_process_stage(
    session: AsyncSession,
    *,
    process_id: int,
    stage_id: int,
    order: int,
    is_final: bool = False,
    is_initial: bool = False,
    user_id: int = 1,
) -> ProcessStage:
    stmt = select(ProcessStage).where(
        ProcessStage.process_id == process_id,
        ProcessStage.stage_id == stage_id,
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        return existing
    ps = ProcessStage(
        process_id=process_id,
        stage_id=stage_id,
        order=order,
        is_final_positive=is_final,
        is_initial=is_initial,
        created_by=user_id,
    )
    session.add(ps)
    await session.flush()
    return ps


async def get_or_create_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    portal_id: int,
    user_id: int = 1,
) -> User:
    stmt = select(User).where(User.email == email)
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        return existing
    user = User(
        email=email,
        password_hash=hash_password(password),
        portal_id=portal_id,
        email_verified=True,
        is_active=True,
        created_by=user_id,
    )
    session.add(user)
    await session.flush()
    return user


async def ensure_user_role(
    session: AsyncSession, *, user_id: int, role_id: int, created_by: int = 1
) -> None:
    stmt = select(UserRole).where(
        UserRole.user_id == user_id, UserRole.role_id == role_id
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if not existing:
        session.add(UserRole(user_id=user_id, role_id=role_id, created_by=created_by))
        await session.flush()


async def ensure_candidate_consents(
    session: AsyncSession, *, user_id: int, created_by: int = 1
) -> None:
    now = datetime.now(UTC)
    for consent_type in (CONSENT_TERMS_PRIVACY, CONSENT_MARKETING):
        stmt = select(Consent).where(
            Consent.user_id == user_id,
            Consent.consent_type == consent_type,
            Consent.revoked_at.is_(None),
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if not existing:
            session.add(
                Consent(
                    user_id=user_id,
                    consent_type=consent_type,
                    accepted_at=now,
                    policy_version="2.0",
                    source="registration",
                    created_by=created_by,
                )
            )
    await session.flush()


# ── Main Seeding Routine ───────────────────────────────────────────────────────


async def seed(session: AsyncSession) -> None:
    print("[*] Obteniendo parámetros base y portales...")

    # Portals
    staff_portal = await get_or_create_param(session, type_="user_portal", code="staff", name="Portal Administrativo")
    cand_portal = await get_or_create_param(session, type_="user_portal", code="candidate", name="Portal Candidato")

    # Get admin user (ID for created_by)
    admin_stmt = select(User).where(User.email == "admin@isc.com")
    admin_user = (await session.execute(admin_stmt)).scalar_one_or_none()
    if not admin_user:
        admin_user = await get_or_create_user(
            session,
            email="admin@isc.com",
            password="Admin123*!",
            portal_id=staff_portal.id,
        )
    admin_id = admin_user.id

    # Roles
    hr_role_stmt = select(Role).where(Role.name == "Talento Humano")
    hr_role = (await session.execute(hr_role_stmt)).scalar_one_or_none()
    cand_role_stmt = select(Role).where(Role.name == "candidate")
    cand_role = (await session.execute(cand_role_stmt)).scalar_one_or_none()

    # Create staff recruiter user
    print("[*] Creando usuario de reclutamiento (rrhh@isc.com)...")
    rrhh_user = await get_or_create_user(
        session,
        email="rrhh@isc.com",
        password="Rrhh123*!",
        portal_id=staff_portal.id,
        user_id=admin_id,
    )
    if hr_role:
        await ensure_user_role(session, user_id=rrhh_user.id, role_id=hr_role.id, created_by=admin_id)

    # Stages (Polymorphic parameters)
    postulantes = await get_or_create_param(session, type_="stage", code="applicants", name="Postulantes", user_id=admin_id)
    cv = await get_or_create_param(session, type_="stage", code="cv_received", name="CV recibido", user_id=admin_id)
    llamada = await get_or_create_param(session, type_="stage", code="validation_call", name="Llamada de validación", user_id=admin_id)
    prueba = await get_or_create_param(session, type_="stage", code="technical_test", name="Prueba técnica", user_id=admin_id)
    entrevista_hr = await get_or_create_param(session, type_="stage", code="hr_interview", name="Entrevista HR", user_id=admin_id)
    entrevista_cli = await get_or_create_param(session, type_="stage", code="client_interview", name="Entrevista cliente", user_id=admin_id)
    oferta = await get_or_create_param(session, type_="stage", code="offer", name="Contratación", user_id=admin_id)
    entrevista_gen = await get_or_create_param(session, type_="stage", code="interview", name="Entrevista", user_id=admin_id)

    # Vacancy Names (Job titles)
    fullstack_name = await get_or_create_param(session, type_="vacancy_name", code="fullstack", name="Desarrollador Fullstack", user_id=admin_id)
    qa_name = await get_or_create_param(session, type_="vacancy_name", code="qa_automatizacion", name="Analista QA Automatización", user_id=admin_id)
    procesos_name = await get_or_create_param(session, type_="vacancy_name", code="ing_procesos", name="Ing. en Procesos", user_id=admin_id)
    datos_name = await get_or_create_param(session, type_="vacancy_name", code="arq_datos", name="Arquitecto de Datos", user_id=admin_id)
    devops_name = await get_or_create_param(session, type_="vacancy_name", code="devops", name="DevOps Engineer", user_id=admin_id)
    scrum_name = await get_or_create_param(session, type_="vacancy_name", code="scrum_master", name="Scrum Master", user_id=admin_id)
    riesgo_name = await get_or_create_param(session, type_="vacancy_name", code="analista_riesgo", name="Analista de Riesgo Crediticio", user_id=admin_id)
    soporte_name = await get_or_create_param(session, type_="vacancy_name", code="ing_soporte", name="Ing. Soporte de Aplicaciones", user_id=admin_id)
    ciber_name = await get_or_create_param(session, type_="vacancy_name", code="ciberseguridad", name="Analista de Ciberseguridad", user_id=admin_id)
    po_name = await get_or_create_param(session, type_="vacancy_name", code="product_owner", name="Product Owner", user_id=admin_id)

    # Catalog references
    guayaquil = await get_or_create_param(session, type_="city", code="guayaquil", name="Guayaquil", user_id=admin_id)
    quito = await get_or_create_param(session, type_="city", code="quito", name="Quito", user_id=admin_id)
    cuenca = await get_or_create_param(session, type_="city", code="cuenca", name="Cuenca", user_id=admin_id)

    onsite = await get_or_create_param(session, type_="work_mode", code="onsite", name="Presencial", user_id=admin_id)
    hybrid = await get_or_create_param(session, type_="work_mode", code="hybrid", name="Híbrido", user_id=admin_id)
    remote = await get_or_create_param(session, type_="work_mode", code="remote", name="Remoto", user_id=admin_id)
    project = await get_or_create_param(session, type_="work_mode", code="project", name="Por proyecto", user_id=admin_id)

    junior = await get_or_create_param(session, type_="resource_level", code="junior", name="Junior", user_id=admin_id)
    semi_senior = await get_or_create_param(session, type_="resource_level", code="semi_senior", name="Semi Senior", user_id=admin_id)
    senior = await get_or_create_param(session, type_="resource_level", code="senior", name="Senior", user_id=admin_id)
    specialist = await get_or_create_param(session, type_="resource_level", code="specialist", name="Especialista", user_id=admin_id)

    status_active = await get_or_create_param(session, type_="vacancy_status", code="active", name="Activa", user_id=admin_id)
    status_draft = await get_or_create_param(session, type_="vacancy_status", code="draft", name="Borrador", user_id=admin_id)
    status_paused = await get_or_create_param(session, type_="vacancy_status", code="paused", name="Pausada", user_id=admin_id)

    app_status_active = await get_or_create_param(session, type_="application_status", code="active", name="Activa", user_id=admin_id)
    app_status_hired = await get_or_create_param(session, type_="application_status", code="hired", name="Contratada", user_id=admin_id)

    career_software = await get_or_create_param(session, type_="career", code="software", name="Software", user_id=admin_id)
    career_sistemas = await get_or_create_param(session, type_="career", code="sistemas", name="Sistemas / Computación", user_id=admin_id)
    career_industrial = await get_or_create_param(session, type_="career", code="industrial", name="Industrial", user_id=admin_id)
    career_economia = await get_or_create_param(session, type_="career", code="economia", name="Economía / Finanzas", user_id=admin_id)
    career_telecom = await get_or_create_param(session, type_="career", code="electronica", name="Electrónica / Telecomunicaciones", user_id=admin_id)

    title_ing = await get_or_create_param(session, type_="title", code="ingeniero", name="Ingeniero", user_id=admin_id)
    title_lic = await get_or_create_param(session, type_="title", code="licenciado", name="Licenciado", user_id=admin_id)
    title_econ = await get_or_create_param(session, type_="title", code="economista", name="Economista", user_id=admin_id)

    uni_espol = await get_or_create_param(session, type_="university", code="espol", name="Escuela Superior Politécnica del Litoral (ESPOL)", user_id=admin_id)
    uni_epn = await get_or_create_param(session, type_="university", code="epn", name="Escuela Politécnica Nacional (EPN)", user_id=admin_id)
    uni_usfq = await get_or_create_param(session, type_="university", code="usfq", name="Universidad San Francisco de Quito (USFQ)", user_id=admin_id)
    uni_uce = await get_or_create_param(session, type_="university", code="uce", name="Universidad Central del Ecuador (UCE)", user_id=admin_id)

    cat_knowledge = await get_or_create_param(session, type_="template_item_category", code="knowledge", name="Conocimientos", user_id=admin_id)
    cat_tools = await get_or_create_param(session, type_="template_item_category", code="tools", name="Herramientas", user_id=admin_id)
    cat_skills = await get_or_create_param(session, type_="template_item_category", code="skills", name="Habilidades", user_id=admin_id)
    cat_certs = await get_or_create_param(session, type_="template_item_category", code="certifications", name="Certificaciones", user_id=admin_id)

    # ── Profile Templates ─────────────────────────────────────────────────────
    print("[*] Poblando plantillas de perfil (org.profile_templates)...")
    template_stmt = select(ProfileTemplate).where(ProfileTemplate.name == "Desarrollador Fullstack Senior")
    tmpl_fullstack = (await session.execute(template_stmt)).scalar_one_or_none()
    if not tmpl_fullstack:
        tmpl_fullstack = ProfileTemplate(name="Desarrollador Fullstack Senior", created_by=admin_id)
        session.add(tmpl_fullstack)
        await session.flush()

        items = [
            (cat_knowledge.id, ".NET 8 / C#"),
            (cat_knowledge.id, "Angular 17+"),
            (cat_knowledge.id, "SQL Server / PostgreSQL"),
            (cat_tools.id, "Docker"),
            (cat_tools.id, "Git / GitHub"),
            (cat_tools.id, "Azure DevOps"),
            (cat_skills.id, "Resolución de problemas"),
            (cat_skills.id, "Trabajo en equipo"),
            (cat_certs.id, "Azure Developer Associate"),
        ]
        for cat_id, name in items:
            session.add(ProfileTemplateItem(template_id=tmpl_fullstack.id, category_id=cat_id, name=name, created_by=admin_id))
        await session.flush()

    # ── Companies, Departments, Contacts ──────────────────────────────────────
    print("[*] Poblando empresas cliente, departamentos y contactos...")
    bg = await get_or_create_company(session, "Banco Guayaquil", legal_name="Banco Guayaquil S.A.", user_id=admin_id)
    bp = await get_or_create_company(session, "Banco del Pacífico", legal_name="Banco del Pacífico S.A.", user_id=admin_id)
    produ = await get_or_create_company(session, "Produbanco", legal_name="Produbanco Grupo Promerica", user_id=admin_id)
    diners = await get_or_create_company(session, "Diners Club", legal_name="Diners Club del Ecuador S.A.", user_id=admin_id)
    pichincha = await get_or_create_company(session, "Banco Pichincha", legal_name="Banco Pichincha C.A.", user_id=admin_id)
    claro = await get_or_create_company(session, "Claro Ecuador", legal_name="CONECEL S.A.", user_id=admin_id)
    cnt = await get_or_create_company(session, "CNT EP", legal_name="Corporación Nacional de Telecomunicaciones", user_id=admin_id)
    favorita = await get_or_create_company(session, "Corp. Favorita", legal_name="Corporación Favorita C.A.", user_id=admin_id)

    tech = await get_or_create_department(session, "Tecnología", user_id=admin_id)
    calidad = await get_or_create_department(session, "Calidad", user_id=admin_id)
    procesos_dept = await get_or_create_department(session, "Procesos", user_id=admin_id)
    datos = await get_or_create_department(session, "Datos & Analytics", user_id=admin_id)
    infra = await get_or_create_department(session, "Infraestructura", user_id=admin_id)
    riesgos = await get_or_create_department(session, "Riesgos", user_id=admin_id)
    ops_ti = await get_or_create_department(session, "Operaciones TI", user_id=admin_id)
    seguridad = await get_or_create_department(session, "Seguridad", user_id=admin_id)
    producto = await get_or_create_department(session, "Producto", user_id=admin_id)

    monica = await get_or_create_contact(session, first_name="Mónica", last_name="Andrade", email="m.andrade@bancog.com", company_id=bg.id, user_id=admin_id)
    ricardo = await get_or_create_contact(session, first_name="Ricardo", last_name="Mora", email="r.mora@bancop.com", company_id=bp.id, user_id=admin_id)
    lucia = await get_or_create_contact(session, first_name="Lucía", last_name="Herrera", email="l.herrera@produbanco.com", company_id=produ.id, user_id=admin_id)
    pablo = await get_or_create_contact(session, first_name="Pablo", last_name="Vásquez", email="p.vasquez@diners.com", company_id=diners.id, user_id=admin_id)
    fernando = await get_or_create_contact(session, first_name="Fernando", last_name="Paredes", email="f.paredes@pichincha.com", company_id=pichincha.id, user_id=admin_id)
    gabriela = await get_or_create_contact(session, first_name="Gabriela", last_name="Saltos", email="g.saltos@claro.com.ec", company_id=claro.id, user_id=admin_id)
    andres = await get_or_create_contact(session, first_name="Andrés", last_name="Villacís", email="a.villacis@cnt.gob.ec", company_id=cnt.id, user_id=admin_id)
    mateo = await get_or_create_contact(session, first_name="Mateo", last_name="Torres", email="m.torres@favorita.com", company_id=favorita.id, user_id=admin_id)

    # ── Hiring Processes & Stages ─────────────────────────────────────────────
    print("[*] Poblando procesos de selección y etapas...")
    proc_bg_tech = await get_or_create_process(session, name="BG · Tecnología — Estándar 5 etapas", company_id=bg.id, dept_id=tech.id, user_id=admin_id)
    proc_bp_qa = await get_or_create_process(session, name="BP · Calidad — QA 4 etapas", company_id=bp.id, dept_id=calidad.id, user_id=admin_id)
    proc_generic = await get_or_create_process(session, name="Genérico — 3 etapas", company_id=produ.id, dept_id=tech.id, user_id=admin_id)

    # BG · Tecnología stages
    st_bg_1 = await get_or_create_process_stage(session, process_id=proc_bg_tech.id, stage_id=postulantes.id, order=1, is_initial=True, user_id=admin_id)
    st_bg_2 = await get_or_create_process_stage(session, process_id=proc_bg_tech.id, stage_id=cv.id, order=2, user_id=admin_id)
    st_bg_3 = await get_or_create_process_stage(session, process_id=proc_bg_tech.id, stage_id=llamada.id, order=3, user_id=admin_id)
    st_bg_4 = await get_or_create_process_stage(session, process_id=proc_bg_tech.id, stage_id=prueba.id, order=4, user_id=admin_id)
    st_bg_5 = await get_or_create_process_stage(session, process_id=proc_bg_tech.id, stage_id=entrevista_cli.id, order=5, user_id=admin_id)
    st_bg_6 = await get_or_create_process_stage(session, process_id=proc_bg_tech.id, stage_id=oferta.id, order=6, is_final=True, user_id=admin_id)

    # BP · Calidad stages
    await get_or_create_process_stage(session, process_id=proc_bp_qa.id, stage_id=postulantes.id, order=1, is_initial=True, user_id=admin_id)
    await get_or_create_process_stage(session, process_id=proc_bp_qa.id, stage_id=cv.id, order=2, user_id=admin_id)
    await get_or_create_process_stage(session, process_id=proc_bp_qa.id, stage_id=entrevista_hr.id, order=3, user_id=admin_id)
    await get_or_create_process_stage(session, process_id=proc_bp_qa.id, stage_id=prueba.id, order=4, user_id=admin_id)
    await get_or_create_process_stage(session, process_id=proc_bp_qa.id, stage_id=oferta.id, order=5, is_final=True, user_id=admin_id)

    # Genérico stages
    await get_or_create_process_stage(session, process_id=proc_generic.id, stage_id=postulantes.id, order=1, is_initial=True, user_id=admin_id)
    await get_or_create_process_stage(session, process_id=proc_generic.id, stage_id=cv.id, order=2, user_id=admin_id)
    await get_or_create_process_stage(session, process_id=proc_generic.id, stage_id=entrevista_gen.id, order=3, user_id=admin_id)
    await get_or_create_process_stage(session, process_id=proc_generic.id, stage_id=oferta.id, order=4, is_final=True, user_id=admin_id)

    # ── Vacancies ─────────────────────────────────────────────────────────────
    print("[*] Poblando vacantes (recruitment.vacancies)...")

    async def get_or_create_vacancy(session: AsyncSession, **kwargs) -> Vacancy:
        stmt = select(Vacancy).where(
            Vacancy.client_company_id == kwargs["client_company_id"],
            Vacancy.vacancy_name_id == kwargs["vacancy_name_id"],
            Vacancy.is_active.is_(True),
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing:
            return existing
        vac = Vacancy(**kwargs)
        session.add(vac)
        await session.flush()
        return vac

    now = datetime.now(UTC)
    v_fullstack = await get_or_create_vacancy(
        session,
        vacancy_name_id=fullstack_name.id, client_company_id=bg.id, contact_id=monica.id,
        department_id=tech.id, process_id=proc_bg_tech.id,
        career_id=career_software.id, city_id=guayaquil.id, work_mode_id=hybrid.id,
        resource_level_id=senior.id, status_id=status_active.id,
        profile_template_id=tmpl_fullstack.id,
        openings=2, experience_years=3,
        work_schedule="Lunes a viernes, 8:00–17:00",
        project_duration_years=2, project_duration_months=0,
        description="Responsable del desarrollo y mantenimiento de aplicaciones bancarias sobre Angular y .NET 8.",
        profile_requirements={
            "knowledge": ["C# / .NET 8", "Angular 17", "TypeScript", "SQL Server", "REST API"],
            "tools": ["Git", "Azure DevOps", "Postman", "Docker"],
            "skills": ["Comunicación efectiva", "Trabajo en equipo", "Resolución de problemas"],
            "certifications": ["Microsoft Certified: Azure Developer (deseable)"],
        },
        published_at=now - timedelta(days=10),
        created_by=admin_id,
    )

    v_qa = await get_or_create_vacancy(
        session,
        vacancy_name_id=qa_name.id, client_company_id=bp.id, contact_id=ricardo.id,
        department_id=calidad.id, process_id=proc_bp_qa.id,
        career_id=career_sistemas.id, city_id=guayaquil.id, work_mode_id=onsite.id,
        resource_level_id=semi_senior.id, status_id=status_active.id,
        openings=3, experience_years=2,
        work_schedule="Lunes a viernes, 8:00–17:00",
        project_duration_years=1, project_duration_months=0,
        description="Automatización de pruebas funcionales y de rendimiento con Cypress y Playwright.",
        profile_requirements={"knowledge": ["QA Funcional", "Cypress", "JavaScript"], "tools": ["Jira", "Postman"], "skills": ["Detallista"], "certifications": []},
        published_at=now - timedelta(days=5),
        created_by=admin_id,
    )

    v_procesos = await get_or_create_vacancy(
        session,
        vacancy_name_id=procesos_name.id, client_company_id=produ.id, contact_id=lucia.id,
        department_id=procesos_dept.id, process_id=proc_generic.id,
        career_id=career_industrial.id, city_id=quito.id, work_mode_id=hybrid.id,
        resource_level_id=senior.id, status_id=status_active.id,
        openings=1, experience_years=4,
        work_schedule="Lunes a viernes, 8:00–17:00",
        project_duration_years=1, project_duration_months=6,
        description="Levantamiento, optimización y automatización de procesos bancarios y de negocio.",
        profile_requirements={"knowledge": ["BPMN", "Six Sigma"], "tools": ["Bizagi", "Visio"], "skills": ["Liderazgo"], "certifications": []},
        published_at=now - timedelta(days=3),
        created_by=admin_id,
    )

    await get_or_create_vacancy(
        session,
        vacancy_name_id=datos_name.id, client_company_id=bg.id, contact_id=monica.id,
        department_id=datos.id, process_id=proc_bg_tech.id,
        career_id=career_sistemas.id, city_id=guayaquil.id, work_mode_id=remote.id,
        resource_level_id=specialist.id, status_id=status_paused.id,
        openings=1, experience_years=5,
        work_schedule="Lunes a viernes, 8:00–17:00",
        project_duration_years=0, project_duration_months=6,
        description="Diseño y orquestación de arquitecturas de datos en la nube y pipelines ETL.",
        profile_requirements={"knowledge": ["Python", "Spark", "Data Warehouse"], "tools": ["Databricks", "Azure Data Factory"], "skills": ["Pensamiento crítico"], "certifications": []},
        created_by=admin_id,
    )

    await get_or_create_vacancy(
        session,
        vacancy_name_id=devops_name.id, client_company_id=diners.id, contact_id=pablo.id,
        department_id=infra.id, process_id=proc_generic.id,
        career_id=career_sistemas.id, city_id=quito.id, work_mode_id=hybrid.id,
        resource_level_id=senior.id, status_id=status_draft.id,
        openings=1, experience_years=4,
        work_schedule="Lunes a viernes, 8:00–17:00",
        project_duration_years=0, project_duration_months=0,
        description="Administración de infraestructura como código (Terraform), Kubernetes y CI/CD.",
        profile_requirements={"knowledge": ["Kubernetes", "Linux", "Terraform"], "tools": ["GitLab CI", "AWS"], "skills": ["Proactividad"], "certifications": []},
        created_by=admin_id,
    )

    await get_or_create_vacancy(
        session,
        vacancy_name_id=scrum_name.id, client_company_id=bp.id, contact_id=ricardo.id,
        department_id=tech.id, process_id=proc_bp_qa.id,
        career_id=career_sistemas.id, city_id=guayaquil.id, work_mode_id=remote.id,
        resource_level_id=senior.id, status_id=status_active.id,
        openings=1, experience_years=3,
        work_schedule="Lunes a viernes, 8:00–17:00",
        project_duration_years=0, project_duration_months=8,
        description="Facilitación de ceremonias ágiles y acompañamiento a células de desarrollo.",
        profile_requirements={"knowledge": ["Scrum", "Kanban"], "tools": ["Jira", "Confluence"], "skills": ["Facilitación", "Comunicación"], "certifications": ["PSM I / CSM"]},
        published_at=now - timedelta(days=2),
        created_by=admin_id,
    )

    await get_or_create_vacancy(
        session,
        vacancy_name_id=riesgo_name.id, client_company_id=pichincha.id, contact_id=fernando.id,
        department_id=riesgos.id, process_id=proc_generic.id,
        career_id=career_economia.id, city_id=quito.id, work_mode_id=onsite.id,
        resource_level_id=junior.id, status_id=status_active.id,
        openings=4, experience_years=1,
        work_schedule="Lunes a viernes, 8:00–17:00",
        project_duration_years=0, project_duration_months=8,
        description="Evaluación de expedientes de crédito corporativo y análisis financiero.",
        profile_requirements={"knowledge": ["Modelos de riesgo", "Finanzas"], "tools": ["Excel avanzado", "R / Python"], "skills": ["Análisis numérico"], "certifications": []},
        published_at=now - timedelta(days=7),
        created_by=admin_id,
    )

    await get_or_create_vacancy(
        session,
        vacancy_name_id=soporte_name.id, client_company_id=claro.id, contact_id=gabriela.id,
        department_id=ops_ti.id, process_id=proc_generic.id,
        career_id=career_sistemas.id, city_id=guayaquil.id, work_mode_id=onsite.id,
        resource_level_id=semi_senior.id, status_id=status_active.id,
        openings=2, experience_years=2,
        work_schedule="Lunes a viernes, 8:00–17:00",
        project_duration_years=1, project_duration_months=0,
        description="Soporte Nivel 2 para aplicativos de facturación y atención a clientes.",
        profile_requirements={"knowledge": ["SQL", "Linux", "Redes"], "tools": ["ServiceNow", "Zabbix"], "skills": ["Servicio al cliente"], "certifications": []},
        published_at=now - timedelta(days=6),
        created_by=admin_id,
    )

    await get_or_create_vacancy(
        session,
        vacancy_name_id=ciber_name.id, client_company_id=cnt.id, contact_id=andres.id,
        department_id=seguridad.id, process_id=proc_generic.id,
        career_id=career_telecom.id, city_id=quito.id, work_mode_id=hybrid.id,
        resource_level_id=senior.id, status_id=status_draft.id,
        openings=1, experience_years=3,
        work_schedule="Lunes a viernes, 8:00–17:00",
        project_duration_years=0, project_duration_months=0,
        description="Monitoreo de incidentes de seguridad en SOC y gestión de vulnerabilidades.",
        profile_requirements={"knowledge": ["Ciberseguridad", "SIEM", "Firewalls"], "tools": ["Splunk", "Wireshark"], "skills": ["Resolución bajo presión"], "certifications": ["CompTIA Security+"]},
        created_by=admin_id,
    )

    await get_or_create_vacancy(
        session,
        vacancy_name_id=po_name.id, client_company_id=favorita.id, contact_id=mateo.id,
        department_id=producto.id, process_id=proc_generic.id,
        career_id=career_industrial.id, city_id=quito.id, work_mode_id=project.id,
        resource_level_id=specialist.id, status_id=status_active.id,
        openings=1, experience_years=5,
        work_schedule="Lunes a viernes, 8:00–17:00",
        project_duration_years=0, project_duration_months=0,
        description="Definición de visión y backlog para la plataforma e-commerce omnicanal.",
        profile_requirements={"knowledge": ["Product Management", "Discovery", "Métricas de producto"], "tools": ["Figma", "Jira", "Mixpanel"], "skills": ["Negociación"], "certifications": ["CSPO"]},
        published_at=now - timedelta(days=4),
        created_by=admin_id,
    )

    # ── Candidates ────────────────────────────────────────────────────────────
    print("[*] Poblando usuarios candidatos y perfiles (recruitment.candidates)...")

    candidates_seed = [
        dict(
            email="santiago.almeida@gmail.com", first_name="Santiago", last_name="Almeida Paredes",
            cedula="1723456789", phone="+593983124567", city_id=quito.id,
            career_id=career_software.id, title_id=title_ing.id, university_id=uni_epn.id,
            home_address="Av. República de El Salvador y Moscú, Quito",
            years_of_experience=Decimal("4.5"),
            is_studying=False, is_working=True, current_company="TechSolutions S.A.",
            parsed_data={
                "skills": ["C#", ".NET 8", "PostgreSQL", "Angular 17", "TypeScript", "RESTful APIs"],
                "tools": ["Git", "Docker", "Postman", "VS Code", "Azure DevOps"],
            },
        ),
        dict(
            email="valeria.mosquera@outlook.com", first_name="Valeria", last_name="Mosquera Cifuentes",
            cedula="0912345678", phone="+593994567890", city_id=guayaquil.id,
            career_id=career_sistemas.id, title_id=title_ing.id, university_id=uni_espol.id,
            home_address="Urdesa Central, Calle Ilanes y Primera, Guayaquil",
            years_of_experience=Decimal("3.0"),
            is_studying=False, is_working=False, current_company=None,
            parsed_data={
                "skills": ["QA Funcional", "Automatización de pruebas", "JavaScript", "SQL", "Casos de prueba"],
                "tools": ["Cypress", "Playwright", "Postman", "Jira", "Git"],
            },
        ),
        dict(
            email="j.intriago@hotmail.com", first_name="Jorge", last_name="Intriago Loor",
            cedula="1312345670", phone="+593967890123", city_id=guayaquil.id,
            career_id=career_telecom.id, title_id=title_ing.id, university_id=uni_espol.id,
            home_address="Alborada 8va Etapa, Guayaquil",
            years_of_experience=Decimal("2.0"),
            is_studying=True, is_working=True, current_company="Freelance",
            parsed_data={
                "skills": ["Python", "Redes TCP/IP", "Linux", "Seguridad Informática", "Bash Scripting"],
                "tools": ["Wireshark", "Docker", "Git", "Linux Ubuntu"],
            },
        ),
        dict(
            email="andrea.cevallos@gmail.com", first_name="Andrea", last_name="Cevallos Espín",
            cedula="1756789012", phone="+593991234567", city_id=quito.id,
            career_id=career_software.id, title_id=title_ing.id, university_id=uni_usfq.id,
            home_address="Cumbayá, Paseo San Francisco, Quito",
            years_of_experience=Decimal("5.0"),
            is_studying=False, is_working=True, current_company="Banco Central del Ecuador",
            parsed_data={
                "skills": ["C#", ".NET 8", "React", "TypeScript", "SQL Server", "Microservicios"],
                "tools": ["Docker", "Azure DevOps", "Git", "Postman", "Visual Studio"],
            },
        ),
        dict(
            email="r.delgado.dev@gmail.com", first_name="Ramiro", last_name="Delgado Vega",
            cedula="0934567890", phone="+593980123456", city_id=guayaquil.id,
            career_id=career_sistemas.id, title_id=title_ing.id, university_id=uni_espol.id,
            home_address="Samborondón Km 2.5, Guayaquil",
            years_of_experience=Decimal("6.0"),
            is_studying=False, is_working=False, current_company=None,
            parsed_data={
                "skills": [".NET 8", "C#", "SQL Server", "Angular 17", "TypeScript", "Microservicios", "Arquitectura Limpia"],
                "tools": ["Docker", "Git", "Azure DevOps", "Kubernetes", "Postman", "SonarQube"],
            },
        ),
        dict(
            email="sofia.herrera.ec@gmail.com", first_name="Sofía", last_name="Herrera Narváez",
            cedula="1778901234", phone="+593996789012", city_id=quito.id,
            career_id=career_economia.id, title_id=title_econ.id, university_id=uni_uce.id,
            home_address="La Mariscal, Av. Amazonas y Foch, Quito",
            years_of_experience=Decimal("1.5"),
            is_studying=True, is_working=False, current_company=None,
            parsed_data={
                "skills": ["Modelos de riesgo", "Finanzas corporativas", "Análisis cuantitativo", "Econometría"],
                "tools": ["Excel avanzado", "Power BI", "R", "Python", "SQL"],
            },
        ),
        dict(
            email="dmorales.tech@outlook.com", first_name="Diego", last_name="Morales Castillo",
            cedula="0956789012", phone="+593974567890", city_id=guayaquil.id,
            career_id=career_software.id, title_id=title_ing.id, university_id=uni_espol.id,
            home_address="Puerto Santa Ana, Edificio Bellini, Guayaquil",
            years_of_experience=Decimal("3.5"),
            is_studying=False, is_working=True, current_company="Corporación FAVORITA",
            parsed_data={
                "skills": ["JavaScript", "TypeScript", "Node.js", "Angular", "Express", "MongoDB"],
                "tools": ["Git", "Docker", "VS Code", "Postman", "Jira"],
            },
        ),
        dict(
            email="catalina.ruiz.rec@gmail.com", first_name="Catalina", last_name="Ruiz Benalcázar",
            cedula="1789012345", phone="+593993456789", city_id=cuenca.id,
            career_id=career_industrial.id, title_id=title_ing.id, university_id=uni_epn.id,
            home_address="Av. Solano y Doce de Abril, Cuenca",
            years_of_experience=Decimal("4.0"),
            is_studying=False, is_working=True, current_company="Superintendencia de Bancos",
            parsed_data={
                "skills": ["BPMN", "Six Sigma", "Optimización de procesos", "Mejora continua", "Scrum"],
                "tools": ["Bizagi", "Microsoft Visio", "Jira", "Power BI", "Excel avanzado"],
            },
        ),
    ]

    seeded_candidates: list[Candidate] = []
    for c_data in candidates_seed:
        email = c_data.pop("email")
        u = await get_or_create_user(
            session,
            email=email,
            password="Candidato123*!",
            portal_id=cand_portal.id,
            user_id=admin_id,
        )
        if cand_role:
            await ensure_user_role(session, user_id=u.id, role_id=cand_role.id, created_by=admin_id)
        await ensure_candidate_consents(session, user_id=u.id, created_by=admin_id)

        c_stmt = select(Candidate).where(Candidate.user_id == u.id)
        cand = (await session.execute(c_stmt)).scalar_one_or_none()
        if not cand:
            cand = Candidate(user_id=u.id, created_by=admin_id, **c_data)
            session.add(cand)
            await session.flush()
        else:
            if not cand.parsed_data and "parsed_data" in c_data:
                cand.parsed_data = c_data["parsed_data"]
                session.add(cand)
                await session.flush()
        seeded_candidates.append(cand)

    # ── Applications ──────────────────────────────────────────────────────────
    print("[*] Poblando postulaciones (recruitment.applications)...")

    # Map candidate applications across stages in the Fullstack vacancy pipeline
    # Stages: st_bg_1 (Postulantes), st_bg_2 (CV recibido), st_bg_3 (Llamada validación),
    # st_bg_4 (Prueba técnica), st_bg_5 (Entrevista cliente), st_bg_6 (Contratación)
    app_distributions = [
        (seeded_candidates[0], v_fullstack, st_bg_4, Decimal("1800.00"), app_status_active),
        (seeded_candidates[1], v_fullstack, st_bg_3, Decimal("1500.00"), app_status_active),
        (seeded_candidates[2], v_fullstack, st_bg_2, Decimal("1400.00"), app_status_active),
        (seeded_candidates[3], v_fullstack, st_bg_5, Decimal("2000.00"), app_status_active),
        (seeded_candidates[4], v_fullstack, st_bg_6, Decimal("2200.00"), app_status_hired),
        (seeded_candidates[6], v_fullstack, st_bg_1, Decimal("1600.00"), app_status_active),
        (seeded_candidates[1], v_qa, None, Decimal("1300.00"), app_status_active),
        (seeded_candidates[5], v_procesos, None, Decimal("1200.00"), app_status_active),
        (seeded_candidates[7], v_procesos, None, Decimal("1700.00"), app_status_active),
    ]

    seeded_applications: list[Application] = []
    for cand, vac, stage, sal, status in app_distributions:
        app_stmt = select(Application).where(
            Application.vacancy_id == vac.id,
            Application.candidate_id == cand.id,
        )
        app = (await session.execute(app_stmt)).scalar_one_or_none()
        if not app:
            app = Application(
                vacancy_id=vac.id,
                candidate_id=cand.id,
                current_stage_id=stage.id if stage else None,
                status_id=status.id,
                salary_expectation=sal,
                created_by=admin_id,
            )
            session.add(app)
            await session.flush()
        seeded_applications.append(app)

    # ── Interviewer Availability & Sample Interviews ─────────────────────────
    print("[*] Poblando disponibilidad de entrevistador y entrevistas...")

    # Recruiter availability: Monday to Friday, 9:00 - 17:00, 45 min
    for day in range(5):  # 0=Monday to 4=Friday
        stmt = select(InterviewerAvailability).where(
            InterviewerAvailability.user_id == rrhh_user.id,
            InterviewerAvailability.day_of_week == day,
        )
        if not (await session.execute(stmt)).scalar_one_or_none():
            session.add(
                InterviewerAvailability(
                    user_id=rrhh_user.id,
                    day_of_week=day,
                    start_time=time(9, 0),
                    end_time=time(17, 0),
                    slot_duration_min=45,
                    buffer_min=15,
                    created_by=admin_id,
                )
            )
    await session.flush()

    # Sample interview for application #4 (Andrea Cevallos en Entrevista cliente)
    int_status_sched = await get_or_create_param(session, type_="interview_status", code="scheduled", name="Agendada", user_id=admin_id)
    int_sched_hr = await get_or_create_param(session, type_="interview_scheduler", code="hr", name="RH", user_id=admin_id)

    app_interview = seeded_applications[3]  # candidate[3]
    int_stmt = select(Interview).where(Interview.application_id == app_interview.id)
    if not (await session.execute(int_stmt)).scalar_one_or_none():
        meeting_time = now + timedelta(days=2, hours=3)
        session.add(
            Interview(
                application_id=app_interview.id,
                process_stage_id=st_bg_5.id,
                interviewer_id=rrhh_user.id,
                scheduled_at=meeting_time,
                ends_at=meeting_time + timedelta(minutes=45),
                extra_email="m.andrade@bancog.com",
                teams_meeting_url="https://teams.microsoft.com/l/meetup-join/sample-seed-dev-meeting",
                teams_meeting_id="meeting-dev-12345",
                status_id=int_status_sched.id,
                scheduled_by_id=int_sched_hr.id,
                created_by=admin_id,
            )
        )
        await session.flush()

    # ── Talent Pool ───────────────────────────────────────────────────────────
    print("[*] Poblando banco de talentos (talent.talent_pool)...")
    for pool_cand in (seeded_candidates[4], seeded_candidates[7]):
        tp_stmt = select(TalentPool).where(TalentPool.candidate_id == pool_cand.id)
        if not (await session.execute(tp_stmt)).scalar_one_or_none():
            session.add(
                TalentPool(
                    candidate_id=pool_cand.id,
                    source_vacancy_id=v_fullstack.id,
                    created_by=admin_id,
                )
            )
    await session.flush()

    print("\n[+] Poblado de base de datos de desarrollo completado exitosamente.")


async def main() -> None:
    async with async_session_factory() as session:
        try:
            await seed(session)
            await session.commit()
            print("[+] Commit realizado correctamente.")
        except Exception as exc:
            await session.rollback()
            print(f"[!] Error durante el seed: {exc}")
            raise


if __name__ == "__main__":
    asyncio.run(main())