"""Isolate UniFi helpers without starting the connector's server/background tasks."""
import ast
import hashlib
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch


source = Path(__file__).with_name('connector.py').read_text()
tree = ast.parse(source)
cut = next(i for i, node in enumerate(tree.body) if isinstance(node, ast.If) and ast.unparse(node.test) == "__name__ == '__main__'")
module = types.ModuleType('connector_test')
exec(compile(ast.Module(body=tree.body[:cut], type_ignores=[]), 'connector.py', 'exec'), module.__dict__)


class UniFiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        module.UNIFI_CONFIG_FILE = str(Path(self.temp.name) / 'unifi' / 'config.json')
        module.UNIFI_CACHE.clear()
        module.UNIFI_CLIENT = None
        module.UNIFI_LAST_GOOD = None
        self.config = dict(url='https://controller.test:8443', username='reader', password='test-only-secret', site='default', certificate_sha256=hashlib.sha256(b'certificate').hexdigest())

    def save(self):
        path = Path(module.UNIFI_CONFIG_FILE)
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(self.config))
        path.chmod(0o600)

    def test_unconfigured(self):
        result = module.unifi_status()
        self.assertFalse(result['configured'])
        self.assertEqual(result['devices'], [])

    def test_missing_metrics_and_offline_are_unknown(self):
        devices = module._unifi_devices([
            {'type': 'uap', 'name': 'Kitchen', 'state': 1, 'num_sta': 0, 'system-stats': {'cpu': '12.5', 'mem': 'NaN'}, 'password': 'private'},
            {'type': 'uap', 'name': 'Garden', 'state': 0, 'num_sta': 9, 'uptime': 90},
            {'type': 'usw', 'name': 'Switch', 'state': 1}])
        self.assertEqual(len(devices), 2)
        self.assertIsNone(devices[0]['clients'])
        self.assertIsNone(devices[0]['uptime_seconds'])
        self.assertEqual(devices[1]['clients'], 0)
        self.assertEqual(devices[1]['cpu_percent'], 12.5)
        self.assertIsNone(devices[1]['memory_percent'])
        self.assertNotIn('password', json.dumps(devices))

    def test_failed_controller_preserves_timestamped_historical_devices(self):
        self.save()
        with patch.object(module._UniFiClient, 'devices', return_value=[{'type': 'uap', 'state': 1}]) as read:
            self.assertTrue(module.unifi_status()['controller_online'])
            module.unifi_status()
            self.assertEqual(read.call_count, 1)
        module.UNIFI_CACHE['expires'] = 0
        with patch.object(module._UniFiClient, 'devices', side_effect=OSError('private diagnostic')):
            result = module.unifi_status()
        self.assertFalse(result['controller_online'])
        self.assertEqual(len(result['devices']), 1)
        self.assertIsNotNone(result['last_seen_at'])
        self.assertNotIn('private diagnostic', json.dumps(result))

    def test_insecure_config_rejected(self):
        self.save()
        Path(module.UNIFI_CONFIG_FILE).chmod(0o644)
        with self.assertRaises(ValueError): module._unifi_config()

    def test_configure_validates_before_save_and_uses_private_modes(self):
        sock = unittest.mock.MagicMock()
        tls = unittest.mock.MagicMock()
        tls.__enter__.return_value.getpeercert.return_value = b'certificate'
        context = unittest.mock.MagicMock()
        context.wrap_socket.return_value = tls
        with patch('builtins.input', side_effect=[self.config['url'], 'reader', '', 'yes']), patch('getpass.getpass', return_value='test-only-secret'), patch.object(module.socket, 'create_connection', return_value=sock), patch.object(module.ssl, '_create_unverified_context', return_value=context), patch.object(module._UniFiClient, 'devices', return_value=[]), patch('builtins.print'):
            module.configure_unifi()
        path = Path(module.UNIFI_CONFIG_FILE)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        before = path.read_text()
        with patch('builtins.input', side_effect=[self.config['url'], 'reader', '', 'yes']), patch('getpass.getpass', return_value='bad'), patch.object(module.socket, 'create_connection', return_value=sock), patch.object(module.ssl, '_create_unverified_context', return_value=context), patch.object(module._UniFiClient, 'devices', side_effect=PermissionError()), patch('builtins.print'):
            with self.assertRaises(PermissionError): module.configure_unifi()
        self.assertEqual(path.read_text(), before)

    def test_session_expiry_reauthenticates_once(self):
        client = module._UniFiClient(self.config)
        client.cookies = {'session': 'expired'}
        calls = []
        def request(path, body=None):
            calls.append((path, body))
            if len(calls) == 1: raise PermissionError()
            if path == '/api/login': client.cookies = {'session': 'new'}; return []
            return [{'type': 'uap'}]
        client.request = request
        self.assertEqual(len(client.devices()), 1)
        self.assertEqual([path for path, _ in calls], ['/api/s/default/stat/device', '/api/login', '/api/s/default/stat/device'])

    def test_certificate_checked_before_password_sent(self):
        connection = unittest.mock.MagicMock()
        connection.sock.getpeercert.return_value = b'different certificate'
        with patch('http.client.HTTPSConnection', return_value=connection):
            with self.assertRaises(ValueError): module._UniFiClient(self.config).request('/api/login', {'password': 'secret'})
        connection.request.assert_not_called()
        connection.close.assert_called_once()

    def test_login_cookie_passed_to_read(self):
        connection = unittest.mock.MagicMock()
        connection.sock.getpeercert.return_value = b'certificate'
        response = connection.getresponse.return_value
        response.status = 200
        response.getheaders.return_value = [('Set-Cookie', 'unifises=test; Path=/; HttpOnly')]
        response.read.return_value = b'{"meta":{"rc":"ok"},"data":[]}'
        with patch('http.client.HTTPSConnection', return_value=connection):
            module._UniFiClient(self.config).devices()
        calls = connection.request.call_args_list
        self.assertEqual(calls[0].args[:2], ('POST', '/api/login'))
        self.assertEqual(calls[1].args[:2], ('GET', '/api/s/default/stat/device'))
        self.assertEqual(calls[1].args[3]['Cookie'], 'unifises=test')

    def test_reject_embedded_password_or_non_https(self):
        for url in ['http://controller.test', 'https://user:secret@controller.test', 'https://controller.test/manage']:
            with self.assertRaises(ValueError): module._unifi_address(url)


if __name__ == '__main__': unittest.main()
