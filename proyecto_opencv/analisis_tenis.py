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
                     hsv_bajo2=None, hsv_alto2=None, area_min=300):
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

    c = max(contornos, key=cv2.contourArea)
    if cv2.contourArea(c) < area_min:
        return None

    M = cv2.moments(c)
    if M["m00"] == 0:
        return None
    return (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))

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

def guardar_resumen_cancha(todos_frank, todos_tim, todos_pelota,
                           ancho_video, alto_video,
                           dist_frank_m, dist_tim_m,
                           ruta="resumen_cancha.png"):
    """
    Genera una imagen estilo 'vista aérea' con la cancha de tenis dibujada
    y las trayectorias completas de ambos jugadores y la pelota.
    Las coordenadas del video se mapean a la cancha esquemática.
    """
    fig, ax = plt.subplots(figsize=(10, 7))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1565C0")   # azul cancha

    # --- Dibujar cancha ---
    # Dimensiones normalizadas: cancha ocupa el 80% del área del plot
    W, H = 10, 7   # unidades del plot

    def linea(x1, y1, x2, y2, lw=1.5):
        ax.plot([x1, x2], [y1, y2], color="white", linewidth=lw, zorder=2)

    # Borde exterior
    linea(1, 0.8, 9, 0.8)
    linea(1, 6.2, 9, 6.2)
    linea(1, 0.8, 1, 6.2)
    linea(9, 0.8, 9, 6.2)

    # Red (centro)
    linea(5, 0.8, 5, 6.2, lw=2.5)

    # Línea de servicio izquierda
    linea(3, 2.1, 3, 4.9)
    # Línea de servicio derecha
    linea(7, 2.1, 7, 4.9)
    # Centro de servicio
    linea(3, 3.5, 7, 3.5)

    # Líneas laterales de dobles
    linea(1, 2.1, 9, 2.1)
    linea(1, 4.9, 9, 4.9)

    # --- Mapear coordenadas video → cancha ---
    def mapear(puntos_video):
        coords = []
        for p in puntos_video:
            if p is None:
                coords.append(None)
            else:
                # Normalizar coordenadas del video al espacio de la cancha
                px = 1 + (p[0] / ancho_video) * 8
                py = 0.8 + (p[1] / alto_video) * 5.4
                coords.append((px, py))
        return coords

    frank_mapped  = mapear([p for p in todos_frank  if p is not None])
    tim_mapped    = mapear([p for p in todos_tim    if p is not None])
    pelota_mapped = mapear([p for p in todos_pelota if p is not None])

    def dibujar_tray_plot(coords, color, label, alpha_line=0.6, lw=2):
        xs = [c[0] for c in coords if c]
        ys = [c[1] for c in coords if c]
        if len(xs) < 2:
            return
        # Dibujar segmentos con degradado de opacidad
        n = len(xs)
        for i in range(1, n):
            a = 0.15 + 0.85 * (i / n)
            ax.plot([xs[i-1], xs[i]], [ys[i-1], ys[i]],
                    color=color, alpha=a, linewidth=lw, zorder=3)
        # Punto final (posición actual)
        ax.scatter(xs[-1], ys[-1], color=color, s=80, zorder=5,
                   edgecolors="white", linewidths=1.2, label=label)

    # Colores matplotlib (RGB 0-1)
    dibujar_tray_plot(frank_mapped,  "#FF5733", f"Frank  ({dist_frank_m:.0f} m)")
    dibujar_tray_plot(tim_mapped,    "#4FC3F7", f"Tim    ({dist_tim_m:.0f} m)")
    dibujar_tray_plot(pelota_mapped, "#FFEB3B", "Pelota", alpha_line=0.8, lw=1)

    # --- Etiquetas de zonas ---
    ax.text(2.7, 3.5, "ZONA\nSERVICIO", color="white", fontsize=7,
            ha="center", va="center", alpha=0.4)
    ax.text(7.3, 3.5, "ZONA\nSERVICIO", color="white", fontsize=7,
            ha="center", va="center", alpha=0.4)
    ax.text(5.0, 6.5, "RED", color="white", fontsize=8,
            ha="center", va="center", alpha=0.6)

    # --- Leyenda y títulos ---
    legend = ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.12),
                       ncol=3, frameon=True, facecolor="#1a1a2e",
                       edgecolor="white", labelcolor="white", fontsize=10)

    ax.set_title("Trayectorias del partido — Vista aérea",
                 color="white", fontsize=14, pad=12)
    ax.set_xlim(0, W)
    ax.set_ylim(0, H + 0.5)
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
    ancho    = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    alto     = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total    = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

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
        pos_frank_p  = detectar_jugador(frame_hsv, mascara_mov,
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

        writer.write(frame)

        cv2.imshow("Analisis Tenis - OpenCV", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            print("  Cancelado por el usuario.")
            break

    cap.release()
    writer.release()
    cv2.destroyAllWindows()

    print(f"\nVideo guardado en: {ruta_salida}")

    fps_ef = fps_orig / FRAME_SKIP
    dist_f, dist_t = exportar_metricas(todos_frank, todos_tim, fps_ef)

    guardar_resumen_cancha(
        todos_frank, todos_tim, todos_pelota,
        ancho, alto,
        dist_f, dist_t
    )

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
