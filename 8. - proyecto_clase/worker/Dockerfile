FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    redis \
    pandas \
    numpy \
    scikit-learn \
    joblib

COPY worker.py /app/worker.py

CMD ["python", "-u", "worker.py"]
