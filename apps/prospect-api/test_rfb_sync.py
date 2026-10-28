import tempfile
import unittest
from pathlib import Path
import httpx
from rfb_sync import download, listing, BASE

class SyncTests(unittest.TestCase):
    def test_short_download_not_published(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'a.zip'
            with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=b'abc'))) as c:
                with self.assertRaises(ValueError): download(c,BASE+'a.zip',path,5)
            self.assertFalse(path.exists())
            self.assertFalse(path.with_suffix('.part').exists())
    def test_download(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'a.zip'
            with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=b'abc'))) as c:
                download(c,BASE+'a.zip',path,3)
            self.assertEqual(path.read_bytes(),b'abc')
    def test_external_host_rejected(self):
        xml=b'<d:multistatus xmlns:d="DAV:"><d:response><d:href>https://evil.invalid/a</d:href></d:response></d:multistatus>'
        with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(207,content=xml))) as c:
            with self.assertRaises(ValueError): listing(c,BASE)
