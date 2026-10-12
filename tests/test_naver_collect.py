import argparse
import copy
import importlib.util
import json
import sys
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import naver_collect as collector

CONFIG = {'verified_live': True, 'verified_by': 'local-fixture-only', 'verified_at': '2026-10-12',
          'blog_tab_selected': '[data-tab="blog"][aria-selected="true"]',
          'result_card': '.card', 'organic_marker': '[data-kind="organic"]',
          'ad_marker': '[data-kind="ad"]', 'result_link': 'a.title',
          'readiness_timeout_ms': 500, 'post_body': '.post-body', 'blocker_selector': '.access-blocker'}
CLASSIFICATION = {'model': 'gpt-6.1-sol', 'reasoning': 'medium', 'invocation_id': 'fixture-not-real-model-call',
                  'user_topic': 'fixture topic', 'primary_field': 'fixture', 'related_fields': [],
                  'audience': 'fixture reader', 'search_intent': 'fixture intent',
                  'search_queries': ['fixture query'], 'rationale': 'fixture rationale'}


class ValidationTests(unittest.TestCase):
    def test_wait_topic_before_reading_other_files_or_browser(self):
        with tempfile.TemporaryDirectory() as tmp:
            brief = Path(tmp) / 'brief.json'
            brief.write_text('{"topic": null}')
            args = argparse.Namespace(brief=brief, classification='/missing', selectors='/missing', output=Path(tmp)/'output', query_index=0)
            with patch.object(collector, 'validate_classification', side_effect=AssertionError('must not run')):
                self.assertEqual(collector.run(args), 2)
            self.assertEqual(collector.read_json(Path(tmp) / 'output' / 'search-evidence.json')['status'], 'WAIT_TOPIC')

    def test_classification_binding_and_metadata(self):
        collector.validate_classification({'topic': 'fixture topic'}, CLASSIFICATION)
        for key, value in [('model', 'gpt-6-luna'), ('reasoning', 'high'), ('invocation_id', ''),
                           ('user_topic', 'stale topic'), ('search_queries', [' '])]:
            with self.subTest(key=key):
                item = copy.deepcopy(CLASSIFICATION)
                item[key] = value
                with self.assertRaises(collector.Blocked):
                    collector.validate_classification({'topic': 'fixture topic'}, item)

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            brief = Path(tmp)/'brief.json'
            brief.write_text('{"topic": null}')
            output = Path(tmp)/'out'
            output.mkdir()
            old = output/'search-evidence.json'
            old.write_text('{"status":"OLD"}')
            args = argparse.Namespace(brief=brief, output=output)
            with self.assertRaisesRegex(collector.Blocked, 'BLOCKED_OUTPUT_EXISTS'):
                collector.run(args)
            self.assertEqual(collector.read_json(old)['status'], 'OLD')

    def test_unverified_selectors_blocked(self):
        item = dict(CONFIG, verified_live=False)
        with self.assertRaisesRegex(collector.Blocked, 'BLOCKED_SELECTORS'):
            collector.validate_selectors(item)

    def test_remote_missing_blocks_without_browser(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, value in [('brief', {'topic': 'fixture topic'}), ('classification', CLASSIFICATION), ('selectors', CONFIG)]:
                collector.write_json(Path(tmp) / (name + '.json'), value)
            args = argparse.Namespace(brief=Path(tmp)/'brief.json', classification=Path(tmp)/'classification.json',
                                      selectors=Path(tmp)/'selectors.json', output=Path(tmp)/'output', query_index=0)
            with patch.dict('os.environ', {}, clear=True):
                self.assertEqual(collector.run(args), 2)
            self.assertTrue(collector.read_json(Path(tmp)/'output'/'search-evidence.json')['status'].startswith('BLOCKED_REMOTE_BROWSER'))


@unittest.skipUnless(importlib.util.find_spec('playwright'),
                     'Optional local browser fixture requires playwright')
class LocalBrowserFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.playwright = sync_playwright().start()
        cls.executable = cls.playwright.chromium.executable_path
        if not Path(cls.executable).exists():
            cls.playwright.stop()
            raise unittest.SkipTest('Install test Chromium with python -m playwright install chromium')
        cls.browser = cls.playwright.chromium.launch(executable_path=cls.executable, headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context()
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()

    def search_html(self, extra=''):
        return '<button data-tab="blog" aria-selected="true">블로그</button>' + extra + ''.join(
            '<div class="card"><span data-kind="organic"></span><a class="title" href="https://blog.naver.com/test/%d">Title %d</a></div>' % (i, i)
            for i in range(1, 7))

    def test_local_cdp_attach_reuses_context_and_preserves_owner_page(self):
        # A separate temporary LOCAL Chromium CDP fixture, not a remote Naver session.
        with tempfile.TemporaryDirectory() as profile, tempfile.TemporaryDirectory() as output:
            owner_context = self.playwright.chromium.launch_persistent_context(profile, executable_path=self.executable, headless=True, args=['--remote-debugging-port=0'])
            try:
                active = Path(profile)/'DevToolsActivePort'
                deadline = time.monotonic() + 10
                while not active.exists():
                    if time.monotonic() >= deadline:
                        self.fail('Local Chromium CDP fixture did not start')
                    time.sleep(0.05)
                port = active.read_text().splitlines()[0]
                attached = self.playwright.chromium.connect_over_cdp('http://127.0.0.1:' + port)
                self.assertEqual(len(attached.contexts), 1)
                context = attached.contexts[0]
                owner = context.pages[0]
                owner.set_content('<title>Owner page preserved</title>')
                def route(request):
                    body = self.search_html() if 'search.naver.com' in request.request.url else '<article class="post-body">Local CDP fixture body.</article>'
                    request.fulfill(body=body, content_type='text/html')
                context.route('**/*', route)
                report = {'timezone': 'Asia/Seoul', 'ranks': []}
                self.assertEqual(collector.collect_session(context, 'fixture', CONFIG, output, report), 0)
                self.assertEqual(len(context.pages), 1)
                self.assertEqual(owner.title(), 'Owner page preserved')
                self.assertEqual(report['status'], 'COLLECTED')
                context.unroute('**/*', route)
            finally:
                owner_context.close()

    def test_actual_dom_order_excludes_ads(self):
        ad = '<div class="card"><span data-kind="ad">광고</span><a class="title" href="https://example.test/ad">Ad</a></div>'
        self.page.set_content(self.search_html(ad))
        ranks = collector.collect_cards(self.page, CONFIG)
        self.assertEqual([r['title'] for r in ranks], ['Title %d' % i for i in range(1, 6)])
        self.assertTrue(all(not r['accessed'] for r in ranks))

    def test_unknown_and_conflicting_ads_fail_closed(self):
        for marker in ['', '<span data-kind="ad"></span><span data-kind="organic"></span>']:
            self.page.set_content(self.search_html('<div class="card">%s<a class="title">Unknown</a></div>' % marker))
            with self.assertRaisesRegex(collector.Blocked, 'BLOCKED_AD_CLASSIFICATION'):
                collector.collect_cards(self.page, CONFIG)

    def test_non_blog_tab_and_captcha_block(self):
        self.page.set_content(self.search_html().replace('aria-selected="true"', 'aria-selected="false"'))
        with self.assertRaisesRegex(collector.Blocked, 'BLOCKED_TAB'):
            collector.collect_cards(self.page, CONFIG)
        self.page.set_content('<h1>자동입력 방지</h1>')
        with self.assertRaisesRegex(collector.Blocked, 'BLOCKED_LOGIN_OR_CAPTCHA'):
            collector.blocker(self.page, CONFIG)

    def test_iframe_body_and_short_evidence(self):
        def route(request):
            if '/frame' in request.request.url:
                request.fulfill(body='<article class="post-body"><h2>Heading</h2>' + '본문입니다. ' * 100 + '</article>', content_type='text/html')
            else:
                request.fulfill(body='<iframe src="https://blog.naver.com/frame"></iframe>', content_type='text/html')
        self.context.route('**/*', route)
        self.page.goto('https://blog.naver.com/test/1', wait_until='load')
        summary = collector.inspect_post(self.page, CONFIG)
        self.assertLessEqual(len(summary['evidence'][0]['text']), 180)
        self.assertEqual(summary['summary_kind'], 'structural_observation_not_model_analysis')
        self.assertIn('Heading', summary['content_summary'])

    def test_partial_result_evidence_is_preserved(self):
        partial = []
        self.page.set_content(self.search_html().replace('data-kind="organic"', 'data-kind="unknown"', 1))
        with self.assertRaises(collector.Blocked):
            collector.collect_cards(self.page, CONFIG, partial)
        self.assertEqual(partial, [])
        self.page.set_content(self.search_html().replace('data-kind="organic"', 'data-kind="unknown"', 5).replace('data-kind="unknown"', 'data-kind="organic"', 2))
        with self.assertRaises(collector.Blocked):
            collector.collect_cards(self.page, CONFIG, partial)
        self.assertEqual(len(partial), 2)

    def test_delayed_body_and_any_visible_blocker(self):
        self.context.route('**/*', lambda route: route.fulfill(body="<script>setTimeout(() => document.body.innerHTML = '<article class=\"post-body\">Delayed body</article>', 120)</script>", content_type='text/html'))
        self.page.goto('https://blog.naver.com/test/1')
        self.assertIn('Delayed body', collector.inspect_post(self.page, CONFIG)['evidence'][0]['text'])
        self.page.set_content('<div class="access-blocker" style="display:none"></div><div class="access-blocker">Stop</div>')
        with self.assertRaisesRegex(collector.Blocked, 'BLOCKED_ACCESS'):
            collector.blocker(self.page, CONFIG)

    def test_missing_body_continues_other_posts(self):
        def route(request):
            url = request.request.url
            body = self.search_html() if 'search.naver.com' in url else ('<p>Unavailable post</p>' if url.endswith('/2') else '<article class="post-body">Body</article>')
            request.fulfill(body=body, content_type='text/html')
        self.context.route('**/*', route)
        with tempfile.TemporaryDirectory() as tmp:
            report = {'timezone': 'Asia/Seoul', 'ranks': []}
            self.assertEqual(collector.collect_session(self.context, 'fixture', CONFIG, tmp, report), 2)
            self.assertEqual(report['status'], 'PARTIAL_POST_FAILURE')
            self.assertEqual([r['accessed'] for r in report['ranks']], [True, False, True, True, True])

    def test_http_access_denial_stops_before_next_post(self):
        visited = []
        def route(request):
            url = request.request.url
            visited.append(url)
            body = self.search_html() if 'search.naver.com' in url else '<article class="post-body">Body</article>'
            request.fulfill(body=body, status=403 if url.endswith('/2') else 200, content_type='text/html')
        self.context.route('**/*', route)
        with tempfile.TemporaryDirectory() as tmp:
            report = {'timezone': 'Asia/Seoul', 'ranks': []}
            self.assertEqual(collector.collect_session(self.context, 'fixture', CONFIG, tmp, report), 2)
            self.assertEqual(report['status'], 'BLOCKED_ACCESS: HTTP 403')
            self.assertTrue(report['ranks'][0]['accessed'])
            self.assertFalse(report['ranks'][1]['accessed'])
            self.assertFalse(report['ranks'][2]['attempted'])
            self.assertFalse(any(url.endswith('/3') for url in visited))

    def test_partial_access_stops_immediately_and_saves_screenshots(self):
        visited = []
        def route(request):
            url = request.request.url
            visited.append(url)
            if 'search.naver.com' in url:
                body = self.search_html()
            elif url.endswith('/2'):
                body = '<h1 class="access-blocker">로그인이 필요</h1>'
            else:
                body = '<article class="post-body"><h2>Fixture</h2>Local fixture content.</article>'
            request.fulfill(body=body, content_type='text/html')
        self.context.route('**/*', route)
        with tempfile.TemporaryDirectory() as tmp:
            report = {'timezone': 'Asia/Seoul', 'ranks': []}
            self.assertEqual(collector.collect_session(self.context, 'fixture', CONFIG, tmp, report), 2)
            result = collector.read_json(Path(tmp)/'search-evidence.json')
            self.assertTrue(result['ranks'][0]['accessed'])
            self.assertFalse(result['ranks'][1]['accessed'])
            self.assertTrue(all(not r['accessed'] for r in result['ranks'][1:]))
            self.assertFalse(any(url.endswith('/3') for url in visited))
            self.assertTrue((Path(tmp)/'search.png').exists())
            self.assertTrue((Path(tmp)/'post-1.png').exists())
            self.assertTrue((Path(tmp)/'blocked.png').exists())


if __name__ == '__main__':
    unittest.main()
