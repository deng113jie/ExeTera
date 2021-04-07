
from typing import Union
from datetime import datetime, timezone

import numpy as np
import numba
import h5py

from exetera.core.abstract_types import Field
from exetera.core.data_writer import DataWriter
from exetera.core import operations as ops
from exetera.core import validation as val

class HDF5Field(Field):
    def __init__(self, session, group, name=None, write_enabled=False):
        super().__init__()

        if name is None:
            field = group
        else:
            field = group[name]
        self._session = session
        self._field = field
        self._fieldtype = self._field.attrs['fieldtype']
        self._write_enabled = write_enabled
        self._value_wrapper = None

    @property
    def name(self):
        return self._field.name

    @property
    def timestamp(self):
        return self._field.attrs['timestamp']

    @property
    def chunksize(self):
        return self._field.attrs['chunksize']

    @property
    def indexed(self):
        return False

    # @property
    # def data(self):
    #     raise NotImplementedError()

    def __bool__(self):
        # this method is required to prevent __len__ being called on derived methods when fields are queried as
        #   if f:
        # rather than
        #   if f is not None:
        return True

    def get_spans(self):
        raise NotImplementedError("Please use get_spans() on specific fields, not the field base class.")

    def apply_filter(self, filter_to_apply, dstfld=None):
        raise NotImplementedError("Please use apply_filter() on specific fields, not the field base class.")

    def apply_index(self, index_to_apply, dstfld=None):
        raise NotImplementedError("Please use apply_index() on specific fields, not the field base class.")





class ReadOnlyFieldArray:
    def __init__(self, field, dataset_name):
        self._field = field
        self._name = dataset_name
        self._dataset = field[dataset_name]

    def __len__(self):
        return len(self._dataset)

    @property
    def dtype(self):
        return self._dataset.dtype

    def __getitem__(self, item):
        return self._dataset[item]

    def __setitem__(self, key, value):
        raise PermissionError("This field was created read-only; call <field>.writeable() "
                              "for a writeable copy of the field")

    def clear(self):
        raise PermissionError("This field was created read-only; call <field>.writeable() "
                              "for a writeable copy of the field")

    def write_part(self, part):
        raise PermissionError("This field was created read-only; call <field>.writeable() "
                              "for a writeable copy of the field")

    def write(self, part):
        raise PermissionError("This field was created read-only; call <field>.writeable() "
                              "for a writeable copy of the field")

    def complete(self):
        raise PermissionError("This field was created read-only; call <field>.writeable() "
                              "for a writeable copy of the field")


class WriteableFieldArray:
    def __init__(self, field, dataset_name):
        self._field = field
        self._name = dataset_name
        self._dataset = field[dataset_name]

    def __len__(self):
        return len(self._dataset)

    @property
    def dtype(self):
        return self._dataset.dtype

    def __getitem__(self, item):
        return self._dataset[item]

    def __setitem__(self, key, value):
        self._dataset[key] = value

    def clear(self):
        nformat = self._dataset.dtype
        DataWriter._clear_dataset(self._field, self._name)
        DataWriter.write(self._field, self._name, [], 0, nformat)
        self._dataset = self._field[self._name]

    def write_part(self, part):
        DataWriter.write(self._field, self._name, part, len(part), dtype=self._dataset.dtype)

    def write(self, part):
        DataWriter.write(self._field, self._name, part, len(part), dtype=self._dataset.dtype)
        self.complete()

    def complete(self):
        DataWriter.flush(self._field[self._name])


