# worker.py
import numpy as np
def procesar_chunk(chunk):
    """Recibe un sub-array de data y devuelve suma+producto por fila."""
    s = np.sum(chunk, axis=1)
    p = np.prod(chunk, axis=1)
    return s + p