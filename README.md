# zm-alarm
Python3 script to process zoneminder alarms with YOLO4 in realtime
Tested on Ubuntu 22.04 and ZM version 1.36.xx

Requirements:
ZM configured for localhost http port 80 access
ZM Auth enabled
ZM API enabled
   
Additional packages:
apt get python3-mysqldb python3-numpy python3-opencv
apt get mailutils 
* mail must be setup to use emails
Download files for YOLO4: coco.names, yolov4.cfg, yolov4.weights
 
Usage:
After updating settings (lines 38 to 86 in script), simply start the python script
Recommend to run script as normal user in home folder to simplify permissions.
e.g. python3 /home/user/zm-alarm_02.py

The script can either email or store to a folder of your choice a JPG of the object detected.


![Screenshot](Screenshot.png)