class ReadOnlyIndexedFieldArray:
    def __init__(self, field, index_name, values_name):
        self._field = field
        self._index_name = index_name
        self._index_dataset = field[index_name]
        self._values_name = values_name
        self._values_dataset = field[values_name]

    def __len__(self):
        # TODO: this occurs because of the initialized state of an indexed string. It would be better for the
        # index to be initialised as [0]
        return max(len(self._index_dataset)-1, 0)

    def __getitem__(self, item):
        try:
            if isinstance(item, slice):
                start = item.start if item.start is not None else 0
                stop = item.stop if item.stop is not None else len(self._index_dataset) - 1
                step = item.step
                #TODO: validate slice
                index = self._index_dataset[start:stop+1]
                bytestr = self._values_dataset[index[0]:index[-1]]
                results = [None] * (len(index)-1)
                startindex = start
                for ir in range(len(results)):
                    results[ir] =\
                        bytestr[index[ir]-np.int64(startindex):
                                index[ir+1]-np.int64(startindex)].tobytes().decode()
                return results
            elif isinstance(item, int):
                if item >= len(self._index_dataset) - 1:
                    raise ValueError("index is out of range")
                start, stop = self._index_dataset[item:item + 2]
                if start == stop:
                    return ''
                value = self._values_dataset[start:stop].tobytes().decode()
                return value
        except Exception as e:
            print("{}: unexpected exception {}".format(self._field.name, e))
            raise

    def __setitem__(self, key, value):
        raise PermissionError("This field was created read-only; call <field>.writeable() "
                              "for a writeable copy of the field")

    def clear(self):
        raise PermissionError("This field was created read-only; call <field>.writeable() "
                              "for a writeable copy of the field")

    def write_part(self, part):
        raise PermissionError("This field was created read-only; call <field>.writeable() "
                              "for a writeable copy of the field")

    def write(self, part):
        raise PermissionError("This field was created read-only; call <field>.writeable() "
                              "for a writeable copy of the field")

    def complete(self):
        raise PermissionError("This field was created read-only; call <field>.writeable() "
                              "for a writeable copy of the field")


class WriteableIndexedFieldArray:
    def __init__(self, field, index_name, values_name):
        self._field = field
        self._index_name = index_name
        self._index_dataset = field[index_name]
        self._values_name = values_name
        self._values_dataset = field[values_name]
        self._chunksize = self._field.attrs['chunksize']
        self._raw_values = np.zeros(self._chunksize, dtype=np.uint8)
        self._raw_indices = np.zeros(self._chunksize, dtype=np.int64)
        self._accumulated = self._index_dataset[-1] if len(self._index_dataset) else 0
        self._index_index = 0
        self._value_index = 0

    def __len__(self):
        return len(self._index_dataset) - 1

    def __getitem__(self, item):
        try:
            if isinstance(item, slice):
                start = item.start if item.start is not None else 0
                stop = item.stop if item.stop is not None else len(self._index_dataset) - 1
                step = item.step
                # TODO: validate slice
                index = self._index_dataset[start:stop + 1]
                bytestr = self._values_dataset[index[0]:index[-1]]
                results = [None] * (len(index) - 1)
                startindex = start
                rmax = min(len(results), stop - start)
                for ir in range(rmax):
                    rbytes = bytestr[index[ir] - np.int64(startindex):
                                index[ir + 1] - np.int64(startindex)].tobytes()
                    rstr = rbytes.decode()
                    results[ir] = rstr
                return results
            elif isinstance(item, int):
                if item >= len(self._index_dataset) - 1:
                    raise ValueError("index is out of range")
                start, stop = self._index_dataset[item:item + 2]
                if start == stop:
                    return ''
                value = self._values_dataset[start:stop].tobytes().decode()
                return value
        except Exception as e:
            print("{}: unexpected exception {}".format(self._field.name, e))
            raise

    def __setitem__(self, key, value):
        raise PermissionError("IndexedStringField instances cannot be edited via array syntax;"
                              "use clear and then write/write_part or write_raw/write_part_raw")

    def clear(self):
        self._accumulated = 0
        DataWriter.clear_dataset(self._field, self._index_name)
        DataWriter.clear_dataset(self._field, self._values_name)
        DataWriter.write(self._field, self._index_name, [], 0, 'int64')
        DataWriter.write(self._field, self._values_name, [], 0, 'uint8')
        self._index_dataset = self._field[self._index_name]
        self._values_dataset = self._field[self._values_name]
        self._accumulated = 0


    def write_part(self, part):
        for s in part:
            evalue = s.encode()
            for v in evalue:
                self._raw_values[self._value_index] = v
                self._value_index += 1
                if self._value_index == self._chunksize:
                    DataWriter.write(self._field, self._values_name,
                                     self._raw_values, self._value_index)
                    self._value_index = 0
                self._accumulated += 1
            self._raw_indices[self._index_index] = self._accumulated
            self._index_index += 1
            if self._index_index == self._chunksize:
                if len(self._field['index']) == 0:
                    DataWriter.write(self._field, self._index_name, [0], 1)
                DataWriter.write(self._field, self._index_name,
                                 self._raw_indices, self._index_index)
                self._index_index = 0


    def write(self, part):
        self.write_part(part)
        self.complete()

    def complete(self):
        if self._value_index != 0:
            DataWriter.write(self._field, self._values_name,
                             self._raw_values, self._value_index)
            self._value_index = 0
        if self._index_index != 0:
            if len(self._field['index']) == 0:
                DataWriter.write(self._field, self._index_name, [0], 1)
            DataWriter.write(self._field, self._index_name,
                             self._raw_indices, self._index_index)
            self._index_index = 0



