"""
Worker de entrenamiento.

Escucha una cola Redis, recibe trabajos serializados en JSON, entrena un modelo
simple con scikit-learn y escribe estado, métricas, logs y ruta del modelo en Redis.

Este Worker está diseñado para una demo docente, no como motor de producción.
Para tolerancia fuerte a fallos, reemplazar BLPOP por Redis Streams, RQ, Celery
o un patrón con acknowledgement explícito.
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


REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
QUEUE_NAME = os.getenv("REDIS_QUEUE", "training_queue")
MODEL_DIR = Path(os.getenv("MODEL_DIR", "/models"))
WORKER_ID = os.getenv("WORKER_ID", socket.gethostname())

MODEL_DIR.mkdir(parents=True, exist_ok=True)


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def log(task_id: str, message: str) -> None:
    line = f"[{now()}] worker={WORKER_ID} · {message}"
    print(line, flush=True)
    try:
        r.lpush(f"logs:{task_id}", line)
        r.expire(f"logs:{task_id}", 60 * 60)
    except Exception:
        # Los logs no deben romper el entrenamiento.
        pass


def update_status(
    task_id: str,
    status: str,
    progress: int,
    message: str,
    result: Optional[Dict[str, Any]] = None,
) -> None:
    payload = {
        "task_id": task_id,
        "status": status,
        "progress": progress,
        "message": message,
        "worker": WORKER_ID,
        "updated_at": now(),
        "result": result,
    }
    r.set(f"task:{task_id}", json.dumps(payload, ensure_ascii=False, default=str))
    r.expire(f"task:{task_id}", 60 * 60)


def connect_to_redis() -> redis.Redis:
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
                f"[{now()}] Worker {WORKER_ID} conectado a Redis en {REDIS_HOST}:{REDIS_PORT}.",
                flush=True,
            )
            return client
        except (ConnectionError, TimeoutError, OSError) as exc:
            print(f"[{now()}] Redis no disponible: {exc}. Reintentando...", flush=True)
            time.sleep(2)


def train_from_task(task: Dict[str, Any]) -> Dict[str, Any]:
    task_id = task["task_id"]
    simulated_seconds = int(task.get("simulated_seconds", 3))
    payload = task["payload"]

    df = pd.DataFrame(payload["data"])
    feature_cols = payload["features"]
    target_col = payload["target"]

    X = df[feature_cols]
    y = df[target_col]

    update_status(task_id, "processing", 20, "Dataset reconstruido desde JSON.")
    log(task_id, f"Dataset {payload.get('dataset_name', 'desconocido')} con {len(df)} filas.")

    # Simula trabajo computacional para que la demo de monitoreo sea visible.
    for step in range(max(simulated_seconds, 1)):
        progress = 25 + int((step / max(simulated_seconds, 1)) * 45)
        update_status(task_id, "processing", progress, f"Preparando entrenamiento, paso {step + 1}.")
        log(task_id, f"Preparando entrenamiento, paso {step + 1}/{simulated_seconds}.")
        time.sleep(1)

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.25,
        random_state=42,
        stratify=y,
    )

    update_status(task_id, "processing", 75, "Entrenando LogisticRegression.")
    log(task_id, "Entrenando modelo LogisticRegression.")

    model = LogisticRegression(max_iter=500)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    accuracy = float(accuracy_score(y_test, y_pred))
    report = classification_report(y_test, y_pred, output_dict=True)

    model_path = MODEL_DIR / f"{task_id}.joblib"
    joblib.dump(model, model_path)

    result = {
        "accuracy": round(accuracy, 4),
        "model_path": str(model_path),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "classes": payload.get("target_names", []),
        "classification_report": report,
    }

    update_status(task_id, "completed", 100, "Entrenamiento completado.", result)
    log(task_id, f"Trabajo completado. Accuracy={accuracy:.4f}. Modelo={model_path}")
    return result


def process_task(raw_task: str) -> None:
    task = json.loads(raw_task)
    task_id = task["task_id"]

    try:
        update_status(task_id, "processing", 10, "Worker tomó el trabajo.")
        log(task_id, "Worker tomó el trabajo desde la cola.")

        if task.get("type") != "train_model":
            raise ValueError(f"Tipo de trabajo no soportado: {task.get('type')}")

        train_from_task(task)

    except Exception as exc:
        error_payload = {
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
        update_status(task_id, "failed", 100, f"Fallo en Worker: {exc}", error_payload)
        log(task_id, f"Fallo: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    r = connect_to_redis()
    print(f"[{now()}] Worker {WORKER_ID} escuchando cola '{QUEUE_NAME}'.", flush=True)

    while True:
        try:
            item = r.blpop(QUEUE_NAME, timeout=0)
            if item is None:
                continue
            _, raw_task = item
            process_task(raw_task)
        except KeyboardInterrupt:
            print("Worker detenido por el usuario.", flush=True)
            sys.exit(0)
        except (ConnectionError, TimeoutError, OSError) as exc:
            print(f"[{now()}] Conexión Redis perdida: {exc}. Reconectando...", flush=True)
            r = connect_to_redis()
        except Exception as exc:
            print(f"[{now()}] Error no controlado en loop principal: {exc}", flush=True)
            time.sleep(1)
