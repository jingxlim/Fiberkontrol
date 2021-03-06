import os,sys
import h5py
import numpy as np
import scipy as sp
import pylab as pl
import scipy.signal as signal

import scipy.stats as ss
#from debleach import exponential_basis_debleach
from scipy.stats import ranksums
from scipy.interpolate import UnivariateSpline
import tkFileDialog

#from wavelet import *
#-----------------------------------------------------------------------------------------

class FiberAnalyze( object ):

    def __init__(self, options):
        """
        Initialize the FiberAnalyze class using options object from OptionsParser.
        """
        # attributes to set for hdf5 loading. Can use these to specify individual trials when using the FiberAnalyze class
        # in another program
        self.subject_id = None
        self.exp_date = None
        self.exp_type = None

        self.load_flat = True

        # values from option parser
        self.smoothness = int(options.smoothness)
        #self.plot_type = options.plot_type
        self.time_range = options.time_range
        self.fluor_normalization = options.fluor_normalization
        self.filter_freqs = options.filter_freqs
        self.exp_type = options.exp_type
        self.event_spacing = float(options.event_spacing)
        self.mouse_type = options.mouse_type

        self.input_path = options.input_path
        self.output_path = options.output_path
        self.trigger_path = options.trigger_path

        self.save_txt = options.save_txt
        self.save_to_h5 = options.save_to_h5
        self.save_and_exit = options.save_and_exit
        self.save_debleach = options.save_debleach
        
        if self.trigger_path is not None:
            self.s_file = options.trigger_path + '_s.npz'
            self.e_file = options.trigger_path + '_e.npz'
        else:
            self.trigger_path= None
            
        # hard coded values
        self.fluor_channel = 0
        self.trigger_channel = 3


        self.fft = None #place holder for fft of rawsignal, if calculated
        self.fft_freq = None #place holder for frequency labels of fft
        self.filt_fluor_data = None #place holder for filtered rawsignal, if calculated
        self.event_start_times = None #place holder event_times that may be calculated by get_sucrose_event_times
        self.event_end_times = None

        
    def load( self, file_type="npz" ):
        """
        Load time series and events from NPZ or HDF5 file. 
        """
        print "Loading"
        self.time_tuples = None
        if file_type == "npz":
            print ""
            print "--> Loading: ", self.input_path
            self.data = np.load( self.input_path )['data']
            self.time_stamps = np.load( self.input_path )['time_stamps']
            self.fluor_data = self.data[:,self.fluor_channel]
            self.load_trigger_data()
            
        elif file_type == "hdf5":
            print "hdf5 file to load: ", self.subject_id, self.exp_date, self.exp_type
            try:
                h5_file = h5py.File( self.input_path, 'r' )
                self.data = np.asarray( h5_file[self.subject_id][self.exp_date][self.exp_type]['time_series_arr'] )
                if self.exp_type != 'sucrose':
                    self.time_tuples = np.asarray( h5_file[self.subject_id][self.exp_date][self.exp_type]['event_tuples'] )
                else:
                    self.time_tuples = None

                self.time_stamps = self.data[:,0]
                self.trigger_data = self.data[:,1] 

                if self.exp_type != 'sucrose':
                    ## ADD AVERAGE LISA REACTION TIME
                    ## IN SELECTING START TIME OF 
                    ## BEHAVIORAL SCORING? (~400 ms)
                    ## THIS NEEDS TO BE A COMMAND LINE FLAG!!
                    ## conclusion: doesn't affect results
                    rxn_time = 0.0 # in seconds, hardcoded based on lisa's reaction time
                    shift_index = self.convert_seconds_to_index(rxn_time)
                    print "shift_index", shift_index
                    if shift_index != 0:
                        self.trigger_data = np.hstack((np.zeros(shift_index), 
                                                        self.trigger_data[:-shift_index]))
                        self.time_tuples = (np.array(self.time_tuples) + rxn_time).tolist()
                    print "REACTION TIME: ", rxn_time


                if (self.load_flat):
                    try:
                        self.fluor_data = np.asarray( h5_file[self.subject_id][self.exp_date][self.exp_type]['flat'] )[:, 0]
                        print "--> Loading flattened data"
                    except:
                        print "--> Flattened data UNAVAILABLE"
                        self.fluor_data = self.data[:,2] 
                else:
                    self.fluor_data = self.data[:,2] #to use unflattened, original data
                    print "--> Loading UNFLATTENED data"

            except Exception, e:
                print "Unable to open HDF5 file", self.subject_id, self.exp_date, self.exp_type, "due to error:"
                print e
                return -1

        self.crop_data() #crop data to range specified at commmand line
        self.normalize_fluorescence_data()

        if self.smoothness != 0:
            print "--> Smoothing data with parameter: ", self.smoothness
            self.fluor_data = self.smooth(self.fluor_data, int(self.smoothness), window_type='gaussian')
        else:
            print "--> No smoothing parameter specified."

            
        if self.filter_freqs is not None:
            freqlist = self.filter_freqs.split(':')
            print freqlist
            self.fluor_data = self.notch_filter(freqlist[0], freqlist[1])
        
        if self.save_txt:
            self.save_time_series(self.output_path)
        if self.save_to_h5 is not None:
            self.save_time_series(self.output_path, 
                                  output_type="h5", 
                                  h5_filename=self.save_to_h5)
        if self.save_debleach:
            self.debleach(self.output_path)

        print "np.min(self.fluor_data)", np.min(self.fluor_data)
        print "np.max(self.fluor_data)", np.max(self.fluor_data)

        return self.fluor_data, self.trigger_data


    def crop_data(self):
        """
        ---Crop data to specified time range--- 
        Range is provided as a command line argument 
        in the format:      <start-time>:<end-time>
        Default is no cropping, specified by 0:-1
        """
        if self.time_range != None:
            tlist = self.time_range.split(':')
            print "--> Crop data to range: ", tlist
            if len(tlist) != 2:
                print 'Error parsing --time-range argument.  Be sure to use <start-time>:<end-time> syntax.'
                sys.exit(1)
            
            self.t_start = 0 if tlist[0] == '-1' else int(self.convert_seconds_to_index(int(tlist[0])))
            self.t_end = len(self.fluor_data) if tlist[1] == '-1' else int(self.convert_seconds_to_index(int(tlist[1])))
            
            if self.t_start < self.t_end:
                self.fluor_data = self.fluor_data[self.t_start:self.t_end]
                self.trigger_data = self.trigger_data[self.t_start:self.t_end]
                self.time_stamps = self.time_stamps[self.t_start:self.t_end]
            else:
                print "--> Data not cropped. (End - start) time must be positive."
        else:
            print "--> Data not cropped. No range has been specified."


    def load_trigger_data(self):
        """
        ---Load trigger data---
        These are the times corresponding to behavioral events 
        such as licks, or social interactions.
        For lickometer data, the trigger data is recorded during data
        acquisition and is included in the previously loaded data file
        For social  behavior, event times must be loaded
        from a separate file location: trigger_path
        """

        if self.trigger_path is None: 
            self.trigger_data = self.data[:,self.trigger_channel]
        else:
            try:
                self.time_tuples = self.load_event_data(self.s_file, self.e_file)
                time_vec = np.asarray(self.time_tuples).flatten()
                time_vec = np.append(time_vec,np.inf)
                self.trigger_data = np.zeros(len(self.fluor_data))
                j = 0
                for i in xrange(len(self.trigger_data)):
                    if self.time_stamps[i] < time_vec[j]:
                        self.trigger_data[i] = np.mod(j,2)
                    else:
                        j+=1
                        self.trigger_data[i] = np.mod(j,2)
            except Exception, e:
                print "Error loading trigger data:"
                print "\t-->",e

        self.trigger_data *= 3/np.max(self.trigger_data)
        self.trigger_data -= np.min(self.trigger_data)
        if self.exp_type == 'sucrose': #event times are recorded differently by behavior handscoring vs. by lickometer
            self.trigger_data = np.max(self.trigger_data) - self.trigger_data
       # self.trigger_data *= -1
       # self.trigger_data += 1

        if self.fluor_normalization == "deltaF":
            self.trigger_data *= 1.5*np.max(self.fluor_data)

        print "--> Trigger data loaded"

    def normalize_fluorescence_data(self):
        """
        Normalize data to either: 
        'deltaF', the standard metric used in 
        publications which shows deviation from 
        the median value of the entire time series,

        'standardize', which shifts and scales
        the time series to be between 0 and 1, 
        
        'raw', which does not alter the time 
        series at all.
        """
            
        if self.fluor_normalization == "deltaF":
            median = np.median(self.fluor_data)
            print "--> Normalization: deltaF. Median of raw fluorescent data: ", median
            self.fluor_data = (self.fluor_data-median)/median #dF/F
            
        elif self.fluor_normalization == "standardize":
            self.fluor_data -= np.min(self.fluor_data)
            self.fluor_data /= np.max(self.fluor_data)
            self.fluor_data +=0.0000001 # keep strictly positive
            print "--> Normalization: standardized to between 0 and 1. Max of raw fluorescent data: ", np.max(self.fluor_data), "min: ", np.min(self.fluor_data)
        
        elif self.fluor_normalization == "raw":
            print "--> Normalization: raw (no normalization). Max of raw fluorescent data: ", np.max(self.fluor_data)
        
        else:
            raise ValueError( self.fluor_normalization, "is not a valid entry for --fluor-normalization.")


    def load_event_data( self, s_filename, e_filename ):
        """
        Load start and end times for coded events. 
        """
        self.s_vals = np.load(s_filename)['arr_0']
        self.e_vals = np.load(e_filename)['arr_0']
        print 's_vals', self.s_vals
        return zip(self.s_vals,self.e_vals)

    def set_resolution(self, start, end):
        """
        Decrease the number of points plotted in
        a time series to decrease the filesize 
        of the plot.
        Start and end are provided in seconds.
        """ 

        #Set a larger resolution to ensure the plotted file size is not too large
        if end - start <= 100 and end - start > 0:
            resolution = 1
        elif end - start < 500 and end - start > 100:
            resolution = 10
            #resolution = 30
        elif end - start >= 500 and end - start < 1000:
            resolution = 30
           #resolution=100
        else:
            resolution = 40
           #resolution=100

        print "--> Resolution: ", resolution
        return resolution

    def get_plot_ylim(self, exp_type, fluor_normalization, ymax_setting='small', max_val=0.0):
        """
        Can set ymax_setting to 'small' or 'large'
        """
        ymin = -1
        ymax = 3.0

        print "max_val", max_val

        if exp_type == 'sucrose':
            if ymax_setting == 'small':
                ymax = 1.0
            if ymax_setting == 'large' or (ymax_setting == 'small' and max_val > ymax):
                ymax = 3.0
            ymin = -1
        elif exp_type == 'homecagesocial':
            if ymax_setting == 'small':
                ymax = 0.35
            if ymax_setting == 'large' or (ymax_setting == 'small' and max_val > ymax):
                ymax = 1.2
            ymin = -ymax/3.0
        elif exp_type == 'homecagenovel':
            if ymax_setting == 'small':
                ymax = 0.35
            if ymax_setting == 'large' or (ymax_setting == 'small' and max_val > ymax):
                ymax = 1.2
            ymin = -ymax/3.0
        elif exp_type == 'EPM':
            if ymax_setting == 'small':
                ymax = 0.35
            if ymax_setting == 'large' or (ymax_setting == 'small' and max_val > ymax):
                ymax = 1.2
            ymin = -ymax/3.0

        if fluor_normalization == 'raw':
            ymax = 10.0
            ymin = -1.0

        return [ymax, ymin]

    def plot_basic_tseries( self, 
                            out_path=None, 
                            window=None, 
                            resolution=None, 
                            plot_all_trigger_data=False ):
        """
        Generate a plot showing the raw calcium time series, 
        with triggers corresponding to events (e.g. licking 
        for sucrose) superimposed. Here the window indicates 
        which segment of the entire time series to plot.

        Make the resolution parameter smaller when plotting 
        zoomed in views of the time series.

        Setting plot_all_trigger_data=True plots the whole 
        trigger timeseries, as opposed to just when the 
        trigger is high. This leads to large plot file
        sizes, however
        """
        # clear figure
        pl.clf()

        start = int(self.time_range.split(':')[0])
        end = int(self.time_range.split(':')[1])
        end = end if end != -1 else max(self.time_stamps)
        start = start if start != -1 else min(self.time_stamps)

        if resolution is None:
            resolution = self.set_resolution(start, end)

        time_vals = self.time_stamps[range(len(self.fluor_data))]
        fluor_data = self.fluor_data
        trigger_data = self.trigger_data

        #Crop to window
        if window is not None:
            window_indices = [self.convert_seconds_to_index( window[0]),
                              self.convert_seconds_to_index( window[1])]
            time_vals = time_vals[window_indices[0]:window_indices[1]] 
            fluor_data = fluor_data[window_indices[0]:window_indices[1]]
            trigger_data = trigger_data[window_indices[0]:window_indices[1]]

        [ymax, ymin] = self.get_plot_ylim(self.exp_type, self.fluor_normalization, max_val=np.max(fluor_data))


        trigger_low = min(trigger_data) + 0.2
        if self.exp_type != 'sucrose':
            trigger_high_locations = [time_vals[i] for i in range(len(trigger_data)) 
                                        if trigger_data[i] > trigger_low]
        elif self.exp_type == 'sucrose':
            print "trigger_data", trigger_data
            trigger_high_locations = [time_vals[i] for i in range(len(trigger_data)) 
                                        if trigger_data[i] > trigger_low]
        
        ## Be careful whether event is recorded 
        ## by trigger high or trigger low (i.e. > or < trigger_low).
        ## Sucrose is recorded differently. 

        if plot_all_trigger_data:
            pl.fill( time_vals[::2], 10*trigger_data[::2] - 2, 
                     color='r', alpha=0.3 )
        else:
            pl.plot(trigger_high_locations, -0.1*np.ones(len(trigger_high_locations)), 
                     'r.', markersize=0.1 )

        pl.plot( time_vals[::resolution], fluor_data[::resolution], 'k-') 

        pl.ylim([ymin,ymax])
        if window is not None:
            pl.xlim([window[0], window[1]])
        else:
            pl.xlim([min(self.time_stamps), max(self.time_stamps)])
        if self.fluor_normalization == "deltaF":
            pl.ylabel('deltaF/F')
        else:
            pl.ylabel('Fluorescence Intensity (a.u.)')
        pl.xlabel('Time since recording onset (seconds)')
        if out_path is None:
            pl.show()
            out_path = '.'
        else:
            pl.savefig(out_path + "basic_time_series.pdf")
            pl.savefig(out_path + "basic_time_series.png")

        return (fluor_data, trigger_high_locations)

    def save_time_series( self, save_path='.', output_type="txt", h5_filename=None ):
        """
        Save the raw calcium time series, with triggers 
        corresponding to events (e.g. licking times for 
        sucrose, approach/interaction times for novel object
        and social) in the same time frame of reference, 
        outputting either:
          -- a txt file, if ouput_type is txt
          -- write to an hdf5 file specified by self.save_to_h5 if output_type is h5
        """
        # get appropriate time values 
        time_vals = self.time_stamps[range(len(self.fluor_data))]

        # make output array
        out_arr = np.zeros((len(time_vals),3))
        out_arr[:,0] = time_vals
        out_arr[:,1] = self.trigger_data
        out_arr[:,2] = self.fluor_data

        # get data prefix
        prefix=self.input_path.split("/")[-1].split(".")[0]
        outfile_name = prefix+"_tseries.txt"
        out_path = os.path.join(save_path,outfile_name)

        if output_type == "txt":
            print "Saving to file:", out_path
            np.savetxt(os.path.join(out_path), out_arr)
            if self.save_and_exit:
                sys.exit(0)
            
        elif output_type == "h5":
            print "\t--> Writing to HDF5 file", self.save_to_h5
            # check if specified h5 file already exists
            h5_exists = os.path.isfile(self.save_to_h5)
            try:
                if h5_exists:
                    # write to existing h5 file
                    h5_file = h5py.File(self.save_to_h5)
                    print "\t--> Writing to exising  HDF5 file:", self.save_to_h5
                else:
                    # create new h5 file
                    h5_file = h5py.File(self.save_to_h5,'w')
                    print "\t--> Created new HDF5 file:", self.save_to_h5
            except Exception, e:
                print "Unable to open HDF5 file", self.save_to_h5, "due to error:"
                print e

            # save output array to folder in h5 file creating a data set named after the subject number
            # with columns corresponding to time, triggers, and fluorescence data, respectively.

            # group by animal number, subgroup by date, subsubgroup by run type
            if prefix.split("-")[3] not in list(h5_file):
                print "\t---> Creating group:", prefix.split("-")[3]
                subject_num= h5_file.create_group(prefix.split("-")[3])
            else:
                print "\t---> Loading group:", prefix.split("-")[3]
                subject_num = h5_file[prefix.split("-")[3]]

            subject_num.attrs['mouse_type'] = self.mouse_type
                
            if prefix.split("-")[0] not in list(subject_num):
                print "\t---> Creating subgroup:", prefix.split("-")[0]
                date = subject_num.create_group(prefix.split("-")[0])
            else:
                print "\t---> Loading subgroup:", prefix.split("-")[0]
                date = subject_num[prefix.split("-")[0]]

            if prefix.split("-")[2] not in list(date):
                print "\t---> Creating subsubgroup:", prefix.split("-")[2]
                run_type = date.create_group(prefix.split("-")[2])
            else:
                print "\t---> Loading subsubgroup:", prefix.split("-")[2]
                run_type = date[prefix.split("-")[2]]

            try:
                dset = run_type.create_dataset("time_series_arr", data=out_arr)
                if np.shape(self.time_tuples) != ():
                    print "self.time_tuples", np.shape(self.time_tuples)
                    dset = run_type.create_dataset("event_tuples", data=self.time_tuples)
                else:
                    print "NO TIME TUPLES"

                dset.attrs["time_series_arr_names"] = ("time_stamp", "trigger_data", "fluor_data")
                dset.attrs["original_file_name"] = prefix
            except Exception, e:
                print "Unable to write data array due to error:", e

            h5_file.close() # close the file
            
            if self.save_and_exit:
                sys.exit(0)
        else:
            raise NotImplemented("The entered output_type has not been implemented.")               

    def plot_next_event_vs_intensity( self, 
                                      intensity_measure="peak", 
                                      next_event_measure="onset", 
                                      window=[1, 3], 
                                      out_path=None, 
                                      plotit=True,
                                      baseline_window=-1):
        """
        Generate a plot of next event onset delay 'onset' (time until next event) or 
        length of next event 'length' as a function of an intensity 
        measure that can be one of
          -- peak intensity of last event (peak)
          -- average intensity of last event (average)
          -- time of the event (event_time)
          -- which number event it is in the trial (event_index)
#          -- integrated intensity over history window (window)
#                (I'm not sure what this one means)

        Set window = [0,0] to use the entire event length as the
            window length (although this length will be different
            for each interaction event).

        Returns: (intensity, next_vals), where:
            intensity = a vector of length (num_events - 1) 
                        whose entries are the metric for each event
            next_vals = the time until the next event

          #TODO TODO: Add a metric that is simply the time of the event

        """
        start_times = self.get_event_times(edge="rising", exp_type=self.exp_type)
        end_times = self.get_event_times(edge="falling", exp_type=self.exp_type)
        if start_times == -1:
            raise ValueError("Event times seem to have failed to load.")

        end_event_times = None
        if window[0] == 0 and window[1] == 0: #if window == [0,0]:
            end_event_times = end_times

        print "window", window

        print "end_event_times", end_event_times
        print "baseline_window", baseline_window
        ts_arr = self.get_time_chunks_around_events(data=self.fluor_data, 
                                              event_times = start_times, 
                                              window=window, 
                                              baseline_window=baseline_window, 
                                              end_event_times=end_event_times)
        intensity = self.score_of_chunks(ts_arr, 
                                        metric=intensity_measure,
                                        start_event_times=start_times, 
                                        end_event_times=end_times)

        # get next event values
        if next_event_measure == "onset":
            next_vals = np.zeros(len(start_times)-1)
            for i in xrange(len(next_vals)):
                next_vals[i] = start_times[i+1] - end_times[i]
        elif next_event_measure == "length":
            next_vals = np.zeros(len(start_times)-1)
            for i in xrange(len(next_vals)):
                next_vals[i] = end_times[i+1] - start_times[i+1]
        else:
            raise ValueError("Entered next_event_measure not implemented.")

        # lag intensities relative to events (except in history window case)
        if intensity_measure == "window":
            intensity = intensity[1::]
        else:
            intensity = intensity[0:-1]

        if plotit:
            #Plot the area vs the time of each event
            pl.clf()
            pl.loglog(intensity, next_vals, 'ro')
            pl.ylabel('Next event value')
            pl.xlabel('Intensity')

            if out_path is None:
                pl.show()
            else:
                pl.savefig(os.path.join(out_path,"next_event_vs_intensity.pdf"))
        else:
            return intensity, next_vals

    def event_vs_baseline_barplot( self, out_path=None ):
        """
        Make a simple barplot of intensity during coded events vs during non-event times.
        """
        pl.clf()
        event = self.trigger_data*self.fluor_data
        baseline = self.fluor_data[ 0:(self.time_tuples[0][0]-self.t_start) ]
        pl.boxplot([event,baseline])
        if out_path is None:
            pl.show()
        else:
           # pl.savefig(os.path.join(out_path,"event_vs_baseline_barplot"))
            pl.savefig(out_path + "event_vs_baseline_barplot.pdf")

    def smooth(self, fluor_data, num_time_points, window_type='gaussian'):
        """
        Convolve a simple averaging window of length num_time_points
        and type window_type ('gaussian, 'rect')
        """

        print "smoothing."
        if window_type == 'gaussian':
            window = signal.gaussian(100, num_time_points)
        elif window_type == 'rect':
            window = np.ones(num_time_points)
        else:
            window = np.ones(num_times_points)

        smoothed_fluor_data = np.convolve(fluor_data, window, mode='same') #returns an array of the original length
        print "done smoothing."
        return smoothed_fluor_data/np.sum(window)

    def notch_filter(self, low, high):
        """
        Notch filter that cuts out frequencies (Hz) between [low:high].
        """
        if self.filt_fluor_data is None:
            rawsignal = self.fluor_data
        else:
            rawsignal = self.filt_fluor_data

        if self.fft is None:
            self.get_fft()
        bp = self.fft

        print "fft calculated."

        bpfilt = np.where(self.fft_freq <=high and self.fft_freq >= low, bp, 0)
        self.fft=bpfilt

        ibp = sp.ifft(bp)
        notch_filt_y = np.real(ibp)
        notch_filt_y += np.median(self.fluor_data) - np.median(notch_filt_y)
        self.filt_fluor_data = notch_filt_y
        return notch_filt_y

    def get_fft(self):
        print "getting fft."
        if self.filt_fluor_data is None:
            rawsignal = self.fluor_data
        else:
            rawsignal = self.filt_fluor_data
        
        print "calculating fft."
        fft = sp.fft(rawsignal)
        self.fft = fft[:]

        n = rawsignal.size
        print "rawsignal.size", n
        timestep = np.max(self.time_stamps[1:] - self.time_stamps[:-1])
        self.fft_freq = np.fft.fftfreq(n, d=timestep)

    def get_time_chunks_around_events(self, 
                                      data, 
                                      event_times, 
                                      window, 
                                      baseline_window=-1, 
                                      end_event_times=None):
        """
        Extracts chunks of fluorescence data around each event in 
        event_times, with before and after event durations
        specified in window as [before, after] (in seconds).
        Subtracts the baseline value from each chunk (i.e. 
        sets the minimum value in a chunk to 0).
        Set baseline_window = -1 for no baseline normalization.
        Set baseline_window ='full' to subtract the minimum of
            a smoothed version of the chunk (if the chunk includes
            no baseline values, then this will produce the wrong
            result)

        To use the entire epoch as the window, provide end_event_times.

        That is, if end_event_times != None, then
        this function will ignore the provided 'window', instead
        using the entire epoch.
        """
        window_indices = [self.convert_seconds_to_index( window[0]),
                          self.convert_seconds_to_index( window[1])]

        baseline_window_provided = (baseline_window is not None  and baseline_window != 'full' and 
                                    ((not isinstance(baseline_window, int) and len(baseline_window) == 2) 
                                      or (isinstance(baseline_window, int) and baseline_window != -1)))

        if baseline_window_provided:
            baseline_indices = [self.convert_seconds_to_index( baseline_window[0]),
                                self.convert_seconds_to_index( baseline_window[1])]

        time_chunks = []
        for i in range(len(event_times)):
            e = event_times[i]
            if end_event_times is not None:
                full_window = [0, end_event_times[i] - event_times[i]]
                window_indices = [self.convert_seconds_to_index( full_window[0]),
                          self.convert_seconds_to_index( full_window[1])]
                #print "len(epoch) = ", full_window[1]

           # try:
            e_idx = np.where(e<self.time_stamps)[0][0]
            if (e_idx + window_indices[1] < len(data)-1) and (e_idx - window_indices[0] > 0):
                chunk = data[range(max(0, (e_idx-window_indices[0])),
                                   min(len(data)-1, (e_idx+window_indices[1])))]
                #print "indices", e_idx-window_indices[0], e_idx+window_indices[1]
                if baseline_window_provided:
                    baseline_chunk = data[range(max(0, (e_idx-baseline_indices[0])), min(len(data)-1, (e_idx+baseline_indices[1])))]
                    baseline = np.min(baseline_chunk)
                elif baseline_window=='full':
                    n = 10
                    print "chunk"
                    smooth_chunk = np.convolve(chunk, np.ones(n)*1.0/n, mode='same')
                    #baseline = np.min(chunk)
                    baseline = np.min(smooth_chunk[n+1:-n-1])
                    print "baseline", baseline
                elif isinstance(baseline_window, int) and baseline_window == -1:
                    baseline = 0
                else:
                    baseline = 0

                time_chunks.append(chunk - baseline)
            #except:
             #   print "Unable to extract window:", [(e-window_indices[0]),(e+window_indices[1])]
        return time_chunks

    def score_of_chunks(self, ts_arr, metric='average', start_event_times=None, end_event_times=None):
        """
        Given an array of time series chunks, return an array
        holding a score for each of these chunks

        metric can be
        'average' (average value of curve),
        'peak' (peak fluorescence value), 
        'spacing', (time from end of current epoch to beginning of the next)
        'epoch_length' (time from beginning of epoch to end of epoch)
        'event_time' (starting time of event (in seconds))
        'event_index' (bout number of the event within the trial, starting at 1)

        TODO: Add a metric that is simply the time of the event
        """

        scores = []
        i=0
        print "metric", metric
        for ts in ts_arr:
            if metric == 'mean' or metric == 'average': # or metric == 'area' or metric == 'integrated': #the latter two are deprecated
                scores.append(np.sum(ts)/len(ts))
            elif metric == 'peak':
                scores.append(np.max(ts))
            elif metric == 'spacing':
                if start_event_times is None or end_event_times is None:
                    raise ValueError( "start_event_times and end_event_times were not passed to score_of_chunks() in fiber_record_analyze.")
                else:
                    if i == len(start_event_times) - 1:
                        scores.append(0)
                    else:
                        scores.append(start_event_times[i+1] - end_event_times[i])
            elif metric == 'epoch_length':
                if start_event_times is None or end_event_times is None:
                    raise ValueError( "start_event_times and end_event_times were not passed to score_of_chunks() in fiber_record_analyze.")
                else:
                    if i == len(start_event_times) - 1:
                        scores.append(0)
                    else:
                        scores.append(end_event_times[i] - start_event_times[i])
            elif metric == 'event_time':
                if start_event_times is None or end_event_times is None:
                    raise ValueError( "start_event_times and end_event_times were not passed to score_of_chunks() in fiber_record_analyze.")
                else:
                    scores.append(start_event_times[i])
            elif metric == 'event_index':
                scores.append(i+1)


            else:
                raise ValueError( "The entered metric is not one of peak, average, or spacing, epoch_length, or time.")

            i = i + 1

        return scores

    def plot_perievent_hist( self, 
                             event_times, 
                             window, 
                             out_path=None,
                             plotit=True, 
                             subplot=None, 
                             baseline_window='full' ):
        """
        Peri-event time histogram for given event times.
        Plots the time series and their median over a time window around
        each event in event_times, with before and after event durations
        specified in window as [before, after] (in seconds).
        """
        # new figure
        if plotit and subplot is None:
            pl.clf()
            fig = pl.figure()
            ax = fig.add_subplot(111)
        elif subplot is not None:
            ax = subplot

        print "Generating peri-event plot..."
        print "\t--> Number of bouts:", len(event_times)
        print "\t--> Window used for peri-event plot:", window

        # get blocks of time series for window around each event time
        time_chunks = self.get_time_chunks_around_events(self.fluor_data, 
                            event_times, window, baseline_window=baseline_window)

        # get time values from frame indices
        window_indices = [ self.convert_seconds_to_index(window[0]),
                           self.convert_seconds_to_index(window[1]) ]

        # plot each time window, colored by order
        time_arr = np.asarray(time_chunks).T
        x = self.time_stamps[0:time_arr.shape[0]]-self.time_stamps[window_indices[0]] ###IS THIS RIGHT?
        ymax = np.max(time_arr)
        ymax += 0.1*ymax
        ymin = np.min(time_arr)
        ymin -= 0.1*ymin
        for i in xrange(time_arr.shape[1]):
            if plotit:
                ax.plot(x, time_arr[:,i], color=pl.cm.jet(255-255*i/time_arr.shape[1]), alpha=0.75, linewidth=1)
            x.shape = (len(x),1) 
            x_padded = np.vstack([x[0], x, x[-1]])
            time_vec = time_arr[:,i]; time_vec.shape = (len(time_vec),1)
            time_vec_padded = np.vstack([0, time_vec,0]) 

            if plotit:
                pl.fill(x_padded, time_vec_padded, facecolor=pl.cm.jet(255-255*i/time_arr.shape[1]), alpha=0.25 )            
                pl.ylim([ymin, ymax])
            
        if plotit:
            # add a line for the event onset time
            pl.axvline(x=0,color='black',linewidth=1,linestyle='--')

            # label the plot axes
            if self.fluor_normalization == "deltaF":
                pl.ylabel(r'$\delta F/F$')
            else:
                pl.ylabel('Fluorescence Intensity (a.u.)')
            pl.xlabel('Time from onset of bout (seconds)')

            # show plot now or save of an output path was specified
            if out_path is None and subplot is None:
                pl.show()
            elif subplot is None:
                print "Saving peri-event time series..."
                pl.savefig(out_path + "perievent_tseries.pdf")
                pl.savefig(out_path + "perievent_tseries.png")

        return (time_arr, x)


    def plot_peritrigger_edge( self, window, edge="rising", out_path=None ):
        """
        Wrapper for plot_perievent histograms specialized for
        loaded event data that comes as a list of pairs of
        event start and end times.
        type can be "homecage" or "sucrose"
        """

        type = self.exp_type

        event_times = self.get_event_times(edge=edge, exp_type=type)

        if event_times[0] != -1:
            self.plot_perievent_hist( event_times, window, out_path=out_path )
        else:
            print "No event times loaded. Cannot plot perievent."        


    def get_event_times( self, edge="rising", exp_type=None):
        """
        Returns a list of either the start ('rising') or end ('falling')
        times of events. For sucrose data, uses the lick density
        as a way to split up licking sessions into events. For homecagesocial
        and homecagenovel, the events are defined by a pair of start and 
        end times directly from the hand-scoring. 

        Set event_spacing as a parser option to enforce a
        minimum time between events. 

        """

        if exp_type == 'sucrose':
            if self.event_start_times is None:
                event_times, end_times = self.get_sucrose_event_times()
                self.event_start_times = event_times
                self.event_end_times = end_times
            else:
                event_times = self.event_start_times
                end_times = self.event_end_times
            if edge == "rising":
                return event_times
            elif edge == "falling":
                return end_times
            else:
                raise ValueError("Edge type must be 'rising' or 'falling'.")

        if self.event_spacing is not None:
            nseconds = self.event_spacing
        else:
            nseconds = 0

        if self.time_tuples is not None:
            event_times = []
            for i in range(len(self.time_tuples)):
                pair = self.time_tuples[i]


                if i==0 or nseconds is None or (self.time_tuples[i][0] - self.time_tuples[i-1][1] >= nseconds):
                    if edge == "rising":
                        event_times.append(pair[0])
                    elif edge == "falling":
                        event_times.append(pair[1])
                    else:
                        raise ValueError("Edge type must be 'rising' or 'falling'.")
            return event_times
        else:            
            print "No event times loaded. Cannot find edges."        
            return [-1]

    def get_sucrose_event_times( self, nseconds=15, density=None, edge="rising"):
        """
        Extracts a list of the times (in seconds) corresponding
        to sucrose lick epochs. Epochs are determined by first calculating
        the density of licks (using a window of nseconds).
        The start ofd a licking epoch is then determined by calculating
        the location of the rising edges of this density plot.
        The end of a licking epoch can be determined by calculating
        the time at which this density returns to zero, minus nseconds.
        """

        print "event_spacing", self.event_spacing
        print "nseconds", nseconds

        if self.event_spacing is not None and self.event_spacing > 0.01:
            nseconds = self.event_spacing

        nindex = self.convert_seconds_to_index(nseconds)
        print "nindex", nindex
        mask = np.ones(nindex)

        self.trigger_data = np.floor(2*self.trigger_data) #make sure that no licks is represented by 0
        time_vals = self.time_stamps[range(len(self.trigger_data))]
        print time_vals
        if density is None:
            print "trigger_data", np.max(self.trigger_data)
            print "mask", mask
            density = np.convolve(self.trigger_data, mask)
            density = density[nindex-1:] 

        dmed = np.median(density)


        start_times = np.zeros(0)
        end_times = np.zeros(0)
        #Determine start and end times of lick epochs by determining
        #rising and falling edges of lick density plot.
        for i in range(nindex, len(density)-2):
            if np.round(density[i-1]) == np.round(dmed) and density[i] > dmed:
                start_times = np.append(start_times, time_vals[i+nindex]) #?Should I subtract -0.013, the length of the lickometer signal
            if np.round(density[i+1]) == np.round(dmed) and density[i] > dmed:
                end_times = np.append(end_times, time_vals[i])

        #filter out all of the single licks.
        filt_start_times = np.zeros(0)
        filt_end_times = np.zeros(0)
        for i in range(len(start_times)):
            if start_times[i] + 5 < end_times[i]: #only use licking epochs that last at least longer than 5 seconds ????
                filt_start_times = np.append(filt_start_times, start_times[i])
                filt_end_times = np.append(filt_end_times, end_times[i])

        print "start_times ", filt_start_times
        print "end_times ", filt_end_times
    
        # pl.plot(time_vals, density)
        # pl.fill(time_vals, 100*self.trigger_data, facecolor='r', alpha=0.5)
        # pl.show()
        return (filt_start_times, filt_end_times)

    def convert_seconds_to_index( self, time_in_seconds):
        return np.where( self.time_stamps >= time_in_seconds)[0][0]

    def debleach( self, out_path=None ):
        """
        Remove trend from data due to photobleaching by fitting the time series with an exponential curve
        and then subtracting the difference between the curve and the median value of the time series. 
        """
        print "--> Debleaching" 
        
        fluor_data = self.fluor_data
        time_stamps = self.time_stamps[range(len(self.fluor_data))]

        trigger_data = self.trigger_data

        #print np.shape(fluor_data), np.shape(time_stamps), np.shape(trigger_data)

        xp, pxp, x0, y0, c, k, r2, yxp = self.fit_exponential(time_stamps, fluor_data)
        w, r2lin, yxplin = self.fit_linear(time_stamps, fluor_data)
        if r2lin > r2:
            flat_fluor_data = fluor_data - yxplin + np.median(fluor_data)
            r2 = r2lin
        else:
            flat_fluor_data = fluor_data - yxp + np.median(fluor_data)

        #flat_fluor_data = flat_fluor_data - min(flat_fluor_data) + 0.000001

        orig, = pl.plot(time_stamps, fluor_data)
        pl.plot(time_stamps, yxp, 'r')
        debleached, = pl.plot(time_stamps, flat_fluor_data)
        pl.xlabel('Time [s]')
        pl.ylabel('Raw fluorescence (a.u.)')
        pl.title('Debleaching the fluorescence curve')
        pl.legend([orig, debleached], [ "Original raw", "Debleached raw"])


        out_arr = np.zeros((len(flat_fluor_data),4))
        out_arr[:,0] = flat_fluor_data

        trigger_data = -1*(trigger_data/np.max(trigger_data) - 1)
        out_arr[:,3] = trigger_data #these numbers are hardcoded above

        if out_path is None:
                pl.title("No output path given")
                #pl.show()
        else:
            pl.savefig(out_path + "_debleached.png")
            np.savez(out_path + "_debleached.npz", data=out_arr, time_stamps=time_stamps)
            print "--> Debleached output: " 
            print out_path + "_debleached.npz"
            print ""

        if self.save_and_exit:
            sys.exit(0)

    def get_areas_under_curve( self, start_times, window, baseline_window=None, normalize=False):
        """
        Returns a vector of the area under the fluorescence curve within the provided
        window [before, after] (in seconds), that surrounds each start_time.
        Normalize determines whether to divide the area by the maximum fluorescence
        value of the window (this is more if you want to look at the "shape" of the curve)
        """
        print "window: ", window
        time_chunks = self.get_time_chunks_around_events(self.fluor_data, start_times, window, baseline_window)
        
        print "len(time_chunks)", len(time_chunks)
        areas = []
        for chunk in time_chunks:
            if normalize:
                if max(chunk) < 0.01: 
                    areas.append(sum(chunk)/len(chunk)/0.01)
                else:
                    areas.append(sum(chunk)/len(chunk)/(max(abs(chunk))))
            else: 
                areas.append(sum(chunk)/len(chunk))

        return areas

    def get_peak( self, start_time, end_time, exp_type=None ):
        """
        Return the maximum fluorescence value found between
        start_time and end_time (in seconds)

        For exp_type == 'sucrose', may eventually account for 
        single licks and possibly for looking at a window
        beyond the length of time of a single lick
        """
        start_time_index = self.convert_seconds_to_index(start_time)
        end_time_index = self.convert_seconds_to_index(end_time)
        print "get_peak_indices", start_time_index, end_time_index
        if start_time_index < end_time_index:
            return np.max(self.fluor_data[start_time_index : end_time_index])
        else:
            return 0

    def eNegX(self, p, x):
        x0, y0, c, k=p
        #Set c=1 to normalize all of the trials, since we
        # are only interested in the rate of decay
        y = (1 * np.exp(-k*(x-x0))) + y0
        return y

    def eNegX_residuals(self, p, x, y):
        return y - self.eNegX(p, x)

    def fit_exponential(self, x, y, num_points=100):
        # Because we are optimizing over a nonlinear function
        # choose a number of possible starting values of (x0, y0, c, k)
        # and use the results from whichever produces the smallest 
        # residual
        # num_points gives the number of points in the returned curve, pxp

        kguess = [0, 0.1, 0.5, 1.0, 10, 100, 500, 1000]
        yguess = [0, 1]
        max_r2 = -1
        maxvalues = ()
        for kg in kguess:
            for yg in yguess:
                p_guess=(np.min(x), yg, 1, kg)
                p, cov, infodict, mesg, ier = sp.optimize.leastsq(
                    self.eNegX_residuals, p_guess, args=(x, y), full_output=1)

                x0,y0,c,k=p 

                numPoints = np.floor((np.max(x) - np.min(x))*num_points)
                xp = np.linspace(np.min(x), np.max(x), numPoints)
                pxp = self.eNegX(p, xp)
                yxp = self.eNegX(p, x)

                sstot = np.sum(np.multiply(y - np.mean(y), y - np.mean(y)))
                sserr = np.sum(np.multiply(y - yxp, y - yxp))
                r2 = 1 - sserr/sstot
                if max_r2 == -1:
                    maxvalues = (xp, pxp, x0, y0, c, k, r2, yxp)
                if r2 > max_r2:
                    max_r2 = r2
                    maxvalues = (xp, pxp, x0, y0, c, k, r2, yxp)

        return maxvalues

    def fit_linear(self, x, y):
        A = np.array([x, np.ones(len(x))])
        w = np.linalg.lstsq(A.T, y)[0]
        yxp = w[0]*x + w[1]

        sstot = np.sum(np.multiply(y - np.mean(y), y - np.mean(y)))
        sserr = np.sum(np.multiply(y - yxp, y - yxp))
        r2lin = 1 - sserr/sstot
        #print "r2lin", r2lin
        
        return (w, r2lin, yxp)

    def plot_peaks_vs_time( self, type="homecage", out_path=None ):
        """
        Plot the maximum fluorescence value within each interaction event vs the start time
        of the event
        type can be "homecage", for novel object and social, where event times were hand scored
        or "sucrose", where event times are from the lickometer
        """
        type = self.exp_type

        start_times = self.get_event_times(edge="rising", exp_type=type)
        end_times = self.get_event_times(edge="falling", exp_type=type)

        filt_start_times = []
        if start_times[0] != -1:
            peaks = np.zeros(len(start_times))
            for i in range(len(start_times)):
                peak = self.get_peak(start_times[i], end_times[i], type)

                if peak != 0:
                    peaks[i] = peak


            fig = pl.figure()
            ax = fig.add_subplot(111)
            print np.max(peaks) + .3
            if type == "sucrose":
                ax.set_ylim([0, np.max(peaks) + 0.4*np.max(peaks)])
            elif type == "homecagesocial" or type == "homecagenovel" or type == 'EPM':
                if np.max(peaks) > 0.8:
                    ax.set_ylim([0, 1.3])
                else:
                    ax.set_ylim([0, 1.1])
                ax.set_xlim([100, 500])
            else:
                ax.set_xlim([0, 1.1*np.max(start_times)])
           
            ax.plot(start_times, peaks, 'o')
            pl.xlabel('Time [s]')
            pl.ylabel('Fluorescence [dF/F]')
            pl.title('Peak fluorescence of interaction event vs. event start time')

            try:
                xp, pxp, x0, y0, c, k, r2, yxp = self.fit_exponential(start_times, peaks + 1)
                ax.plot(xp, pxp-1)
                ax.text(min(200, np.min(start_times)), np.max(peaks) + 0.20*np.max(peaks), "y = c*exp(-k*(x-x0)) + y0")
                ax.text(min(200, np.min(start_times)), np.max(peaks) + 0.15*np.max(peaks), "k = " + "{0:.2f}".format(k) + ", c = " + "{0:.2f}".format(c) + 
                                                ", x0 = " + "{0:.2f}".format(x0) + ", y0 = " + "{0:.2f}".format(y0) )
                ax.text(min(200, np.min(start_times)), np.max(peaks) + 0.1*np.max(peaks), "r^2 = " + str(r2))
            except:
                print "Exponential Curve fit did not work"


            if out_path is None:
                pl.title("No output path given")
                pl.show()
            else:
                pl.savefig(out_path + "plot_peaks_vs_time.pdf")
                np.savez(out_path + "peaks_vs_time.npz", scores=peaks, event_times=start_times, end_times=end_times, window_size=0)

        else:
            print "No event times loaded. Cannot plot peaks_vs_time."  

