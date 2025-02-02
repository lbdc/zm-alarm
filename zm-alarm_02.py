#!/usr/bin/env python3

import MySQLdb
import MySQLdb.cursors
import multiprocessing
import subprocess
import argparse
import datetime
import sys
import requests
from http.cookiejar import MozillaCookieJar
import json
import time
from decimal import Decimal
import os
import shutil
import glob
import imghdr
import re

# imports for opencv
import numpy as np
import cv2

#########################################################
# Requirements:
# ZM configured for local http port 80 access
# ZM Auth enabled
# ZM API enabled
# Ensure "movflags=faststart" is NOT enabled in camera storage
#
# Additional packages:
# apt get python3-mysqldb python3-numpy python3-opencv
# apt get mailutils (mail must be setup to use emails)
# Download files coco.names, yolov4.cfg, yolov4.weights
# 
# Usage:
# After updating settings, simply start the python script
# Recommend to run script as normal user in home folder
#########################################################
# Settings section below. Update as required
#########################################################
#
# Zoneminder credentials
# Camera ID's to perform object detection
#
cameras = "3,12,13,9,8"
#
# Camera ID's to send emails
emails = "9"
#
# How many frames to analyse for each alarm
frame_analysis = 4 # default 3. Increase for better accuracy but analysis takes longer
#
# ZM authentification
zm_user="admin"
zm_pass="admin"

# Zoneminder database credentials.
db_cred = {"host":"localhost", "user":"zmuser", "password":"zmpass", "database":"zm"}
#
# Paths
path_pic = "/home/user/zm_ai/pic/" # tmp folder for img to be analyzed
path_opencv = "/home/user/zm_ai/opencv4/" # locations of files coco.names, yolov4.cfg, yolov4.weights
path_hb = "/tmp/" # heartbeat path for timestamp file. Use crontab and external shell script to scan and restart if timestamp is not current. 
#
# ssmtp has to be setup and working under normal user
# enter email to send notification to
use_email = 1 # 0 = disable, 1 = enable, or use keyword trigger "no_email" in html root to override
email = "user@gmail.com" 
#
# save detection to file
use_save = 1 # 0 = disable
path_save = "/home/user/zm_ai/pic/save/"

# When saving detection to file, use bounding box or not
use_box = 0 # use 1 or 0
#
# what to detect and send email. See coco.names for options
words_list = ["person", "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe"]
thresh = 0.70 # threshold detection 0 to 1
#
# Don't change this
use_opencv = 1 # Leave this to 1

# Set a delay in seconds in case too many alarms (default 1s)
delay = 1

# log file to keep record.
log_file = "/var/www/html/zm-alarm_output.log"
log_enable = 1 # enable logging to file (1) or not (0)
hb_enable = 1 # enable heartbeat

#################################################
# End of settings section
#################################################

#################################################
# Declare globals
#################################################
# main variable to store monitor details
# initialize monitor variable (nested dict)

monitors = {}
alarms = []
cookies = ""

for index in cameras.split(","):
	monitors[index] = {'State':-1,'St':-1,'Et':-1, 'Set': 0}
	
#init database. Use MySQLdb instead of python connector, seems more stable
mydb = MySQLdb.connect(**db_cred, cursorclass=MySQLdb.cursors.DictCursor)

#################################################
# main
#################################################
def main():

# initialize empty list to store alarm events 
	global alarms, cookies, script_start, mydb
	retry = 0
# init misc local variables
	current_time = time.time()
	current_time_hb = time.time()
	heartbeat() # initiate hb file
#init database
	mydb = init_mysql()

# clear screen
	os.system('clear')
	
# Initialize folders
	if not os.path.isdir(path_pic):
		os.makedirs(path_pic)
		
	if use_save == 1 and not os.path.isdir(path_save):
		os.makedirs(path_save)

	if not os.path.isdir(path_opencv):
		printLog(tstamp(), " Verify path and files coco.names, yolov4.cfg, yolov4.weights")
		exit()
		
	if not os.path.isdir(path_hb) and hb_enable == 1:
		printLog(tstamp(), " Verify heartbeat path")
		exit()

	printLog(tstamp(), "zm-alarm monitoring started:", os.path.basename(__file__))
#
# Call login function to get token and store cookie. Login to be reinitialized every hour
#
	a_token, cookies = login()
