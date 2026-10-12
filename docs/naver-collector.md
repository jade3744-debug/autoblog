# 네이버 화면 증거 수집기

`scripts/naver_collect.py`는 사용자 주제와 researcher의 분류를 받아 **기존 지속 프로필 원격 Chromium CDP 세션**에서 블로그 탭 광고 제외 상위 5개를 DOM 순서대로 수집한다. 브라우저가 설치되었다는 사실과 네이버에서 실제 검증되었다는 사실은 다르다. 현재 brief.topic은 null이며 실제 네이버 검색·분류·원고 생성은 수행하지 않았다.

## 실행 준비

```bash
python -m pip install -r requirements-browser.txt
python scripts/naver_collect.py --doctor
python scripts/naver_collect.py --local-smoke
python -m unittest discover -s tests -v
```

`--doctor`는 주제 상태, 패키지 버전, 로컬 Chromium 경로, 환경 변수 **설정 여부만** 출력하며 CDP에 연결하지 않는다. `--local-smoke`는 명시적으로 요청한 로컬 진단이다. 임시 프로필과 인메모리 HTML만 사용한 뒤 닫으며, 네이버 접속·원격 서비스 검증·네이버 로그인 검증을 의미하지 않는다. 로컬 브라우저 테스트는 playwright와 `/usr/bin/chromium`이 없으면 별도로 skip 표시된다. 다른 Chromium 경로에서는 테스트 환경에 맞게 경로를 조정해야 한다. 실제 수집은 로컬 브라우저를 자동 시작하지 않는다.

주제가 없으면 classification/selector 파일을 읽거나 Playwright를 가져오기 전에 `WAIT_TOPIC`, 종료 코드 2, 빈 ranks를 기록한다. 기존 산출물을 덮어쓰지 않으므로 **매 실행 새 빈 output 디렉터리**가 필요하다. 이미 파일이 있으면 `BLOCKED_OUTPUT_EXISTS`로 종료하며 기존 증거는 유지된다.

## researcher 분류 계약

실제 `gpt-6.1-sol` / `medium` researcher가 `AGENTS.md`, `brief.json`, `prompts/research.md`를 읽고 주제 의미·독자 질문·검색 의도를 분석하여 `classification.json`을 작성한다. 수집기는 업종 목록, 키워드 규칙, 대체 모델로 분류를 생성하지 않는다. 다음 필드가 필요하다.

```json
{
  "user_topic": "사용자가 brief.topic에 제공한 동일한 주제",
  "primary_field": "researcher가 도출한 주 분야",
  "related_fields": ["관련 하위 분야"],
  "audience": "대상 독자",
  "search_intent": "독자 질문과 검색 의도",
  "search_queries": ["researcher가 선정한 실제 검색어"],
  "rationale": "주제와 분야·독자·검색어를 연결한 근거",
  "model": "gpt-6.1-sol",
  "reasoning": "medium",
  "invocation_id": "실제 researcher 실행의 식별자"
}
```

위 예시는 필드 설명이며 실행 가능한 실제 분류 결과가 아니다. 원래 주제와 다른 분류, 빈 검색어, 잘못된 모델/추론, 호출 ID 누락은 차단한다. `--query-index`로 분류 안의 검색어 하나를 선택하며 범위를 벗어나면 차단한다. 메타데이터는 researcher의 실행 기록을 전달하는 계약으로, JSON만으로 숨겨진 런타임 모델을 인증하지 않는다. 자동 모델 API 호출기는 아직 구현하지 않았으며 **에이전트가 분류를 제공하는 방식**이다. 모든 검색어를 조사하려면 검색어마다 별도 output 디렉터리로 실행한다.

## 원격 세션 연결

운영자가 지속 프로필 원격 Chromium을 준비하고 로그인 필요 시 직접 로그인한다. 안전한 비공개 설정 경로에서 다음 변수를 제공한다.

- `NAVER_CDP_ENDPOINT`: 명시적인 원격 CDP HTTP 또는 WebSocket 엔드포인트. 비밀 토큰이 포함될 수 있으므로 저장소에 넣지 않는다.
- `NAVER_CDP_PERSISTENT_CONTEXT=1`: 운영자가 해당 세션이 지속 프로필이라는 사실을 확인한 표시.
- `NAVER_PROFILE_CONTEXT`: 비밀이나 파일 경로 대신 프로필을 구분하는 설명/별칭.
- `NAVER_LOGIN_CONTEXT`: 로그인된 계정 별칭 또는 로그아웃 상태와 운영자가 확인한 조건. 비밀번호·쿠키·토큰을 넣지 않는다.

