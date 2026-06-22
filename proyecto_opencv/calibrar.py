import cv2
import sys
from datetime import datetime

ESCALA = 0.5

puntos = []
_cursor = [None]   # guarda (x_display, y_display) para redibujar tras Z/C


def _area_poligono(pts):
    """Fórmula del conteo (shoelace)."""
    n = len(pts)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += pts[i][0] * pts[j][1]
        area -= pts[j][0] * pts[i][1]
    return abs(area) / 2.0


def dibujar(frame, pts, cursor=None):
    img = cv2.resize(frame, None, fx=ESCALA, fy=ESCALA)

    # Instrucciones
    cv2.putText(img,
                "Clic izq: agregar punto | Z: deshacer ultimo | C: limpiar todo | ENTER: guardar | ESC: salir",
                (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 255), 1, cv2.LINE_AA)

    # Coordenadas del cursor
    if cursor is not None:
        xr = int(cursor[0] / ESCALA)
        yr = int(cursor[1] / ESCALA)
        cv2.putText(img, f"x={xr}  y={yr}", (8, 38),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 255, 0), 1, cv2.LINE_AA)

    # Líneas del polígono entre puntos consecutivos
    if len(pts) >= 2:
        for i in range(len(pts) - 1):
            p1 = (int(pts[i][0]   * ESCALA), int(pts[i][1]   * ESCALA))
            p2 = (int(pts[i+1][0] * ESCALA), int(pts[i+1][1] * ESCALA))
            cv2.line(img, p1, p2, (0, 255, 255), 1, cv2.LINE_AA)
        if len(pts) > 2:
            p_ini = (int(pts[0][0]  * ESCALA), int(pts[0][1]  * ESCALA))
            p_fin = (int(pts[-1][0] * ESCALA), int(pts[-1][1] * ESCALA))
            cv2.line(img, p_fin, p_ini, (0, 180, 180), 1, cv2.LINE_AA)

    # Puntos y etiquetas
    for i, p in enumerate(pts):
        px = int(p[0] * ESCALA)
        py = int(p[1] * ESCALA)
        cv2.circle(img, (px, py), 5, (0, 0, 255), -1)
        cv2.putText(img, str(i + 1), (px + 8, py - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)

    # Área del polígono (solo con 4+ puntos)
    if len(pts) >= 4:
        area = _area_poligono(pts)
        cv2.putText(img, f"Area: {area:.0f} px2",
                    (8, img.shape[0] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (180, 255, 180), 1, cv2.LINE_AA)

    cv2.imshow("Calibracion", img)


def mouse(event, x, y, flags, param):
    frame = param
    _cursor[0] = (x, y)
    dibujar(frame, puntos, (x, y))
    if event == cv2.EVENT_LBUTTONDOWN:
        xr = int(x / ESCALA)
        yr = int(y / ESCALA)
        puntos.append((xr, yr))
        print(f"Punto {len(puntos)}: ({xr}, {yr})")


def guardar_resultado(video_name, pts):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lineas = [
        f"# Calibracion generada el {ts}",
        f"# Video: {video_name}",
        f"# Puntos: {len(pts)}",
        "",
        "CANCHA_PUNTOS = np.array([",
    ]
    for p in pts:
        lineas.append(f"    [{p[0]}, {p[1]}],")
    lineas.append("], dtype=np.int32)")

    contenido = "\n".join(lineas)

    print("\n" + "=" * 55)
    print(contenido)
    print("=" * 55)

    with open("calibracion.txt", "w", encoding="utf-8") as f:
        f.write(contenido + "\n")
    print(f"\nGuardado en calibracion.txt")


# ---- Main ----

if len(sys.argv) > 1:
    video_name = sys.argv[1]
else:
    video_name = input("Nombre del video (ej: djokovic.mp4): ").strip()

cap = cv2.VideoCapture(video_name)
if not cap.isOpened():
    print(f"ERROR: No se pudo abrir '{video_name}'")
    sys.exit(1)

ret, frame = cap.read()
cap.release()

if not ret:
    print("ERROR: No se pudo leer el primer frame.")
    sys.exit(1)

cv2.namedWindow("Calibracion")
cv2.setMouseCallback("Calibracion", mouse, frame)
dibujar(frame, puntos)

while True:
    key = cv2.waitKey(30) & 0xFF

    if key == 27:          # ESC — salir
        break
    elif key in (ord('z'), ord('Z')):
        if puntos:
            eliminado = puntos.pop()
            print(f"Punto eliminado: {eliminado}  (quedan {len(puntos)})")
            dibujar(frame, puntos, _cursor[0])
    elif key in (ord('c'), ord('C')):
        puntos.clear()
        print("Todos los puntos eliminados.")
        dibujar(frame, puntos, _cursor[0])
    elif key == 13:        # ENTER — guardar
        if len(puntos) < 4:
            print(f"AVISO: solo hay {len(puntos)} punto(s). Se recomiendan al menos 4.")
        else:
            guardar_resultado(video_name, puntos)

cv2.destroyAllWindows()

print("\n=== CANCHA_PUNTOS listo para copiar/pegar ===")
print("CANCHA_PUNTOS = np.array([")
for p in puntos:
    print(f"    [{p[0]}, {p[1]}],")
print("], dtype=np.int32)")
