import base64
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from storage import Store, cents
from publishing import publish, send, UnknownDelivery
from scoring import score_deal, rank_diverse
from monitoring import run_monitored
from dashboard import application
from state_admin import import_legacy
import manual_publish
import bot


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.url = 'sqlite:///' + str(Path(self.temp.name) / 'state.db')
        self.store = Store(self.url)
        self.deal = {'asin': 'B012345678', 'title': 'Prodotto', 'current_price': 100, 'original_price': 150, 'discount_percent': 33, 'rating': 4.5, 'review_count': 200}

    def tearDown(self):
        self.temp.cleanup()

    def test_atomic_claim_under_contention(self):
        def attempt(_):
            return Store(self.url).claim(self.deal['asin'], 100)
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(attempt, range(24)))
        self.assertEqual(sum(r is not None for r in results), 1)

    def test_persistence_and_exact_price_boundary(self):
        self.assertTrue(publish(self.store, self.deal, lambda: True))
        store = Store(self.url)
        for price in (110, 100, 95.01):
            self.assertIsNone(store.claim(self.deal['asin'], price))
        self.assertIsNotNone(store.claim(self.deal['asin'], 95))
        self.assertEqual(store.history()[bot.get_italy_now().date().isoformat()][self.deal['asin']]['price'], 100)

    def test_pending_does_not_expire(self):
        self.assertIsNotNone(self.store.claim('B012345678', 100, now=1))
        self.assertIsNone(self.store.claim('B012345678', 50))

    def test_unknown_never_retries(self):
        sender = Mock(side_effect=TimeoutError('credential must not leak'))
        with self.assertRaisesRegex(UnknownDelivery, '^Telegram delivery requires reconciliation$'):
            publish(self.store, self.deal, sender)
        self.assertFalse(publish(self.store, self.deal, sender))
        sender.assert_called_once()
        self.assertEqual(self.store.status()['unresolved'][0]['state'], 'unknown')

    def test_rejection_can_retry(self):
        self.assertFalse(publish(self.store, self.deal, lambda: False))
        self.assertTrue(publish(self.store, self.deal, lambda: True))

    def test_reconciliation_deduplicates(self):
        self.store.claim(self.deal['asin'], 100)
        self.store.resolve(self.deal['asin'], True, self.deal)
        self.assertIsNone(self.store.claim(self.deal['asin'], 100))

    def test_claim_ownership(self):
        self.store.claim(self.deal['asin'], 100)
        with self.assertRaises(RuntimeError):
            self.store.finish(self.deal['asin'], 'wrong-token', 'sent', self.deal)
        self.assertEqual(self.store.stats(), {})

    def test_observed_low(self):
        self.store.observe(self.deal, 42)
        self.assertEqual(self.store.minimum(self.deal['asin']), 100)

    def test_monitoring(self):
        with self.assertRaises(ValueError):
            run_monitored(lambda: (_ for _ in ()).throw(ValueError()), self.store)
        self.assertEqual(self.store.status()['runs'][0]['status'], 'error')
        run_monitored(lambda: None, self.store)
        self.assertTrue(self.store.status()['healthy'])

    def test_legacy_import_is_idempotent(self):
        path = Path(self.temp.name) / 'legacy.json'
        day = bot.get_italy_now().date().isoformat()
        path.write_text(json.dumps({day: {self.deal['asin']: {'price': 100}, '_am': True}}))
        import_legacy(self.store, path)
        import_legacy(self.store, path)
        self.assertIsNone(self.store.claim(self.deal['asin'], 100))
        self.assertIsNone(self.store.claim('_am:' + day))
        self.assertEqual(len(next(iter(self.store.stats().values()))), 1)

    def test_export_allowlist(self):
        publish(self.store, dict(self.deal, secret='do-not-export'), lambda: True)
        self.assertNotIn('do-not-export', json.dumps(self.store.status()))

    def test_special_atomic(self):
        sender = Mock(return_value=True)
        with patch.object(bot, 'get_store', return_value=self.store):
            self.assertTrue(bot.publish_special('_am', sender))
            self.assertFalse(bot.publish_special('_am', sender))
        sender.assert_called_once()

    def test_product_path(self):
        with patch.object(bot, 'get_store', return_value=self.store), patch.object(bot, 'send_telegram', return_value=True) as sender:
            self.assertTrue(bot.publish_deal(self.deal, 'test'))
            self.assertFalse(bot.publish_deal(self.deal, 'test'))
        sender.assert_called_once()


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'PostgreSQL integration requires TEST_DATABASE_URL')
class PostgreSQLTests(StorageTests):
    def setUp(self):
        super().setUp()
        self.url = os.environ['TEST_DATABASE_URL']
        self.store = Store(self.url)
        with self.store.tx() as db:
            for table in ('claims', 'publications', 'observations', 'runs', 'metadata'):
                db.execute('DELETE FROM ' + table)


