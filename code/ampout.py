import serial
import re
import time
import numpy as np
import pylab as pl
import atexit

class GetFluor:

    def __init__(self):
        self.rate = 115200
        self.inpin = 0
        self.savepath = '../../../../../Data/20101119_fiberkontrol/'
        self.outname = 'gc_baseline_to_iso'
        self.dev = '/dev/tty.usbserial-A600eu7L'
        self.T = 5000
        self.dt = 100
        self.ser = serial.Serial(self.dev, self.rate)

    def receiving(self,dt=None):
        buffer = ''
        i=0
        out = []
        fill = 0
        if dt is not None:
            self.dt = dt

        while i < self.dt:
            try:
                buffer = buffer + self.ser.read(self.ser.inWaiting())
                i += 1
            except:
                print 1

        if '\n' in buffer:
            lines = buffer.split('\n') 
            for j in range(len(lines)):
                o = re.findall(r"\d+",lines[j])
                if o:
                    out.append(int(o[0]))
                else:
                    out.append(fill)

        self.out = out
        return out

    def plot_out(self):
        pl.plot(self.out)

    def save(self,path=None):
        if path is not None:
            self.savepath = path
        np.savez(self.savepath+self.outname,self.output)

    def load(self,path=None):
        if path is not None:
            self.savepath = path
        self.loaded = np.load(self.savepath+'/out.npz')['arr_0']

    def teardown():
        del globals()['d1']


    def _get_slice( self ):
        pass

    def plot_rt( self ):
        pl.ion() #interactive mode on
        timefig = pl.figure(1)
        timesub = pl.subplot(111)
        dt = 1
        h= np.array(self.receiving())
        t = pl.arange(len(h))
        lines = pl.plot(t,h)
        for i in range(self.T):
            try:
                hnew = np.array(self.receiving())
            except:
                hnew = [0]
                print 1
            h = np.append(h, hnew)
            t=np.append(t, (range(len(hnew)) + t.max() + 1))
            lines[0].set_data(t[:-1],h[:-1])
            timesub.set_xlim((t[0],t[-1]))
            timesub.set_ylim((100,300))
            pl.draw()
            atexit.register(self.teardown)
        self.output = h

def main():
    GF = GetFluor()
    GF.plot_rt()
    GF.save()

if __name__=='__main__':
    main()
