import cv2
import numpy as np
import threading
import time
from kivy.app import App
from kivy.uix.image import Image as KivyImage
from kivy.clock import Clock
from kivy.graphics.texture import Texture

MARKER_SIZE_CM = 5.0
ALPHA = 0.95    # opacidad del cubo (0=invisible, 1=sólido). Subido respecto
                # al original porque un Rubik's cube es plástico opaco, no
                # tiene sentido que se "transparente" como el bloque de tierra.

_S = MARKER_SIZE_CM
_H = _S / 2

# Las 4 esquinas del marcador ArUco en coordenadas 3D reales (en cm, Z=0 = plano del papel).
# Orden: TL, TR, BR, BL — mismo orden que devuelve el detector.
MARKER_OBJ_PTS = np.float32([
    [-_H,  _H, 0], [_H,  _H, 0], [_H, -_H, 0], [-_H, -_H, 0],
])

# 8 vértices del cubo: 4 en la base (Z=0, apoyados en el marcador) y 4 en el techo (Z=_S).
CUBE_VERTS = np.float32([
    [-_H, -_H,  0], [_H, -_H,  0], [_H,  _H,  0], [-_H,  _H,  0],  # base
    [-_H, -_H, _S], [_H, -_H, _S], [_H,  _H, _S], [-_H,  _H, _S],  # techo
])

# Cada cara: lista de índices en CUBE_VERTS + nombre de textura.
# CAMBIO CLAVE respecto al original: antes 4 caras compartían la misma
# textura 'side' (todas iguales, como un bloque de tierra). Un Rubik's
# cube tiene sus 6 caras de colores DISTINTOS, así que ahora cada una
# tiene su propio nombre único: top, bottom, front, back, left, right.
FACES = [
    ([4, 5, 6, 7], 'top'),
    ([0, 1, 2, 3], 'bottom'),
    ([4, 5, 1, 0], 'front'),
    ([5, 6, 2, 1], 'right'),
    ([6, 7, 3, 2], 'back'),
    ([7, 4, 0, 3], 'left'),
]


