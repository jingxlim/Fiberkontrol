import u3, u6, ue9
import time
from datetime import datetime
import struct
import traceback


# MAX_REQUESTS is the number of packets to be read.
MAX_REQUESTS = 75

################################################################################
## U6
## Uncomment these lines to stream from a U6
################################################################################
## At high frequencies ( >5 kHz), the number of samples will be MAX_REQUESTS times 48 (packets per request) times 25 (samples per packet).
d = u6.U6()
#
## For applying the proper calibration to readings.
d.getCalibrationData()
#
print "configuring U6 stream"
#
d.streamConfig( NumChannels = 4, ChannelNumbers = [ 0, 1, 2, 3 ], ChannelOptions = [ 0, 0, 0, 0 ], SettlingFactor = 1, ResolutionIndex = 1, ScanInterval = 6000, SamplesPerPacket = 25)




start = datetime.now()
print "start stream", start
d.streamStart()

missed = 0
dataCount = 0
byteCount = 0
start = datetime.now()

start_time = time.time()
prev_time = start_time
prev_count = 0

for i in range(100):    
    print 'i', i
    new_time = time.time()
    print 'rate', (dataCount-prev_count)/(new_time - prev_time)
    prev_count = dataCount
    prev_time = new_time
    rgen = d.streamData()
    print 'rgen', rgen
    r = rgen.next()
    if r is not None:
        for v in r['AIN1']:
            print v 
            
            dataCount += 1
        else:
            # Got no data back from our read.
            # This only happens if your stream isn't faster than the 
            # the USB read timeout, ~1 sec.
            print "No data", datetime.now()



