FROM python:3.11-slim

WORKDIR /app

# libgomp1 es necesario para que XGBoost pueda usar OpenMP
# dentro de imágenes slim de Debian/Python.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Instalamos las dependencias necesarias del worker XGBoost.
RUN pip install --no-cache-dir \
    redis \
    pandas \
    numpy \
    scikit-learn \
    joblib \
    xgboost

COPY worker.py /app/worker.py

CMD ["python", "-u", "worker.py"]