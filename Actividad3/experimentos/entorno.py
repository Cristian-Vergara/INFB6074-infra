import platform
import psutil
import subprocess
import numpy as np
import pandas as pd
import matplotlib
from pathlib import Path
import seaborn as sns
import dask

def get_processor_info():
    """Obtiene info del procesador (Mac muestra info más detallada)"""
    sistema = platform.system()
    if sistema == "Darwin":
        try:
            result = subprocess.run(
                ['sysctl', '-n', 'machdep.cpu.brand_string'],
                capture_output=True, text=True
            )
            return result.stdout.strip()
        except:
            return platform.processor()
    return platform.processor()


def get_gpu_info():
    """Detecta GPU según el sistema operativo"""
    sistema = platform.system()
    try:
        if sistema == "Darwin":
            result = subprocess.run(
                ['system_profiler', 'SPDisplaysDataType'],
                capture_output=True, text=True
            )
            for line in result.stdout.split('\n'):
                if 'Chipset Model' in line:
                    return line.split(':')[1].strip()
        elif sistema == "Windows":
            result = subprocess.run(
                ['wmic', 'path', 'win32_VideoController', 'get', 'name'],
                capture_output=True, text=True
            )
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                return lines[1].strip()
        elif sistema == "Linux":
            result = subprocess.run(['lspci'], capture_output=True, text=True)
            for line in result.stdout.split('\n'):
                if 'VGA' in line or 'Display' in line:
                    return line.split(':')[-1].strip()
    except Exception as e:
        return f"Error al detectar GPU: {e}"
    return "GPU no detectada"


disk = psutil.disk_usage('/')

# Información general del entorno
env_info = {
    "Sistema operativo": platform.system() + " " + platform.release(),
    "Procesador": get_processor_info(),
    "Núcleos físicos": psutil.cpu_count(logical=False),
    "Núcleos lógicos": psutil.cpu_count(logical=True),
    "GPU": get_gpu_info(),
    "RAM total (GB)": round(psutil.virtual_memory().total / (1024**3), 2),
    "Almacenamiento total (GB)": round(disk.total / (1024**3), 2),
    "Almacenamiento disponible (GB)": round(disk.free / (1024**3), 2),
    "Estructura de almacenamiento": "datos/, visualizaciones/, experimentos/",
    "Python": platform.python_version(),
    "NumPy": np.__version__,
    "Pandas": pd.__version__,
    "Matplotlib": matplotlib.__version__,
    "psutil": psutil.__version__,
    "Seaborn": sns.__version__,
    "Dask": dask.__version__,
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