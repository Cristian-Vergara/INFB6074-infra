# Informe Técnico - Actividad 1: Bootloader en Ensamblador x86

**Asignatura:** Infraestructura para Ciencia de Datos (INFB6052)
**Institución:** Universidad Tecnológica Metropolitana (UTEM)
**Carrera:** Ingeniería Civil en Ciencia de Datos
**Semestre:** Primer Semestre 2026
**Profesor:** Dr. Ing. Michael Miranda Sandoval
**Integrantes:** Ignacio Ramírez, Cristian Vergara y Francisco Provoste
**Repositorio:** [altairBASIC/micro-os-boot](https://github.com/altairBASIC/micro-os-boot)

---

## 1. Introducción

Esta actividad consistió en implementar un bootloader funcional en ensamblador x86 de 16 bits, capaz de arrancar en el emulador QEMU, limpiar la pantalla e imprimir mensajes con color utilizando las interrupciones del BIOS. El binario resultante ocupa exactamente 512 bytes e incluye la firma de arranque estándar `0xAA55`.

El objetivo principal de esta actividad es comprender, desde una perspectiva técnica y sistémica, el proceso de arranque de un sistema computacional x86, abordando el flujo completo desde el código fuente hasta su ejecución en un entorno virtualizado. Esta experiencia permite observar de forma concreta la interacción entre hardware, software base y herramientas de construcción, elementos fundamentales en la infraestructura de sistemas modernos orientados a ciencia de datos.

La actividad se enmarca en la unidad de infraestructura de bajo nivel del curso INFB6052, donde se estudian los fundamentos de la capa de hardware y virtualización sobre la que operan los sistemas de procesamiento de datos.

---

## 2. Marco Conceptual

### 2.1 Proceso de arranque (Boot Sequence)

El arranque de un sistema x86 sigue una secuencia estandarizada:

1. **Encendido y POST:** Al conectar la alimentación, el procesador salta directamente a la dirección `0xFFFFFFF0` (reset vector), donde reside el firmware BIOS/UEFI en ROM. El BIOS ejecuta el **Power-On Self Test (POST)**: verifica la integridad de la RAM, inicializa dispositivos (teclado, video, disco) y establece la tabla de vectores de interrupción (IVT) en la dirección `0x0000`.

2. **Búsqueda del dispositivo de arranque:** El BIOS recorre la lista de dispositivos configurada en el setup (BIOS Setup Utility) — disco duro, USB, DVD — en el orden indicado por el usuario. Para cada dispositivo, lee su primer sector (512 bytes).

3. **Verificación de la firma MBR:** Si los bytes en los offsets `0x1FE` y `0x1FF` del sector son `0x55` y `0xAA` respectivamente, el BIOS reconoce ese sector como un **Master Boot Record (MBR)** válido.

4. **Carga en `0x7C00`:** El BIOS copia los 512 bytes del sector en la dirección física `0x7C00` de la RAM y transfiere el control (jmp) a esa dirección. A partir de ese momento, el código del bootloader tiene el control total del sistema.

Este diseño data del IBM PC original (1981) y sigue siendo el punto de entrada para sistemas que utilizan BIOS legacy, aún presente en millones de máquinas virtuales y entornos de prueba.

### 2.2 Modo real x86 y direccionamiento de 16 bits

Al arrancar, el procesador x86 opera en **modo real** (Real Mode), el modo de operación original del Intel 8086. En este modo:

- El CPU utiliza registros de **16 bits** (AX, BX, CX, DX, SI, DI, SP, BP).
- El espacio de memoria direccionable es de **1 MB** (20 bits de dirección), usando segmentación: `dirección_física = segmento × 16 + offset`.
- No existe protección de memoria: cualquier programa puede leer o escribir en cualquier dirección.
- Las interrupciones del BIOS están disponibles a través de la tabla de vectores en `0x0000`.

El modo real permite acceder directamente a los servicios del BIOS, lo que resulta conveniente para un bootloader que necesita imprimir texto sin tener drivers de video propios.

### 2.3 NASM como ensamblador

**NASM (Netwide Assembler)** es un ensamblador de propósito general para la arquitectura x86/x86-64, ampliamente utilizado en desarrollo de sistemas operativos y programación de bajo nivel. Sus características relevantes:

- **Sintaxis Intel:** los operandos se escriben `destino, fuente` (a diferencia de AT&T, que los invierte).
- **Formato binario plano (`-f bin`):** produce un archivo binario sin encabezados, donde el primer byte del archivo corresponde exactamente al primer byte de código que se ejecutará. Esto es indispensable para un sector de arranque.
- **Directivas de control:** `BITS 16` indica que el código debe ensamblarse para modo real; `ORG 0x7C00` informa a NASM de la dirección en memoria donde se cargará el código, para que los cálculos de offsets sean correctos.

### 2.4 QEMU como emulador de sistema completo

**QEMU (Quick Emulator)** es un emulador y virtualizador de código abierto capaz de simular múltiples arquitecturas de hardware. En este proyecto se utiliza `qemu-system-x86_64` para emular un PC x86 completo:

- Simula CPU Intel x86, memoria RAM, controladores de disco y video.
- Permite cargar un archivo binario como imagen de disco cruda con `-drive format=raw,file=boot.bin`.
- Emula el comportamiento del BIOS, incluyendo la lectura del sector de arranque y la verificación de la firma `0xAA55`.

QEMU elimina la necesidad de hardware físico para probar el bootloader, lo que garantiza reproducibilidad total en cualquier entorno de desarrollo.

### 2.5 Sector de arranque y firma `0xAA55`

El **sector de arranque** (boot sector) es el primer sector físico de un dispositivo de almacenamiento, con un tamaño fijo de **512 bytes**. Su estructura es:

| Offset | Tamaño | Contenido |
|---|---|---|
| `0x000` | variable | Código del bootloader |
| `0x000` – `0x1FD` | hasta 446 bytes | Código + datos |
| `0x1FE` | 1 byte | `0x55` (parte de la firma) |
| `0x1FF` | 1 byte | `0xAA` (parte de la firma) |

La firma `0xAA55` es una secuencia de bytes elegida históricamente por IBM. Almacenada en little-endian, el byte `0x55` ocupa el offset `0x1FE` y `0xAA` el `0x1FF`. El BIOS la verifica para distinguir sectores de arranque válidos de sectores de datos comunes.

---

## 3. Desarrollo

### 3.1 Flujo de trabajo

El desarrollo siguió un flujo iterativo con control de versiones en cada etapa,
este flujo constituye un pipeline reproducible que permite reconstruir el sistema desde cero,
 garantizando consistencia entre entornos de desarrollo:

1. Creación de la estructura del repositorio (directorio `src/`, `build/`, `docs/`)
2. Implementación del bootloader en `src/boot.asm`
3. Definición del Makefile con targets `build`, `run`, `clean` y `verify`
4. Instalación de NASM y compilación del binario
5. Verificación del tamaño (512 bytes) y la firma `0xAA55`
6. Ejecución en QEMU y captura de resultados

### 3.2 Explicación del código fuente

El archivo `src/boot.asm` se estructura en cinco bloques:

**Encabezado y configuración:**
```nasm
BITS 16       ; Código de 16 bits (modo real)
ORG 0x7C00    ; Dirección de carga en memoria
```
`BITS 16` instruye a NASM para generar opcodes de 16 bits. `ORG 0x7C00` establece el origen del segmento, necesario para que los labels calculen offsets correctamente.

**Limpieza de pantalla** (función `0x06` de `int 0x10`):
```nasm
mov ah, 0x06   ; Función scroll up
mov al, 0x00   ; 0 líneas = limpiar región completa
mov bh, 0x07   ; Atributo de relleno (gris/negro)
mov ch, 0       ; Fila superior: 0
mov cl, 0       ; Columna izquierda: 0
mov dh, 24      ; Fila inferior: 24
mov dl, 79      ; Columna derecha: 79
int 0x10
```

**Posicionamiento del cursor** (función `0x02` de `int 0x10`):
```nasm
mov ah, 0x02   ; Función set cursor position
mov bh, 0x00   ; Página 0
mov dh, 0x00   ; Fila 0
mov dl, 0x00   ; Columna 0
int 0x10
```

**Impresión de texto**: se usa una función `imprimir` con `lodsb` en un bucle. `lodsb` carga el byte de `[SI]` en `AL` e incrementa `SI` automáticamente. La función `0x0E` de `int 0x10` imprime el carácter en `AL` con el atributo de color en `BL`. El bucle termina cuando `AL == 0` (null terminator).

**Halt loop**:
```nasm
fin:
    cli       ; Deshabilitar interrupciones
    hlt       ; Suspender el CPU
    jmp fin   ; Bucle de seguridad
```

**Relleno y firma**:
```nasm
times 510-($-$$) db 0   ; Relleno con ceros hasta byte 510
dw 0xAA55               ; Firma: bytes 511-512
```
La expresión `$-$$` calcula el número de bytes usados desde el inicio del segmento. `510-($-$$)` es el número de ceros necesarios para alinear la firma al final del sector.

### 3.3 Comandos de compilación y ejecución

```bash
# Compilación
nasm -f bin -o build/boot.bin src/boot.asm

# Verificación de tamaño
wc -c build/boot.bin     # Debe mostrar 512

# Verificación de firma
xxd build/boot.bin | tail -2    # Últimos bytes deben ser 55 aa

# Ejecución en QEMU
qemu-system-x86_64 -drive format=raw,file=build/boot.bin
```

### 3.4 Problemas encontrados y soluciones

Durante el desarrollo, NASM no estaba instalado en el entorno de trabajo (sistema Fedora Linux). Se instaló con `sudo dnf install -y nasm`. El Makefile fue ajustado para incluir el target `verify` con `xxd` y `wc -c`, herramientas estándar de Unix que permiten confirmar la corrección del binario sin ejecutar QEMU.

---

## 4. Resultados

### 4.1 Verificación del binario

Tras la compilación, el archivo `build/boot.bin` tiene **exactamente 512 bytes**, lo que confirma que el relleno calculado con `times 510-($-$$) db 0` es correcto.

La salida de `xxd build/boot.bin | tail -2` muestra:

```
000001f0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
000001fe: 55aa                                     U.
```

Los bytes en los offsets `0x1FE` y `0x1FF` son `55` y `aa` respectivamente, confirmando la presencia de la firma `0xAA55` requerida por el BIOS.

### 4.2 Ejecución en QEMU

Al ejecutar `make run`, QEMU inicializa el entorno de hardware emulado, carga `boot.bin` como primer sector del disco virtual, verifica la firma y transfiere el control al código. La pantalla aparece limpia y se muestra:

```
MicroOS v1.0 - INFB6052
Boot exitoso! - Ignacio Ramirez
```

El primer mensaje aparece en color cian (atributo `0x0B`) y el segundo en verde claro (atributo `0x0A`). El cursor queda estático después del segundo mensaje, confirmando que el CPU entró en el halt loop.


![Ejecución del bootloader en QEMU mostrando el mensaje de arranque](capturas/qemu-boot.png)

*Figura 1: Ejecución del bootloader en QEMU, mostrando el mensaje de inicio y validando el correcto funcionamiento del sistema.*

La evidencia visual confirma que el sistema arranca correctamente en el entorno virtualizado, cumpliendo con los requisitos funcionales definidos en la actividad.

---

## 5. Análisis de Infraestructura

Este ejercicio, aunque aparentemente elemental, ilustra con precisión los principios que gobiernan la infraestructura moderna de ciencia de datos.

### 5.1 Virtualización y emulación

QEMU emula hardware completo: CPU, memoria, controlador de disco y chipset. Este mismo principio escala directamente a los **hipervisores de tipo 1** (KVM, VMware ESXi, Hyper-V) y **tipo 2** (VirtualBox, Parallels) que sostienen las nubes de datos actuales. En AWS, GCP o Azure, los nodos de cómputo donde corren las cargas de trabajo de machine learning son máquinas virtuales sobre hipervisores que, al igual que QEMU, abstraen el hardware físico y presentan una interfaz estándar al sistema operativo invitado. La ejecución del bootloader en QEMU es, conceptualmente, la versión mínima de ese proceso.

### 5.2 Reproducibilidad e infraestructura como código

El `Makefile` codifica la totalidad del proceso de construcción y ejecución: un colaborador que clone el repositorio, instale las dependencias y ejecute `make build` obtendrá un binario bit a bit idéntico, independientemente de su entorno. Este principio — **infraestructura como código (IaC)** — es central en ciencia de datos: herramientas como Terraform, Ansible y Docker Compose aplican la misma lógica a la provisión de clusters, bases de datos y pipelines. El README garantiza que el proceso sea auditable y repetible por cualquier persona.

### 5.3 Toolchain como pipeline de datos

La cadena `código fuente → ensamblador → binario → emulador` es formalmente análoga a un pipeline de datos:

| Etapa del bootloader | Analogía en ciencia de datos |
|---|---|
| `boot.asm` (fuente) | Script Python o notebook de procesamiento |
| `nasm -f bin` (compilación) | Transformación / ETL |
| `boot.bin` (artefacto) | Dataset procesado, modelo serializado |
| `qemu` (ejecución) | Entorno de inferencia o despliegue |

En ambos casos, la reproducibilidad depende de fijar las versiones de las herramientas (NASM, Python, librerías) y automatizar la cadena de transformación.

### 5.4 Artefactos binarios reproducibles

El archivo `boot.bin` es un **artefacto binario reproducible**: dado el mismo código fuente y la misma versión de NASM, el binario producido es siempre idéntico (byte por byte). Este concepto escala a **imágenes Docker** (capas deterministas a partir de un `Dockerfile`), **wheels de Python** y **modelos de machine learning serializados** (`.pkl`, `.onnx`). La reproducibilidad binaria es una propiedad de calidad en ingeniería de datos porque permite auditar y trazar exactamente qué código produjo qué resultado.

### 5.5 Trazabilidad con Git

Cada fase del desarrollo quedó registrada como un commit atómico con un mensaje descriptivo. Git actúa como **registro de linaje**: es posible reconstruir el estado exacto del proyecto en cualquier punto del tiempo con `git checkout <hash>`. En pipelines de datos, esta trazabilidad es análoga al **lineage tracking** de plataformas como MLflow o DVC: se registra qué versión del código, con qué datos y con qué parámetros se produjo cada modelo.

### 5.6 Escalabilidad a infraestructura real de ciencia de datos

Los conceptos demostrados en este ejercicio aparecen en escala ampliada en entornos de producción:

- **VMs y contenedores:** QEMU → KVM → Docker → Kubernetes. Cada capa añade abstracción y orquestación sobre el mismo principio de aislamiento de hardware/software.
- **CI/CD:** El `make build` manual se automatiza en pipelines de GitHub Actions, GitLab CI o Jenkins, que compilan, prueban y despliegan artefactos sin intervención humana.
- **Imágenes base:** Del mismo modo que el bootloader es el punto de entrada para un SO, una imagen Docker base (e.g., `python:3.11-slim`) es el punto de entrada para un contenedor de procesamiento de datos.

### 5.7 infraestructura como base invisible

En este sentido, la infraestructura computacional puede entenderse como una capa invisible pero crítica que sostiene toda operación de procesamiento de datos. Este ejercicio evidencia que incluso los sistemas más complejos dependen de mecanismos fundamentales de arranque, ejecución y abstracción del hardware. Comprender estas bases permite no solo utilizar herramientas de alto nivel, sino también razonar sobre su funcionamiento interno, optimizar su uso y diagnosticar fallas en entornos productivos.

---

## 6. Conclusiones

Este ejercicio demostró que un bootloader funcional puede implementarse en pocas decenas de instrucciones en ensamblador, siempre que se comprenda con precisión el contrato entre el BIOS y el sector de arranque: cargar exactamente 512 bytes en `0x7C00` y terminar con la firma `0xAA55`.

El aprendizaje más valioso no está en los detalles sintácticos del ensamblador, sino en el modelo mental que ofrece: todo sistema de software, por sofisticado que sea, arranca con un paso uno. En ciencia de datos, ese paso uno es la infraestructura — el hardware, el sistema operativo, el runtime — que hace posible ejecutar el análisis. Entender qué ocurre antes de que Python importe NumPy permite diseñar sistemas más robustos, diagnosticar fallas en capas más bajas y tomar decisiones informadas sobre virtualización, contenedores y recursos de cómputo.

La combinación de ensamblador NASM, emulación QEMU y automatización Make, aunque mínima, reproduce fielmente la lógica de toolchains industriales y aporta una base conceptual sólida para las materias avanzadas del plan de estudios.

En consecuencia, esta actividad no solo cumple un objetivo técnico puntual, sino que establece un puente conceptual entre la programación de bajo nivel y las prácticas modernas de ingeniería de infraestructura, posicionando al estudiante en una comprensión integral del ecosistema computacional.

---

## 7. Referencias

1. QEMU Project. *QEMU Documentation*. https://www.qemu.org/docs/master/
2. NASM Development Team. *NASM Manual*. https://www.nasm.us/doc/
3. OSDev Wiki. *Boot Sequence*. https://wiki.osdev.org/Boot_Sequence
4. OSDev Wiki. *Real Mode*. https://wiki.osdev.org/Real_Mode
5. OSDev Wiki. *Master Boot Record*. https://wiki.osdev.org/MBR_(x86)
6. GitHub Docs. *About Git*. https://docs.github.com/en/get-started/using-git/about-git
7. Intel Corporation. *Intel 64 and IA-32 Architectures Software Developer's Manual, Volume 1: Basic Architecture*. https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html
