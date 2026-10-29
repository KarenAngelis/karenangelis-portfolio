import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
import httpx
import oauth_service as oauth


class OAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patch = patch.object(oauth, 'SECRET_DIR', self.root)
        self.patch.start()
        oauth.write_private(self.root / 'client.json', {'client_id':'test','client_secret':'private'})

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def query(self):
        url = oauth.authorize()
        state = parse_qs(urlsplit(url).query)['state']
        return {'state': state, 'code':['test-code']}

    def transport(self, email=oauth.ACCOUNT, scopes=None):
        def respond(request):
            if request.url.path == '/token':
                return httpx.Response(200,json={'access_token':'access','refresh_token':'refresh',
                    'scope':' '.join(oauth.SCOPES if scopes is None else scopes)})
            return httpx.Response(200,json={'email':email,'email_verified':True})
        return httpx.Client(transport=httpx.MockTransport(respond))

    def test_wrong_state_never_exchanges_token(self):
        query = self.query(); query['state']=['wrong']
        with self.assertRaises(ValueError): oauth.complete(query, self.transport())
        self.assertFalse((self.root/'token.json').exists())

    def test_expired_state_fails(self):
        query = self.query()
        pending = json.loads((self.root/'pending.json').read_text())
        pending['expires']=time.time()-1
        oauth.write_private(self.root/'pending.json',pending)
        with self.assertRaises(ValueError): oauth.complete(query,self.transport())

    def test_wrong_account_is_not_saved(self):
        with self.assertRaises(ValueError): oauth.complete(self.query(),self.transport('other@example.com'))
        self.assertFalse((self.root/'token.json').exists())

    def test_missing_permissions_is_not_saved(self):
        with self.assertRaises(ValueError): oauth.complete(self.query(),self.transport(scopes=['openid']))

    def test_success_private_storage_and_no_replay(self):
        query=self.query()
        oauth.complete(query,self.transport())
        self.assertEqual((self.root/'token.json').stat().st_mode & 0o777,0o600)
        self.assertEqual(json.loads((self.root/'token.json').read_text())['email'],oauth.ACCOUNT)
        with self.assertRaises(FileNotFoundError): oauth.complete(query,self.transport())


if __name__ == '__main__': unittest.main()
