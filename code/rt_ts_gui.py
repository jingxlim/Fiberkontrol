# Major imports
import numpy as np
import serial
import re
import time
import random
import wx

# Enthought imports
from enthought.traits.api \
    import Array, Dict, Enum, HasTraits, Str, Int, Range, Button, String, \
    Bool, Callable, Float, Instance, Trait
from enthought.traits.ui.api import Item, View, Group, HGroup, spring, Handler
from enthought.pyface.timer.api import Timer


# Chaco imports
from enthought.chaco.api import ArrayPlotData, Plot
from enthought.enable.component_editor import ComponentEditor
from enthought.chaco.chaco_plot_editor import ChacoPlotEditor, \
                                                ChacoPlotItem

from threading import Thread

#------------------------------------------------------------------------------------------

class FiberModel( HasTraits ):

    # Public Traits
    plot_type     = Enum( "record", "demo" )
    analog_in_pin = Int( 0 )
    T             = Int( 0 ) 
    dt            = Int( 20 ) # in ms; what does this do to accuracy

    # Private Traits
    _ydata  = Array()
    _xdata  = Array()

    def __init__(self, **kwtraits):
        super( FiberModel, self ).__init__( **kwtraits )
 
        if self.plot_type is "record":
            self.buffer    = ''
            self.rate      = 115200
            self.recording = True
            try:
                self.ser = serial.Serial( '/dev/tty.usbmodem641', self.rate )
                print "serial initialized"
            except:
                self.ser = serial.Serial( '/dev/tty.usbserial-A600emRx', self.rate )                
                print "serial initialized"

#    def run( self ):
#        for i in range(50):
#            if self.recording is True:
#                self._get_current_data()

    def save( self, path = None, name = None ):
        if path is not None:
            self.savepath = path
        if name is not None:
            self.outname = name
        np.savez( self.savepath + self.outname, self.output )

    def load( self, path = None, name = None ):
        if path is not None:
            self.savepath = path
        self.loaded = np.load( self.savepath + '/out.npz' )['arr_0']

    def _get_current_data( self ):

        if self.recording is True:
            hnew = np.array( self.receiving() )

            #except:
            #    hnew = 0. #self._ydata[-1] 
            #    print "missed a serial read listening"

            self._ydata = np.append( self._ydata, hnew )
            self._xdata = range( len( self._ydata ) )

    def receiving( self, dt = None ):

        buffer = self.buffer
        out    = []

        if dt is not None:
            self.dt = dt

#        try:
        time.sleep( self.dt /1000 )
        buffer   = buffer + self.ser.read( self.ser.inWaiting() )

        if '\n' in buffer:
            lines = buffer.split( '\n' ) 
            
            if lines[-2]: 
                full_lines = lines[:-1] 
                 
                for i in range( len( full_lines ) ):
                    o = re.findall( r"\d+", lines[i] )
                    if o:
                        out.append( int( o[0] ) )

            self.buffer = lines[1]
            out = np.median( out[~(out == 0)] )
#        except:
#            print "missed a serial read receiving"

        return out

    def plot_out( self ):
        pl.plot( self.out )


class FiberView( FiberModel ):

    plot_data     = Instance( ArrayPlotData )
    plot          = Instance( Plot )
    record        = Button()
    stop          = Button()
    load_data     = Button()
    save_data     = Button()
    save_plot     = Button()

    # Default TraitsUI view
    traits_view = View(
        Item('plot', editor=ComponentEditor(), show_label=False),
        # Items
        HGroup( spring,
                Item( "record",    show_label = False ), spring,
                Item( "stop",      show_label = False ), spring,
                Item( "load_data", show_label = False ), spring,
                Item( "save_data", show_label = False ), spring,
                Item( "save_plot", show_label = False ), spring,
                Item( "plot_type" ),                     spring,
                Item( "analog_in_pin" ),                 spring,
                Item( "dt" ),                            spring ),

        Item( "T" ),
        # GUI window
        resizable = True,
        width     = 1000, 
        height    = 700 ,
        kind      = 'live' )

    def __init__(self, **kwtraits):
        super( FiberView, self ).__init__( **kwtraits )

        self.plot_data = ArrayPlotData( x = self._xdata, y = self._ydata )

        self.plot = Plot( self.plot_data )
        renderer  = self.plot.plot(("x", "y"), type="line", color="green")[0]

    def run( self ):
        for i in range( 100 ):
            self._plot_update()
            self._get_current_data()


    def _plot_update( self ):

        self.plot_data.set_data( "y", self._ydata ) 
        self.plot_data.set_data( "x", self._xdata )
        self.plot = Plot( self.plot_data )
        self.plot.plot(("x", "y"), type="line", color="green")[0]
        print 1
        self.plot.request_redraw()

    # Note: These should be moved to a proper handler
    def _record_fired( self ):
        self.recording = True
        self.run()

    def _stop_fired( self ):
        self.recording = False

    def _load_data_fired( self ):
        pass

    def _save_data_fired( self ):
        S = Save( save = Save(), display = TextDisplay() )
        S.configure_traits()
        
        self.save( path = S.savepath, name = S.outname )

    def _save_plot_fired( self ):
        pass


#------------------------------------------------------------------------------------------

class Save( HasTraits ):
    """ Save object """

    savepath  = Str( '../../../../../Data/20101119_fiberkontrol/',
                     desc="Location to save data file",
                     label="Save location:", )

    outname   = Str( '',
                     desc="Filename",
                     label="Save file as:", )

#------------------------------------------------------------------------------------------

class TextDisplay(HasTraits):
    string = String()

    view= View( Item('string', show_label = False, springy = True, style = 'custom' ) )

#------------------------------------------------------------------------------------------

class SaveDialog(HasTraits):
#    save = Instance( Save )
#    display = Instance( TextDisplay )

    view = View(
                Item('save', style='custom', show_label=False, ),
                Item('display', style='custom', show_label=False, ),
            )

#------------------------------------------------------------------------------------------


if __name__ == "__main__":
    F = FiberView()
    F.recording = True
#    F.run()
#    1/0
#    F._get_current_data()
    F.configure_traits()
