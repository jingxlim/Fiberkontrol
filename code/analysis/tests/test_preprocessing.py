"""
test_preprocessing.py
This module runs unit tests on 
the preprocessing.py module.
"""

import preprocessing as prp
import json
import h5py
import numpy as np

def load_configuration():
    config_file = 'tests/test_configuration.json'
    config_dict = json.loads(open(config_file).read())
    config_dict = dict((str(k), str(v) if isinstance(v, unicode) else v) for k, v in config_dict.items())
    print config_dict
    return config_dict

    # cfg = {};
    # with open('tests/test_configuration.txt', 'rb') as f:
    #     reader = csv.reader(f, delimiter='=', quoting=csv.QUOTE_NONE)
    #     for row in reader:
    #         cfg[str(row[0].strip())] = row[1].strip()
    #return cfg
            

class Test_read_filenames():
    def setup(self):
        cfg = load_configuration()
        self.filenames_file = str(cfg['analysis_filenames_file'])
        self.path_to_raw_data = str(cfg['path_to_raw_data'])
        self.actual_filenames = ['20130524/20130524-GC5-homecagesocial-0001-600patch_test.npz',
                                 '20130524/20130524-GC5-homecagenovel-0001-600patch_test.npz',
                                 '20130524/20130524-GC5-homecagesocial-0002-600patch_test.npz',
                                 '20130524/20130524-GC5-homecagenovel-0002-600patch_test.npz']

    def tearDown(self):
        pass

    def test_no_path_just_files(self):
        analysis_filenames = prp.read_filenames(self.filenames_file)
        assert analysis_filenames == self.actual_filenames

    def test_with_path(self):
        analysis_filenames = prp.read_filenames(self.filenames_file, self.path_to_raw_data)

        for i in range(len(analysis_filenames)):
            assert analysis_filenames[i] == str(self.path_to_raw_data) + self.actual_filenames[i]
        # assert analysis_filenames == ['/Users/isaackauvar/Dropbox/Fiberkontrol/Fiberkontrol_Data/Lisa_Data/20130524/20130524-GC5-homecagesocial-0001-600patch_test.npz',
        #                               '/Users/isaackauvar/Dropbox/Fiberkontrol/Fiberkontrol_Data/Lisa_Data/20130524/20130524-GC5-homecagenovel-0001-600patch_test.npz']


class Test_generate_hdf5_file():
    def setup(self):
        self.epsilon = 0.000001 #used to check equality of two floats

        cfg = load_configuration()
        self.filenames_file = str(cfg['analysis_filenames_file'])
        self.path_to_raw_data = str(cfg['path_to_raw_data'])
        self.path_to_hdf5 = str(cfg['path_to_hdf5'])

        self.analysis_filenames = prp.read_filenames(self.filenames_file, self.path_to_raw_data)

    def tearDown(self):
        pass

    def test_rewrite_same_hdf5_file(self):
        success = 0;
        prp.generate_hdf5_file(self.analysis_filenames,self.path_to_hdf5)
        try:
            prp.generate_hdf5_file(self.analysis_filenames,self.path_to_hdf5)
            success = 1;
        except:
            success = 0;

        assert success == 1

    def test_multiple_dates(self):
        prp.generate_hdf5_file(self.analysis_filenames,self.path_to_hdf5)
        print "analysis_filenames", self.analysis_filenames
        f = h5py.File(self.path_to_hdf5)
        assert(unicode('0001') in f.keys())
        assert(f['0001'].keys() == [unicode('20130524')])
        assert(f['0001']['20130524'].keys() == [unicode('homecagenovel'), unicode('homecagesocial')])
        assert(f['0001']['20130524']['homecagenovel'].keys() == 
                        [unicode('event_tuples'), unicode('time_series_arr')])
        assert(f['0001']['20130524']['homecagesocial'].keys() == [unicode('event_tuples'), unicode('time_series_arr')])
        assert(f['0001'].attrs['mouse_type'] == 'GC5')

        event_tuple_diffs = np.abs(np.array(f['0001']['20130524']['homecagesocial']['event_tuples']) - np.array([[49.8, 50.7], [100.0, 101.5]]))
        assert((event_tuple_diffs.all() < self.epsilon) == True)

        time_series_arr = np.array(f['0001']['20130524']['homecagesocial']['time_series_arr'])
        print "shape time_series_arr", time_series_arr, np.shape(time_series_arr)
        assert(np.shape(time_series_arr) == (37501, 3))
        assert(np.abs(np.max(time_series_arr[:,0]) - 150.0) < self.epsilon) #max time of simulated data
        assert(np.abs(np.max(time_series_arr[:,1]) - 3.0) < self.epsilon) #trigger data after processing in fiber_record_analyze
        assert(np.abs(np.max(time_series_arr[:,2]) - 8.67774306) < self.epsilon) #max fluorescence of simulated data

        time_series_arr = np.array(f['0001']['20130524']['homecagenovel']['time_series_arr'])
        assert(np.shape(time_series_arr) == (37501, 3))
        assert(np.abs(np.max(time_series_arr[:,2]) - 5.44846108) < self.epsilon) #max fluorescence of simulated data









    #check multiple dates
    #check multiple exp_types
    #check multiple animals
    #check animal type (i.e. GC5)
    #check the stored array
     