def base_field_contructor(session, group, name, timestamp=None, chunksize=None):
    """
    Constructor are for 1)create the field (hdf5 group), 2)add basic attributes like chunksize,
    timestamp, field type, and 3)add the dataset to the field (hdf5 group) under the name 'values'
    """
    if name in group:
        msg = "Field '{}' already exists in group '{}'"
        raise ValueError(msg.format(name, group))

    field = group.create_group(name)
    field.attrs['chunksize'] = session.chunksize if chunksize is None else chunksize
    field.attrs['timestamp'] = session.chunksize if chunksize is None else chunksize
    return field


def indexed_string_field_constructor(session, group, name, timestamp=None, chunksize=None):
    field = base_field_contructor(session, group, name, timestamp, chunksize)
    field.attrs['fieldtype'] = 'indexedstring'
    DataWriter.write(field, 'index', [], 0, 'int64')
    DataWriter.write(field, 'values', [], 0, 'uint8')


def fixed_string_field_constructor(session, group, name, length, timestamp=None, chunksize=None):
    field = base_field_contructor(session, group, name, timestamp, chunksize)
    field.attrs['fieldtype'] = 'fixedstring,{}'.format(length)
    field.attrs['strlen'] = length
    DataWriter.write(field, 'values', [], 0, "S{}".format(length))


def numeric_field_constructor(session, group, name, nformat, timestamp=None, chunksize=None):
    field = base_field_contructor(session, group, name, timestamp, chunksize)
    field.attrs['fieldtype'] = 'numeric,{}'.format(nformat)
    field.attrs['nformat'] = nformat
    DataWriter.write(field, 'values', [], 0, nformat)


def categorical_field_constructor(session, group, name, nformat, key,
                                  timestamp=None, chunksize=None):
    field = base_field_contructor(session, group, name, timestamp, chunksize)
    field.attrs['fieldtype'] = 'categorical,{}'.format(nformat)
    field.attrs['nformat'] = nformat
    DataWriter.write(field, 'values', [], 0, nformat)
    key_values = [v for k, v in key.items()]
    key_names = [k for k, v in key.items()]
    DataWriter.write(field, 'key_values', key_values, len(key_values), 'int8')
    DataWriter.write(field, 'key_names', key_names, len(key_names), h5py.special_dtype(vlen=str))


def timestamp_field_constructor(session, group, name, timestamp=None, chunksize=None):
    field = base_field_contructor(session, group, name, timestamp, chunksize)
    field.attrs['fieldtype'] = 'timestamp'
    DataWriter.write(field, 'values', [], 0, 'float64')


