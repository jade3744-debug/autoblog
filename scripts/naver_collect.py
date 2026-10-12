#!/usr/bin/env python3
"""Fail-closed remote-CDP Naver evidence collector; no model or publishing calls."""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import shutil
import tempfile
import importlib.metadata
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode, urlsplit, parse_qs
from zoneinfo import ZoneInfo

MODEL = 'gpt-6.1-sol'
REASONING = 'medium'


class Blocked(Exception):
    pass


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def validate_classification(brief, classification):
    if not isinstance(brief.get('topic'), str) or not brief['topic'].strip():
        raise Blocked('WAIT_TOPIC')
    if classification.get('model') != MODEL or classification.get('reasoning') != REASONING:
        raise Blocked('BLOCKED_MODEL_ACCESS: classification metadata mismatch')
    if classification.get('user_topic') != brief['topic']:
        raise Blocked('BLOCKED_CLASSIFICATION: topic mismatch')
    for key in ('primary_field', 'audience', 'search_intent', 'rationale'):
        if not isinstance(classification.get(key), str) or not classification[key].strip():
            raise Blocked('BLOCKED_CLASSIFICATION: missing ' + key)
    for key in ('related_fields', 'search_queries'):
        value = classification.get(key)
        if not isinstance(value, list) or (key == 'search_queries' and not value) or any(not isinstance(x, str) or not x.strip() for x in value):
            raise Blocked('BLOCKED_CLASSIFICATION: invalid ' + key)
    if not classification.get('invocation_id'):
        raise Blocked('BLOCKED_MODEL_ACCESS: missing researcher invocation_id')
    # Metadata is an attestation by the calling researcher, not runtime verification.


def validate_selectors(config):
    if config.get('verified_live') is not True or not config.get('verified_by') or not config.get('verified_at'):
        raise Blocked('BLOCKED_SELECTORS: live selector verification required')
    for key in ('blog_tab_selected', 'result_card', 'organic_marker', 'ad_marker', 'result_link', 'post_body', 'blocker_selector'):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise Blocked('BLOCKED_SELECTORS: missing ' + key)


def blocker(page, config):
    for frame in page.frames:
        if re.search(r'(nid\.naver\.com/.*(login|captcha)|/captcha)', frame.url, re.I):
            raise Blocked('BLOCKED_LOGIN_OR_CAPTCHA')
        matches = frame.locator(config['blocker_selector'])
        if any(matches.nth(i).is_visible() for i in range(matches.count())):
            raise Blocked('BLOCKED_ACCESS: visible blocker')
        text = frame.locator('body').inner_text(timeout=5000) if frame.locator('body').count() else ''
        if re.search(r'(자동입력\s*방지|비정상적인\s*접근|접근이?\s*차단|로그인이\s*필요|captcha|access\s*denied|sign\s*in\s*to\s*continue)', text, re.I):
            raise Blocked('BLOCKED_LOGIN_OR_CAPTCHA_OR_ACCESS')


def post_url_allowed(url):
    parsed = urlsplit(url)
    return parsed.scheme == 'https' and parsed.hostname in ('blog.naver.com', 'm.blog.naver.com') and not parsed.username and not parsed.password


def check_response(response):
    if response is not None and response.status in (401, 403, 429):
        raise Blocked('BLOCKED_ACCESS: HTTP %d' % response.status)


