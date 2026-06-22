import cv2

ESCALA = 0.5      # 50%

puntos = []

def mouse(event, x, y, flags, param):
    global puntos

    frame = param

    # Convertir coordenadas de la ventana a coordenadas reales
    xr = int(x / ESCALA)
    yr = int(y / ESCALA)

    img = cv2.resize(frame, None, fx=ESCALA, fy=ESCALA)

    cv2.putText(img,
                f"x={xr} y={yr}",
                (20,30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0,255,0),
                2)

    for i, p in enumerate(puntos):
        px = int(p[0] * ESCALA)
        py = int(p[1] * ESCALA)

        cv2.circle(img, (px,py), 5, (0,0,255), -1)
        cv2.putText(img,
                    str(i+1),
                    (px+8,py-8),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (255,255,255),
                    2)

    cv2.imshow("Calibracion", img)

    if event == cv2.EVENT_LBUTTONDOWN:
        puntos.append((xr, yr))
        print(f"Punto {len(puntos)}: ({xr}, {yr})")

cap = cv2.VideoCapture("amateurtenis.mp4")

ret, frame = cap.read()

cv2.namedWindow("Calibracion")

cv2.setMouseCallback("Calibracion", mouse, frame)

while True:

    img = cv2.resize(frame, None, fx=ESCALA, fy=ESCALA)

    cv2.imshow("Calibracion", img)

    if cv2.waitKey(1) == 27:
        break

cv2.destroyAllWindows()

print("\nCANCHA_PUNTOS = np.array([")
for p in puntos:
    print(f"    [{p[0]}, {p[1]}],")
print("], dtype=np.int32)")