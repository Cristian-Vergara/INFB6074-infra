; =============================================================================
; boot.asm - Bootloader del Micro OS
; Actividad 1 - INFB6052 - Infraestructura para Ciencia de Datos
; Universidad Tecnológica Metropolitana (UTEM)
; Autores: Ignacio Ramírez, Cristian Vergara y Francisco Provoste
; =============================================================================

BITS 16         ; Indicamos al ensamblador que el código es de 16 bits (modo real x86)
ORG 0x7C00      ; El BIOS siempre carga el sector de arranque en la dirección 0x7C00

; =============================================================================
; LIMPIAR PANTALLA
; Usamos la interrupción BIOS int 0x10 con función 0x06 (scroll up / limpiar región)
; Esto borra todo el contenido visible antes de imprimir nuestros mensajes
; =============================================================================
limpiar_pantalla:
    mov ah, 0x06        ; Función 0x06 de int 0x10: desplazar pantalla hacia arriba
    mov al, 0x00        ; Número de líneas a desplazar = 0 significa limpiar toda la región
    mov bh, 0x07        ; Atributo de relleno: texto gris claro sobre fondo negro
    mov ch, 0x00        ; Fila superior: fila 0
    mov cl, 0x00        ; Columna izquierda: columna 0
    mov dh, 0x18        ; Fila inferior: fila 24
    mov dl, 0x4F        ; Columna derecha: columna 79
    int 0x10            ; Llamada a la interrupción BIOS de video

; =============================================================================
; RECUADRO ASCII ART - Colores institucionales UTEM (verde, blanco, azul)
; Caracteres CP437: ╔(0xC9) ═(0xCD) ╗(0xBB) ║(0xBA) ╚(0xC8) ╝(0xBC)
; =============================================================================

; --- Línea superior del recuadro: ╔══════════════╗ en VERDE ---
    mov ah, 0x02        ; Set cursor position
    mov bh, 0x00        ; Página 0
    mov dh, 0x00        ; Fila 0
    mov dl, 0x00        ; Columna 0
    int 0x10
    mov si, box_top     ; Cadena del borde superior
    mov bl, 0x0A        ; Color: verde claro (institucional)
    call imprimir

; --- Línea media del recuadro: ║  MicroOS!  ║ en BLANCO ---
    mov ah, 0x02
    mov bh, 0x00
    mov dh, 0x01        ; Fila 1
    mov dl, 0x00
    int 0x10
    mov si, box_mid     ; Cadena del texto central
    mov bl, 0x0F        ; Color: blanco brillante (institucional)
    call imprimir

; --- Línea inferior del recuadro: ╚══════════════╝ en AZUL ---
    mov ah, 0x02
    mov bh, 0x00
    mov dh, 0x02        ; Fila 2
    mov dl, 0x00
    int 0x10
    mov si, box_bot     ; Cadena del borde inferior
    mov bl, 0x09        ; Color: azul claro (institucional)
    call imprimir

; =============================================================================
; IMPRIMIR LÍNEA: "MicroOS v1.0 - INFB6052" en CIAN (fila 4)
; =============================================================================
    mov ah, 0x02
    mov bh, 0x00
    mov dh, 0x04        ; Fila 4 (dejando fila 3 vacía como separador)
    mov dl, 0x00
    int 0x10
    mov si, msg1        ; Primera cadena de texto
    mov bl, 0x0B        ; Color: cian claro
    call imprimir

; =============================================================================
; IMPRIMIR LÍNEA: "Boot exitoso! // ..." en VERDE (fila 5)
; =============================================================================
    mov ah, 0x02
    mov bh, 0x00
    mov dh, 0x05        ; Fila 5
    mov dl, 0x00
    int 0x10
    mov si, msg2        ; Segunda cadena de texto
    mov bl, 0x0A        ; Color: verde claro
    call imprimir

; =============================================================================
; HALT LOOP - Detener el procesador
; =============================================================================
fin:
    cli                 ; Deshabilitar interrupciones (Clear Interrupt Flag)
    hlt                 ; Detener el procesador (Halt)
    jmp fin             ; Bucle de seguridad

; =============================================================================
; FUNCIÓN: imprimir
; Imprime una cadena terminada en 0 usando int 0x10 / AH=0x09 (con color)
; Entrada:
;   SI = dirección de inicio de la cadena
;   BL = atributo de color del texto
; Modifica: AX, CX, SI, DL
; =============================================================================
imprimir:
    mov dl, 0x00        ; Inicializar columna del cursor en 0
.bucle:
    lodsb               ; Carga byte de [SI] en AL, incrementa SI
    cmp al, 0           ; ¿Fin de cadena?
    je  .fin            ; Si es 0, retornar

    mov ah, 0x09        ; Función 0x09: escribir carácter con atributo
    mov bh, 0x00        ; Página de video: 0
    mov cx, 1           ; Repetir 1 vez
    int 0x10            ; Imprimir carácter con color

    inc dl              ; Avanzar columna
    mov ah, 0x02        ; Función 0x02: mover cursor
    mov bh, 0x00        ; Página 0
    int 0x10            ; Actualizar posición del cursor

    jmp .bucle
.fin:
    ret

; =============================================================================
; DATOS: Recuadro ASCII art con caracteres CP437
; =============================================================================
box_top db 0xC9, 0xCD, 0xCD, 0xCD, 0xCD, 0xCD, 0xCD, 0xCD, 0xCD, 0xCD, 0xCD, 0xCD, 0xCD, 0xCD, 0xBB, 0
box_mid db 0xBA, "  MicroOS!   ", 0xBA, 0
box_bot db 0xC8, 0xCD, 0xCD, 0xCD, 0xCD, 0xCD, 0xCD, 0xCD, 0xCD, 0xCD, 0xCD, 0xCD, 0xCD, 0xCD, 0xBC, 0

; =============================================================================
; DATOS: Mensajes de texto
; =============================================================================
msg1 db "MicroOS v1.0 - INFB6052", 0
msg2 db "Boot exitoso! // I.Ramirez, C.Vergara, F.Provoste", 0

; =============================================================================
; RELLENO Y FIRMA DE ARRANQUE
; =============================================================================
times 510-($-$$) db 0   ; Rellena con ceros hasta el byte 510
dw 0xAA55               ; Firma mágica de sector de arranque
