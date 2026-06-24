# Auditoría de versiones de un dataset con blockchain didáctica

**INFB6071 · Infraestructura para Ciencia de Datos · UTEM**
Semana 7 — Actividad integradora (diapositiva 19)

Este proyecto implementa una cadena de bloques didáctica en Python para auditar las versiones y transformaciones de un pipeline de Machine Learning. El objetivo no es construir una blockchain real, sino observar sus invariantes computacionales —hashes, encadenamiento y validación— en código legible y verificable.



## Qué hace el proyecto

El notebook registra cada etapa de un pipeline de ML real (entrenado sobre el dataset **Iris** con scikit-learn) como un bloque encadenado criptográficamente. Cada bloque guarda la huella hash de la entrada y la salida de su etapa, de modo que el linaje completo del dato queda trazable y verificable.

El pipeline auditado consta de cinco pasos:

1. **Ingesta** del dataset bruto
2. **Limpieza** (eliminación de nulos y duplicados)
3. **Feature engineering** (separación de variables y etiquetas)
4. **Entrenamiento** de un modelo Random Forest
5. **Validación** y reporte de métricas (accuracy y F1)

Sobre esta cadena se ejecuta una función de validación y una prueba de alteración controlada que demuestra cómo la modificación de un bloque intermedio rompe la consistencia de los bloques posteriores.

---

## Requisitos

- Python 3.10 o superior
- Las dependencias listadas más abajo

Las librerías `hashlib`, `json`, `time`, `dataclasses`, `typing`, `os` y `copy` forman parte de la librería estándar de Python y no requieren instalación.

---

## Instalación y ejecución

El proyecto usa [uv](https://docs.astral.sh/uv/) para gestionar el entorno.

```bash
# 1. Crear el entorno e instalar dependencias
uv init
uv add pandas scikit-learn joblib jupyterlab

# 2. Levantar JupyterLab
uv run jupyter lab
```

Una vez abierto el notebook en JupyterLab, ejecuta todas las celdas en orden con **Run → Run All Cells**. Las celdas dependen unas de otras, así que deben correrse de principio a fin.

### Alternativa sin uv

```bash
python -m venv .venv
source .venv/bin/activate        # En Windows: .venv\Scripts\activate
pip install pandas scikit-learn joblib jupyterlab
jupyter lab
```

---

## Estructura del notebook

El notebook está organizado en bloques, cada uno precedido por una celda que explica qué hace y para qué sirve:

| Bloque | Contenido |
|---|---|
| 0 | Importación de librerías |
| 1 | Estructura del bloque (`dataclass`) y función de hash |
| 2 | Creación de la cadena y bloque génesis |
| 3 | Pipeline de Machine Learning real (5 pasos) |
| 4 | Función de validación de la cadena |
| 5 | Tabla pandas de auditoría |
| 6 | Verificación final con `assert` |
| 7 | Prueba de alteración (detección de la ruptura) |
| — | Conclusión crítica |

---

## Archivos generados

Al ejecutar el notebook se crea una carpeta `artefactos/` con la evidencia del pipeline y la auditoría:

- `iris_bruto.csv`, `iris_limpio.csv`, `iris_features.csv` — versiones del dataset
- `modelo_rf.pkl` — modelo entrenado
- `metricas.json` — métricas del modelo
- `tabla_eventos_blockchain.csv` — tabla de auditoría de la cadena
- `prueba_alteracion.txt` — evidencia de la prueba de alteración

---

## Decisiones de diseño

**Hash sobre archivos reales.** Cada hash se calcula leyendo el archivo en binario (`hash_archivo`), de modo que la huella corresponde al artefacto real generado, no a una descripción.

**Serialización canónica.** El hash de cada bloque se construye con `json.dumps(..., sort_keys=True)`, garantizando que el mismo contenido lógico produzca siempre el mismo hash sin importar el orden de las claves.

**Alteración sobre una copia.** La prueba de alteración trabaja sobre una copia profunda (`deepcopy`) de la cadena, de modo que la cadena original permanece intacta y la prueba puede repetirse sin reconstruir todo.

---

## Conclusión crítica

El uso de hashes encadenados permite **detectar** cualquier modificación posterior en la historia registrada del pipeline: alterar un bloque intermedio cambia su hash y rompe la referencia que guarda el bloque siguiente.

Este diseño aporta valor cuando se requiere trazabilidad, auditoría y control de versiones en procesos de datos compartidos por **varios actores con confianza limitada**. Sin embargo, puede ser **sobreingeniería** para trabajos pequeños, locales o individuales, donde un control de versiones como Git, un log firmado o una base de datos auditable resuelven el problema a menor costo.

Una aclaración importante sobre los límites: esta implementación **no demuestra que los datos originales sean verdaderos**; solo demuestra que la representación registrada no fue modificada sin dejar evidencia. La blockchain mejora la resistencia a la manipulación, pero no resuelve la calidad de la captura original del dato.

---

## Nota sobre las métricas

El modelo alcanza un accuracy de 1.0 porque el dataset Iris es linealmente separable y muy sencillo de clasificar. Esto es esperable y no indica un error en el pipeline.