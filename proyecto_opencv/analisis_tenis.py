"""
Análisis de tenis profesional — MOG2 + máscara de polígono + perspectiva
=========================================================================
Detecta jugadores con MOG2 dentro del trapecio exacto de la cancha.
Mapea posiciones a cancha.png con transformación de perspectiva real.

Uso:
    python analisis_tenis.py video.mp4

Salida:
    - video_procesado.mp4
    - trayectorias.png
    - mapa_calor.png

Requisitos:
    pip install opencv-python numpy matplotlib
"""

import cv2
import numpy as np
import matplotlib.pyplot as plt
from collections import deque
from pathlib import Path
import sys

# ============================================================
# CONFIGURACIÓN
# ============================================================

FRAME_SKIP = 2

# Vista cenital
HSV_CANCHA_BAJO = np.array([85,  40,  60])
HSV_CANCHA_ALTO = np.array([160, 255, 255])
UMBRAL_CENITAL  = 0.25

# Polígono exacto de la cancha en el video (perspectiva trapezoidal)
CANCHA_PUNTOS = np.array([
    [630, 190],   # Superior izquierda
    [1334, 202],  # Superior derecha
    [1734, 864],  # Inferior derecha
    [310, 836],   # Inferior izquierda
], dtype=np.int32)

# Zona del árbitro a excluir (silla, borde izquierdo)
ARBITRO_X_MAX = 330
ARBITRO_Y_MAX = 400

# Jugadores — MOG2
JUGADOR_AREA_MIN  = 800
JUGADOR_AREA_MAX  = 25000
JUGADOR_MAX_SALTO = 80     # px en frame original
JUGADOR_MAX_PERD  = 5
MITAD_Y           = 395    # cy > MITAD_Y → Jugador A (cercano); otro → B (lejano)

# MOG2
MOG2_HISTORY       = 500
MOG2_VAR_THRESHOLD = 40

# Pelota — HSV amarillo-verde
PELOTA_HSV_BAJO  = np.array([29, 86,  6])
PELOTA_HSV_ALTO  = np.array([64, 255, 255])
PELOTA_AREA_MIN  = 10
PELOTA_AREA_MAX  = 200
PELOTA_MAX_SALTO = 100

# Golpes
ANGULO_GOLPE   = 60
COOLDOWN_GOLPE = 10

# Colas de trayectoria en el video
COLA_JUGADORES = 20
COLA_PELOTA    = 15

# Imagen final
TRAY_MAX_SALTO = 60

# Colores BGR
COLOR_A      = (0,   0,  220)
COLOR_B      = (200, 80,   0)
COLOR_BBOX_A = (180, 100, 255)   # rosa
COLOR_BBOX_B = (255, 160,  50)   # celeste
COLOR_PELOTA = (0,  220, 255)    # amarillo
COLOR_GOLPE  = (0,  220, 255)
COLOR_CANCHA = (0,  200,   0)    # verde — borde del polígono
COLOR_TEXTO  = (255, 255, 255)


# ============================================================
# MÓDULO 0 — VISTA CENITAL
# ============================================================

def es_cenital(pequeño_hsv):
    """True si el frame (a mitad de resolución) tiene suficiente cancha visible."""
    mask = cv2.inRange(pequeño_hsv, HSV_CANCHA_BAJO, HSV_CANCHA_ALTO)
    return np.count_nonzero(mask) / mask.size > UMBRAL_CENITAL


# ============================================================
# MÓDULO 1 — DETECCIÓN DE JUGADORES CON MOG2
# ============================================================

