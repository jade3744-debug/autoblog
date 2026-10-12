# Windows PC 실행 안내

현재 실행 방향은 클라우드에서 사용자 Windows PC로 변경했습니다. GitHub는 코드 보관에 계속 사용합니다.
Windows 10/11용 설치·전용 Chrome 실행·CDP 연결 진단·기존 수집기 실행을 제공합니다.
전체 원고·이미지·검수·승인 후 발행 기능은 아직 없습니다.
실제 Windows PC 및 네이버 실화면 검증은 사용자 PC에서 해야 합니다.

## 최초 실행
1. Google Chrome과 Python 3.12 이상을 설치합니다. Python 설치 시 Add python.exe to PATH가 보이면 체크합니다.
   - https://www.google.com/chrome/
   - https://www.python.org/downloads/windows/
2. GitHub 저장소 Code → Download ZIP으로 내려받아 압축을 풉니다.
3. 예를 들어 C:\\Autoblog에 둡니다. ZIP 안에서 실행하지 않습니다.
4. 01-setup-windows.cmd를 더블클릭합니다. 프로젝트 전용 .venv에 Playwright와 Windows 시간대 데이터를 설치하고 테스트용 Chromium을 내려받습니다. 기존 Chrome은 교체하지 않습니다.
5. 02-open-naver-chrome.cmd를 더블클릭합니다.
6. 열린 전용 Chrome에서 직접 네이버에 로그인합니다. 일반 Chrome의 로그인과 별개입니다.
7. 전용 Chrome을 열어둔 채 03-check-windows.cmd를 실행합니다.
8. CDP_READY는 프로그램과 Chrome의 연결 성공입니다. 로그인·네이버 접근·프로필 재시작 후 로그인 유지는 별도 확인해야 합니다.
9. 전용 Chrome을 정상 종료한 후 02로 다시 열고 로그인 상태가 남아 있는지 직접 확인합니다. 로그인 만료 시 다시 로그인합니다.

관리자 권한은 기본적으로 필요하지 않습니다. 실행기는 자신의 PowerShell 프로세스에만 실행 정책 Bypass를 사용하며 시스템 정책을 영구 변경하지 않습니다.
회사 보안 정책으로 실행이 막히면 IT 담당자에게 문의합니다.

## 접속과 보관
- 전용 프로필: %LOCALAPPDATA%\\Autoblog\\ChromeProfile
- CDP: http://127.0.0.1:9222 (이 Windows PC 안에서만 접속)
- GitHub 파일을 업데이트해도 같은 Windows 계정에서는 위 프로필을 사용합니다.
- 클라우드 VM의 127.0.0.1은 사용자 PC가 아닙니다. 이 구성에는 클라우드 연결이 필요하지 않습니다.
- 일반 Chrome 프로필·비밀번호·쿠키를 읽거나 업로드하지 않습니다.
- 포트 개방·공개 터널은 사용하지 않습니다. 9222가 다른 프로세스/프로필에 연결되면 중단하며 임의로 종료하지 않습니다.
- 자동화 중에는 PC와 전용 Chrome이 켜져 있어야 합니다.

## 실제 수집에 필요한 후속 설정
1. brief.json의 topic에 사용자 주제를 입력합니다. 비어 있으면 WAIT_TOPIC으로 대기합니다.
2. researcher(GPT-6.1 Sol / Medium)가 실제 실행 ID와 함께 classification.json을 작성해야 합니다. 현재 모델 자동 실행기는 없습니다.
3. 실제 PC의 네이버 검색 화면에서 naver-selectors.json을 검증합니다. docs/naver-collector.md의 fixture 예시를 실제 선택자로 오인하지 않습니다.
4. 이 파일들이 준비된 뒤에만 04-collect-naver.cmd를 실행합니다. 결과는 runs 아래 고유 폴더에 저장합니다.
5. 04는 실제 검색 및 상위 글 열람을 할 수 있지만 원고·이미지·발행을 수행하지 않습니다.
6. CAPTCHA·로그인·접근 차단 시 중단하고 사용자가 처리합니다.

PC 브라우저와 연결해 개발·실행할 때는 PC에서 실행되는 Codex 도구가 필요합니다.
클라우드 환경을 삭제할 필요는 없지만 이 PC 브라우저에 클라우드 localhost로 연결할 수 없습니다.
기존 지정 모델과 Medium 조건은 유지합니다. 다음 단계에서 PC용 Codex 연결·선택자·로그인을 검증합니다.

## 문제 해결
- Python not found: Python 설치 후 실행 창을 다시 열고 01 재실행.
- Chrome not found: Google Chrome 설치.
- Port 9222 belongs to another process/profile: 해당 프로세스를 직접 확인. 자동 강제 종료하지 않음.
- CDP did not start: 전용 Chrome만 정상 종료 후 02 재실행.
- Missing classification/selectors: 연구 결과와 실화면 선택자 검증이 필요.
- 시간대 오류: 01의 tzdata 설치 성공 여부 확인.
- 기존 환경을 덮어쓰지 말고 오류 메시지를 전달하면 해당 단계부터 수정 가능.

## 검증 범위
공통 Python 로직은 테스트로 검증합니다. 브라우저 fixture는 Playwright 설치 Chromium으로 변경해 Windows에서도 실행할 수 있도록 구성합니다.
현재 작성 환경은 Linux이므로 PowerShell·Windows Chrome 실제 실행은 이곳에서 검증하지 못합니다.