#
# The while statement continuously loop over monitors and update state in monitors (1 or 5 = idle, 3 = alarm). Queues alarms in case of many.
# This is the main alarm detection loop
# Scans mnonitor state via monitor_state() function
# If monitor returns from alarm state, execute SQL query to get relevant frames with best scores.
# Frames are queued in a TMP folder for processing via opencv4() function 
#  
	anim = 0
	animation = ["—","\\", "|", "/"]
	while 1:
		if(anim > 2):
			anim = 0
		else:
			anim = anim + 1
		sys.stdout.write("\r" + animation[anim])
		monitor_state(a_token)
		for index in monitors:
			# if monitors come back from alarm state, sets alarm to be processed
			if monitors[index]['State'] == 1 or monitors[index]['State'] == 5:
				if monitors[index]['Set'] == 1:
					monitors[index]['Set'] = 0
					monitors[index]['Et'] = tstamp()
					alarms = alarms + [[index, monitors[index]['St'], monitors[index]['Et']]]
			# if monitors enter alarm state (and not already set)
			elif monitors[index]['State'] == 3:
				if monitors[index]['Set'] == 0:
					monitors[index]['Set'] = 1
					monitors[index]['St'] = tstamp()
		
		# Call mysql query function on alarm list queue, one at a time. Save retries.
		if alarms:
			retry = sql_query(retry)
		# Re initialize cookies and token every hour
		tm = time.time() - current_time
		if(tm > 3600):
			a_token, cookies = login()
			current_time = time.time()
		# printLog(tstamp(), "Reset cookies")
		# Touch heartbeat file every minute
		tm_hb = time.time() - current_time_hb
		if(tm_hb > 60):
			current_time_hb = time.time()
			heartbeat()

		time.sleep(delay)
		
#################################################
# functions	
#################################################

# login to zm and create cookie
def login():
	cookies = MozillaCookieJar()
	with requests.Session() as session:
		session.cookies = cookies
		response = session.post('http://localhost/zm/api/host/login.json', data={'user': zm_user, 'pass': zm_pass, 'stateful':'1'})
		a=response.json()
		a_token = a['access_token']
	return a_token, cookies

# get state of monitors with ZMU. 3 = alarm, 1 or 5 is idle
def monitor_state(a_token):
	for index in monitors:
		cmd = ['zmu', '-m', index, '-T', a_token, '-e', '-s']
		try:
			result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True)
			x = result.stdout.decode('UTF-8').strip().split(" ")
			monitors[index]['State'] = int(x[0])
		except subprocess.CalledProcessError as e:
			# Handle subprocess error
			print(f"Error running subprocess for monitor {index}. Return code: {e.returncode}")
			monitors[index]['State'] = 1  # Default to idle
		except (IndexError, ValueError) as e:
			# Handle index or value errors
			print(f"Error parsing response for monitor {index}. {e}")
			monitors[index]['State'] = 1  # Default to idle



# timestamp
def tstamp():
	x = datetime.datetime.now()
	return x.strftime("%Y-%m-%d %H:%M:%S")

# execute mysql query on zm database to get event and frame id's of alarm. Returns up to 3 highest alarm score
# includes retry code when SQL query doesn't behave
def sql_query(retry):

	global mydb, frame_analysis
	if mydb.open:
		m_id = alarms[0][0]
		st = alarms[0][1]
		et =alarms[0][2]
		# timstamp may be a bit late compared to zoneminder alarm so move the start time by 1s default)
		st = (datetime.datetime.strptime(st, "%Y-%m-%d %H:%M:%S") + datetime.timedelta(seconds=-1)).strftime("%Y-%m-%d %H:%M:%S")
		# if alarms in queue
		if alarms:
			# query alarms. The "DESC Limit 3" means the query will return 3 frameID corresponding the highest summed score of individual seconds
			query = "SELECT EventId, FrameId, TimeStamp, Type, SUM(Score) FROM Frames, Events WHERE Frames.Type='Alarm' AND Events.Id=Frames.EventId AND Frames.TimeStamp >= '" + st + "' AND Frames.Timestamp <= '" + et + "' AND MonitorId=" + m_id + " GROUP BY Timestamp ORDER BY sum(Score) DESC Limit " + str(frame_analysis) + ";"
			mycursor = mydb.cursor(MySQLdb.cursors.DictCursor)
			mycursor.execute(query)
			mydb.commit() # TRYING THIS HERE AS PER GOOGLE. May not be required.
			myresult = mycursor.fetchall()
			# if not empty proceed to write alarms to text file and scrape jpg for future processing
			if myresult:
				printLog(tstamp(), "Alarm MonitorId=", f"{m_id:2}", " Start=", st, " End=", et, " eid=", str(myresult[0]['EventId']))
				with open(path_pic + m_id + "-" + str(myresult[0]['EventId']) + str(myresult[0]['FrameId']) + ".tmp", "w") as f:
					for x, value in enumerate(myresult):
						f.write(path_pic + m_id + "-" + str(myresult[x]['EventId']) + "-" + str(myresult[x]['FrameId']) + '.jpg\n')
						scrape_pic(m_id, str(myresult[x]['EventId']), str(myresult[x]['FrameId']))
					f.close()
				# Rename file for processing by opencv (this waits until all jpg scrapes are finished before writing text file for processing)
				name, _ = os.path.splitext(f.name)
				new_name = name + '.txt'
				os.rename(f.name, new_name)
				# If success, drop the alarm from the queue
				alarms.pop(0)
				retry = 0
				#mydb.commit() # SEE ABOVE, MOVED IT AS A TRY
			else:
				# retry query and restart db connection
				retry = retry + 1
				if(retry >= 5 and retry < 10):
					# print("\nRetry execeeded, skip alarm")
					# move element at end of Q for later processing
					alarms.append(alarms[0])
					alarms.pop(0)
					#restart mysql
					init_mysql()
				# if it stills doesnt work, drop stale query
				elif(retry >= 10):
					printLog(tstamp(), "Stale query, drop alarm ", alarms[0])
					print(myresult);
					print(repr(query))
					alarms.pop(0)
					retry = 0
					
	else: 
		if not mydb.is_connected():
			mydb = mysql.connector.connect(**db_cred)
		elif mydb.is_connected():
			mucursor.close()
			mydb.close()
			time.sleep(2)
			mydb = mysql.connector.connect(**db_cred)
	return retry