def detectar_jugadores_mog2(mask_mog, mascara_cancha):
    """
    Aplica la máscara poligonal al resultado de MOG2 y encuentra los dos
    contornos más grandes como jugadores.
    Jugador A: centroide con cy > MITAD_Y (mitad inferior, cercano a cámara).
    Jugador B: centroide con cy < MITAD_Y (mitad superior, lejano).
    Excluye la zona del árbitro (x < ARBITRO_X_MAX, y < ARBITRO_Y_MAX).
    """
    mask = cv2.bitwise_and(mask_mog, mascara_cancha)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    mask   = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask   = cv2.dilate(mask, kernel, iterations=2)

    contornos, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    cands_A, cands_B = [], []

    for c in contornos:
        area = cv2.contourArea(c)
        if not (JUGADOR_AREA_MIN <= area <= JUGADOR_AREA_MAX):
            continue
        M_mom = cv2.moments(c)
        if M_mom["m00"] == 0:
            continue
        cx = int(M_mom["m10"] / M_mom["m00"])
        cy = int(M_mom["m01"] / M_mom["m00"])

        # Rechazar si el centroide cae fuera del polígono
        if cv2.pointPolygonTest(CANCHA_PUNTOS, (float(cx), float(cy)), False) < 0:
            continue

        # Excluir zona del árbitro
        if cx < ARBITRO_X_MAX and cy < ARBITRO_Y_MAX:
            continue

        x, y, w, h = cv2.boundingRect(c)
        pos  = (cx, y + h)          # punto de tracking: centro-x, pies
        bbox = (x, y, x + w, y + h)

        if cy > MITAD_Y:
            cands_A.append((area, pos, bbox))
        else:
            cands_B.append((area, pos, bbox))

    def mejor(cands):
        if not cands:
            return None, None
        _, pos, bbox = max(cands, key=lambda c: c[0])
        return pos, bbox

    pos_A, bbox_A = mejor(cands_A)
    pos_B, bbox_B = mejor(cands_B)
    return pos_A, bbox_A, pos_B, bbox_B


def filtrar_temporal(pos_nueva, ultima_pos, frames_sin):
    """
    Descarta detecciones con salto imposible (> JUGADOR_MAX_SALTO).
    Resetea la posición conocida tras JUGADOR_MAX_PERD frames sin detección válida.
    """
    if pos_nueva is not None:
        if ultima_pos is not None:
            d = np.hypot(pos_nueva[0] - ultima_pos[0],
                         pos_nueva[1] - ultima_pos[1])
            if d > JUGADOR_MAX_SALTO:
                frames_sin += 1
                if frames_sin > JUGADOR_MAX_PERD:
                    ultima_pos = None
                return None, ultima_pos, frames_sin
        return pos_nueva, pos_nueva, 0
    else:
        frames_sin += 1
        if frames_sin > JUGADOR_MAX_PERD:
            ultima_pos = None
        return None, ultima_pos, frames_sin


# ============================================================
# MÓDULO 2 — DETECCIÓN DE PELOTA
# ============================================================

def detectar_pelota(frame_hsv, mascara_cancha, ultima_pelota=None):
    """
    Detecta la pelota por filtro HSV dentro del polígono de la cancha.
    Aplica consistencia temporal: no puede saltar más de PELOTA_MAX_SALTO px.
    """
    mask = cv2.inRange(frame_hsv, PELOTA_HSV_BAJO, PELOTA_HSV_ALTO)
    mask = cv2.bitwise_and(mask, mascara_cancha)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask   = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    contornos, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    mejor = None
    mejor_score = 0

    for c in contornos:
        area = cv2.contourArea(c)
        if not (PELOTA_AREA_MIN <= area <= PELOTA_AREA_MAX):
            continue
        per = cv2.arcLength(c, True)
        if per == 0:
            continue
        circ = 4 * np.pi * area / (per ** 2)
        if circ < 0.4:
            continue

        M = cv2.moments(c)
        if M["m00"] == 0:
            continue
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])

        if ultima_pelota is not None:
            if np.hypot(cx - ultima_pelota[0], cy - ultima_pelota[1]) > PELOTA_MAX_SALTO:
                continue

        score = circ / (area + 1)
        if score > mejor_score:
            mejor_score = score
            mejor = (cx, cy)

    return mejor