def collect_cards(page, config, partial=None):
    blocker(page, config)
    selected = page.locator(config['blog_tab_selected'])
    if selected.count() != 1 or not selected.is_visible():
        raise Blocked('BLOCKED_TAB: selected blog tab not verified')
    cards = page.locator(config['result_card'])
    ranks = partial if partial is not None else []
    seen = set()
    for i in range(cards.count()):
        card = cards.nth(i)
        if not card.is_visible():
            continue
        organic = card.locator(config['organic_marker']).count() > 0
        ad = card.locator(config['ad_marker']).count() > 0
        if organic == ad:
            raise Blocked('BLOCKED_AD_CLASSIFICATION: ambiguous result card')
        if ad:
            continue
        links = card.locator(config['result_link'])
        if links.count() != 1:
            raise Blocked('BLOCKED_DOM: ambiguous result link')
        url = links.get_attribute('href')
        title = links.inner_text().strip()
        if not url or not post_url_allowed(url) or not title or url in seen:
            raise Blocked('BLOCKED_DOM: invalid or duplicate blog result')
        seen.add(url)
        ranks.append({'rank': len(ranks) + 1, 'title': title, 'url': url, 'accessed': False,
                      'content_summary': None, 'evidence': []})
        if len(ranks) == 5:
            return ranks
    raise Blocked('BLOCKED_RESULTS: fewer than five verified organic results')


def inspect_post(page, config):
    blocker(page, config)
    if not post_url_allowed(page.url):
        raise Blocked('BLOCKED_POST_REDIRECT: unexpected host')
    deadline = time.monotonic() + config.get('readiness_timeout_ms', 10000) / 1000
    while True:
        blocker(page, config)
        bodies = []
        for frame in page.frames:
            if not post_url_allowed(frame.url):
                continue
            matches = frame.locator(config['post_body'])
            for i in range(matches.count()):
                body = matches.nth(i)
                if body.is_visible():
                    text = body.inner_text().strip()
                    if text:
                        bodies.append((frame, body, text))
        if len(bodies) == 1:
            break
        if len(bodies) > 1 or time.monotonic() >= deadline:
            raise Blocked('BLOCKED_POST_BODY: expected one visible verified body')
        page.wait_for_timeout(100)
    frame, body, text = bodies[0]
    headings = [x.strip()[:80] for x in body.locator('h1,h2,h3').all_inner_texts() if x.strip()][:3]
    return {'content_summary': '본문 확인: %d자, 이미지 %d개. 소제목: %s' %
            (len(text), body.locator('img').count(), ' / '.join(headings) or '확인된 소제목 없음'),
            'summary_kind': 'structural_observation_not_model_analysis',
            'evidence': [{'kind': 'short_excerpt', 'text': text[:180], 'frame_url': frame.url},
                         {'kind': 'body_fingerprint', 'sha256': hashlib.sha256(text.encode()).hexdigest(), 'chars': len(text)}]}


