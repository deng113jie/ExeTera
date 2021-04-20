import unittest
from io import BytesIO
import numpy as np

from exetera.core import session
from exetera.core import fields
from exetera.core import persistence as per
from exetera.core import dataframe


class TestDataFrame(unittest.TestCase):

    def test_dataframe_init(self):
        bio = BytesIO()
        with session.Session() as s:
            dst = s.open_dataset(bio, 'w', 'dst')
            # init
            df = dst.create_dataframe('dst')
            self.assertTrue(isinstance(df, dataframe.DataFrame))
            numf = df.create_numeric('numf', 'uint32')
            df2 = dst.create_dataframe('dst2', dataframe=df)
            self.assertTrue(isinstance(df2, dataframe.DataFrame))

            # add & set & contains
            self.assertTrue('numf' in df)
            self.assertTrue('numf' in df2)
            cat = s.create_categorical(df2, 'cat', 'int8', {'a': 1, 'b': 2})
            self.assertFalse('cat' in df)
            self.assertFalse(df.contains_field(cat))
            df['cat'] = cat
            self.assertTrue('cat' in df)

            # list & get
            self.assertEqual(id(numf), id(df.get_field('numf')))
            self.assertEqual(id(numf), id(df['numf']))

            # list & iter
            dfit = iter(df)
            self.assertEqual('numf', next(dfit))
            self.assertEqual('cat', next(dfit))

            # del & del by field
            del df['numf']
            self.assertFalse('numf' in df)
            with self.assertRaises(ValueError, msg="This field is owned by a different dataframe"):
                df.delete_field(cat)
            self.assertFalse(df.contains_field(cat))

    def test_dataframe_create_numeric(self):
        bio = BytesIO()
        with session.Session() as s:
            dst = s.open_dataset(bio, 'r+', 'dst')
            df = dst.create_dataframe('dst')
            num = df.create_numeric('num', 'uint32')
            num.data.write([1, 2, 3, 4])
            self.assertEqual([1, 2, 3, 4], num.data[:].tolist())
            num2 = df.create_numeric('num2', 'uint32')
            num2.data.write([1, 2, 3, 4])

    def test_dataframe_create_numeric(self):
        bio = BytesIO()
        with session.Session() as s:
            np.random.seed(12345678)
            values = np.random.randint(low=0, high=1000000, size=100000000)
            dst = s.open_dataset(bio, 'r+', 'dst')
            df = dst.create_dataframe('dst')
            a = df.create_numeric('a','int32')
            a.data.write(values)

            total = np.sum(a.data[:])
            self.assertEqual(49997540637149, total)

            a.data[:] = a.data[:] * 2
            total = np.sum(a.data[:])
            self.assertEqual(99995081274298, total)

    def test_dataframe_create_categorical(self):
        bio = BytesIO()
        with session.Session() as s:
            np.random.seed(12345678)
            values = np.random.randint(low=0, high=3, size=100000000)
            dst = s.open_dataset(bio, 'r+', 'dst')
            hf = dst.create_dataframe('dst')
            a = hf.create_categorical('a', 'int8',
                                                 {'foo': 0, 'bar': 1, 'boo': 2})
            a.data.write(values)

            total = np.sum(a.data[:])
            self.assertEqual(99987985, total)

    def test_dataframe_create_fixed_string(self):
        bio = BytesIO()
        with session.Session() as s:
            dst = s.open_dataset(bio, 'r+', 'dst')
            hf = dst.create_dataframe('dst')
            np.random.seed(12345678)
            values = np.random.randint(low=0, high=4, size=1000000)
            svalues = [b''.join([b'x'] * v) for v in values]
            a = hf.create_fixed_string('a', 8)
            a.data.write(svalues)

            total = np.unique(a.data[:])
            self.assertListEqual([b'', b'x', b'xx', b'xxx'], total.tolist())

            a.data[:] = np.core.defchararray.add(a.data[:], b'y')
            self.assertListEqual(
                [b'xxxy', b'xxy', b'xxxy', b'y', b'xy', b'y', b'xxxy', b'xxxy', b'xy', b'y'],
                a.data[:10].tolist())


    def test_dataframe_create_indexed_string(self):
        bio = BytesIO()
        with session.Session() as s:
            dst = s.open_dataset(bio, 'r+', 'dst')
            hf = dst.create_dataframe('dst')
            np.random.seed(12345678)
            values = np.random.randint(low=0, high=4, size=200000)
            svalues = [''.join(['x'] * v) for v in values]
            a = hf.create_indexed_string('a', 8)
            a.data.write(svalues)

            total = np.unique(a.data[:])
            self.assertListEqual(['', 'x', 'xx', 'xxx'], total.tolist())

            strs = a.data[:]
            strs = [s + 'y' for s in strs]
            a.data.clear()
            a.data.write(strs)

            # print(strs[:10])
            self.assertListEqual(
                ['xxxy', 'xxy', 'xxxy', 'y', 'xy', 'y', 'xxxy', 'xxxy', 'xy', 'y'], strs[:10])
            # print(a.indices[:10])
            self.assertListEqual([0, 4, 7, 11, 12, 14, 15, 19, 23, 25],
                                 a.indices[:10].tolist())
            # print(a.values[:10])
            self.assertListEqual(
                [120, 120, 120, 121, 120, 120, 121, 120, 120, 120], a.values[:10].tolist())
            # print(a.data[:10])
            self.assertListEqual(
                ['xxxy', 'xxy', 'xxxy', 'y', 'xy', 'y', 'xxxy', 'xxxy', 'xy', 'y'], a.data[:10])


    def test_dataframe_create_mem_numeric(self):
        bio = BytesIO()
        with session.Session() as s:
            dst = s.open_dataset(bio, 'r+', 'dst')
            df = dst.create_dataframe('dst')
            num = df.create_numeric('num', 'uint32')
            num.data.write([1, 2, 3, 4])
            self.assertEqual([1, 2, 3, 4], num.data[:].tolist())
            num2 = df.create_numeric('num2', 'uint32')
            num2.data.write([1, 2, 3, 4])

            df['num3'] = num + num2
            self.assertEqual([2, 4, 6, 8], df['num3'].data[:].tolist())
            df['num4'] = num - np.array([1, 2, 3, 4])
            self.assertEqual([0, 0, 0, 0], df['num4'].data[:].tolist())
            df['num5'] = num * np.array([1, 2, 3, 4])
            self.assertEqual([1, 4, 9, 16], df['num5'].data[:].tolist())
            df['num6'] = df['num5'] / np.array([1, 2, 3, 4])
            self.assertEqual([1, 2, 3, 4], df['num6'].data[:].tolist())
            df['num7'] = df['num'] & df['num2']
            self.assertEqual([1, 2, 3, 4], df['num7'].data[:].tolist())
            df['num8'] = df['num'] | df['num2']
            self.assertEqual([1, 2, 3, 4], df['num8'].data[:].tolist())
            df['num9'] = df['num'] ^ df['num2']
            self.assertEqual([0, 0, 0, 0], df['num9'].data[:].tolist())
            df['num10'] = df['num'] % df['num2']
            self.assertEqual([0, 0, 0, 0], df['num10'].data[:].tolist())


    def test_dataframe_create_mem_categorical(self):
        bio = BytesIO()
        with session.Session() as s:
            dst = s.open_dataset(bio, 'r+', 'dst')
            df = dst.create_dataframe('dst')
            cat1 = df.create_categorical('cat1','uint8',{'foo': 0, 'bar': 1, 'boo': 2})
            cat1.data.write([0, 1, 2, 0, 1, 2])

            cat2 = df.create_categorical('cat2','uint8',{'foo': 0, 'bar': 1, 'boo': 2})
            cat2.data.write([1, 2, 0, 1, 2, 0])

            df['r1'] = cat1 < cat2
            self.assertEqual([True, True, False, True, True, False], df['r1'].data[:].tolist())
            df['r2'] = cat1 <= cat2
            self.assertEqual([True, True, False, True, True, False], df['r2'].data[:].tolist())
            df['r3'] = cat1 == cat2
            self.assertEqual([False, False, False, False, False, False], df['r3'].data[:].tolist())
            df['r4'] = cat1 != cat2
            self.assertEqual([True, True, True, True, True, True], df['r4'].data[:].tolist())
            df['r5'] = cat1 > cat2
            self.assertEqual([False, False, True, False, False, True], df['r5'].data[:].tolist())
            df['r6'] = cat1 >= cat2
            self.assertEqual([False, False, True, False, False, True], df['r6'].data[:].tolist())

    def test_dataframe_static_methods(self):
        bio = BytesIO()
        with session.Session() as s:
            dst = s.open_dataset(bio, 'w', 'dst')
            df = dst.create_dataframe('dst')
            numf = s.create_numeric(df, 'numf', 'int32')
            numf.data.write([5, 4, 3, 2, 1])

            df2 = dst.create_dataframe('df2')
            dataframe.copy(numf, df2,'numf')
            self.assertListEqual([5, 4, 3, 2, 1], df2['numf'].data[:].tolist())
            df.drop('numf')
            self.assertTrue('numf' not in df)
            dataframe.move(df2['numf'], df, 'numf')
            self.assertTrue('numf' not in df2)
            self.assertListEqual([5, 4, 3, 2, 1], df['numf'].data[:].tolist())

    def test_dataframe_ops(self):
        bio = BytesIO()
        with session.Session() as s:
            dst = s.open_dataset(bio, 'w', 'dst')
            df = dst.create_dataframe('dst')
            numf = s.create_numeric(df, 'numf', 'int32')
            numf.data.write([5, 4, 3, 2, 1])

            fst = s.create_fixed_string(df, 'fst', 3)
            fst.data.write([b'e', b'd', b'c', b'b', b'a'])

            index = np.array([4, 3, 2, 1, 0])
            ddf = dst.create_dataframe('dst2')
            df.apply_index(index, ddf)
            self.assertEqual([1, 2, 3, 4, 5], ddf['numf'].data[:].tolist())
            self.assertEqual([b'a', b'b', b'c', b'd', b'e'], ddf['fst'].data[:].tolist())

            filter_to_apply = np.array([True, True, False, False, True])
            ddf = dst.create_dataframe('dst3')
            df.apply_filter(filter_to_apply, ddf)
            self.assertEqual([5, 4, 1], ddf['numf'].data[:].tolist())
            self.assertEqual([b'e', b'd', b'a'], ddf['fst'].data[:].tolist())


class TestDataFrameApplyFilter(unittest.TestCase):

    def test_apply_filter(self):

        src = np.array([1, 2, 3, 4, 5, 6, 7, 8], dtype='int32')
        filt = np.array([0, 1, 0, 1, 0, 1, 1, 0], dtype='bool')
        expected = src[filt].tolist()

        bio = BytesIO()
        with session.Session() as s:
            dst = s.open_dataset(bio, 'w', 'dst')
            df = dst.create_dataframe('df')
            numf = s.create_numeric(df, 'numf', 'int32')
            numf.data.write(src)
            df2 = dst.create_dataframe('df2')
            df2b = df.apply_filter(filt, df2)
            self.assertListEqual(expected, df2['numf'].data[:].tolist())
            self.assertListEqual(expected, df2b['numf'].data[:].tolist())
            self.assertListEqual(src.tolist(), df['numf'].data[:].tolist())

            df.apply_filter(filt)
            self.assertListEqual(expected, df['numf'].data[:].tolist())
