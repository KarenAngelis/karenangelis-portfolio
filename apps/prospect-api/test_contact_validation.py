import unittest
from types import SimpleNamespace
import dns.resolver
import dns.exception
from contact_validation import check

class ContactTests(unittest.TestCase):
    def test_valid_mx(self):
        self.assertEqual(check('a@example.com',lambda *a,**k:[SimpleNamespace(exchange='mx.example.com.')]),'mx_ok')
    def test_null_mx(self):
        self.assertEqual(check('a@example.com',lambda *a,**k:[SimpleNamespace(exchange='.')]),'no_mail')
    def test_invalid_never_resolves(self):
        self.assertEqual(check('bad\nemail',lambda *a,**k:self.fail()),'invalid')
    def test_temporary(self):
        def timeout(*a,**k): raise dns.exception.Timeout()
        self.assertEqual(check('a@example.com',timeout),'temporary')
    def test_nxdomain(self):
        def absent(*a,**k): raise dns.resolver.NXDOMAIN()
        self.assertEqual(check('a@example.com',absent),'no_mail')
