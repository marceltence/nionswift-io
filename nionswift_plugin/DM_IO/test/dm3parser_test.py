# -*- coding: utf-8 -*-
"""
Created on Sun May 19 07:58:10 2013

@author: matt
"""

import array
import datetime
import io
import logging
import pkgutil
import unittest
import shutil
import sys

import h5py
import numpy

from nionswift_plugin.DM_IO import parse_dm3
from nionswift_plugin.DM_IO import dm3_image_utils

from nion.data import Calibration
from nion.data import DataAndMetadata


class TestDM3ImportExportClass(unittest.TestCase):

    def check_write_then_read_matches(self, data, func, _assert=True):
        # we confirm that reading a written element returns the same value
        s = io.BytesIO()
        header = func(s, outdata=data)
        s.seek(0)
        if header is not None:
            r, hy = func(s)
        else:
            r = func(s)
        if _assert:
            self.assertEqual(r, data)
        return r

    def test_dm_read_struct_types(self):
        s = io.BytesIO()
        types = [2, 2, 2]
        parse_dm3.dm_read_struct_types(s, outtypes=types)
        s.seek(0)
        in_types, headerlen = parse_dm3.dm_read_struct_types(s)
        self.assertEqual(in_types, types)

    def test_simpledata(self):
        self.check_write_then_read_matches(45, parse_dm3.dm_types[parse_dm3.get_dmtype_for_name('long')])
        self.check_write_then_read_matches(2**30, parse_dm3.dm_types[parse_dm3.get_dmtype_for_name('uint')])
        self.check_write_then_read_matches(34.56, parse_dm3.dm_types[parse_dm3.get_dmtype_for_name('double')])

    def test_read_string(self):
        data = "MyString"
        ret = self.check_write_then_read_matches(data, parse_dm3.dm_types[parse_dm3.get_dmtype_for_name('array')], False)
        self.assertEqual(data, dm3_image_utils.fix_strings(ret))

    def test_array_simple(self):
        dat = array.array('b', [0]*256)
        self.check_write_then_read_matches(dat, parse_dm3.dm_types[parse_dm3.get_dmtype_for_name('array')])

    def test_array_struct(self):
        dat = parse_dm3.structarray(['h', 'h', 'h'])
        dat.raw_data = array.array('b', [0, 0] * 3 * 8)  # two bytes x 3 'h's x 8 elements
        self.check_write_then_read_matches(dat, parse_dm3.dm_types[parse_dm3.get_dmtype_for_name('array')])

    def test_tagdata(self):
        for d in [45, 2**30, 34.56, array.array('b', [0]*256)]:
            self.check_write_then_read_matches(d, parse_dm3.parse_dm_tag_data)

    def test_tagroot_dict(self):
        mydata = {}
        self.check_write_then_read_matches(mydata, parse_dm3.parse_dm_tag_root)
        mydata = {"Bob": 45, "Henry": 67, "Joe": 56}
        self.check_write_then_read_matches(mydata, parse_dm3.parse_dm_tag_root)

    def test_tagroot_dict_complex(self):
        mydata = {"Bob": 45, "Henry": 67, "Joe": {
                  "hi": [34, 56, 78, 23], "Nope": 56.7, "d": array.array('I', [0] * 32)}}
        self.check_write_then_read_matches(mydata, parse_dm3.parse_dm_tag_root)

    def test_tagroot_list(self):
        # note any strings here get converted to 'H' arrays!
        mydata = []
        self.check_write_then_read_matches(mydata, parse_dm3.parse_dm_tag_root)
        mydata = [45,  67,  56]
        self.check_write_then_read_matches(mydata, parse_dm3.parse_dm_tag_root)

    def test_struct(self):
        # note any strings here get converted to 'H' arrays!
        mydata = tuple()
        f = parse_dm3.dm_types[parse_dm3.get_dmtype_for_name('struct')]
        self.check_write_then_read_matches(mydata, f)
        mydata = (3, 4, 56.7)
        self.check_write_then_read_matches(mydata, f)

    def test_image(self):
        im = array.array('h')
        if sys.version < '3':
            im.fromstring(numpy.random.bytes(64))
        else:
            im.frombytes(numpy.random.bytes(64))
        im_tag = {"Data": im,
                  "Dimensions": [23, 45]}
        s = io.BytesIO()
        parse_dm3.parse_dm_tag_root(s, outdata=im_tag)
        s.seek(0)
        ret = parse_dm3.parse_dm_tag_root(s)
        self.assertEqual(im_tag["Data"], ret["Data"])
        self.assertEqual(im_tag["Dimensions"], ret["Dimensions"])
        self.assertTrue((im_tag["Data"] == ret["Data"]))

    def test_data_write_read_round_trip(self):
        def db_make_directory_if_needed(directory_path):
            if os.path.exists(directory_path):
                if not os.path.isdir(directory_path):
                    raise OSError("Path is not a directory:", directory_path)
            else:
                os.makedirs(directory_path)

        class numpy_array_type:
            def __init__(self, shape, dtype):
                self.data = numpy.ones(shape, dtype)
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc_value, traceback):
                pass

        class h5py_array_type:
            def __init__(self, shape, dtype):
                current_working_directory = os.getcwd()
                self.__workspace_dir = os.path.join(current_working_directory, "__Test")
                db_make_directory_if_needed(self.__workspace_dir)
                self.f = h5py.File(os.path.join(self.__workspace_dir, "file.h5"))
                self.data = self.f.create_dataset("data", data=numpy.ones(shape, dtype))
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc_value, traceback):
                self.f.close()
                shutil.rmtree(self.__workspace_dir)

        array_types = numpy_array_type, h5py_array_type
        dtypes = (numpy.float32, numpy.float64, numpy.complex64, numpy.complex128, numpy.int16, numpy.uint16, numpy.int32, numpy.uint32)
        shape_data_descriptors = (
            ((6,), DataAndMetadata.DataDescriptor(False, 0, 1)),        # spectrum
            ((6, 4), DataAndMetadata.DataDescriptor(False, 1, 1)),      # 1d collection of spectra
            ((6, 8, 10), DataAndMetadata.DataDescriptor(False, 2, 1)),  # 2d collection of spectra
            ((6, 4), DataAndMetadata.DataDescriptor(True, 0, 1)),       # sequence of spectra
            ((6, 4), DataAndMetadata.DataDescriptor(False, 0, 2)),      # image
            ((6, 4, 2), DataAndMetadata.DataDescriptor(False, 1, 2)),   # 1d collection of images
            ((6, 5, 4, 2), DataAndMetadata.DataDescriptor(False, 2, 2)),   # 2d collection of images. not possible?
            ((6, 8, 10), DataAndMetadata.DataDescriptor(True, 0, 2)),   # sequence of images
        )
        for array_type in array_types:
            for dtype in dtypes:
                for shape, data_descriptor_in in shape_data_descriptors:
                    s = io.BytesIO()
                    with array_type(shape, dtype) as a:
                        data_in = a.data
                        dimensional_calibrations_in = list()
                        for index, dimension in enumerate(shape):
                            dimensional_calibrations_in.append(Calibration.Calibration(1.0 + 0.1 * index, 2.0 + 0.2 * index, "µ" + "n" * index))
                        intensity_calibration_in = Calibration.Calibration(4, 5, "six")
                        metadata_in = dict()
                        xdata_in = DataAndMetadata.new_data_and_metadata(data_in, data_descriptor=data_descriptor_in, dimensional_calibrations=dimensional_calibrations_in, intensity_calibration=intensity_calibration_in, metadata=metadata_in)
                        dm3_image_utils.save_image(xdata_in, s)
                        s.seek(0)
                        xdata = dm3_image_utils.load_image(s)
                        self.assertTrue(numpy.array_equal(data_in, xdata.data))
                        self.assertEqual(data_descriptor_in, xdata.data_descriptor)
                        self.assertEqual(dimensional_calibrations_in, xdata.dimensional_calibrations)
                        self.assertEqual(intensity_calibration_in, xdata.intensity_calibration)

    def test_rgb_data_write_read_round_trip(self):
        s = io.BytesIO()
        data_in = (numpy.random.randn(6, 4, 3) * 255).astype(numpy.uint8)
        data_descriptor_in = DataAndMetadata.DataDescriptor(False, 0, 2)
        dimensional_calibrations_in = [Calibration.Calibration(1, 2, "nm"), Calibration.Calibration(2, 3, u"µm")]
        intensity_calibration_in = Calibration.Calibration(4, 5, "six")
        metadata_in = {"abc": None, "": "", "one": [], "two": {}, "three": [1, None, 2]}
        xdata_in = DataAndMetadata.new_data_and_metadata(data_in, data_descriptor=data_descriptor_in, dimensional_calibrations=dimensional_calibrations_in, intensity_calibration=intensity_calibration_in, metadata=metadata_in)
        dm3_image_utils.save_image(xdata_in, s)
        s.seek(0)
        xdata = dm3_image_utils.load_image(s)
        self.assertTrue(numpy.array_equal(data_in, xdata.data))
        self.assertEqual(data_descriptor_in, xdata.data_descriptor)

    def test_calibrations_write_read_round_trip(self):
        s = io.BytesIO()
        data_in = numpy.ones((6, 4), numpy.float32)
        data_descriptor_in = DataAndMetadata.DataDescriptor(False, 0, 2)
        dimensional_calibrations_in = [Calibration.Calibration(1.1, 2.1, "nm"), Calibration.Calibration(2, 3, u"µm")]
        intensity_calibration_in = Calibration.Calibration(4.4, 5.5, "six")
        metadata_in = dict()
        xdata_in = DataAndMetadata.new_data_and_metadata(data_in, data_descriptor=data_descriptor_in, dimensional_calibrations=dimensional_calibrations_in, intensity_calibration=intensity_calibration_in, metadata=metadata_in)
        dm3_image_utils.save_image(xdata_in, s)
        s.seek(0)
        xdata = dm3_image_utils.load_image(s)
        self.assertEqual(dimensional_calibrations_in, xdata.dimensional_calibrations)
        self.assertEqual(intensity_calibration_in, xdata.intensity_calibration)

    def test_data_timestamp_write_read_round_trip(self):
        s = io.BytesIO()
        data_in = numpy.ones((6, 4), numpy.float32)
        data_descriptor_in = DataAndMetadata.DataDescriptor(False, 0, 2)
        dimensional_calibrations_in = [Calibration.Calibration(1.1, 2.1, "nm"), Calibration.Calibration(2, 3, u"µm")]
        intensity_calibration_in = Calibration.Calibration(4.4, 5.5, "six")
        metadata_in = dict()
        timestamp_in = datetime.datetime(2013, 11, 18, 14, 5, 4, 0)
        timezone_in = "America/Los_Angeles"
        timezone_offset_in = "-0700"
        xdata_in = DataAndMetadata.new_data_and_metadata(data_in, data_descriptor=data_descriptor_in, dimensional_calibrations=dimensional_calibrations_in, intensity_calibration=intensity_calibration_in, metadata=metadata_in, timestamp=timestamp_in, timezone=timezone_in, timezone_offset=timezone_offset_in)
        dm3_image_utils.save_image(xdata_in, s)
        s.seek(0)
        xdata = dm3_image_utils.load_image(s)
        self.assertEqual(timestamp_in, xdata.timestamp)
        self.assertEqual(timezone_in, xdata.timezone)
        self.assertEqual(timezone_offset_in, xdata.timezone_offset)

    def test_metadata_write_read_round_trip(self):
        s = io.BytesIO()
        data_in = numpy.ones((6, 4), numpy.float32)
        data_descriptor_in = DataAndMetadata.DataDescriptor(False, 0, 2)
        dimensional_calibrations_in = [Calibration.Calibration(1, 2, "nm"), Calibration.Calibration(2, 3, u"µm")]
        intensity_calibration_in = Calibration.Calibration(4, 5, "six")
        metadata_in = {"abc": 1, "def": "abc", "efg": { "one": 1, "two": "TWO", "three": [3, 4, 5] }}
        xdata_in = DataAndMetadata.new_data_and_metadata(data_in, data_descriptor=data_descriptor_in, dimensional_calibrations=dimensional_calibrations_in, intensity_calibration=intensity_calibration_in, metadata=metadata_in)
        dm3_image_utils.save_image(xdata_in, s)
        s.seek(0)
        xdata = dm3_image_utils.load_image(s)
        self.assertEqual(metadata_in, xdata.metadata)

    def test_metadata_difficult_types_write_read_round_trip(self):
        s = io.BytesIO()
        data_in = numpy.ones((6, 4), numpy.float32)
        data_descriptor_in = DataAndMetadata.DataDescriptor(False, 0, 2)
        dimensional_calibrations_in = [Calibration.Calibration(1, 2, "nm"), Calibration.Calibration(2, 3, u"µm")]
        intensity_calibration_in = Calibration.Calibration(4, 5, "six")
        metadata_in = {"abc": None, "": "", "one": [], "two": {}, "three": [1, None, 2]}
        xdata_in = DataAndMetadata.new_data_and_metadata(data_in, data_descriptor=data_descriptor_in, dimensional_calibrations=dimensional_calibrations_in, intensity_calibration=intensity_calibration_in, metadata=metadata_in)
        dm3_image_utils.save_image(xdata_in, s)
        s.seek(0)
        xdata = dm3_image_utils.load_image(s)
        metadata_expected = {"one": [], "two": {}, "three": [1, 2]}
        self.assertEqual(metadata_expected, xdata.metadata)

    def test_metadata_export_large_integer(self):
        s = io.BytesIO()
        data_in = numpy.ones((6, 4), numpy.float32)
        data_descriptor_in = DataAndMetadata.DataDescriptor(False, 0, 2)
        dimensional_calibrations_in = [Calibration.Calibration(1, 2, "nm"), Calibration.Calibration(2, 3, u"µm")]
        intensity_calibration_in = Calibration.Calibration(4, 5, "six")
        metadata_in = {"abc": 999999999999}
        xdata_in = DataAndMetadata.new_data_and_metadata(data_in, data_descriptor=data_descriptor_in, dimensional_calibrations=dimensional_calibrations_in, intensity_calibration=intensity_calibration_in, metadata=metadata_in)
        dm3_image_utils.save_image(xdata_in, s)
        s.seek(0)
        xdata = dm3_image_utils.load_image(s)
        metadata_expected = {"abc": 999999999999}
        self.assertEqual(metadata_expected, xdata.metadata)

    def test_signal_type_round_trip(self):
        s = io.BytesIO()
        data_in = numpy.ones((12,), numpy.float32)
        data_descriptor_in = DataAndMetadata.DataDescriptor(False, 0, 1)
        dimensional_calibrations_in = [Calibration.Calibration(1, 2, "eV")]
        intensity_calibration_in = Calibration.Calibration(4, 5, "e")
        metadata_in = {"hardware_source": {"signal_type": "EELS"}}
        xdata_in = DataAndMetadata.new_data_and_metadata(data_in, data_descriptor=data_descriptor_in, dimensional_calibrations=dimensional_calibrations_in, intensity_calibration=intensity_calibration_in, metadata=metadata_in)
        dm3_image_utils.save_image(xdata_in, s)
        s.seek(0)
        xdata = dm3_image_utils.load_image(s)
        metadata_expected = {'hardware_source': {'signal_type': 'EELS'}, 'Meta Data': {'Format': 'Spectrum', 'Signal': 'EELS'}}
        self.assertEqual(metadata_expected, xdata.metadata)

    def test_reference_images_load_properly(self):
        shape_data_descriptors = (
            ((3,), DataAndMetadata.DataDescriptor(False, 0, 1)),        # spectrum
            ((3, 2), DataAndMetadata.DataDescriptor(False, 1, 1)),      # 1d collection of spectra
            ((3, 4, 5), DataAndMetadata.DataDescriptor(False, 2, 1)),   # 2d collection of spectra
            ((3, 2), DataAndMetadata.DataDescriptor(True, 0, 1)),       # sequence of spectra
            ((3, 2), DataAndMetadata.DataDescriptor(False, 0, 2)),      # image
            ((4, 3, 2), DataAndMetadata.DataDescriptor(False, 1, 2)),   # 1d collection of images
            ((3, 4, 5), DataAndMetadata.DataDescriptor(True, 0, 2)),    # sequence of images
        )
        for shape, data_descriptor in shape_data_descriptors:
            dimensional_calibrations = list()
            for index, dimension in enumerate(shape):
                dimensional_calibrations.append(Calibration.Calibration(1.0 + 0.1 * index, 2.0 + 0.2 * index, "µ" + "n" * index))
            intensity_calibration = Calibration.Calibration(4, 5, "six")
            data = numpy.arange(numpy.product(shape), dtype=numpy.float32).reshape(shape)

            name = f"ref_{'T' if data_descriptor.is_sequence else 'F'}_{data_descriptor.collection_dimension_count}_{data_descriptor.datum_dimension_count}.dm3"

            # import pathlib
            # xdata = DataAndMetadata.new_data_and_metadata(data, dimensional_calibrations=dimensional_calibrations, intensity_calibration=intensity_calibration, data_descriptor=data_descriptor)
            # file_path = pathlib.Path(__file__).parent / "resources" / name
            # with file_path.open('wb') as f:
            #     dm3_image_utils.save_image(xdata, f)

            try:
                s = io.BytesIO(pkgutil.get_data(__name__, f"resources/{name}"))
                xdata = dm3_image_utils.load_image(s)
                self.assertEqual(intensity_calibration, xdata.intensity_calibration)
                self.assertEqual(dimensional_calibrations, xdata.dimensional_calibrations)
                self.assertEqual(data_descriptor, xdata.data_descriptor)
                self.assertTrue(numpy.array_equal(data, xdata.data))
                # print(f"{name} {data_descriptor} PASS")
            except Exception as e:
                print(f"{name} {data_descriptor} FAIL")
                raise

    def disabled_test_specific_file(self):
        file_path = "/path/to/test.dm3"
        xdata = dm3_image_utils.load_image(file_path)

        # file_path = "/path/to/test-new.dm3"
        # with open(file_path, "wb") as f:
        #     dm3_image_utils.save_image(xdata, f)


# some functions for processing multiple files.
# useful for testing reading and writing a large number of files.
import os


def process_dm3(path, mode):
    opath = path + ".out.dm3"
    data = odata = None
    if mode == 0 or mode == 1:  # just open source
        # path=opath
        with open(path, 'rb') as f:
            data = parse_dm3.parse_dm_header(f)
    if mode == 1:  # open source, write to out
        with open(opath, 'wb') as f:
            parse_dm3.parse_dm_header(f, outdata=data)
    elif mode == 2:  # open both
        with open(path, 'rb') as f:
            data = parse_dm3.parse_dm_header(f)
        with open(opath, 'rb') as f:
            odata = parse_dm3.parse_dm_header(f)
        # this ensures keys in root only are the same
        assert(sorted(odata) == sorted(data))
    return data, odata


def process_all(mode):
    for f in [x for x in os.listdir(".")
              if x.endswith(".dm3")
              if not x.endswith("out.dm3")]:
        print("reading", f, "...")
        data, odata = process_dm3(f, mode)

if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    unittest.main()
    # process_all(1)
