"""
Worker XGBoost para la Actividad 6.

Este segundo worker implementa la Opción B:

"Agregar un segundo tipo de Worker que use otra librería, por ejemplo XGBoost."

Arquitectura:

- Streamlit encola un trabajo XGBoost en Redis.
- Este worker escucha una cola propia llamada xgboost_queue.
- Cuando llega una tarea, entrena un modelo XGBClassifier.
- Guarda el modelo entrenado en el volumen compartido /models.
- Publica en Redis el accuracy, el reporte y la ruta del modelo guardado.

Este worker corre en paralelo al worker original de LogisticRegression.
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
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier


# ---------------------------------------------------------------------------
# Configuración desde variables de entorno
# ---------------------------------------------------------------------------

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

# Este worker NO escucha training_queue.
# Escucha una cola separada para trabajos XGBoost.
QUEUE_NAME = os.getenv("REDIS_QUEUE", "xgboost_queue")

# Carpeta interna del contenedor donde se guardan los modelos.
MODEL_DIR = Path(os.getenv("MODEL_DIR", "/models"))

# Ruta equivalente vista desde tu Mac.
MODEL_HOST_PREFIX = os.getenv("MODEL_HOST_PREFIX", "./models")

# Identificador del worker.
WORKER_ID = os.getenv("WORKER_ID", socket.gethostname())

# Crea /models si no existe.
MODEL_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Funciones auxiliares
# ---------------------------------------------------------------------------

def now() -> str:
    """
    Retorna fecha y hora actual como texto.

    Se usa para guardar logs y estados legibles en Redis.
    """
    return time.strftime("%Y-%m-%d %H:%M:%S")


def connect_to_redis() -> redis.Redis:
    """
    Conecta el worker XGBoost a Redis.

    Si Redis todavía no está listo, el worker espera y reintenta.
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

            client.ping()

            print(
                f"[{now()}] XGBoost worker {WORKER_ID} conectado a Redis "
                f"en {REDIS_HOST}:{REDIS_PORT}.",
                flush=True,
            )

            return client

        except (ConnectionError, TimeoutError, OSError) as exc:
            print(
                f"[{now()}] Redis no disponible para XGBoost worker: {exc}. "
                "Reintentando...",
                flush=True,
            )
            time.sleep(2)


def log(task_id: str, message: str) -> None:
    """
    Escribe logs en consola y también en Redis.

    Streamlit puede leer logs:{task_id} para mostrar trazabilidad.
    """
    line = f"[{now()}] worker={WORKER_ID} · XGBoost · {message}"

    print(line, flush=True)

    try:
        r.lpush(f"logs:{task_id}", line)
        r.expire(f"logs:{task_id}", 60 * 60)
    except Exception:
        pass


