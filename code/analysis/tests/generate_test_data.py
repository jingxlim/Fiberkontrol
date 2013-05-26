"""
Generate test data for FiberPhotometry plotting

The observed time series is the sum of the
binary spiking time series of a group of numNeurons

We simulate an increase in activity during an interaction/
licking event by increasing the probability of a spike
within a window surrounding this event. 

"""

import numpy as np
import scipy.signal
import random
import matplotlib.pyplot as plt
import os

class TimeSeriesSimulator( object ):
	def __init__(self, options):

		self.output_path = options.output_path

		# acquisition parameters from fiberkontrol_LED.py
		self.SampleFrequency = 250.0 #in Hz
		self.totalTime = 150.0 #total time of trial in seconds
		self.numNeurons = 1000 # we will sum together the time series o
		self.numDataPoints = int(self.SampleFrequency*self.totalTime)
		self.time_stamps = np.arange(self.numDataPoints+1)*self.totalTime/self.numDataPoints

		self.exp_type = options.exp_type
		self.mouse_number = options.mouse_number

		if self.exp_type == 'social':
			self.no_event_lambda = 200
			self.event_lambda = 50
		elif self.exp_type == 'novel':
			self.no_event_lambda = 200
			self.event_lambda = 100

	def GenerateEventTimes(self, avgEventLength=1, avgSpacing=10):
		"""
		Returns an array of start_times and end_times of interaction events 
		based on the provided statistics.
		"""
		if self.mouse_number == '0001':
			start_times = [49.8, 100]
			end_times = [50.7, 101.5]
		elif self.mouse_number == '0002':
			start_times = [40.8, 44.6, 110]
			end_times = [42.3, 45.1, 111.5]

		start_indices = self.SecondsToIndices(start_times)
		end_indices = self.SecondsToIndices(end_times)

		event_indicator = np.zeros(self.numDataPoints+1)
		for i in range(len(start_times)):
			event_indicator[start_indices[i]:end_indices[i]] = 1.0
		
		print "event_indicator", np.max(event_indicator)
		return (start_times, end_times, event_indicator, start_indices, end_indices)

	def SecondsToIndices(self, secondsArr):
		"""
		Given an array of timestamp in seconds,
		returns an array with the corresponding
		indices into the timeseries
		"""
		return np.array(secondsArr)*self.numDataPoints/self.totalTime

	def GetSpikeTimeSeries(self, dist_lambda, array_length, num_time_series):
		"""
		Uses a poisson distribution with mean 'dist_lambda'
		to generate 'num_time_series' binary time series 
		(0 for off, 1 for a spike) of length 'array_length'.
		Each row is a time series for a neuron.
		"""
		spike_times = np.cumsum(np.random.poisson(dist_lambda, 
								(num_time_series, array_length)), axis=1) + \
								np.ceil(dist_lambda/2*(.5 - 
									np.random.rand(num_time_series, array_length)))
		spike_times = np.multiply(spike_times, (spike_times<array_length))
		spike_times = spike_times.astype(int)
		time_series = np.zeros((num_time_series, array_length))
		for j in range(num_time_series):
			time_series[j, spike_times[j,:]] = 1
		time_series[:, 0] = 0
		return time_series

	def ConvolveWithFluorescenceDecay(self, all_time_series, tao=0.510):
		"""
		Convolve the point process time series
		with the exponential decay of the calcium
		indicator (for GCaMP5, tao = 0.510 seconds).
		see: http://www.jneurosci.org/content/32/40/13819.full#F9
		"""

		index_tao = np.ceil(tao*self.SampleFrequency) #convert tao to units of [sample rate]

		kernel = np.zeros((3, 4*index_tao))
		kernel[1, (2*index_tao):] = np.exp(-np.arange(2*index_tao)/index_tao)

		all_time_series = scipy.signal.fftconvolve(all_time_series, kernel, mode='same')
		return all_time_series



	def GenerateTimeSeries(self):
		"""
		Returns a single time series that represents
		the sum of the binary time series of individual
		neurons convolved with an approximation of
		the decay profile of GCaMP.
		"""

		start_times, end_times, event_indicator, \
			start_indices, end_indices = self.GenerateEventTimes(self.totalTime)
		self.start_times = start_times
		self.end_times = end_times

		prev_index = 0
		all_time_series = np.zeros((self.numNeurons, 1))
		for i in range(len(start_indices)):
			start_index = start_indices[i]
			end_index = end_indices[i]

			no_event_time_series = self.GetSpikeTimeSeries(self.no_event_lambda, 
											start_index - prev_index, self.numNeurons)
			event_time_series = self.GetSpikeTimeSeries(self.event_lambda, 
											end_index - start_index, self.numNeurons)
			all_time_series = np.hstack((all_time_series, no_event_time_series, event_time_series))

			prev_index = end_index

			if i == len(start_indices) -1:
				no_event_time_series = self.GetSpikeTimeSeries(self.no_event_lambda, 
											self.numDataPoints - prev_index, self.numNeurons)
				all_time_series = np.hstack((all_time_series, no_event_time_series))


		all_time_series = self.ConvolveWithFluorescenceDecay(all_time_series, 4)
		#t = np.tile(range(self.numDataPoints+1), (self.numNeurons,1))
		#y = np.sum(np.cumsum(indiv_time_series, axis = 1), axis = 0)
		self.fluor = np.sum(all_time_series, axis = 0)
		self.fluor = self.fluor/self.numNeurons

		resolution = 10
		plt.plot(self.time_stamps[::resolution], self.fluor[::resolution])
		plt.plot(self.time_stamps[::resolution], event_indicator[::resolution]*np.max(self.fluor), 'r')
		directory = '20130524/figs'
		if not os.path.isdir(self.output_path + directory):
		    os.mkdir(self.output_path + directory)
		plt.savefig(self.output_path + directory + '/20130524-GC5-homecage' + self.exp_type + '-'+self.mouse_number+'-600patch_test.png')


	def save(self):
		self.out_arr = np.tile(self.fluor, (4, 1)).T;
		print "out_arr", self.out_arr, np.shape(self.out_arr)
		outfile = self.output_path + '20130524/20130524-GC5-homecage' + self.exp_type + '-'+self.mouse_number+'-600patch_test'
		np.savez(outfile, data=self.out_arr, time_stamps=self.time_stamps)

		np.savez(self.output_path + '20130524/GC5_'+self.mouse_number+'_'+self.exp_type+'_s', self.start_times)
		np.savez(self.output_path + '20130524/GC5_'+self.mouse_number+'_'+self.exp_type+'_e', self.end_times)


if __name__ == "__main__":
	# Parse command line options
	from optparse import OptionParser

	parser = OptionParser()
	parser.add_option("-o", "--output-path", dest="output_path", default=None,
                      help="Specify the ouput path.")
	parser.add_option("", "--exp-type", dest="exp_type", default='social',
                  help="Specify the experiment type 'social', or 'novel'.")
	parser.add_option("", "--mouse-number", dest="mouse_number", default='0001',
                   help="Specify the mouse number (stick to 0001, 0002...).")
	(options, args) = parser.parse_args()


	random.seed(1)
	TSS = TimeSeriesSimulator(options)
	TSS.GenerateTimeSeries()
	TSS.save()