class IndexedStringField(HDF5Field):
    def __init__(self, session, group, name=None, write_enabled=False):
        super().__init__(session, group, name=name, write_enabled=write_enabled)
        self._session = session
        self._data_wrapper = None
        self._index_wrapper = None
        self._value_wrapper = None

    def writeable(self):
        return IndexedStringField(self._session, self._field, write_enabled=True)

    def create_like(self, group, name, timestamp=None):
        ts = self.timestamp if timestamp is None else timestamp
        return group.create_indexed_string(self._session, name, ts, self.chunksize)


    @property
    def indexed(self):
        return True

    @property
    def data(self):
        if self._data_wrapper is None:
            wrapper =\
                WriteableIndexedFieldArray if self._write_enabled else ReadOnlyIndexedFieldArray
            self._data_wrapper = wrapper(self._field, 'index', 'values')
        return self._data_wrapper

    @property
    def indices(self):
        if self._index_wrapper is None:
            wrapper = WriteableFieldArray if self._write_enabled else ReadOnlyFieldArray
            self._index_wrapper = wrapper(self._field, 'index')
        return self._index_wrapper

    @property
    def values(self):
        if self._value_wrapper is None:
            wrapper = WriteableFieldArray if self._write_enabled else ReadOnlyFieldArray
            self._value_wrapper = wrapper(self._field, 'values')
        return self._value_wrapper

    def __len__(self):
        return len(self.data)

    def get_spans(self):
        return ops._get_spans_for_index_string_field(self.indices[:], self.values[:])

    def apply_filter(self,filter_to_apply,dstfld=None):
        """
        Apply a filter (array of boolean) to the field, return itself if destination field (detfld) is not set.
        """
        dest_indices, dest_values = \
            ops.apply_filter_to_index_values(filter_to_apply,
                                             self.indices[:], self.values[:])

        dstfld = self if dstfld is None else dstfld
        if not dstfld._write_enabled:
            dstfld = dstfld.writeable()
        if len(dstfld.indices) == len(dest_indices):
            dstfld.indices[:] = dest_indices
        else:
            dstfld.indices.clear()
            dstfld.indices.write(dest_indices)
        if len(dstfld.values) == len(dest_values):
            dstfld.values[:]=dest_values
        else:
            dstfld.values.clear()
            dstfld.values.write(dest_values)
        return dstfld

    def apply_index(self,index_to_apply,dstfld=None):
        """
        Reindex the current field, return itself if destination field is not set.
        """
        dest_indices, dest_values = \
            ops.apply_indices_to_index_values(index_to_apply,
                                              self.indices[:], self.values[:])
        dstfld = self if dstfld is None else dstfld
        if not dstfld._write_enabled:
            dstfld = dstfld.writeable()
        if len(dstfld.indices) == len(dest_indices):
            dstfld.indices[:] = dest_indices
        else:
            dstfld.indices.clear()
            dstfld.indices.write(dest_indices)
        if len(dstfld.values) == len(dest_values):
            dstfld.values[:] = dest_values
        else:
            dstfld.values.clear()
            dstfld.values.write(dest_values)
        return dstfld


class FixedStringField(HDF5Field):
    def __init__(self, session, group, name=None, write_enabled=False):
        super().__init__(session, group, name=name, write_enabled=write_enabled)

    def writeable(self):
        return FixedStringField(self._session, self._field, write_enabled=True)

    def create_like(self, group, name, timestamp=None):
        ts = self.timestamp if timestamp is None else timestamp
        length = self._field.attrs['strlen']
        return group.create_fixed_string(self._session,name,length,ts,self.chunksize)

    @property
    def data(self):
        if self._value_wrapper is None:
            if self._write_enabled:
                self._value_wrapper = WriteableFieldArray(self._field, 'values')
            else:
                self._value_wrapper = ReadOnlyFieldArray(self._field, 'values')
        return self._value_wrapper

    def __len__(self):
        return len(self.data)

    def get_spans(self):
        return ops.get_spans_for_field(self.data[:])

    def apply_filter(self, filter_to_apply, dstfld=None):
        array = self.data[:]
        result = array[filter_to_apply]
        dstfld = self if dstfld is None else dstfld
        if not dstfld._write_enabled:
            dstfld = dstfld.writeable()
        if len(dstfld.data) == len(result):
            dstfld.data[:] = result
        else:
            dstfld.data.clear()
            dstfld.data.write(result)
        return dstfld


    def apply_index(self, index_to_apply, dstfld=None):
        array = self.data[:]
        result = array[index_to_apply]
        dstfld = self if dstfld is None else dstfld
        if not dstfld._write_enabled:
            dstfld = dstfld.writeable()
        if len(dstfld.data) == len(result):
            dstfld.data[:] = result
        else:
            dstfld.data.clear()
            dstfld.data.write(result)
        return dstfld


