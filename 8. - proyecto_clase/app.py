"""
Orquestador Asíncrono de Entrenamiento
Presentación interactiva + demo funcional con Streamlit, Redis y Workers.

Ejecución local sugerida:
    docker-compose up -d
    streamlit run app.py

La app se conecta a Redis en localhost por defecto. En despliegue Docker,
puede cambiarse con variables de entorno REDIS_HOST y REDIS_PORT.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import redis
import streamlit as st
from redis.exceptions import ConnectionError, TimeoutError
from sklearn.datasets import load_iris


# ---------------------------------------------------------------------------
# Configuración general de Streamlit
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Orquestador Asíncrono de Entrenamiento",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="collapsed",
)

TOTAL_SLIDES = 23
QUEUE_NAME = os.getenv("REDIS_QUEUE", "training_queue")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
ACCENT_BLUE = "#005EB8"   # acento institucional sobrio
ACCENT_RED = "#D71920"    # acento institucional secundario


# ---------------------------------------------------------------------------
# Estado de sesión
# ---------------------------------------------------------------------------

if "slide" not in st.session_state:
    st.session_state.slide = 0

if "tracked_tasks" not in st.session_state:
    st.session_state.tracked_tasks = []

if "ui_logs" not in st.session_state:
    st.session_state.ui_logs = []


# ---------------------------------------------------------------------------
# Estilo visual
# ---------------------------------------------------------------------------

def inject_css() -> None:
    """Define un estilo blanco, sobrio, con acentos puntuales."""
    st.markdown(
        f"""
        <style>
        .stApp {{
            background: #FAFAFA;
            color: #1F2933;
        }}

        section.main > div {{
            padding-top: 2.2rem;
            padding-left: 4.5rem;
            padding-right: 4.5rem;
            padding-bottom: 2.0rem;
        }}

        h1, h2, h3 {{
            color: #111827;
            letter-spacing: -0.02em;
        }}

        h1 {{
            font-size: 2.55rem !important;
            font-weight: 720 !important;
            margin-bottom: 0.6rem !important;
        }}

        h2 {{
            font-size: 1.55rem !important;
            font-weight: 650 !important;
            margin-top: 1.0rem !important;
        }}

        h3 {{
            font-size: 1.18rem !important;
            font-weight: 620 !important;
        }}

        p, li {{
            font-size: 1.02rem;
            line-height: 1.55;
        }}

        .slide-box {{
            background: #FFFFFF;
            border: 1px solid #E5E7EB;
            border-left: 5px solid {ACCENT_BLUE};
            border-radius: 18px;
            padding: 1.35rem 1.55rem;
            margin: 0.6rem 0 1rem 0;
            box-shadow: 0 8px 22px rgba(15, 23, 42, 0.035);
        }}

        .muted {{
            color: #5E6A75;
            font-size: 0.98rem;
        }}

        .small {{
            color: #5E6A75;
            font-size: 0.88rem;
        }}

        .metric-card {{
            background: #FFFFFF;
            border: 1px solid #E5E7EB;
            border-radius: 16px;
            padding: 1rem 1.15rem;
            min-height: 115px;
        }}

        .diagram-node {{
            background: #FFFFFF;
            border: 1.5px solid #D0D7DE;
            border-bottom: 3px solid {ACCENT_BLUE};
            border-radius: 14px;
            padding: 1.0rem;
            text-align: center;
            min-height: 102px;
        }}

        .diagram-arrow {{
            text-align: center;
            color: {ACCENT_RED};
            font-size: 1.6rem;
            padding-top: 1.6rem;
        }}

        .footer-note {{
            color: #6B7280;
            font-size: 0.86rem;
            margin-top: 0.4rem;
        }}

        div.stButton > button {{
            background: #FFFFFF;
            color: #111827;
            border: 1px solid #D0D7DE;
            border-radius: 999px;
            padding: 0.42rem 1.05rem;
            box-shadow: none;
        }}

        div.stButton > button:hover {{
            border-color: {ACCENT_BLUE};
            color: {ACCENT_BLUE};
            background: #FFFFFF;
        }}

        div[data-testid="stMetricValue"] {{
            color: #111827;
        }}

        .code-caption {{
            color: #6B7280;
            font-size: 0.86rem;
            margin-top: -0.25rem;
            margin-bottom: 0.25rem;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Utilidades Redis
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def get_redis_client() -> redis.Redis:
    """Crea un cliente Redis cacheado por Streamlit."""
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True,
        socket_connect_timeout=1.5,
        socket_timeout=2.0,
    )


def redis_ping() -> Tuple[bool, str]:
    """Comprueba si Redis está disponible sin romper la aplicación."""
    try:
        client = get_redis_client()
        client.ping()
        return True, f"Redis disponible en {REDIS_HOST}:{REDIS_PORT}, db={REDIS_DB}."
    except (ConnectionError, TimeoutError, OSError) as exc:
        return False, (
            f"No fue posible conectar con Redis en {REDIS_HOST}:{REDIS_PORT}. "
            f"Detalle: {type(exc).__name__}. Levante Redis con docker-compose."
        )


def safe_redis_info() -> Dict[str, Any]:
    """Retorna un resumen mínimo del estado de Redis y de la cola."""
    ok, message = redis_ping()
    if not ok:
        return {
            "redis_ok": False,
            "message": message,
            "queue": QUEUE_NAME,
            "queue_length": None,
            "tracked_tasks": len(st.session_state.tracked_tasks),
        }

    client = get_redis_client()
    try:
        return {
            "redis_ok": True,
            "message": message,
            "queue": QUEUE_NAME,
            "queue_length": client.llen(QUEUE_NAME),
            "tracked_tasks": len(st.session_state.tracked_tasks),
        }
    except (ConnectionError, TimeoutError, OSError) as exc:
        return {
            "redis_ok": False,
            "message": f"Redis respondió inicialmente, pero falló al consultar cola: {exc}",
            "queue": QUEUE_NAME,
            "queue_length": None,
            "tracked_tasks": len(st.session_state.tracked_tasks),
        }


def iris_payload() -> Dict[str, Any]:
    """Prepara el dataset Iris serializado en JSON para enviarlo a Redis."""
    iris = load_iris(as_frame=True)
    df = iris.frame.copy()
    feature_cols = list(iris.feature_names)
    return {
        "dataset_name": "iris",
        "features": feature_cols,
        "target": "target",
        "data": df.to_dict(orient="records"),
        "target_names": list(iris.target_names),
    }


def enqueue_training_job(
    *,
    dataset: str = "iris",
    model: str = "logistic_regression",
    simulated_seconds: int = 3,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Encola un trabajo real en Redis.

    La app también escribe un estado inicial en Redis para que el monitoreo
    no dependa de que el Worker ya haya tomado el trabajo.
    """
    ok, message = redis_ping()
    if not ok:
        return False, message, {}

    task_id = str(uuid.uuid4())[:8]
    created_at = time.strftime("%Y-%m-%d %H:%M:%S")

    if dataset == "iris":
        payload = iris_payload()
    else:
        payload = iris_payload()

    task = {
        "task_id": task_id,
        "type": "train_model",
        "model": model,
        "created_at": created_at,
        "simulated_seconds": simulated_seconds,
        "payload": payload,
    }

    initial_status = {
        "task_id": task_id,
        "status": "queued",
        "progress": 0,
        "message": "Trabajo encolado desde Streamlit.",
        "created_at": created_at,
        "updated_at": created_at,
        "worker": None,
        "result": None,
    }

    client = get_redis_client()
    try:
        pipe = client.pipeline()
        pipe.set(f"task:{task_id}", json.dumps(initial_status, ensure_ascii=False))
        pipe.rpush(QUEUE_NAME, json.dumps(task, ensure_ascii=False))
        pipe.lpush(f"logs:{task_id}", f"[{created_at}] Streamlit encoló el trabajo {task_id}.")
        pipe.expire(f"task:{task_id}", 60 * 60)
        pipe.expire(f"logs:{task_id}", 60 * 60)
        pipe.execute()
    except (ConnectionError, TimeoutError, OSError) as exc:
        return False, f"No se pudo escribir en Redis: {exc}", {}

    if task_id not in st.session_state.tracked_tasks:
        st.session_state.tracked_tasks.insert(0, task_id)

    st.session_state.ui_logs.insert(0, f"{created_at} · Trabajo {task_id} encolado.")
    return True, f"Trabajo {task_id} encolado correctamente.", task


def get_task_status(task_id: str) -> Dict[str, Any]:
    """Lee el estado de un trabajo desde Redis."""
    ok, message = redis_ping()
    if not ok:
        return {
            "task_id": task_id,
            "status": "redis_unavailable",
            "progress": 0,
            "message": message,
            "result": None,
        }

    client = get_redis_client()
    raw = client.get(f"task:{task_id}")
    if raw is None:
        return {
            "task_id": task_id,
            "status": "unknown",
            "progress": 0,
            "message": "No existe estado en Redis para este task_id.",
            "result": None,
        }

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "task_id": task_id,
            "status": "invalid_state",
            "progress": 0,
            "message": raw,
            "result": None,
        }


def get_task_logs(task_id: str, limit: int = 8) -> List[str]:
    """Recupera logs de un trabajo desde Redis."""
    try:
        ok, _ = redis_ping()
        if not ok:
            return []
        client = get_redis_client()
        return list(reversed(client.lrange(f"logs:{task_id}", 0, limit - 1)))
    except Exception:
        return []


def refresh_task_panel(task_ids: List[str], *, seconds: int = 8) -> None:
    """
    Monitoreo simple por polling.

    Streamlit no es un runtime de eventos en tiempo real. Para una demo docente,
    este patrón con st.empty(), time.sleep() y st.rerun() es suficiente y legible.
    """
    panel = st.empty()
    for tick in range(seconds):
        with panel.container():
            rows = []
            for task_id in task_ids:
                status = get_task_status(task_id)
                rows.append(
                    {
                        "task_id": task_id,
                        "status": status.get("status"),
                        "progress": status.get("progress", 0),
                        "worker": status.get("worker"),
                        "message": status.get("message"),
                        "accuracy": (
                            status.get("result", {}) or {}
                        ).get("accuracy"),
                    }
                )

            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)

            avg_progress = 0
            if rows:
                avg_progress = int(sum(int(r.get("progress") or 0) for r in rows) / len(rows))
            st.progress(avg_progress, text=f"Avance agregado: {avg_progress}%")

            if task_ids:
                logs = []
                for task_id in task_ids[:3]:
                    logs.extend(get_task_logs(task_id, limit=4))
                if logs:
                    st.code("\n".join(logs[-10:]), language="text")

        if all(get_task_status(t).get("status") in {"completed", "failed"} for t in task_ids):
            break
        time.sleep(1)

    # Rerun final para que métricas y estado queden actualizados en la página.
    st.rerun()


# ---------------------------------------------------------------------------
# Componentes visuales
# ---------------------------------------------------------------------------

def slide_title(n: int, title: str, subtitle: Optional[str] = None) -> None:
    st.markdown(f"# {n}. {title}")
    if subtitle:
        st.markdown(f"<p class='muted'>{subtitle}</p>", unsafe_allow_html=True)
    st.divider()


def callout(text: str) -> None:
    st.markdown(f"<div class='slide-box'>{text}</div>", unsafe_allow_html=True)


def metric_cards(items: List[Tuple[str, str, str]]) -> None:
    cols = st.columns(len(items))
    for col, (title, value, note) in zip(cols, items):
        with col:
            st.markdown(
                f"""
                <div class='metric-card'>
                    <h3>{title}</h3>
                    <p style='font-size:1.45rem;margin:0.1rem 0 0.3rem 0;'><b>{value}</b></p>
                    <p class='small'>{note}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )


def architecture_diagram() -> None:
    cols = st.columns([1.1, 0.25, 1.1, 0.25, 1.1, 0.25, 1.1])
    labels = [
        ("Usuario", "Profesor o estudiante dispara un trabajo."),
        ("Streamlit", "Frontend que encola y consulta estado."),
        ("Redis", "Cola de trabajos y almacén de resultados."),
        ("Worker", "Proceso que entrena el modelo y persiste métricas."),
    ]

    positions = [0, 2, 4, 6]
    for idx, (title, desc) in zip(positions, labels):
        with cols[idx]:
            st.markdown(
                f"""
                <div class='diagram-node'>
                    <h3>{title}</h3>
                    <p class='small'>{desc}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
    for idx in [1, 3, 5]:
        with cols[idx]:
            st.markdown("<div class='diagram-arrow'>→</div>", unsafe_allow_html=True)

    st.markdown(
        "<p class='footer-note'>Resultado: la interfaz no se bloquea mientras el entrenamiento ocurre fuera del proceso web.</p>",
        unsafe_allow_html=True,
    )


def redis_status_block() -> None:
    info = safe_redis_info()
    if info["redis_ok"]:
        st.success(info["message"])
    else:
        st.warning(info["message"])
    st.json(info)


def tracked_tasks_table() -> None:
    tasks = st.session_state.tracked_tasks[:10]
    if not tasks:
        st.info("Todavía no hay trabajos registrados en esta sesión.")
        return

    rows = []
    for task_id in tasks:
        status = get_task_status(task_id)
        result = status.get("result") or {}
        rows.append(
            {
                "task_id": task_id,
                "estado": status.get("status"),
                "progreso": status.get("progress", 0),
                "worker": status.get("worker"),
                "accuracy": result.get("accuracy"),
                "modelo": result.get("model_path"),
                "mensaje": status.get("message"),
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Diapositivas
# ---------------------------------------------------------------------------

def slide_01() -> None:
    slide_title(1, "Orquestador Asíncrono de Entrenamiento")
    left, right = st.columns([1.3, 1])
    with left:
        st.markdown(
            """
            ## Demostración de Arquitectura para Ciencia de Datos

            Esta presentación no es una maqueta estática. Es una aplicación Streamlit que
            funciona como material de clase y, al mismo tiempo, como frontend de una mini
            arquitectura asíncrona con Redis y Workers en Python.
            """
        )
        callout(
            "<b>Asignatura:</b> Infraestructura para Ciencia de Datos<br>"
            "<b>Profesor:</b> Profesor<br>"
            f"<b>Fecha:</b> {date.today().strftime('%d-%m-%Y')}"
        )
    with right:
        metric_cards(
            [
                ("Modo", "PPTX web", "23 diapositivas navegables"),
                ("Demo", "Real", "Redis + Worker + Streamlit"),
            ]
        )
        st.markdown(
            r"""
            $$
            \text{Frontend} \neq \text{Entrenamiento}
            $$
            """
        )


def slide_02() -> None:
    slide_title(2, "Objetivos de la Demostración")
    st.markdown(
        """
        La demostración busca conectar conceptos de infraestructura con una situación
        frecuente en ciencia de datos: ejecutar tareas pesadas sin bloquear la interfaz.
        """
    )
    metric_cards(
        [
            ("Docker", "entorno reproducible", "Servicios aislados y levantados por composición."),
            ("Redis", "cola + estado", "Comunicación liviana entre procesos."),
            ("Workers", "cómputo externo", "Procesan trabajos fuera del frontend."),
            ("Escalabilidad", "horizontal", "Más workers para más trabajos."),
        ]
    )
    callout(
        "El punto pedagógico central es distinguir entre <b>solicitar</b> un trabajo, "
        "<b>procesarlo</b> y <b>monitorear</b> su resultado."
    )


def slide_03() -> None:
    slide_title(3, "El Problema", "Entrenamiento bloqueante en notebooks y prototipos web.")
    st.markdown(
        """
        En un flujo ingenuo, el usuario presiona un botón y el mismo proceso que atiende
        la interfaz ejecuta el entrenamiento. Esto es aceptable en una prueba pequeña,
        pero se vuelve frágil cuando crecen los datos, los modelos o los usuarios.
        """
    )
    st.code(
        """
# Patrón bloqueante
if st.button("Entrenar"):
    model.fit(X_train, y_train)        # La interfaz queda esperando.
    st.write(evaluate(model, X_test))  # El resultado aparece solo al final.
        """,
        language="python",
    )
    st.markdown(
        """
        Problemas: mala experiencia de usuario, pérdida de trazabilidad, riesgo de timeout,
        dificultad para paralelizar y nula separación entre interfaz y cómputo.
        """
    )


def slide_04() -> None:
    slide_title(4, "La Solución", "Arquitectura asíncrona con cola de trabajos.")
    architecture_diagram()
    st.markdown(
        """
        La interfaz deja de entrenar directamente. En su lugar, produce un mensaje con la
        especificación del trabajo. Redis lo conserva en una cola. Uno o más Workers lo
        consumen, entrenan el modelo y escriben el estado final para que Streamlit lo lea.
        """
    )
    st.code(
        "Usuario -> Streamlit -> Redis[cola] -> Worker -> Redis[resultado] -> Streamlit",
        language="text",
    )


def slide_05() -> None:
    slide_title(5, "Componente 1: Streamlit (Frontend)")
    st.markdown(
        """
        Streamlit cumple dos funciones: presentar la clase y operar como panel de control.
        En una arquitectura asíncrona, el frontend no debería asumir la carga de cómputo.
        Su responsabilidad es recibir entradas, encolar trabajos y consultar estados.
        """
    )
    st.code(
        """
# Responsabilidad del frontend
task_id = crear_identificador()
task = construir_mensaje(dataset, modelo, parametros)
redis.rpush("training_queue", json.dumps(task))
estado = redis.get(f"task:{task_id}")
        """,
        language="python",
    )
    callout(
        "Una interfaz robusta no necesita saber <i>dónde</i> se ejecuta el entrenamiento. "
        "Solo necesita producir una solicitud verificable y observar su evolución."
    )


def slide_06() -> None:
    slide_title(6, "Componente 2: Redis (Broker)")
    st.markdown(
        """
        Redis actúa como memoria compartida entre procesos. En esta demo cumple dos roles:
        cola de mensajes para trabajos pendientes y almacén rápido de estado para consultar
        resultados, progreso y logs.
        """
    )
    metric_cards(
        [
            ("Lista Redis", "training_queue", "Trabajos pendientes con RPUSH/BLPOP."),
            ("Clave estado", "task:{id}", "JSON con progreso, worker y métricas."),
            ("Logs", "logs:{id}", "Eventos recientes del procesamiento."),
        ]
    )
    st.code(
        """
RPUSH training_queue '{"task_id": "...", "type": "train_model", ...}'
BLPOP training_queue 0
SET task:abc123 '{"status": "completed", "accuracy": 0.97}'
        """,
        language="bash",
    )


def slide_07() -> None:
    slide_title(7, "Redis: Qué Es", "Servidor de estructuras de datos en memoria.")
    st.markdown(
        """
        Redis significa **Remote Dictionary Server**. En términos prácticos, es un
        servidor de datos que vive principalmente en memoria RAM y permite que distintas
        aplicaciones lean y escriban información muy rápido usando claves.

        Aunque suele presentarse como una base de datos clave-valor, Redis es más preciso
        si se entiende como un **servidor de estructuras de datos**. Cada clave puede
        guardar strings, listas, hashes, sets, sorted sets, streams y otros tipos
        pensados para resolver problemas de coordinación entre procesos.
        """
    )
    metric_cards(
        [
            ("Memoria", "baja latencia", "Las operaciones comunes se resuelven en milisegundos."),
            ("Estructuras", "listas, hashes, streams", "No almacena solo texto plano: modela patrones de uso."),
            ("Red", "cliente-servidor", "Python, Streamlit y Workers se conectan al mismo servicio."),
            ("Persistencia", "opcional", "Puede escribir snapshots o AOF en disco si se configura."),
        ]
    )

    left, right = st.columns([1.1, 1])
    with left:
        st.markdown(
            """
            **Modelo mental:** Redis es una libreta compartida, muy rápida y accesible por
            red, donde cada componente del sistema deja mensajes o estados que otro
            componente puede consumir.

            No reemplaza necesariamente a PostgreSQL, MySQL o un data lake. Su fortaleza
            está en datos operacionales pequeños, temporales y de acceso frecuente:
            colas, sesiones, contadores, cache, locks, eventos y estados de tareas.
            """
        )
    with right:
        st.code(
            """
SET curso:estado "activo"
GET curso:estado

HSET task:abc123 status queued progress 0
HGETALL task:abc123

RPUSH training_queue "{...job...}"
BLPOP training_queue 0
            """,
            language="bash",
        )

    callout(
        "La idea clave: Redis no se usa aquí para guardar el dataset histórico, sino para "
        "<b>coordinar ejecución</b> entre procesos que trabajan a distinto ritmo."
    )


def slide_08() -> None:
    slide_title(8, "Redis: Para Qué Sirve", "Patrones típicos en infraestructura de datos.")
    st.markdown(
        """
        Redis aparece en arquitecturas modernas porque resuelve bien problemas donde se
        necesita velocidad, coordinación y estado compartido de corta o mediana duración.
        Su API es simple, pero sus estructuras permiten implementar patrones muy usados
        en sistemas distribuidos.
        """
    )

    left, right = st.columns([1, 1])
    with left:
        st.markdown(
            """
            **Cache:** guardar resultados calculados para evitar repetir trabajo costoso.

            **Colas de trabajo:** separar quien produce una tarea de quien la procesa.

            **Estado de sesiones:** conservar información temporal de usuarios o procesos.

            **Contadores y rate limits:** medir eventos y limitar frecuencia de solicitudes.
            """
        )
    with right:
        st.markdown(
            """
            **Pub/Sub:** distribuir eventos simples entre productores y suscriptores.

            **Streams:** manejar eventos con historial, grupos de consumidores y
            acknowledgements.

            **Locks distribuidos:** coordinar acceso a recursos compartidos con cuidado.

            **Rankings:** mantener ordenamientos eficientes con sorted sets.
            """
        )

    st.code(
        """
# Cache
SET resultado:modelo:iris '{"accuracy": 0.97}' EX 3600

# Cola simple
RPUSH training_queue '{"task_id": "abc123"}'
BLPOP training_queue 0

# Contador
INCR metric:jobs_completed

# Stream con historial
XADD training_events * task_id abc123 status completed
        """,
        language="bash",
    )

    callout(
        "En ciencia de datos, Redis suele ubicarse entre la interfaz, los jobs y los "
        "servicios de monitoreo: no entrena modelos, pero ayuda a que el sistema que los "
        "entrena sea observable, escalable y desacoplado."
    )


def slide_09() -> None:
    slide_title(9, "Por Qué Redis se Usa en Este Contexto")
    st.markdown(
        """
        En esta demo, Redis es el contrato de comunicación entre Streamlit y los Workers.
        Streamlit atiende al usuario y produce solicitudes; el Worker consume solicitudes,
        entrena modelos y deja resultados. Redis queda al medio como punto de coordinación.
        """
    )

    redis_mapping = pd.DataFrame(
        [
            {
                "Elemento Redis": "training_queue",
                "Tipo": "Lista",
                "Quién escribe": "Streamlit",
                "Quién lee": "Worker",
                "Propósito": "Mantener trabajos pendientes en orden de llegada.",
            },
            {
                "Elemento Redis": "task:{task_id}",
                "Tipo": "String JSON",
                "Quién escribe": "Streamlit / Worker",
                "Quién lee": "Streamlit",
                "Propósito": "Publicar estado, progreso, worker asignado y resultado.",
            },
            {
                "Elemento Redis": "logs:{task_id}",
                "Tipo": "Lista",
                "Quién escribe": "Streamlit / Worker",
                "Quién lee": "Streamlit",
                "Propósito": "Guardar eventos recientes para trazabilidad de la demo.",
            },
        ]
    )
    st.dataframe(redis_mapping, use_container_width=True, hide_index=True)

    metric_cards(
        [
            ("Desacopla", "UI y cómputo", "Streamlit no queda atrapado entrenando modelos."),
            ("Coordina", "1 cola común", "Varios Workers pueden consumir trabajos pendientes."),
            ("Observa", "estado + logs", "La app puede mostrar progreso sin tocar el proceso Worker."),
            ("Recupera", "estado temporal", "Una recarga de la interfaz no borra lo que está en Redis."),
        ]
    )

    st.code(
        """
Streamlit:
  SET   task:{id}        -> estado inicial queued
  RPUSH training_queue   -> trabajo serializado

Worker:
  BLPOP training_queue   -> espera hasta recibir un trabajo
  SET   task:{id}        -> processing / completed / failed
  LPUSH logs:{id}        -> eventos de ejecución
        """,
        language="text",
    )

    callout(
        "<b>Decisión de diseño:</b> una lista Redis con <code>RPUSH/BLPOP</code> es suficiente "
        "para una clase porque muestra asincronía con poco código. Para producción, donde se "
        "requieren acknowledgements y reintentos robustos, convendría evaluar Redis Streams, "
        "Celery, RQ o una cola administrada."
    )


def slide_10() -> None:
    slide_title(10, "Componente 3: Worker (Backend)")
    st.markdown(
        """
        El Worker es un proceso especializado. No renderiza UI, no atiende navegación y
        no depende del ciclo de recarga de Streamlit. Su tarea es esperar mensajes,
        ejecutar entrenamiento y persistir resultados.
        """
    )
    st.code(
        """
while True:
    _, raw_task = redis.blpop("training_queue")
    task = json.loads(raw_task)
    marcar_como_processing(task_id)
    entrenar_modelo(task)
    guardar_resultado(task_id)
        """,
        language="python",
    )
    callout(
        "La idea de fondo es simple: <b>separar la latencia humana de la latencia computacional</b>. "
        "El usuario no debe quedar atrapado dentro del tiempo de entrenamiento."
    )


def slide_11() -> None:
    slide_title(11, "docker-compose.yml")
    st.markdown(
        """
        El archivo de composición levanta Redis y el Worker. Streamlit se ejecuta localmente
        con `streamlit run app.py`, aunque se incluye un Dockerfile opcional para contenerizarlo.
        """
    )
    st.code(
        """
services:
  redis:
    image: redis:7-alpine
    container_name: clase-redis
    ports:
      - "6379:6379"
    command: ["redis-server", "--appendonly", "yes"]
    volumes:
      - redis-data:/data

  worker:
    build:
      context: ./worker
    container_name: clase-worker
    environment:
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_QUEUE=training_queue
      - MODEL_DIR=/models
    volumes:
      - ./models:/models
    depends_on:
      - redis
    restart: unless-stopped

volumes:
  redis-data:
        """,
        language="yaml",
    )


def slide_12() -> None:
    slide_title(12, "Código del Worker (worker.py)")
    st.markdown(
        """
        El Worker usa `BLPOP`, por lo que queda bloqueado hasta que aparezca un trabajo.
        Cuando lo recibe, reconstruye el dataset, entrena un modelo de scikit-learn y
        escribe métricas en Redis.
        """
    )
    st.code(
        """
while True:
    queue, raw_task = r.blpop(QUEUE_NAME, timeout=0)
    task = json.loads(raw_task)
    task_id = task["task_id"]

    update_status(task_id, "processing", 10, "Worker tomó el trabajo.")
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25)
    model = LogisticRegression(max_iter=500)
    model.fit(X_train, y_train)

    accuracy = accuracy_score(y_test, model.predict(X_test))
    joblib.dump(model, f"/models/{task_id}.joblib")
    update_status(task_id, "completed", 100, "Entrenamiento completado.", result)
        """,
        language="python",
    )


def slide_13() -> None:
    slide_title(13, "Código de Encolado en Streamlit")
    st.markdown(
        """
        Streamlit genera un identificador único, prepara el dataset Iris en JSON y publica
        el trabajo en Redis. También crea un estado inicial para que el usuario vea el
        trabajo incluso antes de que un Worker lo tome.
        """
    )
    st.code(
        """
task_id = str(uuid.uuid4())[:8]

task = {
    "task_id": task_id,
    "type": "train_model",
    "model": "logistic_regression",
    "payload": iris_payload(),
}

r.set(f"task:{task_id}", json.dumps({"status": "queued", "progress": 0}))
r.rpush("training_queue", json.dumps(task))
        """,
        language="python",
    )


def slide_14() -> None:
    slide_title(14, "Código de Monitoreo")
    st.markdown(
        """
        El monitoreo se implementa con polling: cada segundo la interfaz consulta Redis.
        En producción se podrían usar WebSockets, eventos o un panel externo, pero para
        esta clase el patrón es transparente y suficiente.
        """
    )
    st.code(
        """
placeholder = st.empty()

for _ in range(10):
    status = json.loads(r.get(f"task:{task_id}"))
    placeholder.json(status)

    if status["status"] in {"completed", "failed"}:
        break

    time.sleep(1)
        """,
        language="python",
    )
    st.latex(r"\text{Polling} = \{t_0, t_1, t_2, ...\} \rightarrow \text{consulta de estado}")


def slide_15() -> None:
    slide_title(15, "Demo en Vivo - Parte 1: Levantar el Sistema")
    st.markdown(
        """
        Antes de iniciar la demo, levante Redis y el Worker. El frontend puede seguir
        funcionando aunque Redis no esté disponible, pero las acciones de encolado
        mostrarán una advertencia controlada.
        """
    )
    st.code(
        """
pip install -r requirements.txt
docker-compose up -d
streamlit run app.py
        """,
        language="bash",
    )

    if st.button("Comprobar conexión con Redis", key="check_redis"):
        redis_status_block()
    else:
        st.markdown("<p class='muted'>Presione el botón para comprobar Redis desde la app.</p>", unsafe_allow_html=True)


def slide_16() -> None:
    slide_title(16, "Demo en Vivo - Parte 2: Encolar un Trabajo")
    st.markdown(
        """
        Esta diapositiva ejecuta el flujo real: Streamlit serializa Iris, encola el trabajo
        en Redis y monitorea el estado hasta que el Worker escribe las métricas.
        """
    )

    left, right = st.columns([1, 1])
    with left:
        st.subheader("Estado de Redis")
        redis_status_block()

        if st.button("Entrenar modelo Iris", key="train_iris"):
            ok, message, task = enqueue_training_job(simulated_seconds=3)
            if ok:
                st.success(message)
                refresh_task_panel([task["task_id"]], seconds=10)
            else:
                st.error(message)

    with right:
        st.subheader("Trabajos observados")
        tracked_tasks_table()

        if st.session_state.tracked_tasks:
            selected = st.session_state.tracked_tasks[0]
            st.markdown(f"**Logs recientes del trabajo `{selected}`**")
            logs = get_task_logs(selected, limit=8)
            st.code("\n".join(logs) if logs else "Sin logs todavía.", language="text")


def slide_17() -> None:
    slide_title(17, "Demo en Vivo - Parte 3: Escalar Horizontalmente")
    st.markdown(
        """
        La escalabilidad horizontal consiste en aumentar el número de procesos Worker
        que consumen de la misma cola. La app no escala contenedores por sí sola, pero
        puede encolar varios trabajos para que la diferencia se observe al levantar más
        Workers.
        """
    )
    st.code("docker-compose up --scale worker=2 -d", language="bash")

    col_a, col_b = st.columns([1, 1.2])
    with col_a:
        redis_status_block()
        if st.button("Encolar 5 trabajos simultáneos", key="enqueue_5"):
            created = []
            for i in range(5):
                ok, message, task = enqueue_training_job(simulated_seconds=4)
                if ok:
                    created.append(task["task_id"])
                else:
                    st.error(message)
                    break

            if created:
                st.success(f"Trabajos encolados: {', '.join(created)}")
                refresh_task_panel(created, seconds=16)

    with col_b:
        st.subheader("Monitoreo de lote")
        tracked_tasks_table()
        st.markdown(
            """
            Si hay dos Workers activos, dos trabajos pueden pasar a `processing` casi al
            mismo tiempo. Con un solo Worker, la cola se drena secuencialmente.
            """
        )


def slide_18() -> None:
    slide_title(18, "Demo en Vivo - Parte 4: Tolerancia a Fallas")
    st.markdown(
        """
        Conceptualmente, una cola permite desacoplar la vida del frontend de la vida de los
        Workers. Si un Worker no está activo, los trabajos quedan pendientes en Redis hasta
        que otro Worker los consuma.
        """
    )
    callout(
        "<b>Advertencia metodológica importante:</b> con una lista Redis y <code>BLPOP</code>, "
        "si el Worker muere <i>después</i> de extraer el trabajo y <i>antes</i> de guardar resultado, "
        "ese trabajo puede perderse. Para tolerancia real se usaría Redis Streams, Celery, RQ "
        "o un patrón de cola pendiente con acknowledgements."
    )

    left, right = st.columns([1, 1])
    with left:
        redis_status_block()
        st.code(
            """
# Demostración conceptual
docker-compose stop worker
# En la app: encolar trabajo
docker-compose start worker
# El trabajo pendiente será tomado al volver el Worker.
            """,
            language="bash",
        )
        if st.button("Encolar trabajo de prueba para tolerancia", key="fault_demo"):
            ok, message, task = enqueue_training_job(simulated_seconds=6)
            if ok:
                st.success(message)
                st.info(
                    "Ahora puede detener e iniciar el Worker desde otra terminal para discutir el comportamiento."
                )
            else:
                st.error(message)

    with right:
        st.subheader("Estado y logs")
        tracked_tasks_table()
        if st.session_state.tracked_tasks:
            selected = st.session_state.tracked_tasks[0]
            st.code("\n".join(get_task_logs(selected, limit=10)) or "Sin logs todavía.", language="text")


def slide_19() -> None:
    slide_title(19, "Conexión con la Teoría del Curso")
    st.markdown(
        """
        La demo funciona como punto de convergencia entre varios bloques de la asignatura.
        No es solo una herramienta de software; es una representación ejecutable de
        principios de infraestructura.
        """
    )
    metric_cards(
        [
            ("Semana 3", "Escalabilidad", "Más Workers, mayor capacidad de procesamiento."),
            ("Semana 5", "Contenedores", "Servicios reproducibles y aislados."),
            ("Semana 9", "Asincronía", "Colas, polling, estados y desacoplamiento."),
            ("Semana 10", "Distribución", "Procesos autónomos coordinados por broker."),
        ]
    )


def slide_20() -> None:
    slide_title(20, "Ventajas de esta Arquitectura")
    st.markdown(
        """
        La arquitectura aporta valor cuando la tarea excede la comodidad de una ejecución
        interactiva directa. Su ventaja no está en hacer más simple el primer prototipo,
        sino en hacerlo más robusto cuando se aproxima a condiciones reales.
        """
    )
    st.markdown(
        """
        **Desacoplamiento:** la interfaz no depende del tiempo de entrenamiento.

        **Resiliencia:** si el frontend se recarga, el estado sigue en Redis.

        **Escalabilidad:** se agregan Workers sin reescribir la interfaz.

        **Reproducibilidad:** Docker define servicios y dependencias de ejecución.

        **Observabilidad:** cada tarea tiene estado, progreso, métricas y logs.
        """
    )


def slide_21() -> None:
    slide_title(21, "Limitaciones y Cuándo No Usarla")
    st.markdown(
        """
        Esta arquitectura no es una solución universal. Introduce más piezas móviles:
        broker, serialización, monitoreo, Workers, volúmenes y manejo de fallos.
        """
    )
    callout(
        "No conviene para operaciones triviales, sistemas transaccionales de ultra baja "
        "latencia o prototipos donde el costo operativo supere claramente el beneficio."
    )
    st.markdown(
        """
        Una decisión madura exige preguntar: ¿el entrenamiento tarda lo suficiente como
        para justificar la cola?, ¿hay múltiples usuarios?, ¿necesitamos trazabilidad?,
        ¿el proceso debe sobrevivir a recargas de interfaz?, ¿la carga será variable?
        """
    )


def slide_22() -> None:
    slide_title(22, "Actividad para Estudiantes")
    st.markdown(
        """
        El desafío no es copiar la arquitectura, sino modificarla de manera controlada.
        Cada grupo debe cambiar una pieza y justificar qué propiedad del sistema mejora.
        """
    )
    st.markdown(
        """
        **Opción A:** guardar el modelo entrenado en un volumen compartido y exponer la
        ruta desde Redis.

        **Opción B:** agregar un segundo tipo de Worker que use otra librería, por ejemplo
        XGBoost, LightGBM o un pipeline de preprocesamiento.

        **Opción C:** reemplazar `BLPOP` por Redis Streams para introducir acknowledgements
        y discutir tolerancia a fallos real.

        **Opción D:** crear una vista de monitoreo con tiempos de espera, duración de
        entrenamiento y throughput.
        """
    )


def slide_23() -> None:
    slide_title(23, "Cierre y Transición")
    st.markdown(
        """
        La arquitectura asíncrona permite que un sistema de ciencia de datos deje de ser
        una secuencia manual y pase a comportarse como una infraestructura operable.
        """
    )
    callout(
        "Aprendizaje central: <b>un modelo no vive solo en el notebook</b>. "
        "Necesita mecanismos de ejecución, monitoreo, aislamiento, persistencia y recuperación."
    )
    st.markdown(
        """
        En la siguiente etapa, esta base puede extenderse hacia pipelines más completos:
        almacenamiento de modelos, versionamiento, evaluación continua, despliegue de
        endpoints y observabilidad operacional.
        """
    )


SLIDES = [
    slide_01,
    slide_02,
    slide_03,
    slide_04,
    slide_05,
    slide_06,
    slide_07,
    slide_08,
    slide_09,
    slide_10,
    slide_11,
    slide_12,
    slide_13,
    slide_14,
    slide_15,
    slide_16,
    slide_17,
    slide_18,
    slide_19,
    slide_20,
    slide_21,
    slide_22,
    slide_23,
]


# ---------------------------------------------------------------------------
# Navegación
# ---------------------------------------------------------------------------

def navigation_controls() -> None:
    st.divider()
    left, center, right = st.columns([1, 2, 1])

    with left:
        if st.button("← Anterior", disabled=st.session_state.slide <= 0, use_container_width=True):
            st.session_state.slide = max(0, st.session_state.slide - 1)
            st.rerun()

    with center:
        current = st.session_state.slide + 1
        st.markdown(
            f"<p style='text-align:center;color:#6B7280;'>Diapositiva {current} de {TOTAL_SLIDES}</p>",
            unsafe_allow_html=True,
        )
        st.progress(current / TOTAL_SLIDES)

    with right:
        if st.button("Siguiente →", disabled=st.session_state.slide >= TOTAL_SLIDES - 1, use_container_width=True):
            st.session_state.slide = min(TOTAL_SLIDES - 1, st.session_state.slide + 1)
            st.rerun()


def sidebar_navigation() -> None:
    with st.sidebar:
        st.markdown("### Navegación")
        selected = st.selectbox(
            "Ir a diapositiva",
            options=list(range(TOTAL_SLIDES)),
            index=st.session_state.slide,
            format_func=lambda i: f"{i + 1}.",
        )
        if selected != st.session_state.slide:
            st.session_state.slide = selected
            st.rerun()

        st.divider()
        st.markdown("### Sistema")
        info = safe_redis_info()
        if info["redis_ok"]:
            st.success("Redis activo")
        else:
            st.warning("Redis no disponible")
        st.caption(f"Cola: {QUEUE_NAME}")
        st.caption(f"Host: {REDIS_HOST}:{REDIS_PORT}")


def main() -> None:
    inject_css()
    sidebar_navigation()

    # Render de la diapositiva actual.
    SLIDES[st.session_state.slide]()

    navigation_controls()


if __name__ == "__main__":
    main()
