# 네이버 블로그 Codex 초기 구성 패키지

현재 상태: 새 GitHub 저장소에 올릴 수 있는 **설정·작업 규약·승인 게이트 초기 코드**입니다.
완전 자동화 서비스나 설치 완료된 발행 프로그램은 아닙니다. 실제 네이버 검색, 이미지 생성, 승인 UI, 네이버 에디터 발행 연결은 아직 구현되지 않았습니다.

## 권장 구성
GitHub 비공개 저장소(코드) + 클라우드 작업 실행기(Codex) + 지속 프로필 원격 Chrome(검색/발행) + 인증된 검토 화면(승인) + 비공개 산출물 저장소.
GitHub만 연결해도 네이버 로그인이나 발행 권한이 생기는 것은 아닙니다. 임시 GitHub 러너 안에서 승인 응답을 기다리지 말고 작업 상태를 저장한 뒤 종료하고 승인 이벤트로 발행 작업을 별도 시작합니다.

## 담당 모델
| 작업 | 모델 | 추론 |
|---|---|---|
| 주제 선정·네이버 검색·분석 | gpt-6.1-sol | medium |
| 원고·이미지 기획 | gpt-6-luna | medium |
| 최종 검수 | gpt-6.1-sol | medium |

실제 픽셀 이미지는 별도 이미지 생성 모델이 만듭니다. Luna가 이미지 기획을 담당하는 구성과 픽셀 생성까지 Luna로 하는 구성은 다릅니다. 이미지 엔진은 사용자가 선택하기 전까지 비워 두었습니다. 요청 조건을 충족했다고 허위 보고하거나 다른 모델로 자동 교체하지 않습니다.

## 최초 설정 순서
1. GitHub에서 New repository → 이름 `naver-blog-automation` → Private → Create repository.
2. ZIP을 풀고 폴더 내부 파일을 올립니다. `.codex`, `.github`, `.gitignore`도 포함해야 합니다. GitHub 브라우저 업로드가 숨김 폴더를 제외하면 Git 클라이언트로 올립니다.
3. Codex에서 이 저장소를 연결합니다. 모델 접근 권한과 프로젝트 설정 로딩을 확인합니다.
4. brief.example.json을 brief.json으로 복사하고 업종·대상 독자·블로그 주소를 입력합니다.
5. 지속 프로필을 가진 원격 브라우저를 선택하고 사용자가 직접 네이버에 로그인합니다. 이 환경에 연결되는 브라우저 MCP/Playwright 어댑터를 추가합니다.
6. 이미지 생성 엔진을 결정합니다. Luna의 이미지 기획 + 별도 엔진의 생성에 동의할지 확인해야 합니다.
7. 승인 UI·발행 어댑터를 연결한 뒤 비공개 초안 1건으로 통합 검증하고 운영합니다.

## Codex에 보낼 첫 지시
“AGENTS.md와 brief.json을 읽고 researcher → writer → chief_reviewer로 작업을 위임하세요. 각 에이전트의 지정 모델과 medium 추론을 지키세요. 부족한 브라우저·이미지·승인·발행 연결부터 구현하고 검증하세요. 도구 연결 전에는 네이버 검색 완료나 발행 가능을 보고하지 마세요. 실제 글은 팀장 검수 후 사용자 승인을 기다리세요.”

## 승인 게이트 코드 사용
Python 3.12 이상, 추가 패키지 없이 실행됩니다. `bundle/`에는 제목·원고·실제 이미지·분석·검색 증거·미리보기 등 사용자에게 보여줄 모든 파일을 넣습니다.
review.json과 approval.json은 bundle **밖에** 둡니다.

```bash
python scripts/gate.py digest runs/job-001/bundle
python scripts/gate.py check-review runs/job-001/bundle runs/job-001/review.json
python scripts/gate.py check-publish runs/job-001/bundle runs/job-001/review.json runs/job-001/approval.json
python -m unittest discover -s tests -v
```

approval.json 예시(승인 서비스가 인증된 사용자의 명시적 승인으로만 생성):
```json
{"approved":true,"artifact_sha256":"실제 digest 값","approved_by":"인증된 사용자 ID","approved_at":"2026-10-07T09:00:00+00:00"}
```
게이트는 산출물 변경을 검출하고 내부 검수/승인 누락을 막습니다. 승인자가 진짜 사용자라는 사실까지 검증하지 않습니다. 운영 연결 시 승인 파일 저장소를 사용자 승인 서비스만 쓸 수 있게 하고 AI에는 쓰기 권한을 주지 않아야 합니다.

## 남은 구현과 완료 기준
- 네이버 어댑터: 실제 블로그 탭 1~5위 캡처, 각각 본문 열람, 순위/시간/검색 조건 증거. 미열람 글을 분석 완료로 처리하지 않음.
- 모델 실행기: 역할별 실제 모델·추론·호출 ID 기록. 설정 파일만으로 모든 UI 환경의 모델 선택이 강제된다고 가정하지 않음.
- 이미지 어댑터: 사용자 선택 엔진으로 생성, 파일 저장, Luna 기획/실제 생성 모델 각각 기록.
- 검토 서비스: 검수 통과된 동일 버전만 제시. 수정 시 재검수·재승인. 승인 보류·거절 지원.
- 발행 어댑터: 발행 직전에 게이트를 검사하고 승인 버전만 업로드. 로그인 만료 시 재로그인 요청. 제목·본문·이미지 순서·블로그 계정 확인.
- 중복 방지: job_id와 digest별 상태 및 잠금. 발행 도중 응답 유실이면 재발행하지 않고 공개 여부를 먼저 확인.
- 사후 검증: 공개 URL과 실제 본문·이미지 확인 뒤 PUBLISHED. 클릭 성공만으로 완료 처리하지 않음.

## 품질 원칙
내부 점수 85점은 네이버의 SEO/DIA 점수가 아닙니다. 상위 글 비교로 실제 랭킹 결정 원인을 확정할 수 없습니다. 키워드 횟수·이미지 개수만으로 상위 노출을 보장하지 않습니다. 허위 후기 대신 출처가 있는 설명·유용한 비교·독자 질문에 대한 답을 작성합니다.

## 클라우드 실행과 비용
수동 Codex 작업과 GitHub Actions 자동 호출은 인증 방식이 다를 수 있습니다. GitHub 자동 호출은 공식 Codex Action과 별도 API 인증을 우선 검토합니다. Plus 구독만으로 API 호출 비용이나 클라우드 브라우저 비용이 모두 포함된다고 가정하지 않습니다. API 키·브라우저 인증 파일을 저장소에 올리지 않습니다.
현재 check.yml은 코드 테스트만 수행합니다. 검색·작성·발행 자동 실행이나 정기 예약은 등록하지 않았습니다.

## 근거 문서
- https://learn.chatgpt.com/docs/agent-configuration/subagents
- https://learn.chatgpt.com/docs/non-interactive-mode
- https://developers.openai.com/api/docs/models/gpt-6-luna
- https://developers.openai.com/api/docs/guides/image-generation
- https://searchadvisor.naver.com/guide/report-seo (웹사이트 가이드이며 블로그 DIA 배점표는 아님)