def collect_session(context, query, config, output, report, search_url=None):
    """context must be remote persistent CDP in production; injectable for local fixture tests."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    page = context.new_page()
    report['requested_search_url'] = search_url or 'https://search.naver.com/search.naver?' + urlencode({'ssc': 'tab.blog.all', 'query': query})
    report['query'] = query
    active_rank = None
    try:
        response = page.goto(report['requested_search_url'], wait_until='domcontentloaded', timeout=30000)
        check_response(response)
        blocker(page, config)
        report['search_url'] = page.url
        report['observed_at'] = datetime.now(ZoneInfo(report['timezone'])).isoformat()
        report['device'] = {'user_agent': page.evaluate('navigator.userAgent'), 'viewport': page.viewport_size,
                            'screen': page.evaluate('({width:screen.width,height:screen.height,devicePixelRatio:devicePixelRatio})')}
        parsed = urlsplit(page.url)
        params = parse_qs(parsed.query)
        if not search_url and (parsed.hostname != 'search.naver.com' or params.get('query') != [query] or params.get('ssc') != ['tab.blog.all']):
            raise Blocked('BLOCKED_SEARCH_REDIRECT: search query or blog tab changed')
        deadline = time.monotonic() + config.get('readiness_timeout_ms', 10000) / 1000
        while not page.locator(config['result_card']).count() or not page.locator(config['blog_tab_selected']).count():
            blocker(page, config)
            if time.monotonic() >= deadline:
                raise Blocked('BLOCKED_DOM: search readiness timeout')
            page.wait_for_timeout(100)
        collect_cards(page, config, report['ranks'])
        report['observed_at'] = datetime.now(ZoneInfo(report['timezone'])).isoformat()
        report['screenshot_path'] = str(output / 'search.png')
        page.screenshot(path=report['screenshot_path'], full_page=True)
        write_json(output / 'search-evidence.json', report)
        failed = False
        for rank in report['ranks']:
            active_rank = rank
            rank['attempted'] = True
            try:
                response = page.goto(rank['url'], wait_until='domcontentloaded', timeout=30000)
                check_response(response)
                blocker(page, config)
                rank['observed_at'] = datetime.now(ZoneInfo(report['timezone'])).isoformat()
                summary = inspect_post(page, config)
                blocker(page, config)
                rank['screenshot_path'] = str(output / ('post-%d.png' % rank['rank']))
                page.screenshot(path=rank['screenshot_path'], full_page=True)
                rank.update(summary)
                rank['accessed'] = True
            except Exception as exc:
                failed = True
                rank['failure'] = str(exc) if isinstance(exc, Blocked) else 'BLOCKED_POST: ' + type(exc).__name__
                rank['accessed'] = False
                # Real access/login/CAPTCHA barriers halt the entire session immediately.
                if isinstance(exc, Blocked) and not str(exc).startswith('BLOCKED_POST_BODY'):
                    raise
                try:
                    rank['screenshot_path'] = str(output / ('post-%d-failed.png' % rank['rank']))
                    page.screenshot(path=rank['screenshot_path'], full_page=True, timeout=5000)
                except Exception:
                    pass
            write_json(output / 'search-evidence.json', report)
        report['status'] = 'PARTIAL_POST_FAILURE' if failed else 'COLLECTED'
    except Exception as exc:
        report['status'] = str(exc) if isinstance(exc, Blocked) else 'BLOCKED_BROWSER: ' + type(exc).__name__
        for rank in report['ranks']:
            if not rank.get('attempted'):
                rank['attempted'] = False
                rank['failure'] = 'NOT_ATTEMPTED: collection stopped'
        if active_rank is not None:
            active_rank['accessed'] = False
            active_rank['failure'] = report['status']
        try:
            failure_path = output / 'blocked.png'
            page.screenshot(path=str(failure_path), full_page=True, timeout=5000)
            report['failure_screenshot_path'] = str(failure_path)
        except Exception:
            pass
    finally:
        write_json(output / 'search-evidence.json', report)
        try:
            page.close()
        except Exception:
            pass
    return 0 if report['status'] == 'COLLECTED' else 2


def run(args):
    brief = read_json(args.brief)
    output = Path(args.output)
    if output.exists() and any(output.iterdir()):
        raise Blocked('BLOCKED_OUTPUT_EXISTS: use a new empty run directory')
    report = {'status': 'WAIT_TOPIC', 'ranks': [], 'tab': 'naver_blog_tab_organic_top5',
              'timezone': brief.get('timezone', 'Asia/Seoul'), 'cdp_connected': False}
    # Topic is checked before loading classification, selectors, Playwright, or any browser/network.
    if not isinstance(brief.get('topic'), str) or not brief['topic'].strip():
        write_json(output / 'search-evidence.json', report)
        return 2
    try:
        classification = read_json(args.classification)
        validate_classification(brief, classification)
        if brief.get('search_scope', 'naver_blog_tab_organic_top5') != 'naver_blog_tab_organic_top5':
            raise Blocked('BLOCKED_SCOPE: only organic blog top5 supported')
        config = read_json(args.selectors)
        validate_selectors(config)
        endpoint = os.environ.get('NAVER_CDP_ENDPOINT')
        if not endpoint:
            raise Blocked('BLOCKED_REMOTE_BROWSER: NAVER_CDP_ENDPOINT required')
        if os.environ.get('NAVER_CDP_PERSISTENT_CONTEXT') != '1':
            raise Blocked('BLOCKED_REMOTE_BROWSER: persistent context attestation required')
        login_context = os.environ.get('NAVER_LOGIN_CONTEXT', '').strip()
        if not login_context:
            raise Blocked('BLOCKED_LOGIN_CONTEXT: describe signed-in account alias or logged-out state')
        profile_context = os.environ.get('NAVER_PROFILE_CONTEXT', '').strip()
        if not profile_context:
            raise Blocked('BLOCKED_PROFILE_CONTEXT: operator profile description required')
        if args.query_index < 0 or args.query_index >= len(classification['search_queries']):
            raise Blocked('BLOCKED_CLASSIFICATION: query index outside classification')
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(endpoint, timeout=15000)
            if len(browser.contexts) != 1:
                raise Blocked('BLOCKED_REMOTE_BROWSER: expected one existing persistent context')
            report.update({'cdp_connected': True, 'connection_kind': 'local_cdp' if urlsplit(endpoint).hostname in ('127.0.0.1', 'localhost', '::1') else 'remote_cdp',
                           'persistent_context': 'operator_attested', 'profile_context': profile_context, 'login_context': login_context,
                           'login_context_source': 'operator_attested_not_authenticated_by_collector',
                           'classification_model_metadata': {k: classification[k] for k in ('model', 'reasoning', 'invocation_id')},
                           'selector_provenance': {k: config[k] for k in ('verified_by', 'verified_at', 'verified_live')}})
            return collect_session(browser.contexts[0], classification['search_queries'][args.query_index], config, output, report)
    except Exception as exc:
        report['status'] = str(exc) if isinstance(exc, Blocked) else 'BLOCKED_SETUP: ' + type(exc).__name__
        write_json(output / 'search-evidence.json', report)
        return 2


def doctor(brief_path, local_smoke=False):
    """Read-only diagnostics unless an explicit temporary local smoke is requested."""
    brief = read_json(brief_path)
    info = {'topic_status': 'READY' if isinstance(brief.get('topic'), str) and brief['topic'].strip() else 'WAIT_TOPIC',
            'cdp_configured': bool(os.environ.get('NAVER_CDP_ENDPOINT')),
            'persistent_context_attested': os.environ.get('NAVER_CDP_PERSISTENT_CONTEXT') == '1',
            'login_context_supplied': bool(os.environ.get('NAVER_LOGIN_CONTEXT')),
            'profile_context_supplied': bool(os.environ.get('NAVER_PROFILE_CONTEXT')),
            'chromium_path': shutil.which('chromium'), 'naver_validated': False}
    try:
        info['playwright_version'] = importlib.metadata.version('playwright')
    except importlib.metadata.PackageNotFoundError:
        info['playwright_version'] = None
    if local_smoke:
        from playwright.sync_api import sync_playwright
        with tempfile.TemporaryDirectory(prefix='naver-local-smoke-') as profile:
            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(profile, executable_path=info['chromium_path'], headless=True)
                try:
                    page = context.new_page()
                    page.set_content('<h1>Local smoke only</h1>')
                    assert page.locator('h1').inner_text() == 'Local smoke only'
                    info['local_smoke'] = 'PASS: temporary local profile; no Naver navigation or remote connection'
                finally:
                    context.close()
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--doctor', action='store_true')
    parser.add_argument('--local-smoke', action='store_true', help='Explicit temporary local browser diagnostic; no Naver navigation')
    parser.add_argument('--brief', default='brief.json')
    parser.add_argument('--classification', default='classification.json')
    parser.add_argument('--selectors', default='naver-selectors.json')
    parser.add_argument('--output', default='runs/search')
    parser.add_argument('--query-index', type=int, default=0)
    args = parser.parse_args()
    if args.doctor or args.local_smoke:
        return doctor(args.brief, args.local_smoke)
    try:
        result = run(args)
    except Exception as exc:
        print(str(exc) if isinstance(exc, Blocked) else 'BLOCKED_SETUP: ' + type(exc).__name__)
        return 2
    print(read_json(Path(args.output) / 'search-evidence.json')['status'])
    return result


if __name__ == '__main__':
    sys.exit(main())
