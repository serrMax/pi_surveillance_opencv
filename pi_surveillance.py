from pyimagesearch.tempimage import TempImage
from picamera.array import PiRGBArray
from picamera import PiCamera
import argparse
import warnings
import datetime
import imutils
import json
import time
import cv2
import smtplib
import imghdr
from email.message import EmailMessage

# constructing the argument parser and parsing arguments
ap = argparse.ArgumentParser()
ap.add_argument("-c", "--conf", required=True,help="path to the JSON configuration file")
args = vars(ap.parse_args())

# filtering useless warnings
warnings.filterwarnings("ignore")
conf = json.load(open(args["conf"]))

# camera initialisation 
camera = PiCamera()
camera.resolution = tuple(conf["resolution"])
camera.framerate = conf["fps"]
rawCapture = PiRGBArray(camera, size=tuple(conf["resolution"]))

# allowing the camera to warmup, then initializing the average frame, last
# uploaded timestamp, and frame motion counter
print("[INFO] warming up...")
time.sleep(conf["camera_warmup_time"])
avg = None
lastUploaded = datetime.datetime.now()
motionCounter = 0
send = True

# capturing frames from the camera
for f in camera.capture_continuous(rawCapture, format="bgr", use_video_port=True):
	# using the raw NumPy array representing the image and initializing the timestamp and room status
	frame = f.array
	timestamp = datetime.datetime.now()
	text = "Unoccupied"

	# resizing the frame, converting it to grayscale, and blurring it
	frame = imutils.resize(frame, width=500)
	gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
	gray = cv2.GaussianBlur(gray, (21, 21), 0)

	# if the average frame is None, should initialize it
	if avg is None:
		print("[INFO] starting background model...")
		avg = gray.copy().astype("float")
		rawCapture.truncate(0)
		continue

	# using the difference between current frame and average to "see" motion
	cv2.accumulateWeighted(gray, avg, 0.5)
	frameDelta = cv2.absdiff(gray, cv2.convertScaleAbs(avg))

    # finding contours
	thresh = cv2.threshold(frameDelta, conf["delta_thresh"], 255,cv2.THRESH_BINARY)[1]
	thresh = cv2.dilate(thresh, None, iterations=2)
	cnts = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
	cnts = imutils.grab_contours(cnts)

	# looping over the contours
	for c in cnts:
		# if the contour is too small, ignoring it
		if cv2.contourArea(c) < conf["min_area"]:
			continue

		# drawing the contour on the frame and updating the room status(occupied/not occupied)
		(x, y, w, h) = cv2.boundingRect(c)
		cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
		text = "Occupied"
	# drawing the text and timestamp on the frame
	ts = timestamp.strftime("%A %d %B %Y %I:%M:%S%p")

	cv2.putText(frame, "Room Status: {}".format(text), (10, 20),cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

	cv2.putText(frame, ts, (10, frame.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX,0.35, (0, 0, 255), 1)
    
    # checking to see if the room is occupied
	if text == "Occupied":
		# check to see if enough time has passed between notifications
		if (timestamp - lastUploaded).seconds >= conf["min_upload_seconds"]:
			# increment the motion counter
			motionCounter += 1
            send=True
			# checking to see if the number of frames with consistent motion is high enough (actual motion, big size)
			if motionCounter >= conf["min_motion_frames"]:
				# checking to see if the email notifications should be sent
				if conf["use_dropbox"]:

					# writing the image to temporary file
					t = TempImage()
					cv2.imwrite(t.path, frame)
                    
					#send the email and clean the picture
					print("[UPLOAD] {}".format(ts))
                    if send == True :
                        Sender_Email = ""
                        Receiver_Email = ""
                        Password = ""
                        newMessage = EmailMessage()
                        newMessage['Subject'] = ""
                        newMessage['From'] = Sender_Email
                        newMessage['To'] = Receiver_Email
                        newMessage.set_content("")
                        with open(t.path, 'rb') as f :
                            image_data = f.read()
                            image_type = imghdr.what(f.name)
                            image_name = f.name
                        newMessage.add_attachment(image_data, maintype="image", subtype=image_type, filename=image_name)
                        with smtplib.SMTP_SSL('smtp.anymailservice.com', 465) as smtp:
                            smtp.login(Sender_Email, Password)
                            smtp.send_message(newMessage)
                        send=False
					t.cleanup()

				# updating the last uploaded timestamp and resetting the motion counter
				lastUploaded = timestamp
				motionCounter = 0

	# otherwise, the room is not occupied
	else:
		motionCounter = 0

    # checking to see if the frames should be displayed to screen
	if conf["show_video"]:
		# displaying the security feed
		cv2.imshow("Security Feed", frame)
		key = cv2.waitKey(1) & 0xFF

		# if the `q` key is pressed, stop everything
		if key == ord("q"):
			break

	# clearing the stream in preparation for the next frame
	rawCapture.truncate(0)