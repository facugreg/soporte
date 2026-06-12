"""
Análisis deportivo de tenis amateur con OpenCV
===============================================
Uso:
    python analisis_tenis.py amateurtenis.mp4

Salida:
    - video_procesado.mp4      → video con trayectorias dibujadas
    - metricas.csv             → distancias y velocidades por jugador
    - resumen_cancha.png       → vista aérea de la cancha con trayectorias finales

Requisitos:
    pip install opencv-python numpy matplotlib
"""

import cv2
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from collections import deque
import csv
import sys

# =============================================================================
# CONFIGURACIÓN GENERAL
# =============================================================================

# Saltar N-1 frames por cada frame procesado (2 = procesa 1 de cada 2, etc.)
# Subir este valor si va lento. Con 3 ya se nota mucha mejora de velocidad.
FRAME_SKIP = 3

# Escalar el frame antes de procesar (1.0 = resolución original, 0.5 = mitad)
# Bajar a 0.5 acelera mucho sin perder demasiada precisión de detección
ESCALA = 0.5

# Dimensiones reales de una cancha de tenis para calibrar píxeles → metros
LARGO_CANCHA_METROS = 23.77
PIXELS_CANCHA = 600  # píxeles que mide el largo de cancha en el video (ajustar)
METROS_POR_PIXEL = LARGO_CANCHA_METROS / PIXELS_CANCHA

# Longitud de la "cola" de trayectoria visible (en frames procesados)
COLA_JUGADORES = 40
COLA_PELOTA    = 20

# Colores BGR
COLOR_FRANK  = (30,  80,  215)   # naranja-rojizo
COLOR_TIM    = (200, 200,  50)   # azul claro
COLOR_PELOTA = (0,  255,  255)   # amarillo

# =============================================================================
# RANGOS HSV PARA DETECCIÓN
# =============================================================================

# Frank — remera ROJA
FRANK_HSV_BAJO  = np.array([0,   100,  60])
FRANK_HSV_ALTO  = np.array([10,  255, 255])
FRANK_HSV_BAJO2 = np.array([165, 100,  60])
FRANK_HSV_ALTO2 = np.array([180, 255, 255])

# Tim — remera OSCURA (negro / gris oscuro)
TIM_HSV_BAJO = np.array([0,   0,   0])
TIM_HSV_ALTO = np.array([180, 60,  80])

# Pelota — amarillo-verde fluorescente
PELOTA_HSV_BAJO = np.array([25,  80, 120])
PELOTA_HSV_ALTO = np.array([45, 255, 255])

# =============================================================================
# MÓDULO 1 — DETECCIÓN DE JUGADORES
# =============================================================================

def detectar_jugador(frame_hsv, mascara_mov, hsv_bajo, hsv_alto,
                     hsv_bajo2=None, hsv_alto2=None, area_min=300, area_max=8000):
    mascara_color = cv2.inRange(frame_hsv, hsv_bajo, hsv_alto)
    if hsv_bajo2 is not None:
        mascara_color = cv2.bitwise_or(
            mascara_color, cv2.inRange(frame_hsv, hsv_bajo2, hsv_alto2))

    mascara = cv2.bitwise_and(mascara_mov, mascara_color)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN,  kernel)
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, kernel, iterations=2)

    contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contornos:
        return None

    # Filtrar por rango de área válido antes de elegir el contorno mayor.
    # Contornos demasiado grandes son ruido o partes fuera del frame, no el jugador.
    contornos = [c for c in contornos if area_min <= cv2.contourArea(c) <= area_max]
    if not contornos:
        return None

    c = max(contornos, key=cv2.contourArea)

    # Bounding box del contorno
    x, y, w, h = cv2.boundingRect(c)

    # Usamos el centro horizontal + la parte BAJA del box (los pies)
    # Esto evita que el swing de la raqueta desplace el punto hacia arriba
    cx = x + w // 2
    cy = y + h          # <-- punto más bajo = pies
    return (cx, cy)

