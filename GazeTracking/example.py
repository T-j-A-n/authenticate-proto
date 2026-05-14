"""
Demonstration of the GazeTracking library.
Check the README.md for complete documentation.
"""

import sys

import cv2

from gaze_tracking import GazeTracking

gaze = GazeTracking()
webcam = cv2.VideoCapture(0)

if not webcam.isOpened():
    sys.exit("Could not open the webcam. Check that it is connected and that camera permissions are granted.")

while True:
    # We get a new frame from the webcam
    ret, frame = webcam.read()
    if not ret or frame is None:
        sys.exit("Lost the webcam stream. Check that no other app is using the camera.")

    # We send this frame to GazeTracking to analyze it
    frame = cv2.flip(frame, 1)

    gaze.refresh(frame)

    frame = gaze.annotated_frame()
    text = ""

    if gaze.is_blinking():
        text = "Blinking"
    elif gaze.is_right():
        text = "Looking right"
    elif gaze.is_left():
        text = "Looking left"
    elif gaze.is_center():
        text = "Looking center"

    cv2.putText(frame, text, (90, 60), cv2.FONT_HERSHEY_DUPLEX, 1.6, (147, 58, 31), 2)

    left_pupil = gaze.pupil_left_coords()
    right_pupil = gaze.pupil_right_coords()
    cv2.putText(frame, f"Left pupil:  {left_pupil}", (90, 130), cv2.FONT_HERSHEY_DUPLEX, 0.9, (147, 58, 31), 1)
    cv2.putText(frame, f"Right pupil: {right_pupil}", (90, 165), cv2.FONT_HERSHEY_DUPLEX, 0.9, (147, 58, 31), 1)

    cv2.imshow("Demo", frame)

    if cv2.waitKey(1) & 0xFF == 27:
        break

webcam.release()