class NumericField(HDF5Field):
    def __init__(self, session, group, name=None, write_enabled=False):
        super().__init__(session, group, name=name, write_enabled=write_enabled)

    def writeable(self):
        return NumericField(self._session, self._field, write_enabled=True)

    def create_like(self, group, name, timestamp=None):
        ts = self.timestamp if timestamp is None else timestamp
        nformat = self._field.attrs['nformat']
        return group.create_numeric(self._session,name,nformat,ts,self.chunksize)

    @property
    def data(self):
        if self._value_wrapper is None:
            if self._write_enabled:
                self._value_wrapper = WriteableFieldArray(self._field, 'values')
            else:
                self._value_wrapper = ReadOnlyFieldArray(self._field, 'values')
        return self._value_wrapper

    def __len__(self):
        return len(self.data)

    def get_spans(self):
        return ops.get_spans_for_field(self.data[:])

    def apply_filter(self, filter_to_apply, dstfld=None):
        array = self.data[:]
        result = array[filter_to_apply]
        dstfld = self if dstfld is None else dstfld
        if not dstfld._write_enabled:
            dstfld = dstfld.writeable()
        if len(dstfld.data) == len(result):
            dstfld.data[:] = result
        else:
            dstfld.data.clear()
            dstfld.data.write(result)
        return dstfld

    def apply_index(self, index_to_apply, dstfld=None):
        array = self.data[:]
        result = array[index_to_apply]
        dstfld = self if dstfld is None else dstfld
        if not dstfld._write_enabled:
            dstfld = dstfld.writeable()
        if len(dstfld.data) == len(result):
            dstfld.data[:] = result
        else:
            dstfld.data.clear()
            dstfld.data.write(result)
        return dstfld

class CategoricalField(HDF5Field):
    def __init__(self, session, group,
                 name=None, write_enabled=False):
        super().__init__(session, group, name=name, write_enabled=write_enabled)

    def writeable(self):
        return CategoricalField(self._session, self._field, write_enabled=True)

    def create_like(self, group, name, timestamp=None):
        ts = self.timestamp if timestamp is None else timestamp
        nformat = self._field.attrs['nformat'] if 'nformat' in self._field.attrs else 'int8'
        keys = {v: k for k, v in self.keys.items()}
        return group.create_categorical(self._session,name,nformat,keys,ts,self.chunksize)

    @property
    def data(self):
        if self._value_wrapper is None:
            if self._write_enabled:
                self._value_wrapper = WriteableFieldArray(self._field, 'values')
            else:
                self._value_wrapper = ReadOnlyFieldArray(self._field, 'values')
        return self._value_wrapper

    def __len__(self):
        return len(self.data)

    def get_spans(self):
        return ops.get_spans_for_field(self.data[:])

    # Note: key is presented as value: str, even though the dictionary must be presented
    # as str: value
    @property
    def keys(self):
        kv = self._field['key_values']
        kn = self._field['key_names']
        keys = dict(zip(kv, kn))
        return keys

    def get_spans(self):
        return ops.get_spans_for_field(self.data[:])

    def apply_filter(self, filter_to_apply, dstfld=None):
        array = self.data[:]
        result = array[filter_to_apply]
        dstfld = self if dstfld is None else dstfld
        if not dstfld._write_enabled:
            dstfld = dstfld.writeable()
        if len(dstfld.data) == len(result):
            dstfld.data[:] = result
        else:
            dstfld.data.clear()
            dstfld.data.write(result)
        return dstfld

    def apply_index(self, index_to_apply, dstfld=None):
        array = self.data[:]
        result = array[index_to_apply]
        dstfld = self if dstfld is None else dstfld
        if not dstfld._write_enabled:
            dstfld = dstfld.writeable()
        if len(dstfld.data) == len(result):
            dstfld.data[:] = result
        else:
            dstfld.data.clear()
            dstfld.data.write(result)
        return dstfld