# =============================================================================
# MÓDULO 1b — DETECCIÓN DE FRANK POR COLOR HSV + EXTRAPOLACIÓN DE PIES
# =============================================================================

def detectar_frank_hsv(frame_hsv, mascara_mov, hsv_bajo, hsv_alto,
                       hsv_bajo2=None, hsv_alto2=None, area_min=300, area_max=8000,
                       y_min_pies=300, y_max_pies=540):
    """
    Detecta a Frank por el color de su remera roja y localiza los pies buscando
    el píxel más bajo con movimiento en la franja debajo del bounding box de la remera.
    Zona válida de pies: y_min_pies..y_max_pies en coordenadas del frame escalado.
    """
    mascara_color = cv2.inRange(frame_hsv, hsv_bajo, hsv_alto)
    if hsv_bajo2 is not None:
        mascara_color = cv2.bitwise_or(
            mascara_color, cv2.inRange(frame_hsv, hsv_bajo2, hsv_alto2))

    mascara = cv2.bitwise_and(mascara_mov, mascara_color)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN,  kernel)
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, kernel, iterations=2)

    contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contornos:
        return None

    contornos = [c for c in contornos if area_min <= cv2.contourArea(c) <= area_max]
    if not contornos:
        return None

    c = max(contornos, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(c)
    cx = x + w // 2

    # Buscar el píxel más bajo con movimiento en la franja debajo de la remera
    # (zona x_center±30, desde el borde inferior de la remera hasta ~2x su altura)
    h_frame = mascara_mov.shape[0]
    x_izq  = max(0, cx - 30)
    x_der  = min(mascara_mov.shape[1], cx + 30)
    y_top  = y + h
    y_bot  = min(h_frame, y + h * 2)

    filas_con_mov = np.where(mascara_mov[y_top:y_bot, x_izq:x_der].any(axis=1))[0]
    if len(filas_con_mov) > 0:
        cy = y_top + int(filas_con_mov[-1])
    else:
        cy = int(y + h + h * 0.8)  # fallback: 80% de la altura por debajo de la remera

    # Descartar si los pies caen fuera de la zona válida de Frank
    if not (y_min_pies <= cy <= y_max_pies):
        return None

    return (cx, cy)

# =============================================================================
# MÓDULO 2 — DETECCIÓN DE LA PELOTA (contorno, sin HoughCircles)
# =============================================================================

def detectar_pelota(frame_hsv, hsv_bajo, hsv_alto, area_min=10, area_max=800):
    """
    Detecta la pelota filtrando por color y buscando el contorno más pequeño
    y compacto (circularidad alta). Más robusto que HoughCircles en videos amateur.
    """
    mascara = cv2.inRange(frame_hsv, hsv_bajo, hsv_alto)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN,  kernel)
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, kernel)

    contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contornos:
        return None

    mejor = None
    mejor_score = 0

    for c in contornos:
        area = cv2.contourArea(c)
        if area < area_min or area > area_max:
            continue
        perimetro = cv2.arcLength(c, True)
        if perimetro == 0:
            continue
        # Circularidad: 1.0 = círculo perfecto
        circularidad = 4 * np.pi * area / (perimetro ** 2)
        # Buscamos objetos pequeños y circulares
        score = circularidad * (1 / (area + 1))
        if score > mejor_score:
            mejor_score = score
            mejor = c

    if mejor is None:
        return None

    M = cv2.moments(mejor)
    if M["m00"] == 0:
        return None
    return (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))

# =============================================================================
# MÓDULO 3 — DIBUJAR TRAYECTORIAS SOBRE EL VIDEO
# =============================================================================

