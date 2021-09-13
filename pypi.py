#!/usr/local/opt/python-3.5.1/bin/python3.5
# SDI-12 Sensor Data Logger Copyright Dr. John Liu 2017-11-06
# 2019-03-01 Michelle Wilber tailored this to be specific to the pipy pyronometer project
# 2017-11-06 Updated telemetry code to upload to thingspeak.com from data.sparkfun.com.
# 2017-06-23 Added exception handling in case the SDI-12 + GPS USB adapter doesn't return any data (no GPS lock).
#            Added serial port and file closing in ctrl + C handler.
# 2017-02-02 Added multiple-sensor support. Just type in multiple sensor addresses when asked for addresses.
#            Changed sdi_12_address into regular string from byte string. I found out that byte strings when iterated over becomes integers.
#            It's easy to cast each single character string into byte string with .encode() when needed as address.
#            Removed specific analog input code and added the adapter address to the address string instead.
# 2016-11-12 Added support for analog inputs
# 2016-07-01 Added .strip() to remove \r from input files typed in windows
# Added Ctrl-C handler
# Added sort of serial port placing FTDI at item 0 if it exists

import os # For running command line commands
import requests #http library to use api to get weather data
import json #for dealing with weather data
import numpy #math - mostly for taking natural logs below!
import time # For delaying in seconds
import datetime # For finding system's real time
import serial.tools.list_ports # For listing available serial ports
import serial # For serial communication
import re # For regular expression support 
import platform # For detecting operating system flavor
import urllib.parse # For encoding data to be url safe.
import signal # For trapping ctrl-c or SIGINT
import sys # For exiting program with exit code

def SIGINT_handler(signal, frame):
    ser.close()
    data_file.close()
    print('Quitting program!')
    sys.exit(0)
signal.signal(signal.SIGINT, SIGINT_handler)

curl_exists=False # The code will test whether cURL exists. If it exists, it will be used to upload data.
adapter_sdi_12_address='z'
no_data=False # This is the flag to break out of the inner loops and continue the next data point loop in case no data is received from a sensor such as the GPS.
Htrcntrl = False #this will be used to turn the CS320 heater on and off
Tc = 0 #initialize outdoor temperature variable
rh = 0 #initialize outdoor humidity variable
timestep = 5 # #Data point interval
#this is some stuff needed to get weather data from OpenWeatherMap:
#city_name = "Anchorage" #change for location of pypi - may need to use coordinates instead
#yes, use city ID or coordinates instead for accuracy
lat = "64.8378" #Fairbanks
lon = "-147.7167" #Fairbanks
owm_api_key = "35e2127ff5a8c609c0fa6114b82b5548"
#get_weather_url = "https://api.openweathermap.org/data/2.5/weather?appid=" + owm_api_key+ "&q=" + city_name
get_weather_url = "https://api.openweathermap.org/data/2.5/weather?appid=" + owm_api_key+ "&lat=" + lat + "&lon=" + lon


#wait up to one minture for the network to be avaialble
for i in range(30):
    try:
        #os.system('curl -V')
        os.system('ping -c 1 www.google.com')
        #curl_exists=True #really this is curl and connection_exists, but I am leaving the legacy variable name in for laziness
        print('internet connection exists')
        break
    except:
        #if curl returns non-zero error code, an exception is raised
        #wait and try again
        time.sleep(2)
    

print('+-'*40)
print('SDI-12 Sensor and Analog Sensor Python Data Logger with Telemetry V1.5.0')
print('Designed for Dr. Liu\'s family of SDI-12 USB adapters (standard,analog,GPS)\n\tDr. John Liu Saint Cloud MN USA 2017-11-06\n\t\tFree software GNU GPL V3.0')
print('\nCompatible with Windows, GNU/Linux, Mac OSX, and Raspberry PI')
print('\nThis program requires Python 3.4, Pyserial 3.0, and cURL (data upload)')
print('\nData is logged to YYYYMMDD.CVS in the Python code\'s folder')
#print('\nVisit https://thingspeak.com/channels/%s to inspect or retrieve data' %(channelID))
# print('\nIf multiple people are running this code, they are distinguished by unit_id, although all raspberry pis have the same "raspberrypi" unit_id.')
print ('\nFor assistance with customization, telemetry etc., contact Dr. Liu.\n\thttps://liudr.wordpress.com/gadget/sdi-12-usb-adapter/')
print('+-'*40)

VID_FTDI=0x0403; #vendor ID in hexidecimal, this is 1027 when returned as an int, as below

a=serial.tools.list_ports.comports()
for w in a:
    if w.vid == 1027: #this is the USB vendor ID for the SDI12 adapter in int form.  This will only work if there is only one of this type of adapter!
        print('port:', w.vid)
        port = w
    
print('port:', port)

ser=serial.Serial(port.device,baudrate=9600,timeout=10)
time.sleep(2.5) # delay for arduino bootloader and the 1 second delay of the adapter.


#    now=datetime.datetime.utcnow() # use UTC time instead of local time

now=datetime.datetime.now() # use local time, not recommended for multiple data loggers in different time zones

