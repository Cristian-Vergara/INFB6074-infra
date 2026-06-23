# Orquestador Asíncrono de Entrenamiento

Aplicación docente para la asignatura **Infraestructura para Ciencia de Datos**. El proyecto funciona como presentación interactiva de 20 diapositivas en Streamlit y como frontend real de una mini arquitectura asíncrona basada en Redis y Workers Python.

## Estructura

```text
proyecto_clase/
├── app.py
├── docker-compose.yml
├── requirements.txt
├── README.md
├── models/
├── worker/
│   ├── Dockerfile
│   └── worker.py
└── streamlit/
    └── Dockerfile
```

## Ejecución local recomendada

Desde la carpeta `proyecto_clase`:

```bash
pip install -r requirements.txt
docker-compose up -d
streamlit run app.py
```

Luego abra la URL que indique Streamlit, normalmente:

```text
http://localhost:8501
```

## Flujo de la demo

1. Avance hasta la diapositiva 12 y compruebe la conexión con Redis.
2. En la diapositiva 13, presione **Entrenar modelo Iris**.
3. En la diapositiva 14, presione **Encolar 5 trabajos simultáneos**.
4. Para mostrar escalabilidad horizontal, ejecute en otra terminal:

```bash
docker-compose up --scale worker=2 -d
```

5. Para la discusión de tolerancia a fallas, use la diapositiva 15:

```bash
docker-compose stop worker
docker-compose start worker
```

## Comandos útiles

Ver contenedores:

```bash
docker-compose ps
```

Ver logs del worker:

```bash
docker-compose logs -f worker
```

Detener servicios:

```bash
docker-compose down
```

Limpiar Redis persistido:

```bash
docker-compose down -v
```

## Nota metodológica

La demo usa Redis Lists con `RPUSH` y `BLPOP`, lo que es didáctico y simple. Para tolerancia real a fallos durante el procesamiento, conviene migrar a Redis Streams, RQ, Celery o un patrón con acknowledgements explícitos.
