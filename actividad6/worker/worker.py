"""
Worker de entrenamiento para la Actividad 6.

Este archivo representa el proceso que queda escuchando una cola Redis.
Su responsabilidad NO es mostrar interfaz, sino:

1. Esperar trabajos en Redis.
2. Reconstruir el dataset recibido desde Streamlit.
3. Entrenar un modelo de scikit-learn.
4. Guardar el modelo entrenado como archivo .joblib.
5. Escribir en Redis el estado final, las métricas y la ruta del modelo.

Esto implementa la OPCIÓN A:

"Guardar el modelo entrenado en un volumen compartido y exponer la ruta desde Redis."

La gracia es que el modelo no queda perdido dentro del proceso Python.
Queda persistido como archivo en una carpeta compartida entre Docker y tu computador.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import joblib
import pandas as pd
import redis
from redis.exceptions import ConnectionError, TimeoutError
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split


# ---------------------------------------------------------------------------
# Configuración desde variables de entorno
# ---------------------------------------------------------------------------

# Dentro de Docker, el host de Redis es "redis" porque así se llama
# el servicio en docker-compose.yml.
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

# Nombre de la cola Redis desde donde el worker consumirá trabajos.
QUEUE_NAME = os.getenv("REDIS_QUEUE", "training_queue")

# Carpeta interna del contenedor donde se guardarán los modelos.
# En docker-compose.yml la configuramos como /models.
MODEL_DIR = Path(os.getenv("MODEL_DIR", "/models"))

# Ruta equivalente desde el computador anfitrión.
# Esto sirve solo para mostrar una ruta más entendible en Streamlit.
# Ejemplo:
#   dentro del contenedor: /models/abc123.joblib
#   en tu Mac:             ./models/abc123.joblib
MODEL_HOST_PREFIX = os.getenv("MODEL_HOST_PREFIX", "./models")

# Identificador del worker.
# Si tienes varios workers, esto ayuda a saber cuál procesó cada trabajo.
WORKER_ID = os.getenv("WORKER_ID", socket.gethostname())

# Crea la carpeta de modelos si no existe.
# Esto evita errores cuando el worker intente guardar el archivo.
MODEL_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Utilidades generales
# ---------------------------------------------------------------------------

def now() -> str:
    """
    Retorna la fecha y hora actual como string.

    Se usa para logs y estados en Redis.
    """
    return time.strftime("%Y-%m-%d %H:%M:%S")


def connect_to_redis() -> redis.Redis:
    """
    Intenta conectarse a Redis.

    Si Redis todavía no está disponible, el worker espera y reintenta.
    Esto es útil porque a veces Docker levanta primero el worker y luego Redis.
    """
    while True:
        try:
            client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=5,
            )

            # Verifica que Redis realmente responda.
            client.ping()

            print(
                f"[{now()}] Worker {WORKER_ID} conectado a Redis "
                f"en {REDIS_HOST}:{REDIS_PORT}.",
                flush=True,
            )

            return client

        except (ConnectionError, TimeoutError, OSError) as exc:
            print(
                f"[{now()}] Redis no disponible: {exc}. Reintentando...",
                flush=True,
            )
            time.sleep(2)


def log(task_id: str, message: str) -> None:
    """
    Guarda un log del trabajo.

    El log se escribe en dos lugares:

    1. Consola del worker:
       Sirve para verlo con:
       docker compose logs -f worker

    2. Redis:
       Se guarda en logs:{task_id}, para que Streamlit pueda mostrarlo.
    """
    line = f"[{now()}] worker={WORKER_ID} · {message}"

    print(line, flush=True)

    try:
        r.lpush(f"logs:{task_id}", line)
        r.expire(f"logs:{task_id}", 60 * 60)
    except Exception:
        # Los logs no deberían botar el entrenamiento.
        # Si falla escribir el log, el worker sigue trabajando.
        pass


def update_status(
    task_id: str,
    status: str,
    progress: int,
    message: str,
    result: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Actualiza el estado de una tarea en Redis.

    Redis guardará un JSON en la clave:

        task:{task_id}

    Ejemplo:

        task:abc123

    Streamlit lee esa misma clave para mostrar:
    - estado
    - progreso
    - mensaje
    - worker
    - accuracy
    - ruta del modelo guardado

    Esta función es clave para la opción A, porque el worker publica en Redis
    la ruta donde quedó guardado el modelo.
    """
    payload = {
        "task_id": task_id,
        "status": status,
        "progress": progress,
        "message": message,
        "worker": WORKER_ID,
        "updated_at": now(),
        "result": result,
    }

    r.set(
        f"task:{task_id}",
        json.dumps(payload, ensure_ascii=False, default=str),
    )

    # El estado queda disponible durante 1 hora.
    # Para una demo docente es suficiente.
    r.expire(f"task:{task_id}", 60 * 60)


