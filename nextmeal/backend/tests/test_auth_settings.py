import json
import unittest
import httpx
from tools.check_auth_settings import configuration, inspect_settings


class AuthSettingsTests(unittest.TestCase):
    values={'APP_MODE':'supabase','SUPABASE_URL':'https://example.supabase.co',
            'SUPABASE_PUBLISHABLE_KEY':'sb_publishable_test_key'}

    def test_only_public_settings_read_and_field_mapping(self):
        requests=[]
        def handler(request):
            requests.append(request)
            return httpx.Response(200,json={'disable_signup':False,'external':{'email':True},'mailer_autoconfirm':False})
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            report=inspect_settings(self.values,client)
        self.assertEqual(report,dict(signup_allowed=True,email_login_enabled=True,email_confirmation_required=True))
        self.assertEqual(len(requests),1)
        self.assertEqual(requests[0].method,'GET')
        self.assertEqual(requests[0].url.path,'/auth/v1/settings')
        self.assertEqual(requests[0].headers['apikey'],self.values['SUPABASE_PUBLISHABLE_KEY'])
        self.assertNotIn('authorization',requests[0].headers)
        self.assertEqual(requests[0].content,b'')

    def test_missing_or_unexpected_fields_are_unknown(self):
        for data in ({},{'disable_signup':'false','external':{'email':'true'},'mailer_autoconfirm':0}):
            with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=data))) as client:
                self.assertEqual(inspect_settings(self.values,client),dict(signup_allowed=None,email_login_enabled=None,email_confirmation_required=None))

    def test_errors_never_print_key_body_or_transport_url(self):
        key=self.values['SUPABASE_PUBLISHABLE_KEY']
        def transport_failure(request):
            raise httpx.ConnectError('private diagnostic '+key,request=request)
        for handler in (lambda r:httpx.Response(403,text=key),lambda r:httpx.Response(200,text=key),transport_failure):
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaises(ValueError) as caught:
                    inspect_settings(self.values,client)
                self.assertNotIn(key,str(caught.exception))
                self.assertNotIn('https://',str(caught.exception))

    def test_local_invalid_urls_and_private_keys_rejected(self):
        import base64
        private='header.'+base64.urlsafe_b64encode(json.dumps({'role':'service_role'}).encode()).decode().rstrip('=')+'.signature'
        for override in ({'APP_MODE':'local'},{'SUPABASE_URL':'http://example.supabase.co'},
                         {'SUPABASE_URL':'https://user:pass@example.supabase.co'},
                         {'SUPABASE_URL':'https://example.supabase.co/?token=value'},
                         {'SUPABASE_PUBLISHABLE_KEY':private},{'SUPABASE_PUBLISHABLE_KEY':'sb_secret_private'}):
            with self.assertRaises(ValueError):
                configuration(self.values|override)