def detectar_golpe(hist_pelota, ultimo_golpe_p, proc_actual):
    """True si la pelota cambió de dirección más de ANGULO_GOLPE grados."""
    if proc_actual - ultimo_golpe_p < COOLDOWN_GOLPE:
        return False
    puntos = [p for p in hist_pelota if p is not None]
    if len(puntos) < 3:
        return False
    v1 = np.array([puntos[-2][0] - puntos[-3][0],
                   puntos[-2][1] - puntos[-3][1]], dtype=float)
    v2 = np.array([puntos[-1][0] - puntos[-2][0],
                   puntos[-1][1] - puntos[-2][1]], dtype=float)
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 < 2 or n2 < 2:
        return False
    angulo = np.degrees(np.arccos(np.clip(np.dot(v1, v2) / (n1 * n2), -1, 1)))
    return angulo > ANGULO_GOLPE


# ============================================================
# MÓDULO 3 — TRANSFORMACIÓN DE PERSPECTIVA
# ============================================================

def crear_transformacion(img_cancha_rgb):
    """
    Calcula la homografía: 4 vértices del trapecio en el video
    → zona de juego en cancha.png.
    """
    H, W = img_cancha_rgb.shape[:2]
    pts_video = np.float32([
        [320,  155],
        [995,  155],
        [1240, 635],
        [55,   635]
    ])
    pts_cancha = np.float32([
        [W * 0.18, H * 0.02],
        [W * 0.82, H * 0.02],
        [W * 0.82, H * 0.98],
        [W * 0.18, H * 0.98],
    ])
    return cv2.getPerspectiveTransform(pts_video, pts_cancha)


def video_a_cancha(x, y, M):
    """Mapea un punto (x, y) del video a coordenadas de cancha.png."""
    pt  = np.float32([[[float(x), float(y)]]])
    res = cv2.perspectiveTransform(pt, M)
    return int(res[0][0][0]), int(res[0][0][1])


# ============================================================
# MÓDULO 5 — DIBUJO EN VIDEO
# ============================================================

def dibujar_cola(frame, cola, color, radio_max=4):
    pts = list(cola)
    n   = len(pts)
    for i, p in enumerate(pts):
        if p is None:
            continue
        alpha = (i + 1) / n
        c = tuple(int(ch * alpha) for ch in color)
        cv2.circle(frame, p, max(1, int(radio_max * alpha)), c, -1)