# Get stills jpg from highest alarm scores.
def scrape_pic(m_id, eid, fid):
	url = "http://localhost/zm/?view=image&eid=" + eid + "&fid=" + fid
	response = requests.get(url,cookies=cookies)
	pic = path_pic + m_id + "-" + eid + "-" + fid + ".jpg"
	with open(pic, 'wb') as f:
		f.write(response.content)

# initialize mysql
def init_mysql():
	global mydb
	if not mydb.open:
		#print("Mysql not connected, function connecting")
		mydb = MySQLdb.connect(**db_cred)
		
	elif mydb.open:
		#print("\nMysql connected, function restarting")
		mydb.close()
		time.sleep(1)
		mydb = MySQLdb.connect(**db_cred)
	time.sleep(2)
	return(mydb)

# opencv object detection code yolov4
def ai_opencv4():
	while(1):
		# obj2 must be list in the form below for processing
		#['car', 0.72265625, '/home/pic/13-561155-39.jpg', 'car', 0.73828125, '/home/pic/13-561155-46.jpg', 'car', 0.73828125, '/home/pic/13-561155-53.jpg']
		global use_email
		obj = []
		obj1 = []
		obj2 = []
		subject = []
		attachment = []
		save_attach = []
		line_str = []
		deleteme = 1
		
		# Get list of all files only in the given directory
		list_of_files = filter( os.path.isfile,
                        glob.glob(path_pic + '*.txt') )
		# Sort list of files based on last modification time in ascending order
		list_of_files = sorted( list_of_files,
                        key = os.path.getmtime)
		# Iterate over sorted list of files and content for object detection. Sort by timestamp. 
		if list_of_files:
			# Setup arguments 
			LABELS_FILE = path_opencv + "coco.names"
			CONFIG_FILE = path_opencv + "yolov4.cfg"
			WEIGHTS_FILE = path_opencv + "yolov4.weights"
	
			#########################################
			# Part 1 opencv code 
			#########################################
			net = cv2.dnn.readNetFromDarknet(CONFIG_FILE, WEIGHTS_FILE)
			model = cv2.dnn_DetectionModel(net)
			model.setInputParams(scale=1 / 255, size=(608, 608), swapRB=True)
			#########################################
			# End of opencv
			#########################################
			with open(LABELS_FILE, 'r') as f:
				classes = f.read().splitlines()

			# iterate through pictures listed in txt file
			with open(list_of_files[0]) as f:
				for x, line in enumerate(f):
					line = line.strip()
					line_str.append(line)
					# 
					try:
						#########################################
						# Part 2 opencv code 
						#########################################

						image = cv2.imread(line)
						if image is not None:
							classIds, scores, boxes = model.detect(image, confThreshold=thresh, nmsThreshold=0.4)
							for (classId, score, box) in zip(classIds, scores, boxes):
								cv2.rectangle(image, (box[0], box[1]), (box[0] + box[2], box[1] + box[3]), color=(0, 255, 0), thickness=2)

								text = '%s: %.2f' % (classes[classId], score)

								cv2.putText(image, text, (box[0], box[1] - 5), cv2.FONT_HERSHEY_SIMPLEX, 1, color=(0, 255, 0), thickness=2)
								obj1 = [classes[classId], score, line]
								obj2 = obj2 + obj1

