# Copyright 2020 KCL-BMEIS - King's College London
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from typing import Optional, Sequence, Tuple, Union
import numpy as np
import pandas as pd

from exetera.core.abstract_types import Dataset, DataFrame
from exetera.core import fields as fld
from exetera.core import operations as ops
import h5py


class HDF5DataFrame(DataFrame):
    """
    DataFrame that utilising HDF5 file as storage.
    """
    def __init__(self,
                 dataset: Dataset,
                 name: str,
                 h5group: h5py.Group):
        """
        Create a Dataframe object, that contains a dictionary of fields. User should always create dataframe by
        dataset.create_dataframe, otherwise the dataframe is not stored in the dataset.

        :param name: name of the dataframe.
        :param dataset: a dataset object, where this dataframe belongs to.
        :param h5group: the h5group object to store the fields. If the h5group is not empty, acquire data from h5group
        object directly. The h5group structure is h5group<-h5group-dataset structure, the later group has a
        'fieldtype' attribute and only one dataset named 'values'. So that the structure is mapped to
        Dataframe<-Field-Field.data automatically.
        :param dataframe: optional - replicate data from another dictionary of (name:str, field: Field).
        """

        self.name = name
        self._columns = dict()
        self._dataset = dataset
        self._h5group = h5group

        for subg in h5group.keys():
            self._columns[subg] = dataset.session.get(h5group[subg])

    @property
    def columns(self):
        """
        The columns property interface. Columns is a dictionary to store the fields by (field_name, field_object).
        The field_name is field.name without prefix '/' and HDF5 group name.
        """
        return dict(self._columns)

    @property
    def dataset(self):
        """
        The dataset property interface.
        """
        return self._dataset

    @property
    def h5group(self):
        """
        The h5group property interface, used to handle underlying storage.
        """
        return self._h5group

    def add(self, field):
        """
        Add a field to this dataframe as well as the HDF5 Group.

        :param field: field to add to this dataframe, copy the underlying dataset
        """
        dname = field.name[field.name.index('/', 1)+1:]
        nfield = field.create_like(self, dname)
        if field.indexed:
            nfield.indices.write(field.indices[:])
            nfield.values.write(field.values[:])
        else:
            nfield.data.write(field.data[:])
        self._columns[dname] = nfield

    def drop(self, name):
        del self._columns[name]
        del self._h5group[name]

    def create_group(self, name):
        """
        Create a group object in HDF5 file for field to use. Please note, this function is for
        backwards compatibility with older scripts and should not be used in the general case.

        :param name: the name of the group and field
        :return: a hdf5 group object
        """
        self._h5group.create_group(name)
        return self._h5group[name]

    def create_indexed_string(self, name, timestamp=None, chunksize=None):
        """
        Create a indexed string type field.
        """
        fld.indexed_string_field_constructor(self._dataset.session, self, name,
                                             timestamp, chunksize)
        field = fld.IndexedStringField(self._dataset.session, self._h5group[name], self, name,
                                       write_enabled=True)
        self._columns[name] = field
        return self._columns[name]

    def create_fixed_string(self, name, length, timestamp=None, chunksize=None):
        """
        Create a fixed string type field.
        """
        fld.fixed_string_field_constructor(self._dataset.session, self, name,
                                           length, timestamp, chunksize)
        field = fld.FixedStringField(self._dataset.session, self._h5group[name], self, name,
                                     write_enabled=True)
        self._columns[name] = field
        return self._columns[name]

    def create_numeric(self, name, nformat, timestamp=None, chunksize=None):
        """
        Create a numeric type field.
        """
        fld.numeric_field_constructor(self._dataset.session, self, name,
                                      nformat, timestamp, chunksize)
        field = fld.NumericField(self._dataset.session, self._h5group[name], self, name,
                                 write_enabled=True)
        self._columns[name] = field
        return self._columns[name]

    def create_categorical(self, name, nformat, key, timestamp=None, chunksize=None):
        """
        Create a categorical type field.
        """
        fld.categorical_field_constructor(self._dataset.session, self, name, nformat, key,
                                          timestamp, chunksize)
        field = fld.CategoricalField(self._dataset.session, self._h5group[name], self, name,
                                     write_enabled=True)
        self._columns[name] = field
        return self._columns[name]

    def create_timestamp(self, name, timestamp=None, chunksize=None):
        """
        Create a timestamp type field.
        """
        fld.timestamp_field_constructor(self._dataset.session, self, name,
                                        timestamp, chunksize)
        field = fld.TimestampField(self._dataset.session, self._h5group[name], self, name,
                                   write_enabled=True)
        self._columns[name] = field
        return self._columns[name]

    def __contains__(self, name):
        """
        check if dataframe contains a field, by the field name

        :param name: the name of the field to check,return a bool
        """
        if not isinstance(name, str):
            raise TypeError("The name must be a str object.")
        else:
            return self._columns.__contains__(name)

    def contains_field(self, field):
        """
        check if dataframe contains a field by the field object

        :param field: the filed object to check, return a tuple(bool,str). The str is the name stored in dataframe.
        """
        if not isinstance(field, fld.Field):
            raise TypeError("The field must be a Field object")
        else:
            for v in self._columns.values():
                if id(field) == id(v):
                    return True
            return False

    def __getitem__(self, name):
        """
        Get a field stored by the field name.

        :param name: The name of field to get.
        """
        if not isinstance(name, str):
            raise TypeError("The name must be of type str but is of type '{}'".format(str))
        elif not self.__contains__(name):
            raise ValueError("There is no field named '{}' in this dataframe".format(name))
        else:
            return self._columns[name]

    def get_field(self, name):
        """
        Get a field stored by the field name.

        :param name: The name of field to get.
        """
        return self.__getitem__(name)

    # def get_name(self, field):
    #     """
    #     Get the name of the field in dataframe.
    #     """
    #     if not isinstance(field, fld.Field):
    #         raise TypeError("The field argument must be a Field object.")
    #     for name, v in self._columns.items():
    #         if id(field) == id(v):
    #             return name
    #     return None

    def __setitem__(self, name, field):
        if not isinstance(name, str):
            raise TypeError("The name must be of type str but is of type '{}'".format(str))
        if not isinstance(field, fld.Field):
            raise TypeError("The field must be a Field object.")
        nfield = field.create_like(self, name)
        if field.indexed:
            nfield.indices.write(field.indices[:])
            nfield.values.write(field.values[:])
        else:
            nfield.data.write(field.data[:])
        self._columns[name] = nfield

    def __delitem__(self, name):
        if not self.__contains__(name=name):
            raise ValueError("There is no field named '{}' in this dataframe".format(name))
        else:
            del self._h5group[name]
            del self._columns[name]

    def delete_field(self, field):
        """
        Remove field from dataframe by field.

        :param field: The field to delete from this dataframe.
        """
        if field.dataframe != self:
            raise ValueError("This field is owned by a different dataframe")
        name = field.name
        if name is None:
            raise ValueError("This dataframe does not contain the field to delete.")
        else:
            self.__delitem__(name)

    def keys(self):
        return self._columns.keys()

    def values(self):
        return self._columns.values()

    def items(self):
        return self._columns.items()

    def __iter__(self):
        return iter(self._columns)

    def __next__(self):
        return next(self._columns)

    def __len__(self):
        return len(self._columns)

    def get_spans(self):
        """
        Return the name and spans of each field as a dictionary.

        :returns: A dictionary of (field_name, field_spans).
        """
        spans = {}
        for name, field in self._columns.items():
            spans[name] = field.get_spans()
        return spans

    def apply_filter(self, filter_to_apply, ddf=None):
        """
        Apply the filter to all the fields in this dataframe, return a dataframe with filtered fields.

        :param filter_to_apply: the filter to be applied to the source field, an array of boolean
        :param ddf: optional- the destination data frame
        :returns: a dataframe contains all the fields filterd, self if ddf is not set
        """
        if ddf is not None:
            if not isinstance(ddf, DataFrame):
                raise TypeError("The destination object must be an instance of DataFrame.")
            for name, field in self._columns.items():
                newfld = field.create_like(ddf, name)
                field.apply_filter(filter_to_apply, target=newfld)
            return ddf
        else:
            for field in self._columns.values():
                field.apply_filter(filter_to_apply, in_place=True)
            return self

    def apply_index(self, index_to_apply, ddf=None):
        """
        Apply the index to all the fields in this dataframe, return a dataframe with indexed fields.

        :param index_to_apply: the index to be applied to the fields, an ndarray of integers
        :param ddf: optional- the destination data frame
        :returns: a dataframe contains all the fields re-indexed, self if ddf is not set
        """
        if ddf is not None:
            if not isinstance(ddf, DataFrame):
                raise TypeError("The destination object must be an instance of DataFrame.")
            for name, field in self._columns.items():
                newfld = field.create_like(ddf, name)
                field.apply_index(index_to_apply, target=newfld)
            return ddf
        else:
            for field in self._columns.values():
                field.apply_index(index_to_apply, in_place=True)
            return self