if 'data' not in os.listdir('/home/pi/pypi'):
    os.mkdir('/home/pi/pypi/data')
    
sdi_12_address=''
#user_sdi_12_address=input('Enter all SDI-12 sensor addresses, such as 1234:')
#user_sdi_12_address=user_sdi_12_address.strip() # Remove any \r from an input file typed in windows
user_sdi_12_address='0' #this is the default for a single sensor that has not been re-addressed - this could cause problems, better to manually set addresses maybe


for an_address in user_sdi_12_address:
    if ((an_address>='0') and (an_address<='9')) or ((an_address>='A') and (an_address<='Z')) or ((an_address>='a') and (an_address<='z')):
        print("Using address:",an_address);
        sdi_12_address=sdi_12_address+an_address
    else:
        print('Invalid address:',an_address)

if len(sdi_12_address)==0:
    sdi_12_address=adapter_sdi_12_address # Use default address

for an_address in sdi_12_address:
    ser.write(an_address.encode()+b'I!')
    sdi_12_line=ser.readline()
    print('Sensor address:',an_address,' Sensor info:',sdi_12_line.decode('utf-8').strip())
    
ser.close()

# print('Saving to %s' %data_file_path)

while True:
    # Data filename needs to be inside the While loop so it properly starts a new file at midnight
    data_file_name="%04d%02d%02d.csv" %(now.year,now.month,now.day)
    data_file_path = "/home/pi/pypi/data/" + data_file_name
    
    while True:
        if datetime.datetime.now().second % timestep == 0:
            break
        else:
            time.sleep(0.05)
            
            
    i=0 # This counts to 6 to truncate all data to the 6 values set up in sparkfun's phant server upload.
    value_str='' # This stores &value0=xxx&value1=xxx&value2=xxx&value3=xxx&value4=xxx&value5=xxx and is only reset after all sensors are read.
    #now=datetime.datetime.utcnow() 
    now=datetime.datetime.now()
    #output_str="%04d/%02d/%02d %02d:%02d:%02d%s" %(now.year,now.month,now.day,now.hour,now.minute,now.second,' GMT')  # formatting date and time
    output_str="%04d/%02d/%02d %02d:%02d:%02d" %(now.year,now.month,now.day,now.hour,now.minute,now.second) # formatting date and time
    for an_address in sdi_12_address:
        # for CS 320 pyranometer, M! returns calibrated solar radiation in W/m2, M1! is raw detector mV, M2! is sensor Temp in c, M3! is x,y,z axis degrees
        # and M4! is all of the above.  D0! returns the first 3 values, D1! the last 3
        
        #also, XHON! turns heater on and XHOFF! turns heater off.  Should be done depending on Temp and rH (need a probe or weather station data)
        #here we turn the heater on every measurement to test if it is working:
    #
     #   write(an_address.encode()+b'XHON!') # turn heater on
     #   ser.write(an_address.encode()+b'XHOFF!') # turn heater off
     #   print(an_address.encode()+b'XHON!') # print on screen for debugging
     #   sdi_12_line=ser.readline()
     #   print(sdi_12_line)
        
        #send the M! to start the measurement - repeat this until get the correct response - could get stuck in a loop - may only want to do 3 times?
  #      ser.write(an_address.encode()+b'M!'); # start the SDI-12 sensor measurement
        ser.open()
        ser.write(an_address.encode()+b'M4!'); # start the SDI-12 sensor measurement
  #      print(an_address.encode()+b'M!'); # start the SDI-12 sensor measurement
        sdi_12_line=ser.readline()
        #need to do something here if this is empty!  It's failing sometimes
        print(sdi_12_line)
        if sdi_12_line == b'': #the M! command failed
            ser.write(an_address.encode()+b'M4!'); # start the SDI-12 sensor measurement
            sdi_12_line=ser.readline() 

        sdi_12_line=sdi_12_line[:-2] # remove \r and \n since [0-9]$ has trouble with \r
        m=re.search(b'[0-9]$',sdi_12_line) # having trouble with the \r
        total_returned_values=int(m.group(0)) # find how many values are returned
        print('total values returned:',total_returned_values)
        sdi_12_line=ser.readline() # read the service request line
        ser.write(an_address.encode()+b'D0!') # request data
        print(an_address.encode()+b'D0!') # request data
        sdi_12_line=ser.readline() # read the data line
        sdi_12_line=sdi_12_line[1:-2] # remove address, \r and \n since [0-9]$ has trouble with \r
        print(sdi_12_line)
        ser.write(an_address.encode()+b'D1!') # request data
        print(an_address.encode()+b'D1!') # request data
        sdi_12_line1=ser.readline() # read the data line
        sdi_12_line1=sdi_12_line1[1:-2] # remove address, \r and \n since [0-9]$ has trouble with \r
        print(sdi_12_line1)
        ser.write(an_address.encode()+b'D2!') # request data
        print(an_address.encode()+b'D2!') # request data
        sdi_12_line2=ser.readline() # read the data line
        sdi_12_line2=sdi_12_line2[1:-2] # remove address, \r and \n since [0-9]$ has trouble with \r
        print(sdi_12_line2)
        ser.write(an_address.encode()+b'D3!') # request data
        print(an_address.encode()+b'D3!') # request data
        sdi_12_line3=ser.readline() # read the data line
        sdi_12_line3=sdi_12_line3[1:-2] # remove address, \r and \n since [0-9]$ has trouble with \r
        print(sdi_12_line3)
        
        ser.close()
        
        values=[] # clear before each sensor
        for iterator in range(total_returned_values): # extract the returned values from SDI-12 sensor and append to values[]
            if iterator <= 2: #(this should work in the case of the CS320 pyranometer - it is not general!!)
                m=re.search(b'[+-][0-9.]+',sdi_12_line) # match a number string
                try: # if values found is less than values indicated by return from M, report no data found.
                #This is a simple solution to GPS sensors before they acquire lock.
                #For sensors that have lots of values to return, you need to find a better solution.
                    values.append(float(m.group(0))) # convert into a number
                    print('values:',values)
                    sdi_12_line=sdi_12_line[len(m.group(0)):]
                except AttributeError:
                    print("No data received from sensor at address %c\n" %(an_address))
                    time.sleep(delay_between_pts)
                    no_data=True
                    break
            else:
                m=re.search(b'[+-][0-9.]+',sdi_12_line1) # match a number string
                try: # if values found is less than values indicated by return from M, report no data found.
                #This is a simple solution to GPS sensors before they acquire lock.
                #For sensors that have lots of values to return, you need to find a better solution.
                    values.append(float(m.group(0))) # convert into a number
                    print('values:',values)
                    sdi_12_line1=sdi_12_line1[len(m.group(0)):]
                except AttributeError:
                    print("No data received from sensor at address %c\n" %(an_address))
                    time.sleep(delay_between_pts)
                    no_data=True
                    break
                
            if (no_data==True):
                break;
        
        output_str=output_str+','+an_address

        for value_i in values:
            output_str=output_str+",%s" %(value_i) # Output returned values
            if (i<6):
                value_str=value_str+"&field%d=%s" %(i+1,value_i) # format values for posting. Field starts with field1, not field0.
                i=i+1
    if (no_data==True):
        no_data=False
        continue;
    while (i<6): # Pad with zeros in case we don't have 6 fields. This is only necessary for certain servers.
        value_str=value_str+"&field%d=0" %(i+1) # format values for posting. Field starts with field1, not field0.
        i=i+1
    #add outdoor Temperature and Humidity to end:
    output_str=output_str+",%s,%s" %(Tc,rh)
    value_str=value_str+"&field7=%s&field8=%s" %(Tc,rh)
  
    print(output_str)
    output_str=output_str+'\n'
    data_file = open(data_file_path, 'a+') # open yyyymmdd.csv for appending
    data_file.write(output_str)
    data_file.close()
    
    try:
        response = requests.get(get_weather_url)
        
        #convert json format to python format data:
        weather_data = response.json()
        #check if the city was found:
        if weather_data["cod"] != "404":
            #want temperature and humidity
            y = weather_data["main"]
            temp = y["temp"]
            rh = y["humidity"]
            
            #calculate the dewpoint from T and rH:
            Tc = temp - 273.15 #need T in celcius
            dp = 243.04*(numpy.log(rh/100)+((17.625*Tc)/(243.04+Tc)))/(17.625-numpy.log(rh/100)-((17.625*Tc)/(243.04+Tc)))
            print(" T(K) = " + str(temp) + "\n rH = " + str(rh) + "\n Dewpoint = " + str(dp))
            
            #the following if is only for testing purposes to force the heater on after a minute
            #if j > 4:
            #    Tc = 0
                
            
            #now follow Campbell Scientific's reccommended heater control algorithm:
            if dp > Tc:
                dp = Tc
            dewdiff = values[2] - dp #note that values[2] is the returned value of the cs320 temperature
            if Htrcntrl == False:
                if Tc <= 2:
                    Htrcntrl = True
                else:
                    if dewdiff <= 2:
                        Htrcntrl = True
            elif (Tc >3) & (dewdiff >=3):
                Htrcntrl = False
            if Htrcntrl == True:
                ser.open()
                ser.write(an_address.encode()+b'XHON!') # turn heater on
                print(an_address.encode()+b'XHON!') # print on screen for debugging
                sdi_12_line=ser.readline() #need to read this line to not have problems later
                print(sdi_12_line) #print on screen for debugging
                ser.close()
                
            if Htrcntrl == False:
                ser.open()
                ser.write(an_address.encode()+b'XHOFF!') # turn heater off
                print(an_address.encode()+b'XHOFF!') # print on screen for debugging
                sdi_12_line=ser.readline()
                print(sdi_12_line)
                ser.close()
                
        else:
            print("city not found")
            
    except:   
        print("problem getting weather data")        
   
        
    values=[] # clear values for the next iteration, 3.2.3 doesn't support clear as 3.4.3 and 3.5.1 does
    
    data_file.close() # make sure data is written to the disk so stopping the scrit with ctrl - C will not cause data loss
    ser.close()

#now reboot the Pi so that it fixes any errors with cell modem etc and keeps running!






