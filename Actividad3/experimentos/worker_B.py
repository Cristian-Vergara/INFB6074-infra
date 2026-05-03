import unicodedata
import hashlib
import re
import tempfile
import os

def limpiar_texto(texto):
    # 1. quitar espacios al inicio/final
    texto = texto.strip()
    # 2. colapsar espacios dobles a uno solo
    texto = re.sub(r'\s+', ' ', texto)
    # 3. quitar acentos
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return texto

PATRON_EMAIL = re.compile(r'^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$')

def es_email_valido(email):
    return bool(PATRON_EMAIL.match(email))

def son_coherentes(nombre_limpio, username):
    palabras_nombre = nombre_limpio.lower().split()
    return any(palabra in username for palabra in palabras_nombre if len(palabra) >= 3)

def hash_md5(texto):
    return hashlib.md5(texto.encode('utf-8')).hexdigest()

def procesar_lote_cpu(lote):
    resultados=[]
    for nombre, email in lote:
        nombre_limpio = limpiar_texto(nombre).title()
        email_limpio = limpiar_texto(email).lower().replace(' ','')
        if '@' in email_limpio:
            username, dominio = email_limpio.split('@', 1)
        else:
            username=email_limpio
            dominio=''
        nombre_valido = (len(nombre_limpio.split())>=2 and all (palabra.isalpha() for palabra in nombre_limpio.split()))
        email_valido = es_email_valido(email_limpio)
        coherencia= son_coherentes(nombre_limpio, username)
        hash_id= hash_md5(nombre_limpio + email_limpio)

        resultados.append((nombre_limpio, email_limpio, username, dominio, nombre_valido, email_valido, coherencia, hash_id))
    return resultados


def procesar_lote_io(lote):
    resultados=[]
    for id in lote:
        contenido=f"datos sinteticos para id {id}\n"*50
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(contenido)
            ruta = f.name
        with open(ruta, 'r') as f:
            leido = f.read()
        os.remove(ruta)
        resultados.append((id,len(leido)))
    return resultados