def save_model_artifact(
    *,
    task_id: str,
    model: LogisticRegression,
    payload: Dict[str, Any],
    feature_cols: list[str],
    target_col: str,
    accuracy: float,
) -> Dict[str, str]:
    """
    Guarda el modelo entrenado como archivo .joblib.

    Esta función implementa directamente la parte de:

        "guardar el modelo entrenado en un volumen compartido"

    El modelo se guarda en MODEL_DIR, que dentro del contenedor es:

        /models

    Pero como docker-compose.yml monta:

        ./models:/models

    Entonces el archivo queda visible en tu computador en:

        actividad6/models/

    Además, esta función retorna las rutas para guardarlas luego en Redis.
    """

    # Nombre único del archivo del modelo.
    # Usamos task_id para que cada entrenamiento genere su propio archivo.
    model_filename = f"{task_id}.joblib"

    # Ruta dentro del contenedor Docker.
    container_model_path = MODEL_DIR / model_filename

    # Ruta equivalente desde tu Mac.
    host_model_path = f"{MODEL_HOST_PREFIX.rstrip('/')}/{model_filename}"

    # No guardamos solo el modelo.
    # Guardamos un "paquete" con el modelo + metadatos útiles.
    # Esto es mejor porque después sabemos con qué columnas fue entrenado.
    artifact = {
        "task_id": task_id,
        "model": model,
        "dataset_name": payload.get("dataset_name", "desconocido"),
        "features": feature_cols,
        "target": target_col,
        "target_names": payload.get("target_names", []),
        "accuracy": round(accuracy, 4),
        "created_at": now(),
    }

    # joblib.dump serializa el objeto Python en disco.
    # Este archivo queda persistido en el volumen compartido.
    joblib.dump(artifact, container_model_path)

    # Retornamos información para publicarla en Redis.
    return {
        "model_filename": model_filename,
        "model_path": str(container_model_path),
        "model_path_container": str(container_model_path),
        "model_path_host": host_model_path,
    }


# ---------------------------------------------------------------------------
# Entrenamiento
# ---------------------------------------------------------------------------