#-----------------------------------------------------------------------------------------
def add_command_line_options():
    # Parse command line options
    from optparse import OptionParser

    parser = OptionParser()
    parser.add_option("-o", "--output-path", dest="output_path", default=None,
                      help="Specify the ouput path.")
    parser.add_option("-t", "--trigger-path", dest="trigger_path", default=None,
                      help="Specify path to files with trigger times, minus the '_s.npz' and '_e.npz' suffixes.")
    parser.add_option("-i", "--input-path", dest="input_path",
                      help="Specify the input path (either to npz or hdf5 data).")
    parser.add_option("", "--time-range", dest="time_range",default='0:-1',
                      help="Specify a time window over which to analyze the time series in format start:end. -1 chooses the appropriate extremum")
    # parser.add_option('-p', "--plot-type", default = '', dest="plot_type",
    #                   help="Type of plot to produce.")
    parser.add_option('', "--fluor-normalization", default = 'deltaF', dest="fluor_normalization",
                      help="Normalization of fluorescence trace. Can be a.u. between [0,1]: 'standardize' or deltaF/F: 'deltaF' or 'raw'.")
    parser.add_option('-s', "--smoothness", default = 0, dest="smoothness",
                      help="Should the time series be smoothed, and how much.")
    parser.add_option("", "--save-txt", action="store_true", default=False, dest="save_txt",
                      help="Save data matrix out to a text file.")
    parser.add_option("", "--save-to-h5", default=None, dest="save_to_h5",
                      help="Provide the filepath to an hdf5 file. Saves data matrix to a dataset in this hdf5 file.")
    parser.add_option("", "--save-and-exit", action="store_true", default=False, dest="save_and_exit",
                      help="Exit immediately after saving data out.")
    parser.add_option("", "--save-debleach", action="store_true", default=False, dest="save_debleach",
                      help="Debleach fluorescence time series by fitting with an exponential curve.")
    parser.add_option("", "--filter-freqs", default=None, dest="filter_freqs",
                      help="Use a notch filter to remove high frequency noise. Format lowfreq:highfreq.")
    parser.add_option("", "--exp-type", dest="exp_type", default=None,
                       help="Specify either 'homecagenovel', 'homecagesocial', or 'sucrose', or 'EPM'.")
    parser.add_option("", "--event-spacing", dest="event_spacing", default=0,
                       help="Specify minimum time (in seconds) between the end of one event and the beginning of the next")
    parser.add_option("", "--mouse-type", dest="mouse_type", default="GC5",
                       help="Specify the type of virus injected in the mouse (GC5, GC5_NAcprojection, GC3, EYFP)")


    return parser



if __name__ == "__main__":

    parser = add_command_line_options()
    (options, args) = parser.parse_args()
    
    FA = FiberAnalyze( options )
    FA.load()

    # Test the class
#    test_FiberAnalyze(options)
    
# EOF