def dibujar_jugador(frame, pos, bbox, color_bbox, nombre):
    if bbox is not None:
        x1, y1, x2, y2 = bbox
        cv2.rectangle(frame, (x1, y1), (x2, y2), color_bbox, 2)
        cv2.putText(frame, nombre, (x1, max(y1 - 8, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color_bbox, 2, cv2.LINE_AA)
    if pos is not None:
        cv2.circle(frame, pos, 9,  (255, 255, 255), -1)
        cv2.circle(frame, pos, 7,  color_bbox,      -1)


def dibujar_overlay(frame, frame_num, fps, golpes, pos_A, pos_B):
    h  = frame.shape[0]
    px, py = 8, h - 80

    ov = frame.copy()
    cv2.rectangle(ov, (px, py), (px + 400, h - 8), (0, 0, 0), -1)
    cv2.addWeighted(ov, 0.5, frame, 0.5, 0, frame)

    t = frame_num / fps

    def txt(texto, dy, color=COLOR_TEXTO):
        cv2.putText(frame, texto, (px + 8, py + dy),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 1, cv2.LINE_AA)

    txt(f"t = {t:.1f}s  |  Golpes: {golpes}", 22)
    txt(f"Jugador A: {'detectado' if pos_A else 'no detectado'}", 46, COLOR_BBOX_A)
    txt(f"Jugador B: {'detectado' if pos_B else 'no detectado'}", 68, COLOR_BBOX_B)


# ============================================================
# UTILIDAD — RECT DE CANCHA EN cancha.png
# ============================================================

def detectar_rect_cancha_imagen(img_cancha_rgb):
    """Bounding rect de los píxeles blancos (líneas) en cancha.png."""
    gris = cv2.cvtColor(img_cancha_rgb, cv2.COLOR_RGB2GRAY)
    _, thresh = cv2.threshold(gris, 200, 255, cv2.THRESH_BINARY)
    coords = cv2.findNonZero(thresh)
    if coords is None:
        return None
    x, y, w, h = cv2.boundingRect(coords)
    alto_img, ancho_img = img_cancha_rgb.shape[:2]
    if w < ancho_img * 0.2 or h < alto_img * 0.2:
        return None
    return x, y, w, h


# ============================================================
# MÓDULO 6 — IMÁGENES FINALES
# ============================================================

def conclusion_tactica(ys_cancha, alto_c, nombre):
    if not ys_cancha:
        return f"{nombre}: sin datos"
    n = len(ys_cancha)
    pct_fondo = sum(1 for y in ys_cancha if y > alto_c * 0.65) / n
    pct_red   = sum(1 for y in ys_cancha if y < alto_c * 0.35) / n
    if pct_fondo > 0.55:
        return f"{nombre} jugó principalmente desde el fondo"
    if pct_red > 0.35:
        return f"{nombre} subió frecuentemente a la red"
    return f"{nombre} dominó la zona media de la cancha"


def guardar_trayectorias(tray_A, tray_B, img_cancha_rgb,
                         frames_A, frames_B, ruta="trayectorias.png"):
    if len(tray_A) < 2 and len(tray_B) < 2:
        print("  No hay datos suficientes para trayectorias.png")
        return

    alto_c, ancho_c = img_cancha_rgb.shape[:2]
    fig, ax = plt.subplots(figsize=(6, 6 * alto_c / ancho_c))
    fig.patch.set_facecolor("#0d1b2a")
    ax.imshow(img_cancha_rgb, zorder=1)
    ax.set_xlim(0, ancho_c)
    ax.set_ylim(alto_c, 0)

    for tray, rgb, etiqueta in [
        (tray_A, (0.85, 0.1, 0.1),  f"Jugador A ({frames_A} frames)"),
        (tray_B, (0.1,  0.3, 0.95), f"Jugador B ({frames_B} frames)"),
    ]:
        if len(tray) < 2:
            continue
        n = len(tray)
        for i in range(1, n):
            dist = np.hypot(tray[i][0] - tray[i-1][0],
                            tray[i][1] - tray[i-1][1])
            if dist > TRAY_MAX_SALTO:
                continue
            t = i / n
            color_seg = (rgb[0] * t,
                         rgb[1] * t + 0.1 * (1 - t),
                         rgb[2] * t + 0.2 * (1 - t))
            ax.plot([tray[i-1][0], tray[i][0]],
                    [tray[i-1][1], tray[i][1]],
                    color=color_seg, linewidth=1.0 + t * 1.5,
                    alpha=0.75, solid_capstyle="round", zorder=3)
        ax.scatter(tray[0][0],  tray[0][1],  s=60, color="white",
                   edgecolors=rgb, linewidths=1.5, zorder=5,
                   label=f"{etiqueta} — inicio")
        ax.scatter(tray[-1][0], tray[-1][1], s=80, color=rgb,
                   edgecolors="white", linewidths=1.5, zorder=5,
                   label=f"{etiqueta} — fin")

    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.12),
              ncol=2, fontsize=8, frameon=True,
              facecolor="#0d1b2a", edgecolor="white", labelcolor="white")
    ax.set_title("Trayectorias del partido",
                 color="white", fontsize=13, fontweight="bold", pad=10)
    ax.axis("off")
    plt.tight_layout()
    plt.savefig(ruta, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close()
    print(f"  Guardado: {ruta}")


def guardar_mapa_calor(calor_A, calor_B, ys_A, ys_B,
                       img_cancha_rgb, alto_c,
                       rect_cancha_img=None, ruta="mapa_calor.png"):
    def blur_norm(acc):
        if acc.max() == 0:
            return None
        b = cv2.GaussianBlur(acc, (81, 81), 0)
        return b / b.max()

    def to_disp(arr):
        if arr is None:
            return None
        d = arr.astype(float)
        d[d < 0.02] = np.nan
        return d

    concl = (f"• {conclusion_tactica(ys_A, alto_c, 'Jugador A')}\n"
             f"• {conclusion_tactica(ys_B, alto_c, 'Jugador B')}")

    alto_ci, ancho_ci = img_cancha_rgb.shape[:2]
    fig, ax = plt.subplots(figsize=(6, 6 * alto_ci / ancho_ci))
    fig.patch.set_facecolor("#0d1b2a")
    ax.imshow(img_cancha_rgb, zorder=1)
    ax.set_xlim(0, ancho_ci)
    ax.set_ylim(alto_ci, 0)

    if rect_cancha_img is not None:
        rx, ry, rw, rh = rect_cancha_img
        extent = [rx, rx + rw, ry + rh, ry]
        def preparar(acc):
            h = blur_norm(acc)
            if h is None:
                return None
            return to_disp(h[ry:ry + rh, rx:rx + rw])
    else:
        extent = None
        def preparar(acc):
            return to_disp(blur_norm(acc))

    for acc, cmap_name in [(calor_A, "Reds"), (calor_B, "Blues")]:
        heat = preparar(acc)
        if heat is None:
            continue
        cmap = plt.colormaps[cmap_name].copy()
        cmap.set_bad(alpha=0.0)
        kw = dict(cmap=cmap, alpha=0.65, vmin=0, vmax=1,
                  zorder=2, origin="upper")
        if extent is not None:
            ax.imshow(heat, extent=extent, **kw)
        else:
            ax.imshow(heat, **kw)

    ax.set_title("Mapa de calor de posición",
                 color="white", fontsize=13, fontweight="bold", pad=10)
    ax.axis("off")
    fig.text(0.5, 0.01, concl, ha="center", color="white",
             fontsize=9, linespacing=1.6,
             bbox=dict(boxstyle="round,pad=0.4",
                       facecolor="#0d1b2a", edgecolor="#555555"))
    plt.tight_layout()
    plt.savefig(ruta, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close()
    print(f"  Guardado: {ruta}")


# ============================================================
# PIPELINE PRINCIPAL
# ============================================================

def procesar_video(ruta_entrada, ruta_salida="video_procesado.mp4"):
    cap = cv2.VideoCapture(ruta_entrada)
    if not cap.isOpened():
        print(f"ERROR: No se puede abrir '{ruta_entrada}'")
        sys.exit(1)

    fps_orig = cap.get(cv2.CAP_PROP_FPS)
    total    = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    ret_t, frame_t = cap.read()
    if not ret_t:
        print("ERROR: No se puede leer el primer frame.")
        sys.exit(1)
    alto_v, ancho_v = frame_t.shape[:2]
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    fps_salida = fps_orig / FRAME_SKIP

    # Máscara del polígono de la cancha (tamaño del frame original)
    mascara_cancha = np.zeros((alto_v, ancho_v), dtype=np.uint8)
    cv2.fillPoly(mascara_cancha, [CANCHA_PUNTOS], 255)

    # Cargar cancha.png
    cancha_path = Path("cancha.png")
    if cancha_path.exists():
        img_cancha_rgb = cv2.cvtColor(cv2.imread(str(cancha_path)),
                                      cv2.COLOR_BGR2RGB)
        print(f"  cancha.png: {img_cancha_rgb.shape[1]}×{img_cancha_rgb.shape[0]} px")
    else:
        print("  AVISO: cancha.png no encontrada — fondo genérico")
        img_cancha_rgb = np.full((900, 500, 3), 30, dtype=np.uint8)
    alto_c, ancho_c = img_cancha_rgb.shape[:2]

    M_perspectiva   = crear_transformacion(img_cancha_rgb)
    rect_cancha_img = detectar_rect_cancha_imagen(img_cancha_rgb)
    if rect_cancha_img:
        print(f"  Rect cancha en imagen: {rect_cancha_img}")

    # MOG2 — se alimenta con TODOS los frames para mejor modelo del fondo
    sustractor = cv2.createBackgroundSubtractorMOG2(
        history=MOG2_HISTORY,
        varThreshold=MOG2_VAR_THRESHOLD,
        detectShadows=False
    )

    # Acumuladores en espacio de cancha.png
    calor_A     = np.zeros((alto_c, ancho_c), dtype=np.float32)
    calor_B     = np.zeros((alto_c, ancho_c), dtype=np.float32)
    tray_A_all  = []
    tray_B_all  = []
    ys_A_cancha = []
    ys_B_cancha = []

    cola_A      = deque(maxlen=COLA_JUGADORES)
    cola_B      = deque(maxlen=COLA_JUGADORES)
    cola_pelota = deque(maxlen=COLA_PELOTA)

    ultima_A_p    = None;  frames_sin_A = 0
    ultima_B_p    = None;  frames_sin_B = 0

    ultima_pelota  = None
    hist_pelota    = deque(maxlen=5)
    ultimo_golpe_p = -(COOLDOWN_GOLPE + 1)
    golpe_pos      = None

    writer        = None
    fourcc        = cv2.VideoWriter_fourcc(*"mp4v")
    golpes_count  = 0
    frames_cenital= 0
    frames_A      = 0
    frames_B      = 0
    frame_num     = 0
    procesados    = 0

    print(f"Video: {ancho_v}×{alto_v} @ {fps_orig:.1f} fps — {total} frames")
    print(f"frame_skip={FRAME_SKIP}  area_jugador={JUGADOR_AREA_MIN}-{JUGADOR_AREA_MAX}")
    print("Procesando... (presioná 'q' para cancelar)\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_num += 1

        # MOG2 recibe todos los frames para estabilizar el modelo del fondo
        mask_mog = sustractor.apply(frame)

        if frame_num % FRAME_SKIP != 0:
            continue
        procesados += 1

        # Cenital check en frame a mitad de resolución
        pequeño     = cv2.resize(frame, (ancho_v // 2, alto_v // 2))
        pequeño_hsv = cv2.cvtColor(pequeño, cv2.COLOR_BGR2HSV)
        if not es_cenital(pequeño_hsv):
            continue
        frames_cenital += 1

        # Módulo 1: jugadores
        pos_A_raw, bbox_A, pos_B_raw, bbox_B = detectar_jugadores_mog2(
            mask_mog, mascara_cancha
        )

        pos_A, ultima_A_p, frames_sin_A = filtrar_temporal(
            pos_A_raw, ultima_A_p, frames_sin_A
        )
        pos_B, ultima_B_p, frames_sin_B = filtrar_temporal(
            pos_B_raw, ultima_B_p, frames_sin_B
        )

        if pos_A is None:
            bbox_A = None
        if pos_B is None:
            bbox_B = None

        # Acumular posiciones en cancha.png con perspectiva correcta
        def acumular(pos, calor, tray_all, ys_list):
            if pos is None:
                return 0
            xi, yi = video_a_cancha(*pos, M_perspectiva)
            xi = int(np.clip(xi, 0, ancho_c - 1))
            yi = int(np.clip(yi, 0, alto_c - 1))
            tray_all.append((xi, yi))
            if rect_cancha_img is None or (
                rect_cancha_img[0] <= xi < rect_cancha_img[0] + rect_cancha_img[2] and
                rect_cancha_img[1] <= yi < rect_cancha_img[1] + rect_cancha_img[3]
            ):
                calor[yi, xi] += 1
                ys_list.append(yi)
            return 1

        frames_A += acumular(pos_A, calor_A, tray_A_all, ys_A_cancha)
        frames_B += acumular(pos_B, calor_B, tray_B_all, ys_B_cancha)

        cola_A.append(pos_A)
        cola_B.append(pos_B)

        # Módulo 2: pelota
        frame_hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        pelota    = detectar_pelota(frame_hsv, mascara_cancha, ultima_pelota)
        if pelota:
            ultima_pelota = pelota
        hist_pelota.append(pelota)
        cola_pelota.append(pelota)

        # Golpes
        if detectar_golpe(hist_pelota, ultimo_golpe_p, procesados):
            golpes_count  += 1
            ultimo_golpe_p = procesados
            golpe_pos      = pelota or ultima_pelota

        # ---- Dibujo ----
        if writer is None:
            writer = cv2.VideoWriter(ruta_salida, fourcc, fps_salida, (ancho_v, alto_v))

        # Polígono de la cancha (verde, 1px)
        cv2.polylines(frame, [CANCHA_PUNTOS], isClosed=True,
                      color=COLOR_CANCHA, thickness=1, lineType=cv2.LINE_AA)

        dibujar_cola(frame, cola_A,      COLOR_A,      radio_max=4)
        dibujar_cola(frame, cola_B,      COLOR_B,      radio_max=4)
        dibujar_cola(frame, cola_pelota, COLOR_PELOTA, radio_max=3)

        dibujar_jugador(frame, pos_A, bbox_A, COLOR_BBOX_A, "Jugador A")
        dibujar_jugador(frame, pos_B, bbox_B, COLOR_BBOX_B, "Jugador B")

        if pelota:
            cv2.circle(frame, pelota, 9,  COLOR_PELOTA, -1)
            cv2.circle(frame, pelota, 11, (0, 0, 0),    1)

        frames_desde_golpe = procesados - ultimo_golpe_p
        if 0 < frames_desde_golpe <= 8 and golpe_pos and frames_desde_golpe % 2 == 1:
            cv2.circle(frame, golpe_pos, 28, COLOR_GOLPE, 3)
            cv2.putText(frame, "GOLPE", (golpe_pos[0] + 30, golpe_pos[1]),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.75, COLOR_GOLPE, 2, cv2.LINE_AA)

        dibujar_overlay(frame, frame_num, fps_orig, golpes_count, pos_A, pos_B)

        if procesados % 50 == 0:
            pct = 100 * frame_num // total
            print(f"  Frame {frame_num}/{total} ({pct}%) — "
                  f"cenital: {frames_cenital}  golpes: {golpes_count}")

        writer.write(frame)

        preview = cv2.resize(frame, (ancho_v // 2, alto_v // 2))
        cv2.imshow("Analisis Tenis", preview)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            print("  Cancelado por el usuario.")
            break

    cap.release()
    if writer:
        writer.release()
    cv2.destroyAllWindows()

    print()
    print("=== RESUMEN DEL PARTIDO ===")
    print(f"Frames con vista cenital: {frames_cenital} / {procesados} procesados")
    print(f"Golpes detectados:         {golpes_count}")
    print(f"Jugador A detectado:       {frames_A} frames")
    print(f"Jugador B detectado:       {frames_B} frames")
    print("===========================")

    guardar_trayectorias(tray_A_all, tray_B_all, img_cancha_rgb, frames_A, frames_B)
    guardar_mapa_calor(calor_A, calor_B, ys_A_cancha, ys_B_cancha,
                       img_cancha_rgb, alto_c, rect_cancha_img)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python analisis_tenis.py <video.mp4>")
        sys.exit(1)
    procesar_video(sys.argv[1])
