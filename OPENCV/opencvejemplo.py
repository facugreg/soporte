import cv2

cap =cv2.VideoCapture(0)

while(True):
    _, frame = cap.read()
    cv2.imshow("Mi primer OpenCV", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break
cap.release()
cv2.destroyAllWindows()


#Circulo 
cv2.circle()

#para escribir
cv2.putText()


#para tener una parte de la imagen especifica roi (region de interes)

#grabar frames 
import cv2
cap = cv2.VideoCapture(0)

while(True):
    _, frame = cap.read()
    cv2.imshow("Mi primer OpenCV", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

#grabar grabaciones
cv2.VideoWriter