def make_textures(size=90):
    """
    Genera una textura de 3x3 "stickers" por cada cara del cubo, imitando
    un Rubik's cube real: fondo negro (el plástico del cubo) con 9 cuadrados
    de color separados por una grilla, igual que las etiquetas pegadas en
    un cubo físico.

    Usa el esquema de colores clásico (orientación occidental BOY):
    blanco arriba, amarillo abajo, rojo-naranja opuestos, azul-verde opuestos.
    Los colores están en BGR porque así los usa OpenCV, no RGB.
    """
    rng = np.random.default_rng(7)

    def sticker_face(color_bgr):
        img = np.zeros((size, size, 3), dtype=np.uint8)
        img[:] = (18, 18, 18)  # plástico negro de fondo / separaciones entre stickers

        border = max(2, size // 18)   # grosor del "surco" negro entre stickers
        cell = size // 3

        for row in range(3):
            for col in range(3):
                y0, y1 = row * cell + border, (row + 1) * cell - border
                x0, x1 = col * cell + border, (col + 1) * cell - border

                # Pequeña variación de tono por sticker, para que no se vea
                # un color totalmente plano/digital sino con algo de textura
                # plástica (como el ruido que usaba la versión Minecraft).
                shade = rng.integers(-8, 8, 3)
                sticker = np.clip(np.array(color_bgr, dtype=np.int32) + shade, 0, 255)
                img[y0:y1, x0:x1] = sticker.astype(np.uint8)

        return img

    colores_bgr = {
        'top':    (255, 255, 255),  # blanco
        'bottom': (0, 213, 255),    # amarillo
        'front':  (0, 0, 213),      # rojo
        'back':   (0, 115, 255),    # naranja
        'left':   (70, 155, 0),     # verde
        'right':  (200, 70, 0),     # azul
    }

    return {nombre: sticker_face(color) for nombre, color in colores_bgr.items()}


def camera_matrix(w, h):
    """
    Matriz intrínseca de cámara aproximada (SIN calibración real).
    f = focal length estimada como el lado mayor de la imagen (en píxeles).
    cx, cy = centro óptico asumido en el centro del frame.
    Esto es intencional: no se pide tablero de ajedrez ni proceso de
    calibración, a costa de algo de precisión en la pose del cubo.
    """
    f = max(w, h)
    return np.float32([[f, 0, w/2], [0, f, h/2], [0, 0, 1]])


def draw_rubiks_cube(frame, pts2d, verts_cam, textures):
    """
    Dibuja el cubo sobre el frame usando painter's algorithm:
    ordena las caras de más lejos a más cerca (por profundidad Z en cámara)
    y las pinta en ese orden para que las cercanas tapen a las lejanas.

    Para cada cara:
      1. getPerspectiveTransform: calcula la homografía textura → cuadrilátero 2D.
      2. warpPerspective: deforma la textura (el sticker 3x3) al cuadrilátero proyectado.
      3. fillPoly + addWeighted: aplica la textura con opacidad (ALPHA).
    """
    h_f, w_f = frame.shape[:2]
    faces_by_depth = sorted(
        [(np.mean([verts_cam[i][2] for i in vidx]), vidx, tname) for vidx, tname in FACES],
        reverse=True,  # painter's algorithm: más lejos primero
    )
    for _, vidx, tname in faces_by_depth:
        dst = np.array([pts2d[i] for i in vidx], dtype=np.float32)
        tex = textures[tname]
        t_h, t_w = tex.shape[:2]
        src = np.float32([[0, 0], [t_w, 0], [t_w, t_h], [0, t_h]])
        M = cv2.getPerspectiveTransform(src, dst)
        warped = cv2.warpPerspective(tex, M, (w_f, h_f), flags=cv2.INTER_NEAREST)
        mask = np.zeros((h_f, w_f), dtype=np.uint8)
        cv2.fillPoly(mask, [dst.astype(int)], 255)
        blended = cv2.addWeighted(frame, 1 - ALPHA, warped, ALPHA, 0)
        frame[mask > 0] = blended[mask > 0]


class AR3DApp(App):
    title = "ArUco 3D - Rubik's Cube"

    def build(self):
        """Inicializa la app: widget de imagen, detector ArUco, hilo de cámara y timer de UI."""
        self.img_widget = KivyImage()
        self.textures = make_textures()
        self.dist = np.zeros(4)   # coeficientes de distorsión (sin calibración = cero)
        self.K = None             # matriz de cámara, se calcula al recibir el primer frame
        self.poses = {}           # {marker_id: [rvec, tvec, frames_sin_detectar]}
        self.kv_tex = None        # textura Kivy reutilizable (evita crearla cada frame)
        self._frame = None        # último frame procesado, compartido entre threads
        self._lock = threading.Lock()

        params = cv2.aruco.DetectorParameters()
        params.cornerRefinementMethod    = cv2.aruco.CORNER_REFINE_SUBPIX
        params.minMarkerPerimeterRate      = 0.05
        params.adaptiveThreshWinSizeMin    = 7
        params.adaptiveThreshWinSizeMax    = 23
        params.adaptiveThreshWinSizeStep   = 8
        params.polygonalApproxAccuracyRate = 0.03
        params.errorCorrectionRate         = 0.6
        self.detector = cv2.aruco.ArucoDetector(
            cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_250), params
        )

        threading.Thread(target=self._capture_loop, daemon=True).start()
        Clock.schedule_interval(self.update, 1 / 60)
        return self.img_widget

    def _capture_loop(self):
        """
        Hilo dedicado a la cámara: captura frames, detecta marcadores ArUco,
        calcula la pose con solvePnP y dibuja el cubo antes de pasar el frame a la UI.
        """
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("ERROR: no se pudo abrir la cámara")
            return
        while True:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.01)
                continue
            if self.K is None:
                h, w = frame.shape[:2]
                self.K = camera_matrix(w, h)

            corners, ids, _ = self.detector.detectMarkers(frame)
            detected_ids = set()
            if ids is not None:
                for corner, mid in zip(corners, ids.flatten()):
                    if cv2.contourArea(corner[0]) < 400:
                        continue
                    ok, rvec, tvec = cv2.solvePnP(
                        MARKER_OBJ_PTS, corner[0], self.K, self.dist,
                        flags=cv2.SOLVEPNP_IPPE_SQUARE,
                    )
                    if ok:
                        self.poses[mid] = [rvec, tvec, 0]
                        detected_ids.add(mid)

            for mid in list(self.poses):
                if mid not in detected_ids:
                    self.poses[mid][2] += 1
                    if self.poses[mid][2] > 8:
                        del self.poses[mid]

            for rvec, tvec, _ in self.poses.values():
                pts2d, _ = cv2.projectPoints(CUBE_VERTS, rvec, tvec, self.K, self.dist)
                pts2d = pts2d.reshape(-1, 2)
                R, _ = cv2.Rodrigues(rvec)
                verts_cam = (R @ CUBE_VERTS.T + tvec).T
                draw_rubiks_cube(frame, pts2d, verts_cam, self.textures)

            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame = cv2.flip(frame, 0)
            with self._lock:
                self._frame = frame

    def update(self, dt):
        """Llamada 60 veces/seg por Kivy: copia el último frame y lo sube a la textura de la UI."""
        with self._lock:
            if self._frame is None:
                return
            frame = self._frame.copy()
        h, w, _ = frame.shape
        if self.kv_tex is None:
            self.kv_tex = Texture.create(size=(w, h))
        self.kv_tex.blit_buffer(frame.tobytes(), colorfmt='rgb', bufferfmt='ubyte')
        self.img_widget.texture = self.kv_tex
        self.img_widget.canvas.ask_update()


if __name__ == "__main__":
    AR3DApp().run()