수집기는 CDP 엔드포인트·쿠키·토큰을 로그나 evidence에 기록하지 않는다. 기존 컨텍스트 하나만 사용하며 새 프로필, storage state, device 설정, pagination, 계정 전환을 만들지 않는다. 수집용 새 페이지 하나만 열고 닫는다. 원격 브라우저와 기존 사용자 페이지는 닫지 않는다. `cdp_connected=true`는 CDP 연결의 관측이며, 프로필 지속성과 로그인 신원은 `operator_attested`로 구분한다. 연결 성공만으로 네이버 로그인이나 원격 서비스 적합성이 검증되었다고 주장하지 않는다.

원격 브라우저의 네트워크에는 `search.naver.com`, `blog.naver.com`, `m.blog.naver.com`, 로그인 시 `nid.naver.com`, 필요한 `*.pstatic.net` 자산과 실제 관측된 추가 자산 도메인이 허용되어야 한다. 실행기는 CDP 호스트에 접근할 수 있어야 한다. 실제 접속 조건은 원격 서비스에 따라 달라진다.

`NAVER_CDP_ENDPOINT`는 **수집 Python 프로세스의 환경 변수**에 설정한다. 클라우드 환경 설정의 런타임 환경 변수로 등록하거나 실행 셸에서 export하여 전달한다. `.codex/config.toml`, brief.json에 넣지 않으며, 이 코드는 `.env` 파일을 자동으로 읽지 않는다. 토큰이 없는 주소는 일반 환경 변수로 사용할 수 있지만, 인증 정보가 포함된 주소는 사용 중인 플랫폼/브라우저 제공자의 비밀 설정 경로를 이용한다. 비밀 프록시의 값이 실제 WebSocket 연결에 전달되는지도 제공자별로 확인해야 한다.

## 현재 작업 환경 연결 점검 (2026-10-12)

- Chromium 154와 Playwright 1.62.0은 설치되어 있다. 로컬 테스트의 프로필은 `TemporaryDirectory`로 생성하고 종료 시 삭제된다. 별도의 지속 Chrome 프로필은 설정하지 않았으므로 작업 종료 후 네이버 로그인 세션이 유지된다는 보장은 없다. 같은 프로필로 브라우저를 재시작하는 테스트 쿠키 유지와 새 클라우드 작업으로의 복원은 다른 검증이다.
- 사용자에게 제공되는 원격 Chrome 화면/CDP 연결이 없고 DISPLAY/WAYLAND_DISPLAY도 설정되어 있지 않다. 현재 테스트용 headless Chrome 화면에서 사용자가 직접 로그인할 수 있다고 보고할 수 없다. 사용자용 브라우저 화면(원격 데스크톱 또는 브라우저 제공자의 접속 UI), 지속 디스크의 전용 프로필, 실행기에서 접근 가능한 CDP 주소를 함께 제공하는 환경이 필요하다. 사용자가 직접 로그인하고 작업을 다시 연결해야 한다.
- `NAVER_CDP_ENDPOINT`와 로그인/프로필 조건은 현재 미설정이다. 원격 브라우저를 준비한 뒤 위 환경 변수와 실제 화면에서 검증한 selector 설정을 공급해야 한다. 브라우저 프로세스와 로그인 연결은 클라우드 파일 스냅샷만으로 유지되지 않는다.
- 검색어 없이 각 도메인 루트에 HTTPS HEAD 요청을 보낸 결과 `search.naver.com`, `blog.naver.com`, `m.blog.naver.com`, `nid.naver.com` 모두 네트워크 프록시의 `403 Forbidden` 터널 오류로 접근하지 못했다. 이는 네이버가 응답한 차단 페이지나 CAPTCHA를 관측한 결과가 아니다. 환경 네트워크 허용 목록에 필요한 네이버 도메인/자산과 실제 CDP 호스트를 추가하고, 원격 브라우저 쪽 네트워크도 별도로 확인해야 한다. 실제 검색은 실행하지 않았다.

## DOM 검증과 설정

네이버 DOM은 변경될 수 있다. 이 환경에서는 실제 네이버 화면을 관측하지 않았으므로 검증되지 않은 기본 선택자로 성공을 주장하지 않는다. 연결된 브라우저에서 해당 사용자 주제의 실제 화면을 확인하고 `naver-selectors.json`을 작성해야 한다. 아래 값은 **로컬 테스트 fixture용 선택자 예시**이며 네이버에서 검증된 선택자가 아니다.