class TimestampField(HDF5Field):
    def __init__(self, session, group, name=None, write_enabled=False):
        super().__init__(session, group, name=name, write_enabled=write_enabled)

    def writeable(self):
        return TimestampField(self._session, self._field, write_enabled=True)

    def create_like(self, group, name, timestamp=None):
        ts = self.timestamp if timestamp is None else timestamp
        return group.create_timestamp(self._session, name, ts, self.chunksize)

    @property
    def data(self):
        if self._value_wrapper is None:
            if self._write_enabled:
                self._value_wrapper = WriteableFieldArray(self._field, 'values')
            else:
                self._value_wrapper = ReadOnlyFieldArray(self._field, 'values')
        return self._value_wrapper

    def __len__(self):
        return len(self.data)

    def get_spans(self):
        return ops.get_spans_for_field(self.data[:])

    def apply_filter(self, filter_to_apply, dstfld=None):
        array = self.data[:]
        result = array[filter_to_apply]
        dstfld = self if dstfld is None else dstfld
        if not dstfld._write_enabled:
            dstfld = dstfld.writeable()
        if len(dstfld.data) == len(result):
            dstfld.data[:] = result
        else:
            dstfld.data.clear()
            dstfld.data.write(result)
        return dstfld

    def apply_index(self, index_to_apply, dstfld=None):
        array = self.data[:]
        result = array[index_to_apply]
        dstfld = self if dstfld is None else dstfld
        if not dstfld._write_enabled:
            dstfld = dstfld.writeable()
        if len(dstfld.data) == len(result):
            dstfld.data[:] = result
        else:
            dstfld.data.clear()
            dstfld.data.write(result)
        return dstfld



class IndexedStringImporter:
    def __init__(self, session, group, name, timestamp=None, chunksize=None):
        self._field=group.create_indexed_string(session,name,timestamp,chunksize)

    def chunk_factory(self, length):
        return [None] * length

    def write_part(self, values):
        self._field.data.write_part(values)

    def complete(self):
        self._field.data.complete()

    def write(self, values):
        self.write_part(values)
        self.complete()


class FixedStringImporter:
    def __init__(self, session, group, name, length, timestamp=None, chunksize=None):
        self._field=group.create_fixed_string(session,name,length,timestamp,chunksize)

    def chunk_factory(self, length):
        return np.zeros(length, dtype=self._field.data.dtype)

    def write_part(self, values):
        self._field.data.write_part(values)

    def complete(self):
        self._field.data.complete()

    def write(self, values):
        self.write_part(values)
        self.complete()


class NumericImporter:
    def __init__(self, session, group, name, dtype, parser, timestamp=None, chunksize=None):
        filter_name = '{}_valid'.format(name)
        self._field=group.create_numeric(session,name,dtype, timestamp, chunksize)
        self._filter_field=group.create_numeric(session,filter_name, 'bool',timestamp, chunksize)
        chunksize = session.chunksize if chunksize is None else chunksize
        self._parser = parser
        self._values = np.zeros(chunksize, dtype=self._field.data.dtype)
        self._filter_values = np.zeros(chunksize, dtype='bool')

    def chunk_factory(self, length):
        # return np.zeros(length, dtype=self._field.data.dtype)
        return [None] * length

    def write_part(self, values):
        for i in range(len(values)):
            valid, value = self._parser(values[i])
            self._values[i] = value
            self._filter_values[i] = valid
        self._field.data.write_part(self._values[:len(values)])
        self._filter_field.data.write_part(self._filter_values[:len(values)])

    def complete(self):
        self._field.data.complete()
        self._filter_field.data.complete()

    def write(self, values):
        self.write_part(values)
        self.complete()


class CategoricalImporter:
    def __init__(self, session, group, name, value_type, keys, timestamp=None, chunksize=None):
        chunksize = session.chunksize if chunksize is None else chunksize
        self._field=group.create_categorical(session,name,value_type,keys,timestamp,chunksize)
        self._keys = keys
        self._dtype = value_type
        self._key_type = 'U{}'.format(max(len(k.encode()) for k in keys))
        # self._results = np.zeros(chunksize, dtype=value_type)

    def chunk_factory(self, length):
        # return np.zeros(length, dtype=self._key_type)
        return np.zeros(length, dtype=self._dtype)

    def write_part(self, values):
        self._field.data.write_part(values)

    def complete(self):
        self._field.data.complete()

    def write(self, values):
        self.write_part(values)
        self.complete()


