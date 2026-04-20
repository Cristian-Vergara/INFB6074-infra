import platform
import psutil
import numpy as np
import pandas as pd
import matplotlib
from pathlib import Path

disk = psutil.disk_usage('/')
# Información general del entorno
env_info = {
    "Sistema operativo": platform.system() + " " + platform.release(),
    "Procesador": platform.processor(),
    "RAM total (GB)": round(psutil.virtual_memory().total / (1024**3), 2),
    "Almacenamiento total (GB)": round(disk.total / (1024**3), 2),
    "Almacenamiento disponible (GB)": round(disk.free / (1024**3), 2),
    "Estructura de almacenamiento": "datos/, visualizaciones/, experimentos/",
    "Python": platform.python_version(),
    "NumPy": np.__version__,
    "Pandas": pd.__version__,
    "Matplotlib": matplotlib.__version__,
    "psutil": psutil.__version__,
    "Directorio de trabajo": str(Path.cwd().resolve().name)
}

# Ruta del archivo markdown general
md_path = Path("entorno_experimental.md")

md_lines = [
    "# Configuración del Entorno Experimental\n",
    "## Información del sistema\n",
    "| Componente | Detalle |",
    "|------------|---------|"
]

for k, v in env_info.items():
    md_lines.append(f"| {k} | {v} |")



with open(md_path, "w", encoding="utf-8") as f:
    f.write("\n".join(md_lines))

print(f"Archivo generado en: {md_path.resolve()}")