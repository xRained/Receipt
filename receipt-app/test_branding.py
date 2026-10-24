import unittest
import app as module


class BrandingTests(unittest.TestCase):
    def test_active_interface_is_english_and_branded(self):
        page=module.app.test_client().get('/').get_data(as_text=True)
        self.assertIn('Jolyn TAE',page)
        self.assertIn('Tangaw, Atiris, Esmiringhoy',page)
        for text in ['nasa voucher','Walang','Kasama','Kapag','resibo','checklist lang']:
            self.assertNotIn(text,page)
        for asset in ['style.css','presence.css','presence.js']:
            response=module.app.test_client().get('/assets/'+asset)
            self.assertEqual(response.status_code,200)
            response.close()

    def test_hosted_preview_is_explicitly_read_only(self):
        old=module.HOSTED_PREVIEW
        module.HOSTED_PREVIEW=True
        try:
            c=module.app.test_client()
            self.assertIn('Hosted preview only',c.get('/').get_data(as_text=True))
            r=c.post('/api/materials-presence/decision',json={})
            self.assertEqual(r.status_code,503)
            self.assertIn('read-only',r.get_json()['error'])
        finally:module.HOSTED_PREVIEW=old


if __name__=='__main__':unittest.main()