class LeakyCategoricalImporter:
    def __init__(self, session, group, name, value_type, keys, out_of_range,
                 timestamp=None, chunksize=None):
        chunksize = session.chunksize if chunksize is None else chunksize
        out_of_range_name = '{}_{}'.format(name, out_of_range)
        self._field=group.create_categorical(session,name, value_type, keys,timestamp, chunksize)
        self._str_field =group.create_indexed_string(session,out_of_range_name,timestamp, chunksize)
        self._keys = keys
        self._dtype = value_type
        self._key_type = 'S{}'.format(max(len(k.encode()) for k in keys))

        self._results = np.zeros(chunksize, dtype=value_type)
        self._strresult = [None] * chunksize

    def chunk_factory(self, length):
        return [None] * length

    def write_part(self, values):
        keys = self._keys
        results = self._results
        strresults = self._strresult
        for i in range(len(values)):
            value = keys.get(values[i], -1)
            if value == -1:
                strresults[i] = values[i]
            else:
                strresults[i] = ''
            results[i] = value
            # results = keys[values[i]]
        if len(values) != len(results):
            self._field.data.write_part(results[:len(values)])
            self._str_field.data.write_part(strresults[:len(values)])
        else:
            self._field.data.write_part(results)
            self._str_field.data.write_part(strresults)

    def complete(self):
        self._field.data.complete()
        self._str_field.data.complete()

    def write(self, values):
        self.write_part(values)
        self.complete()


class DateTimeImporter:
    def __init__(self, session, group, name,
                 optional=False, write_days=False, timestamp=None, chunksize=None):
        chunksize = session.chunksize if chunksize is None else chunksize
        self._field =group.create_timestamp(session,name, timestamp, chunksize)
        self._results = np.zeros(chunksize , dtype='float64')
        self._optional = optional

        if optional is True:
            filter_name = '{}_set'.format(name)
            numeric_field_constructor(session, group, filter_name, 'bool',
                                      timestamp, chunksize)
            self._filter_field = NumericField(session, group, filter_name, write_enabled=True)

    def chunk_factory(self, length):
        return np.zeros(length, dtype='U32')

    def write_part(self, values):
        results = self._results

        for i, v in enumerate(values):
            if len(v) == 32:
                ts = datetime.strptime(v, '%Y-%m-%d %H:%M:%S.%f%z')
                results[i] = ts.timestamp()
            elif len(v) == 25:
                ts = datetime.strptime(v, '%Y-%m-%d %H:%M:%S%z')
                results[i] = ts.timestamp()
            else:
                if self._optional is True and len(v) == 0:
                    results[i] = np.nan
                else:
                    msg = "Date field '{}' has unexpected format '{}'"
                    raise ValueError(msg.format(self._field, v))

        self._field.data.write_part(results)

    def complete(self):
        self._field.data.complete()

    def write(self, values):
        self.write_part(values)
        self.complete()


class DateImporter:
    def __init__(self, session, group, name,
                 optional=False, timestamp=None, chunksize=None):
        self._field=group.create_timestamp(session,name, timestamp, chunksize)
        self._results = np.zeros(chunksize, dtype='float64')

        if optional is True:
            filter_name = '{}_set'.format(name)
            numeric_field_constructor(session, group, filter_name, 'bool',
                                      timestamp, chunksize)
            self._filter_field = NumericField(session, group, filter_name, write_enabled=True)

    def chunk_factory(self, length):
        return np.zeros(length, dtype='U10')

    def write_part(self, values):
        timestamps = np.zeros(len(values), dtype=np.float64)
        for i in range(len(values)):
            value = values[i]
            if value == '':
                timestamps[i] = np.nan
            else:
                ts = datetime.strptime(value, '%Y-%m-%d')
                timestamps[i] = ts.timestamp()
        self._field.data.write_part(timestamps)

    def complete(self):
        self._field.data.complete()

    def write(self, values):
        self.write_part(values)
        self.complete()