#							if bounding box option is set, copy the opencv image on the zm frame 
							if use_box:
								cv2.imwrite(line, image)	
						
						#########################################
						# End of opencv
						#########################################
					except IOError:
						printLog(tstamp(), "cannot identify image file", line)
						continue
				
			# result manipulation
			# convert list in triplets
			obj2 = [obj2[n:n+3] for n in range(0, len(obj2), 3)]
			# sort before importing in dict to get max unique values
			obj2.sort(key=lambda x: x[1])
			obj2_dict = {item[0]: item[1:] for item in obj2}

			# iterate through dict and find detected words
			for word in words_list:
				for k,v in obj2_dict.items():
					if k == word:
						#print("word found: ", k, v)
						percentage = "{:.0%}".format(float(v[0]))
						subject.append(k)
						subject.append(percentage)
						attachment.append("-A " + v[1])
						save_attach.append(v[1])
	
			#if object detected, process triggers
			if subject:
				printLog(tstamp(), "Detected: ", subject)
				# Trigger 1, do we keep files
				if use_save:
					for x in save_attach:
						head_tail = os.path.split(x)
						shutil.copy(x, path_save+head_tail[1])
				# Trigger 2, Do we email
				# Verify if email oveeride is enabled or not
				if os.path.exists("/var/www/html/no_email"):
					printLog(tstamp(), "email override enabled: /var/www/html/no_email")
				elif use_email:
					# Verify if camera is set to send email using filename
					match = re.search(r'(\d+)-', attachment[0])
					if match:
						cam_number = match.group(1)
						# split the emails variable into list
						email_numbers = emails.split(',') # e.g. ['3', '17', '20', '9', '8', '11']
						# email if cam is on the email list
						if str(cam_number) in email_numbers:
							print(f"Number {cam_number} found in emails!")
							# convert lists to string
							subject = " ".join(subject)
							attachment = " ".join(attachment)
							# prepare mail command
							mail_string = "echo \"" + subject + "\" | mail --mime -s \"" + subject + "\" " + attachment + " " + email
							mailstat = os.system(mail_string)
							if mailstat != 0:
								printLog(tstamp(), "mail status failed, will retry")
								deleteme = 0 # keep files and trying to send mail
			# after detection, delete items from tmp
			if deleteme:
				for x in line_str:
					try:
						os.remove(x)
					except OSError as e:
						# Handle the case when the file doesn't exist
						print(f"Error removing file {x}: {e}")

				if list_of_files:
					try:
						os.remove(list_of_files[0])
					except OSError as e:
						# Handle the case when the file doesn't exist
						print(f"Error removing file {list_of_files[0]}: {e}")	
		time.sleep(delay)
		# return is not used
		# return subject
		
# Function mailme not used. Code in opencv4 function.
def mailme(subject, attachment):
	mail_string = "echo \"" + subject + "\" | mail --mime -s \"" + subject + "\" " + attachment + " " + email
	if subject:
		printLog(tstamp(), " mail status:", os.system(mail_string))

# Functio to print to console and log. Maintain log files to 100 lines or less.
def printLog(*args, **kwargs):
	global log_enable
	max_lines = 500  # Maximum number of lines in the log file
	print("\b\033[32m*", "\033[0m", *args, **kwargs)
	if log_enable:
		with open(log_file, 'r') as file:
		# Read all lines from the file
			lines = file.readlines()
		# Keep only the last 100 lines
		lines = lines[-max_lines:]
		# Open the file in write mode to overwrite its content
		with open(log_file, 'w') as file:
			# Write the last 100 lines back to the file
			file.writelines(lines)	
			# Write the new log entry
			print(*args, **kwargs, file=file)
def heartbeat():
	# update timestamp to tmp file. Use external shell script to verify it runs normally.
	if hb_enable:
		try:
		# Open the file in 'a' (append) mode and immediately close it
			with open(path_hb + "alarm_hb", 'a'):
				os.utime(path_hb + "alarm_hb", None)
		except Exception as e:
			printLog(tstamp(), "Error touching heartbeat file: " + str(e))
	# Verify if opencv4 function is running in multiprocessing. If not exit.
	if not ai_opencv4.is_alive():
		printLog(tstamp(), "Function ai_opencv4 failed. Exiting.")
		sys.exit()
		
if __name__ == '__main__':
	#
	# Create a multiprocessing Process with function ai_opencv4() and start it
	#
	ai_opencv4 = multiprocessing.Process(target=ai_opencv4)
	ai_opencv4.start()
	# Call main function
	main()
	# Wait for both subprocesses to finish before exiting. Not needed.
	# ai_opencv4.join()