def update_status(
    task_id: str,
    status: str,
    progress: int,
    message: str,
    result: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Actualiza el estado de la tarea XGBoost en Redis.

    La clave usada será:

        task:{task_id}

    Ejemplo:

        task:xgb_a1b2c3d4

    Streamlit no necesita saber cómo se entrenó internamente el modelo.
    Solo lee esta clave y muestra estado, progreso, accuracy y ruta.
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

    r.expire(f"task:{task_id}", 60 * 60)


def save_xgboost_artifact(
    *,
    task_id: str,
    model: XGBClassifier,
    payload: Dict[str, Any],
    feature_cols: list[str],
    target_col: str,
    accuracy: float,
) -> Dict[str, str]:
    """
    Guarda el modelo XGBoost entrenado como archivo .joblib.

    Esto reutiliza la lógica de la opción A:
    el archivo se guarda en /models dentro del contenedor,
    pero se ve en ./models desde tu computador.
    """

    model_filename = f"{task_id}.joblib"

    # Ruta interna del contenedor.
    container_model_path = MODEL_DIR / model_filename

    # Ruta visible desde tu Mac.
    host_model_path = f"{MODEL_HOST_PREFIX.rstrip('/')}/{model_filename}"

    # Guardamos no solo el modelo, sino también metadatos.
    # Así después se puede saber qué modelo era, con qué dataset
    # y con qué columnas fue entrenado.
    artifact = {
        "task_id": task_id,
        "model_type": "xgboost",
        "model": model,
        "dataset_name": payload.get("dataset_name", "desconocido"),
        "features": feature_cols,
        "target": target_col,
        "target_names": payload.get("target_names", []),
        "accuracy": round(accuracy, 4),
        "created_at": now(),
    }

    joblib.dump(artifact, container_model_path)

    return {
        "model_filename": model_filename,
        "model_path": str(container_model_path),
        "model_path_container": str(container_model_path),
        "model_path_host": host_model_path,
    }


# ---------------------------------------------------------------------------
# Entrenamiento XGBoost
# ---------------------------------------------------------------------------

def train_xgboost_from_task(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Entrena un XGBClassifier a partir de una tarea recibida desde Redis.

    Flujo:
    1. Reconstruye el DataFrame enviado por Streamlit.
    2. Separa variables predictoras y variable objetivo.
    3. Divide train/test.
    4. Entrena XGBClassifier.
    5. Evalúa accuracy.
    6. Guarda el modelo en /models.
    7. Publica el resultado en Redis.
    """

    task_id = task["task_id"]
    simulated_seconds = int(task.get("simulated_seconds", 3))
    payload = task["payload"]

    df = pd.DataFrame(payload["data"])

    feature_cols = payload["features"]
    target_col = payload["target"]

    X = df[feature_cols]
    y = df[target_col]

    target_names = payload.get("target_names", [])
    num_classes = len(target_names) if target_names else int(y.nunique())

    update_status(
        task_id,
        "processing",
        20,
        "Dataset reconstruido para XGBoost.",
    )

    log(
        task_id,
        f"Dataset {payload.get('dataset_name', 'desconocido')} "
        f"con {len(df)} filas y {len(feature_cols)} variables.",
    )

    # Simulación de avance para que la demo muestre progreso.
    # El dataset Iris entrena muy rápido, por eso agregamos esta espera didáctica.
    for step in range(max(simulated_seconds, 1)):
        progress = 25 + int((step / max(simulated_seconds, 1)) * 35)

        update_status(
            task_id,
            "processing",
            progress,
            f"Preparando entrenamiento XGBoost, paso {step + 1}.",
        )

        log(
            task_id,
            f"Preparando entrenamiento XGBoost, paso "
            f"{step + 1}/{simulated_seconds}.",
        )

        time.sleep(1)

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
        70,
        "Entrenando XGBClassifier.",
    )

    log(task_id, "Entrenando modelo XGBClassifier.")

    # Modelo XGBoost para clasificación multiclase.
    #
    # n_jobs=1 evita que XGBoost use demasiados hilos dentro del contenedor,
    # algo recomendable en demos con Docker.
    model = XGBClassifier(
        objective="multi:softprob",
        num_class=num_classes,
        eval_metric="mlogloss",
        n_estimators=80,
        max_depth=3,
        learning_rate=0.1,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=42,
        n_jobs=1,
    )

    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)

    accuracy = float(accuracy_score(y_test, y_pred))

    report = classification_report(
        y_test,
        y_pred,
        output_dict=True,
        zero_division=0,
    )

    model_paths = save_xgboost_artifact(
        task_id=task_id,
        model=model,
        payload=payload,
        feature_cols=feature_cols,
        target_col=target_col,
        accuracy=accuracy,
    )

    result = {
        "model_type": "xgboost",
        "accuracy": round(accuracy, 4),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "classes": target_names,
        "classification_report": report,
        **model_paths,
    }

    update_status(
        task_id,
        "completed",
        100,
        "Entrenamiento XGBoost completado y modelo guardado.",
        result,
    )

    log(
        task_id,
        f"Trabajo XGBoost completado. Accuracy={accuracy:.4f}. "
        f"Modelo={model_paths['model_path_container']}",
    )

    return result


def process_task(raw_task: str) -> None:
    """
    Procesa una tarea cruda leída desde Redis.

    La tarea llega como JSON serializado.
    """
    task = json.loads(raw_task)
    task_id = task["task_id"]

    try:
        update_status(
            task_id,
            "processing",
            10,
            "XGBoost worker tomó el trabajo.",
        )

        log(task_id, "XGBoost worker tomó el trabajo desde la cola.")

        if task.get("type") != "train_xgboost":
            raise ValueError(
                f"Tipo de trabajo no soportado por XGBoost worker: "
                f"{task.get('type')}"
            )

        train_xgboost_from_task(task)

    except Exception as exc:
        error_payload = {
            "model_type": "xgboost",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }

        update_status(
            task_id,
            "failed",
            100,
            f"Fallo en XGBoost worker: {exc}",
            error_payload,
        )

        log(task_id, f"Fallo: {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    r = connect_to_redis()

    print(
        f"[{now()}] XGBoost worker {WORKER_ID} escuchando cola "
        f"'{QUEUE_NAME}'.",
        flush=True,
    )

    while True:
        try:
            # Este BLPOP escucha exclusivamente xgboost_queue.
            # Por eso no compite con el worker original.
            item = r.blpop(QUEUE_NAME, timeout=0)

            if item is None:
                continue

            _, raw_task = item

            process_task(raw_task)

        except KeyboardInterrupt:
            print("XGBoost worker detenido por el usuario.", flush=True)
            sys.exit(0)

        except (ConnectionError, TimeoutError, OSError) as exc:
            print(
                f"[{now()}] Conexión Redis perdida en XGBoost worker: {exc}. "
                "Reconectando...",
                flush=True,
            )
            r = connect_to_redis()

        except Exception as exc:
            print(
                f"[{now()}] Error no controlado en XGBoost worker: {exc}",
                flush=True,
            )
            time.sleep(1)