def copy(field: fld.Field, dataframe: DataFrame, name: str):
    """
    Copy a field to another dataframe as well as underlying dataset.

    :param field: The source field to copy.
    :param dataframe: The destination dataframe to copy to.
    :param name: The name of field under destination dataframe.
    """
    dfield = field.create_like(dataframe, name)
    if field.indexed:
        dfield.indices.write(field.indices[:])
        dfield.values.write(field.values[:])
    else:
        dfield.data.write(field.data[:])
    dataframe.columns[name] = dfield


def move(field: fld.Field, dest_df: DataFrame, name: str):
    """
    Move a field to another dataframe as well as underlying dataset.

    :param src_df: The source dataframe where the field is located.
    :param field: The field to move.
    :param dest_df: The destination dataframe to move to.
    :param name: The name of field under destination dataframe.
    """
    copy(field, dest_df, name)
    field.dataframe.drop(field.name)


def merge(left: DataFrame,
          right: DataFrame,
          dest: DataFrame,
          left_on: Union[str, fld.Field],
          right_on: Union[str, fld.Field],
          left_fields: Optional[Sequence[str]] = None,
          right_fields: Optional[Sequence[str]] = None,
          left_suffix: str = '_l',
          right_suffix: str = '_r',
          how='left'):

    left_on_ = left[left_on] if isinstance(left_on, str) else left_on
    right_on_ = right[right_on] if isinstance(right_on, str) else right_on
    if len(left_on_.data) < (2 << 30) and len(right_on_.data) < (2 << 30):
        index_dtype = np.int32
    else:
        index_dtype = np.int64

    # create the merging dataframes, using only the fields involved in the merge
    l_df = pd.DataFrame({'l_k': left_on_.data[:],
                         'l_i': np.arange(len(left_on_.data), dtype=index_dtype)})
    r_df = pd.DataFrame({'r_k': right_on_.data[:],
                         'r_i': np.arange(len(right_on_.data), dtype=index_dtype)})
    df = pd.merge(left=l_df, right=r_df, left_on='l_k', right_on='r_k', how=how)
    l_to_d_map = df['l_i'].to_numpy(dtype=np.int32)
    l_to_d_filt = np.logical_not(df['l_i'].isnull()).to_numpy()
    r_to_d_map = df['r_i'].to_numpy(dtype=np.int32)
    r_to_d_filt = np.logical_not(df['r_i'].isnull()).to_numpy()

    # perform the mapping
    left_fields_ = left.keys() if left_fields is None else left_fields
    right_fields_ = right.keys() if right_fields is None else right_fields
    for f in right_fields_:
        dest_f = f
        if f in left_fields_:
            dest_f += right_suffix
        r = right[f]
        d = r.create_like(dest, dest_f)
        if r.indexed:
            i, v = ops.safe_map_indexed_values(r.indices[:], r.values[:], r_to_d_map, r_to_d_filt)
            d.indices.write(i)
            d.values.write(v)
        else:
            v = ops.safe_map_values(r.data[:], r_to_d_map, r_to_d_filt)
            d.data.write(v)
    if np.all(r_to_d_filt) == False:
        d = dest.create_numeric('valid'+right_suffix, 'bool')
        d.data.write(r_to_d_filt)

    for f in left_fields_:
        dest_f = f
        if f in right_fields_:
            dest_f += left_suffix
        l = left[f]
        d = l.create_like(dest, dest_f)
        if l.indexed:
            i, v = ops.safe_map_indexed_values(l.indices[:], l.values[:], l_to_d_map, l_to_d_filt)
            d.indices.write(i)
            d.values.write(v)
        else:
            v = ops.safe_map_values(l.data[:], l_to_d_map, l_to_d_filt)
            d.data.write(v)
    if np.all(l_to_d_filt) == False:
        d = dest.create_numeric('valid'+left_suffix, 'bool')
        d.data.write(l_to_d_filt)
