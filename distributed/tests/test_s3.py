from contextlib import contextmanager

import boto3
from dask.imperative import Value
from distributed import Executor
from distributed.executor import _wait
from distributed.s3 import read_bytes, get_list_of_summary_objects, read_content_from_keys
from distributed.utils import get_ip
from distributed.utils_test import gen_cluster

ip = get_ip()
test_bucket_name = 'distributed-test'


@contextmanager
def make_s3(bucket_name):
    s3 = boto3.resource('s3')
    bucket = s3.create_bucket(Bucket=bucket_name)

    try:
        yield bucket
    finally:
        for key in bucket.objects.all():
            key.delete()
        bucket.delete()


def test_get_list_of_summary_objects():
    with make_s3(test_bucket_name) as bucket:
        data = b'a' * int(10)
        fn_1 = 'tmp/test/file1'
        fn_2 = 'tmp/test/file2'

        bucket.put_object(Key=fn_1, Body=data)
        bucket.put_object(Key=fn_2, Body=data)

        L = get_list_of_summary_objects(test_bucket_name, prefix='tmp')

        assert len(L) == 2
        assert map(lambda o: o.key, L) == ['tmp/test/file1', 'tmp/test/file2']


def test_read_keys_from_bucket():
    with make_s3(test_bucket_name) as bucket:
        data = b'a' * int(10)
        fn_1 = 'tmp/test/file1'

        bucket.put_object(Key=fn_1, Body=data)

        file_contents = read_content_from_keys(test_bucket_name, fn_1)

        assert file_contents == data


def test_list_summary_object_with_prefix_and_delimiter():
    with make_s3(test_bucket_name) as bucket:
        data = b'a' * int(10)
        first_level_key = 'tmp/file1'
        deep_key = 'tmp/test/file2'
        deep_key_1 = 'tmp/test/file1'
        top_level_key = 'top-level'

        bucket.put_object(Key=first_level_key, Body=data)
        bucket.put_object(Key=top_level_key, Body=data)
        bucket.put_object(Key=deep_key, Body=data)
        bucket.put_object(Key=deep_key_1, Body=data)

        keys = get_list_of_summary_objects(test_bucket_name, delimiter='/')

        assert len(keys) == 1
        assert keys[0].key == u'top-level'

        keys = get_list_of_summary_objects(test_bucket_name, delimiter='/', prefix='tmp/test/')

        assert len(keys) == 2
        assert map(lambda o: o.key, keys) == [u'tmp/test/file1', u'tmp/test/file2']

        keys = get_list_of_summary_objects(test_bucket_name, prefix='tmp/')

        assert len(keys) == 3
        assert map(lambda o: o.key, keys) == [u'tmp/file1', u'tmp/test/file1', u'tmp/test/file2']


@gen_cluster([(ip, 1), (ip, 2)], timeout=60)
def test_read_bytes(s, a, b):
    with make_s3(test_bucket_name) as bucket:
        data = b'a'

        for i in range(3):
            for j in range(2):
                fn = 'tmp/test/data-%d/file-%d.csv' % (i, j)
                bucket.put_object(Key=fn, Body=data)

        e = Executor((s.ip, s.port), start=False)
        yield e._start()
        futures = read_bytes(test_bucket_name, prefix='tmp/test/data')
        assert len(futures) == 6
        results = yield e._gather(futures)
        assert len(results) == 6
        assert all(x == b'a' for x in results)


@gen_cluster([(ip, 1), (ip, 2)], timeout=60)
def test_read_bytes_lazy(s, a, b):
    with make_s3(test_bucket_name) as bucket:
        data = b'a'

        for i in range(3):
            for j in range(2):
                fn = 'tmp/test/data-%d/file-%d.csv' % (i, j)
                bucket.put_object(Key=fn, Body=data)

        e = Executor((s.ip, s.port), start=False)
        yield e._start()
        values = read_bytes(test_bucket_name, prefix='tmp/test/data', lazy=True)
        assert all(isinstance(v, Value) for v in values)
        results = e.compute(*values, sync=False)
        yield _wait(results)
        results = yield e._gather(results)
        assert len(results) == 6
        assert all(x == b'a' for x in results)