def train_from_task(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ejecuta el entrenamiento a partir de un trabajo recibido desde Redis.

    El trabajo contiene:
    - task_id
    - tipo de trabajo
    - modelo solicitado
    - payload con dataset Iris serializado en JSON

    Flujo:
    1. Reconstruir DataFrame.
    2. Separar X e y.
    3. Dividir train/test.
    4. Entrenar LogisticRegression.
    5. Evaluar accuracy.
    6. Guardar modelo en /models.
    7. Publicar resultado en Redis.
    """

    task_id = task["task_id"]
    simulated_seconds = int(task.get("simulated_seconds", 3))

    # Streamlit envía el dataset como JSON.
    payload = task["payload"]

    # Reconstruimos el DataFrame desde la lista de registros.
    df = pd.DataFrame(payload["data"])

    # Columnas predictoras.
    feature_cols = payload["features"]

    # Columna objetivo.
    target_col = payload["target"]

    X = df[feature_cols]
    y = df[target_col]

    update_status(
        task_id,
        "processing",
        20,
        "Dataset reconstruido desde JSON.",
    )

    log(
        task_id,
        f"Dataset {payload.get('dataset_name', 'desconocido')} "
        f"con {len(df)} filas.",
    )

    # Simulación de trabajo computacional.
    # Esto no es necesario para entrenar Iris, pero sirve para que la demo
    # muestre progreso y no termine instantáneamente.
    for step in range(max(simulated_seconds, 1)):
        progress = 25 + int((step / max(simulated_seconds, 1)) * 45)

        update_status(
            task_id,
            "processing",
            progress,
            f"Preparando entrenamiento, paso {step + 1}.",
        )

        log(
            task_id,
            f"Preparando entrenamiento, paso {step + 1}/{simulated_seconds}.",
        )

        time.sleep(1)

    # División train/test.
    # stratify=y mantiene proporciones similares de clases en train y test.
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.25,
        random_state=42,
        stratify=y,
    )

    update_status(
        task_id,
        "processing",
        75,
        "Entrenando LogisticRegression.",
    )

    log(task_id, "Entrenando modelo LogisticRegression.")

    # Modelo simple para la demo.
    model = LogisticRegression(max_iter=500)

    # Entrenamiento real del modelo.
    model.fit(X_train, y_train)

    # Predicción sobre test.
    y_pred = model.predict(X_test)

    # Métrica principal.
    accuracy = float(accuracy_score(y_test, y_pred))

    # Reporte más completo por clase.
    report = classification_report(
        y_test,
        y_pred,
        output_dict=True,
        zero_division=0,
    )

    # -----------------------------------------------------------------------
    # OPCIÓN A:
    # Guardar el modelo en volumen compartido.
    # -----------------------------------------------------------------------
    model_paths = save_model_artifact(
        task_id=task_id,
        model=model,
        payload=payload,
        feature_cols=feature_cols,
        target_col=target_col,
        accuracy=accuracy,
    )

    # Resultado que quedará publicado en Redis.
    # Aquí se expone la ruta del modelo.
    result = {
        "accuracy": round(accuracy, 4),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "classes": payload.get("target_names", []),
        "classification_report": report,

        # Rutas del archivo guardado:
        # - model_path_container: ruta dentro del contenedor.
        # - model_path_host: ruta visible desde tu Mac.
        **model_paths,
    }

    update_status(
        task_id,
        "completed",
        100,
        "Entrenamiento completado y modelo guardado en volumen compartido.",
        result,
    )

    log(
        task_id,
        f"Trabajo completado. Accuracy={accuracy:.4f}. "
        f"Modelo={model_paths['model_path_container']}",
    )

    return result


def process_task(raw_task: str) -> None:
    """
    Procesa un trabajo crudo leído desde Redis.

    Redis entrega el trabajo como string JSON.
    Esta función lo convierte a diccionario y maneja errores.
    """
    task = json.loads(raw_task)
    task_id = task["task_id"]

    try:
        update_status(
            task_id,
            "processing",
            10,
            "Worker tomó el trabajo.",
        )

        log(task_id, "Worker tomó el trabajo desde la cola.")

        if task.get("type") != "train_model":
            raise ValueError(
                f"Tipo de trabajo no soportado: {task.get('type')}"
            )

        train_from_task(task)

    except Exception as exc:
        error_payload = {
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }

        update_status(
            task_id,
            "failed",
            100,
            f"Fallo en Worker: {exc}",
            error_payload,
        )

        log(task_id, f"Fallo: {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Loop principal del worker
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Cliente Redis global.
    # Las funciones log(), update_status() y process_task() lo usan.
    r = connect_to_redis()

    print(
        f"[{now()}] Worker {WORKER_ID} escuchando cola '{QUEUE_NAME}'.",
        flush=True,
    )

    while True:
        try:
            # BLPOP bloquea el proceso hasta que llegue un trabajo.
            # Es decir, el worker queda esperando sin consumir CPU.
            item = r.blpop(QUEUE_NAME, timeout=0)

            if item is None:
                continue

            _, raw_task = item

            process_task(raw_task)

        except KeyboardInterrupt:
            print("Worker detenido por el usuario.", flush=True)
            sys.exit(0)

        except (ConnectionError, TimeoutError, OSError) as exc:
            print(
                f"[{now()}] Conexión Redis perdida: {exc}. Reconectando...",
                flush=True,
            )
            r = connect_to_redis()

        except Exception as exc:
            print(
                f"[{now()}] Error no controlado en loop principal: {exc}",
                flush=True,
            )
            time.sleep(1)