def dibujar_trayectoria(frame, puntos, color, grosor=2, radio=6):
    if len(puntos) < 2:
        return
    for i in range(1, len(puntos)):
        if puntos[i - 1] is None or puntos[i] is None:
            continue
        alpha = i / len(puntos)
        c = tuple(int(ch * alpha) for ch in color)
        cv2.line(frame, puntos[i - 1], puntos[i], c, max(1, int(grosor * alpha)))
    if puntos[-1]:
        cv2.circle(frame, puntos[-1], radio, color, -1)
        cv2.circle(frame, puntos[-1], radio + 2, (255, 255, 255), 1)

def dibujar_trayectoria_pelota(frame, puntos, color, radio_max=4):
    for i, p in enumerate(puntos):
        if p is None:
            continue
        alpha = (i + 1) / len(puntos)
        c = tuple(int(ch * alpha) for ch in color)
        r = max(1, int(radio_max * alpha))
        cv2.circle(frame, p, r, c, -1)
    if puntos and puntos[-1]:
        cv2.circle(frame, puntos[-1], radio_max + 1, (255, 255, 255), 1)

# =============================================================================
# MÓDULO 4 — OVERLAY DE INFORMACIÓN
# =============================================================================

def dibujar_overlay(frame, frame_num, fps, pos_frank, pos_tim, pos_pelota,
                    dist_frank_px, dist_tim_px):
    overlay = frame.copy()
    cv2.rectangle(overlay, (5, 5), (290, 130), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.45, frame, 0.55, 0, frame)

    t = frame_num / fps
    cv2.putText(frame, f"t = {t:.1f}s  |  frame {frame_num}",
                (12, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

    def fmt(pos): return f"({pos[0]},{pos[1]})" if pos else "no detectado"

    dist_f = dist_frank_px * METROS_POR_PIXEL
    dist_t = dist_tim_px   * METROS_POR_PIXEL

    cv2.putText(frame, f"Frank:  {fmt(pos_frank)}  {dist_f:.1f}m",
                (12, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_FRANK, 1)
    cv2.putText(frame, f"Tim:    {fmt(pos_tim)}  {dist_t:.1f}m",
                (12, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_TIM, 1)
    cv2.putText(frame, f"Pelota: {fmt(pos_pelota)}",
                (12, 94), cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_PELOTA, 1)
    cv2.putText(frame, "OpenCV - Analisis Tenis",
                (12, 118), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (140, 140, 140), 1)

# =============================================================================
# MÓDULO 5 — IMAGEN FINAL: VISTA AÉREA DE LA CANCHA CON TRAYECTORIAS
# =============================================================================

def guardar_resumen_cancha(todos_frank, ruta="resumen_cancha.png"):
    """
    Genera imagen con la cancha de tenis vista de frente (orientación portrait)
    y el recorrido completo de Frank (jugador más cercano a la cámara).
    """
    # Filtrar solo puntos válidos
    puntos = [p for p in todos_frank if p is not None]
    print(f"Puntos válidos de Frank: {len(puntos)}")
    if len(puntos) < 10:
        print(f"  Primeros valores de todos_frank: {todos_frank[:5]}")
    if len(puntos) < 2:
        print("  No hay suficientes puntos para graficar.")
        return

    # Suavizar la trayectoria para eliminar saltos de detección
    # Usamos una media móvil simple sobre x e y por separado
    ventana = 5
    xs_raw = [p[0] for p in puntos]
    ys_raw = [p[1] for p in puntos]

    def suavizar(vals, v):
        resultado = []
        for i in range(len(vals)):
            inicio = max(0, i - v // 2)
            fin    = min(len(vals), i + v // 2)
            resultado.append(sum(vals[inicio:fin]) / (fin - inicio))
        return resultado

    xs = suavizar(xs_raw, ventana)
    ys = suavizar(ys_raw, ventana)

    # Eliminar saltos bruscos (teleportaciones por falsa detección)
    # Si entre dos frames consecutivos el jugador "salta" más de MAX_SALTO píxeles, lo descartamos
    MAX_SALTO = 200
    xs_limpios, ys_limpios = [xs[0]], [ys[0]]
    for i in range(1, len(xs)):
        dx = xs[i] - xs_limpios[-1]
        dy = ys[i] - ys_limpios[-1]
        if (dx**2 + dy**2) ** 0.5 < MAX_SALTO:
            xs_limpios.append(xs[i])
            ys_limpios.append(ys[i])

    # --- Figura con cancha dibujada en matplotlib ---
    fig, ax = plt.subplots(figsize=(10, 7))
    fig.patch.set_facecolor("#0d1b2a")
    ax.set_facecolor("#0d1b2a")

    # Área de la cancha (fondo azul claro)
    ax.add_patch(plt.Rectangle((0.5, 0.5), 9.0, 6.0,
                                color="#2E86C1", zorder=1))

    def L(x1, y1, x2, y2, lw=1.5):
        ax.plot([x1, x2], [y1, y2], color="white", linewidth=lw,
                solid_capstyle="round", zorder=2)

    # Rectángulo exterior
    L(0.5, 0.5, 9.5, 0.5)   # fondo inferior
    L(0.5, 6.5, 9.5, 6.5)   # fondo superior
    L(0.5, 0.5, 0.5, 6.5)   # lateral izquierdo
    L(9.5, 0.5, 9.5, 6.5)   # lateral derecho

    # Red (centro, vertical)
    ax.plot([5, 5], [0.5, 6.5], color="white", linewidth=3,
            solid_capstyle="round", zorder=2)

    # Líneas de singles
    L(0.5, 1.3, 9.5, 1.3)
    L(0.5, 5.7, 9.5, 5.7)

    # Líneas de servicio
    L(2.5, 1.3, 2.5, 5.7)
    L(7.5, 1.3, 7.5, 5.7)

    # Línea central de servicio
    L(2.5, 3.5, 7.5, 3.5)

    # --- Mapear coordenadas del video a la cancha landscape ---
    # Calibración con referencias reales del video en coords ORIGINALES (1920x1080).
    # Los valores escalados del enunciado se multiplican x2 porque todos_frank
    # almacena posiciones en coords originales (tras escalar() con ESCALA=0.5).
    #
    # mapear_x: video x (ancho de cancha visto desde cámara) → plot x (profundidad)
    #   x=480 orig (lateral izq singles, x=240 esc) → plot x=5  (red)
    #   x=1380 orig (lateral der singles, x=690 esc) → plot x=9.2 (fondo Frank)
    #
    # mapear_y: video y (profundidad en frame) → plot y (ancho de cancha), invertido
    #   y=430 orig (red, y=215 esc) → plot y=5.7 (lateral superior)
    #   y=950 orig (fondo, y=475 esc) → plot y=1.3 (lateral inferior)

    def mapear_x(px):
        return 5 + ((px - 480) / (1380 - 480)) * 4.2

    def mapear_y(py):
        return 5.7 - ((py - 430) / (950 - 430)) * 4.4

    xm = [mapear_x(x) for x in xs_limpios]
    ym = [mapear_y(y) for y in ys_limpios]

    # Descartar puntos fuera del lado de Frank o fuera del área visible de la cancha
    pares_validos = [(xi, yi) for xi, yi in zip(xm, ym)
                     if 5 <= xi <= 9.5 and 0.5 <= yi <= 6.5]
    if len(pares_validos) < 2:
        print("  No hay suficientes puntos en la mitad de cancha de Frank tras filtrar.")
        return
    xm, ym = zip(*pares_validos)
    xm, ym = list(xm), list(ym)

    # --- Dibujar trayectoria con degradado de color (inicio=azul oscuro → fin=rojo) ---
    n = len(xm)
    for i in range(1, n):
        t = i / n
        r = int(180 * t + 40 * (1 - t))
        g = int(20  * t + 80 * (1 - t))
        b = int(20  * t + 180 * (1 - t))
        color_hex = f"#{r:02x}{g:02x}{b:02x}"
        lw = 1.5 + t * 1.5
        ax.plot([xm[i-1], xm[i]], [ym[i-1], ym[i]],
                color=color_hex, linewidth=lw, alpha=0.85,
                solid_capstyle="round", zorder=3)

    # Punto de inicio (círculo hueco) y punto final (círculo sólido)
    ax.scatter(xm[0],  ym[0],  s=80,  color="#4FC3F7", zorder=6,
               edgecolors="white", linewidths=1.5, label="Inicio")
    ax.scatter(xm[-1], ym[-1], s=100, color="#FF5733", zorder=6,
               edgecolors="white", linewidths=1.5, label="Fin")

    # --- Leyenda y títulos ---
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.07), ncol=2,
              frameon=True, facecolor="#0d1b2a", edgecolor="white",
              labelcolor="white", fontsize=10, markerscale=1.2)

    ax.set_title("Recorrido de Frank  (mitad derecha de la cancha)",
                 color="white", fontsize=13, pad=14, fontweight="bold")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 7)
    ax.axis("off")

    plt.tight_layout()
    plt.savefig(ruta, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"  Imagen resumen guardada en: {ruta}")

# =============================================================================
# MÓDULO 6 — MÉTRICAS
# =============================================================================

def calcular_distancia_px(puntos):
    total = 0.0
    for i in range(1, len(puntos)):
        if puntos[i] and puntos[i - 1]:
            dx = puntos[i][0] - puntos[i - 1][0]
            dy = puntos[i][1] - puntos[i - 1][1]
            total += np.sqrt(dx**2 + dy**2)
    return total

def exportar_metricas(datos_frank, datos_tim, fps_efectivo, ruta="metricas.csv"):
    def calcular(datos):
        dist_px  = calcular_distancia_px(datos)
        dist_m   = dist_px * METROS_POR_PIXEL
        dur_s    = len(datos) / fps_efectivo
        vels = []
        for i in range(1, len(datos)):
            if datos[i] and datos[i - 1]:
                dx = datos[i][0] - datos[i - 1][0]
                dy = datos[i][1] - datos[i - 1][1]
                vels.append(np.sqrt(dx**2 + dy**2) * METROS_POR_PIXEL * fps_efectivo)
        vp = np.mean(vels) if vels else 0
        vm = np.max(vels)  if vels else 0
        return dist_m, vp, vm, dur_s

    df, vpf, vmf, dur = calcular(datos_frank)
    dt, vpt, vmt, _   = calcular(datos_tim)

    print("\n========== MÉTRICAS FINALES ==========")
    print(f"  Frank — {df:.1f} m | prom {vpf:.2f} m/s | máx {vmf:.2f} m/s")
    print(f"  Tim   — {dt:.1f} m | prom {vpt:.2f} m/s | máx {vmt:.2f} m/s")
    print(f"  Duración: {dur:.1f} s")
    print("======================================\n")

    with open(ruta, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["jugador", "distancia_m", "vel_promedio_ms", "vel_maxima_ms", "duracion_s"])
        w.writerow(["Frank", f"{df:.2f}", f"{vpf:.2f}", f"{vmf:.2f}", f"{dur:.1f}"])
        w.writerow(["Tim",   f"{dt:.2f}", f"{vpt:.2f}", f"{vmt:.2f}", f"{dur:.1f}"])
    print(f"  Métricas guardadas en: {ruta}")

    return df, dt

# =============================================================================
# PIPELINE PRINCIPAL
# =============================================================================

def procesar_video(ruta_entrada, ruta_salida="video_procesado.mp4"):
    cap = cv2.VideoCapture(ruta_entrada)
    if not cap.isOpened():
        print(f"ERROR: No se puede abrir '{ruta_entrada}'")
        sys.exit(1)

    fps_orig = cap.get(cv2.CAP_PROP_FPS)
    total    = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Leer el primer frame para obtener las dimensiones REALES del frame.
    # cap.get(CAP_PROP_FRAME_WIDTH/HEIGHT) puede devolver valores distintos
    # a los del frame real (diferencia entre tamaño de display y tamaño codificado),
    # lo que hace que el VideoWriter recorte los frames silenciosamente.
    ret_test, frame_test = cap.read()
    if not ret_test:
        print(f"ERROR: No se puede leer el primer frame de '{ruta_entrada}'")
        sys.exit(1)
    alto, ancho = frame_test.shape[:2]
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # volver al inicio

    # Dimensiones escaladas para procesamiento interno
    ancho_proc = int(ancho * ESCALA)
    alto_proc  = int(alto  * ESCALA)

    # El video de salida se escribe a resolución original
    fps_salida = fps_orig / FRAME_SKIP
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(ruta_salida, fourcc, fps_salida, (ancho, alto))

    print(f"Video: {ancho}x{alto} @ {fps_orig:.1f} fps — {total} frames")
    print(f"Modo:  escala={ESCALA}  frame_skip={FRAME_SKIP}  → procesa ~{total//FRAME_SKIP} frames")

    sustractor = cv2.createBackgroundSubtractorMOG2(
        history=200, varThreshold=60, detectShadows=True)

    tray_frank  = deque(maxlen=COLA_JUGADORES)
    tray_tim    = deque(maxlen=COLA_JUGADORES)
    tray_pelota = deque(maxlen=COLA_PELOTA)

    todos_frank  = []
    todos_tim    = []
    todos_pelota = []

    dist_frank_px = 0.0
    dist_tim_px   = 0.0
    frame_num     = 0
    procesados    = 0

    print("Procesando... (presioná 'q' para cancelar)")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_num += 1

        # Saltar frames para ganar velocidad
        if frame_num % FRAME_SKIP != 0:
            continue

        procesados += 1
        if procesados % 50 == 0:
            pct = 100 * frame_num // total
            print(f"  Frame {frame_num}/{total} ({pct}%)")

        # Escalar para procesamiento (más rápido)
        pequeño = cv2.resize(frame, (ancho_proc, alto_proc))

        mascara_mov = sustractor.apply(pequeño)
        _, mascara_mov = cv2.threshold(mascara_mov, 200, 255, cv2.THRESH_BINARY)

        frame_hsv = cv2.cvtColor(pequeño, cv2.COLOR_BGR2HSV)

        # Detectar en coordenadas pequeñas
        pos_frank_p  = detectar_frank_hsv(frame_hsv, mascara_mov,
                                          FRANK_HSV_BAJO, FRANK_HSV_ALTO,
                                          FRANK_HSV_BAJO2, FRANK_HSV_ALTO2)
        pos_tim_p    = detectar_jugador(frame_hsv, mascara_mov,
                                        TIM_HSV_BAJO, TIM_HSV_ALTO)
        pos_pelota_p = detectar_pelota(frame_hsv, PELOTA_HSV_BAJO, PELOTA_HSV_ALTO)

        # Escalar posiciones de vuelta a coordenadas originales
        def escalar(pos):
            if pos is None: return None
            return (int(pos[0] / ESCALA), int(pos[1] / ESCALA))

        pos_frank  = escalar(pos_frank_p)
        pos_tim    = escalar(pos_tim_p)
        pos_pelota = escalar(pos_pelota_p)

        # Acumular trayectorias
        tray_frank.append(pos_frank)
        tray_tim.append(pos_tim)
        tray_pelota.append(pos_pelota)
        todos_frank.append(pos_frank)
        todos_tim.append(pos_tim)
        todos_pelota.append(pos_pelota)

        # Distancia acumulada
        if len(todos_frank) >= 2 and todos_frank[-1] and todos_frank[-2]:
            dx = todos_frank[-1][0] - todos_frank[-2][0]
            dy = todos_frank[-1][1] - todos_frank[-2][1]
            dist_frank_px += np.sqrt(dx**2 + dy**2)

        if len(todos_tim) >= 2 and todos_tim[-1] and todos_tim[-2]:
            dx = todos_tim[-1][0] - todos_tim[-2][0]
            dy = todos_tim[-1][1] - todos_tim[-2][1]
            dist_tim_px += np.sqrt(dx**2 + dy**2)

        # Dibujar sobre frame original (resolución completa)
        dibujar_trayectoria(frame, list(tray_frank),  COLOR_FRANK,  grosor=3)
        dibujar_trayectoria(frame, list(tray_tim),    COLOR_TIM,    grosor=3)
        dibujar_trayectoria_pelota(frame, list(tray_pelota), COLOR_PELOTA)
        dibujar_overlay(frame, frame_num, fps_orig,
                        pos_frank, pos_tim, pos_pelota,
                        dist_frank_px, dist_tim_px)

        # Garantía explícita: solo se escribe el frame original sin resize.
        # Si por cualquier razón el shape no coincide, se corrige antes de escribir
        # para evitar el efecto de zoom/recorte silencioso del VideoWriter.
        if frame.shape[1] != ancho or frame.shape[0] != alto:
            frame = cv2.resize(frame, (ancho, alto))
        writer.write(frame)

        preview = cv2.resize(frame, (frame.shape[1] // 2, frame.shape[0] // 2))
        cv2.imshow("Analisis Tenis - OpenCV", preview)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            print("  Cancelado por el usuario.")
            break

    cap.release()
    writer.release()
    cv2.destroyAllWindows()

    print(f"\nVideo guardado en: {ruta_salida}")

    fps_ef = fps_orig / FRAME_SKIP
    # dist_f, dist_t = exportar_metricas(todos_frank, todos_tim, fps_ef)

    guardar_resumen_cancha(todos_frank)

# =============================================================================
# UTILIDAD: CALIBRADOR HSV
# =============================================================================

def calibrar_hsv(ruta_video):
    cap = cv2.VideoCapture(ruta_video)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        print("No se pudo leer el video.")
        return

    frame = cv2.resize(frame, (int(frame.shape[1] * ESCALA), int(frame.shape[0] * ESCALA)))
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    cv2.namedWindow("Calibrador HSV")
    for name, val, maxv in [("H min",0,179),("H max",179,179),
                             ("S min",0,255),("S max",255,255),
                             ("V min",0,255),("V max",255,255)]:
        cv2.createTrackbar(name, "Calibrador HSV", val, maxv, lambda x: None)

    print("Ajustá los sliders. ESC para imprimir los valores y salir.")
    while True:
        hmin = cv2.getTrackbarPos("H min","Calibrador HSV")
        hmax = cv2.getTrackbarPos("H max","Calibrador HSV")
        smin = cv2.getTrackbarPos("S min","Calibrador HSV")
        smax = cv2.getTrackbarPos("S max","Calibrador HSV")
        vmin = cv2.getTrackbarPos("V min","Calibrador HSV")
        vmax = cv2.getTrackbarPos("V max","Calibrador HSV")

        mask = cv2.inRange(hsv, np.array([hmin,smin,vmin]), np.array([hmax,smax,vmax]))
        res  = cv2.bitwise_and(frame, frame, mask=mask)
        cv2.imshow("Calibrador HSV", np.hstack([frame, res]))

        if cv2.waitKey(30) == 27:
            print(f"\nHSV bajo: [{hmin}, {smin}, {vmin}]")
            print(f"HSV alto: [{hmax}, {smax}, {vmax}]")
            break
    cv2.destroyAllWindows()

# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.argv.append("amateurtenis.mp4")   # nombre del video por defecto

    ruta = sys.argv[1]

    if "--calibrar" in sys.argv:
        calibrar_hsv(ruta)
    else:
        procesar_video(ruta)
