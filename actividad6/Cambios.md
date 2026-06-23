## Cambios realizados para el trabajo

En esta versión se implementaron mejoras asociadas a las opciones **A** y **B** de la actividad. El objetivo fue extender la arquitectura original basada en Streamlit, Redis y Workers para incorporar persistencia de modelos y un segundo tipo de entrenamiento especializado.

### Opción A: guardar el modelo entrenado en un volumen compartido

Se modificó la arquitectura para que cada modelo entrenado quede guardado físicamente como un archivo `.joblib`.

Cambios principales:

- Se agregó/verificó el volumen compartido en `docker-compose.yml`:

```yaml
volumes:
  - ./models:/models
```

- El worker guarda el modelo dentro del contenedor en:

```text
/models
```

- Esa ruta se refleja en la máquina local como:

```text
./models
```

- El worker serializa el modelo entrenado usando `joblib.dump(...)`.
- El archivo generado queda asociado al `task_id` del trabajo.
- El worker publica en Redis la ruta del modelo guardado dentro de la clave:

```text
task:{task_id}
```

Ejemplo de resultado esperado en Redis:

```json
{
  "model_filename": "de60c8fe.joblib",
  "model_path_container": "/models/de60c8fe.joblib",
  "model_path_host": "./models/de60c8fe.joblib"
}
```

Con esto, Streamlit puede mostrar al usuario dónde quedó almacenado el modelo entrenado.

### Opción B: segundo worker especializado con XGBoost

Se agregó un segundo tipo de worker para entrenar un modelo usando la librería **XGBoost**. Este worker corre como un servicio separado dentro de Docker y escucha una cola distinta en Redis.

La arquitectura quedó separada en dos flujos:

```text
Streamlit → Redis → training_queue → worker LogisticRegression
Streamlit → Redis → xgboost_queue  → xgboost-worker XGBoost
```

Cambios principales:

- Se creó la carpeta:

```text
xgboost_worker/
```

- Se agregó un nuevo `Dockerfile` para el worker de XGBoost.
- El `Dockerfile` instala las dependencias necesarias, incluyendo:

```text
xgboost
libgomp1
```

- Se creó un nuevo archivo:

```text
xgboost_worker/worker.py
```

- Este worker escucha exclusivamente la cola:

```text
xgboost_queue
```

- Se agregó un nuevo servicio en `docker-compose.yml`:

```yaml
xgboost-worker:
  build:
    context: ./xgboost_worker
  environment:
    - REDIS_QUEUE=xgboost_queue
```

- El worker XGBoost entrena un modelo `XGBClassifier`.
- El modelo XGBoost también se guarda en el mismo volumen compartido:

```text
./models
```

- El resultado del entrenamiento se publica en Redis bajo su propio `task_id`.

### Cambios en Streamlit

Se modificó `app.py` para permitir ejecutar una comparación entre el modelo clásico y XGBoost.

Cambios principales:

- Se agregó la cola:

```python
XGB_QUEUE_NAME = os.getenv("XGB_REDIS_QUEUE", "xgboost_queue")
```

- Se agregó la función:

```python
enqueue_comparison_jobs(...)
```

Esta función crea dos tareas independientes:

```text
lr_xxxxxxxx  → LogisticRegression
xgb_xxxxxxxx → XGBoost
```

- Cada tarea se encola en una cola distinta de Redis.
- Se modificó la diapositiva 16 para agregar el botón:

```text
Comparar LogisticRegression vs XGBoost
```

- Se actualizó `refresh_task_panel(...)` para monitorear más de una tarea al mismo tiempo.
- Se actualizó la tabla de trabajos observados para mostrar:
  - `task_id`
  - modelo entrenado
  - estado
  - progreso
  - accuracy
  - archivo generado
  - ruta del modelo guardado

### Resultado esperado

Al ejecutar la comparación desde Streamlit, se generan dos tareas con un mismo identificador base:

```text
lr_19edc5f3
xgb_19edc5f3
```

Cada worker procesa su propia tarea en paralelo:

```text
worker           → LogisticRegression
xgboost-worker   → XGBoost
```

Al finalizar, ambos modelos quedan guardados en:

```text
models/
```

Ejemplo de archivos generados:

```text
lr_19edc5f3.joblib
xgb_19edc5f3.joblib
```

### Comandos de verificación

Levantar los servicios:

```bash
docker compose up -d --build
```

Verificar contenedores activos:

```bash
docker compose ps
```

Resultado esperado:

```text
redis
worker
xgboost-worker
```

Ver logs del worker clásico:

```bash
docker compose logs -f worker
```

Ver logs del worker XGBoost:

```bash
docker compose logs -f xgboost-worker
```

Verificar modelos guardados:

```bash
ls -lh models
```

Consultar resultados en Redis:

```bash
docker exec -it clase-redis redis-cli GET task:lr_19edc5f3
docker exec -it clase-redis redis-cli GET task:xgb_19edc5f3
```

Cargar el modelo LogisticRegression desde la máquina local:

```bash
python -c "import joblib; a=joblib.load('./models/lr_19edc5f3.joblib'); print(a.keys()); print(a['accuracy'])"
```

Cargar el modelo XGBoost desde el contenedor:

```bash
docker compose exec xgboost-worker python -c "import joblib; a=joblib.load('/models/xgb_19edc5f3.joblib'); print(a.keys()); print(a.get('model_type')); print(a['accuracy'])"
```

> Nota: si se intenta cargar el modelo XGBoost directamente desde macOS, puede ser necesario instalar OpenMP con `brew install libomp`, ya que XGBoost depende de esa librería nativa.

### Justificación técnica

La opción A mejora la **persistencia** y la **trazabilidad** del sistema, porque los modelos entrenados dejan de existir solo en memoria y pasan a quedar guardados como artefactos reutilizables.

La opción B mejora la **modularidad**, la **extensibilidad** y el **paralelismo** de la arquitectura. En vez de mezclar todos los algoritmos en un único worker, se agregó un segundo worker especializado. Esto permite incorporar nuevos motores de entrenamiento sin romper el worker original y permite ejecutar comparaciones entre modelos de forma paralela usando Redis como intermediario.

