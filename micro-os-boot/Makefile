# =============================================================================
# Makefile - micro-os-boot
# Actividad 1 - INFB6052 - Infraestructura para Ciencia de Datos
# UTEM - Ignacio Ramírez
# =============================================================================

ASM    = nasm
SRC    = src/boot.asm
OUT    = build/boot.bin
QEMU   = qemu-system-x86_64

.PHONY: all build run clean verify

# Target por defecto: compila y ejecuta
all: build run

# Compila el bootloader con NASM en formato binario plano
build:
	@echo "Ensamblando bootloader..."
	$(ASM) -f bin -o $(OUT) $(SRC)
	@echo "Listo: $(OUT)"

# Ejecuta el binario en QEMU como si fuera un disco de arranque real
run:
	$(QEMU) -drive format=raw,file=$(OUT)

# Elimina el binario compilado
clean:
	rm -f $(OUT)
	@echo "Limpieza completada."

# Verifica el binario: muestra tamaño y los últimos bytes para confirmar firma 0xAA55
verify:
	@echo "=== Verificación del binario ==="
	@echo "Tamaño del archivo:"
	@wc -c < $(OUT) | xargs -I{} echo "  {} bytes (debe ser exactamente 512)"
	@echo "Últimos 16 bytes (debe terminar en 55 aa):"
	@xxd $(OUT) | tail -2