class PolicyTests(unittest.TestCase):
    def test_invalid_prices(self):
        for value in ('nan', 'inf', '-1', '0', '100000', None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                cents(value)

    def test_quality_scoring(self):
        deal = {'current_price': 50, 'original_price': 100, 'rating': 4.5, 'review_count': 1000}
        baseline, parts = score_deal(deal)
        low, _ = score_deal(deal, 60)
        self.assertEqual(round(sum(parts.values()), 2), baseline)
        self.assertAlmostEqual(low, baseline + 10)
        self.assertGreater(baseline, score_deal(dict(deal, rating=None, review_count=None))[0])

    def test_diversity(self):
        deals = [{'asin': 'a', 'title': 'one', 'score': 90}, {'asin': 'b', 'title': 'one', 'score': 80}, {'asin': 'c', 'title': 'two', 'score': 50}]
        self.assertEqual([d['asin'] for d in rank_diverse(deals, lambda t: t)], ['a', 'c', 'b'])

    def test_manual_message(self):
        with patch.dict(os.environ, {'AMAZON_PARTNER_TAG': 'test-21'}):
            message = manual_publish.build_message('B012345678', '<b>test</b>', '10.00')
        self.assertIn('&lt;b&gt;', message)
        self.assertIn('\n', message)
        self.assertNotIn('\\n', message)

    def test_runner_requires_database(self):
        with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true'}, clear=True), self.assertRaises(RuntimeError):
            Store()

    def test_timeout_no_retry(self):
        import requests
        with patch('publishing.requests.post', side_effect=requests.Timeout('https://secret-token')) as post:
            with self.assertRaisesRegex(UnknownDelivery, '^Telegram delivery requires reconciliation$'):
                send('secret-token', 'channel', 'test', 'https://example.com/photo.jpg')
            post.assert_called_once()

    def test_response_classification(self):
        with patch('publishing.requests.post', return_value=Mock(status_code=400, json=lambda: {'ok': False})):
            self.assertFalse(send('test', 'channel', 'test'))
        with patch('publishing.requests.post', return_value=Mock(status_code=500, json=lambda: {'ok': False})), self.assertRaises(UnknownDelivery):
            send('test', 'channel', 'test')

    def test_pause(self):
        with patch.dict(os.environ, {'BOT_PAUSED': 'true'}), patch.object(bot, 'create_api') as api:
            bot.main()
        api.assert_not_called()


class DashboardTests(unittest.TestCase):
    def request(self, path='/api/status', auth=True, method='GET', scheme='https'):
        env = {'PATH_INFO': path, 'REQUEST_METHOD': method, 'wsgi.url_scheme': scheme}
        if auth:
            env['HTTP_AUTHORIZATION'] = 'Basic ' + base64.b64encode(b'operator:long-password-for-testing').decode()
        status = []
        with patch.dict(os.environ, {'DASHBOARD_USER': 'operator', 'DASHBOARD_PASSWORD': 'long-password-for-testing', 'DASHBOARD_ALLOW_HTTP': 'false'}):
            body = b''.join(application(env, lambda s, h: status.extend([s, dict(h)])))
        return status[0], status[1], body

    def test_auth(self):
        status, headers, body = self.request(auth=False)
        self.assertEqual(status, '401 Unauthorized')
        self.assertIn('WWW-Authenticate', headers)
        self.assertNotIn(b'deals', body)

    def test_https(self):
        self.assertEqual(self.request(scheme='http')[0], '403 Forbidden')

    def test_methods_and_traversal(self):
        self.assertEqual(self.request(method='POST')[0], '405 Method Not Allowed')
        self.assertEqual(self.request(path='/../.env')[0], '404 Not Found')

    def test_errors_redacted(self):
        with patch('dashboard.Store', side_effect=RuntimeError('secret-connection-url')):
            status, headers, body = self.request()
        self.assertEqual(status, '503 Service Unavailable')
        self.assertNotIn(b'secret', body)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])


if __name__ == '__main__':
    unittest.main()