```json
{
  "verified_live": false,
  "verified_by": "실제 화면을 확인한 담당자/실행 ID",
  "verified_at": "실제 검증 시점 ISO-8601",
  "blog_tab_selected": "[data-tab=blog][aria-selected=true]",
  "result_card": ".card",
  "organic_marker": "[data-kind=organic]",
  "ad_marker": "[data-kind=ad]",
  "result_link": "a.title",
  "post_body": ".post-body",
  "blocker_selector": ".access-blocker",
  "readiness_timeout_ms": 10000
}
```

실제 관측 뒤 값과 검증 메타데이터를 갱신하고 `verified_live=true`로 표시한다. result_card는 블로그 검색 결과 카드 전체(광고 포함)를 DOM 순서로 선택해야 한다. organic_marker와 ad_marker는 카드의 명시적인 분류 근거여야 한다. 양쪽 모두 있거나 양쪽 모두 없으면 즉시 실패한다. 광고를 단순히 표시 누락으로 organic이라고 추정하지 않는다. result_link는 카드당 정확히 한 실제 네이버 블로그 제목 링크를 선택해야 한다. blog_tab_selected는 단순 탭 존재가 아니라 선택 상태까지 확인하는 선택자다. post_body는 실제 본문 하나만 선택하고, iframe 본문도 네이버 블로그 호스트 안에서 확인한다. blocker_selector는 로그인/차단/CAPTCHA UI를 선택하며 숨겨진 첫 요소 뒤의 보이는 차단 요소도 검사한다. URL 및 본문 텍스트 차단 패턴도 함께 검사한다. 이 계약은 설정의 진실성을 자동 인증하지 않으며, 운영자가 실제 DOM을 확인해야 한다.

```bash
python scripts/naver_collect.py --brief brief.json --classification classification.json --selectors naver-selectors.json --output runs/job-001-query-0
```

## 증거와 실패 의미

`search-evidence.json`에는 요청/관측 검색 URL, 검색어, 선택된 블로그 탭, Asia/Seoul 등 brief 시간대의 시각, 실제 user agent·viewport·screen, 운영자가 제공한 로그인/프로필 조건, 분류/선택자 출처와 ranks를 기록한다. 검색 redirect가 검색어나 블로그 tab 파라미터를 바꾸면 차단한다. 실제 결과 준비와 분류 확인 뒤 검색 전체 화면, 본문 확인 뒤 각 글 화면을 캡처한다. 실패 화면도 가능한 한 남긴다.

본문을 확인한 항목만 `accessed=true`다. `content_summary`는 글자 수·이미지 수·최대 3개 소제목을 설명하는 **구조 관측 요약**이고 모델이 의미를 분석했다는 주장이 아니다. 본문 증거는 최대 180자 발췌, 본문 해시·글자 수와 iframe URL만 보관한다. 전체 외부 글을 JSON에 복사하지 않는다. 스크린샷에는 페이지 화면이 담기므로 비공개 보관하고 로그인 화면 등 개인정보 포함 여부를 검토한다. 의미 비교·공식 사실 검증·analysis.md·outline.json은 실제 researcher의 후속 작업이며 이 수집기가 자동 완료하지 않는다.

- 5개 본문 모두 확인되면 `COLLECTED`, 종료 코드 0. 이는 검색 증거 수집 완료이지 순위 원인 규명이나 원고/검수/발행 완료가 아니다.
- 본문을 찾지 못하거나 일반 탐색 오류가 있으면 해당 항목은 `accessed=false`, 실패 화면을 기록하고 다른 선택된 글을 계속 확인한다. 최종 `PARTIAL_POST_FAILURE`, 종료 코드 2.
- 로그인·CAPTCHA·접근 차단을 감지하면 즉시 전체 수집을 중단한다. 앞서 확인한 글은 유지하며 나머지는 `attempted=false`, `accessed=false`, `NOT_ATTEMPTED`로 구분한다. 우회·재로그인·외부 검색/API fallback은 수행하지 않는다.
- 결과가 5개 미만이거나 광고/DOM/탭이 불명확하면 이미 확인한 순서와 실패 화면을 유지하되 완료로 처리하지 않는다.

로컬 fixture 테스트는 광고 제외 DOM 순서, 분류/주제/모델 계약, 대기 상태, iframe 본문과 지연 로딩, 차단 즉시 중단, 일반 본문 실패 후 계속 수집, 부분 증거, 임시 **로컬 CDP** 연결과 기존 페이지 보존을 검증한다. fixture의 네이버 형태 URL은 Playwright route로 로컬 HTML을 반환하며 실제 네이버 검색을 하지 않는다. 원격 제공자 연결·실제 네이버 선택자·계정 조건은 아직 실증하지 않았다.
