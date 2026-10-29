import unittest
from datetime import date
from rfb_import import parse_row

class RFBTests(unittest.TestCase):
    def row(self):
        r=['']*30
        r[:3]=['12345678','0001','90']
        r[5]='02'; r[10]='20261001'; r[19]='SC'; r[20]='8179'; r[27]='TEST@example.com'
        return r
    def parse(self,r):
        return parse_row(r,date(2026,10,1),date(2026,10,31),'fixture')
    def test_email_and_cnpj(self):
        x=self.parse(self.row())
        self.assertEqual(x['cnpj'],'12345678000190')
        self.assertEqual(x['email'],'test@example.com')
        self.assertNotIn('contact_verified',x)
    def test_inactive(self):
        r=self.row(); r[5]='08'; self.assertIsNone(self.parse(r))
    def test_date_filter(self):
        r=self.row(); r[10]='20250901'; self.assertIsNone(self.parse(r))
    def test_invalid_email(self):
        r=self.row(); r[27]='bad\nBcc: other'; self.assertIsNone(self.parse(r)['email'])
    def test_layout(self):
        with self.assertRaises(ValueError): self.parse(['bad'])
