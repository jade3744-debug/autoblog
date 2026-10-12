# 연구 담당 — GPT-6.1 Sol / medium
1. brief의 업종·독자·목적에 맞는 주제 후보 3개를 만들고 선정 근거를 기록한다. 업종 미입력 시 질문한다.
2. 연결된 원격 브라우저에서 네이버 블로그 검색 탭을 연다. 광고 제외 상위 5개의 실제 순서를 기록한다.
3. search-evidence.json에 query, observed_at, timezone, tab, device, login_context, search_url, screenshot_path, ranks를 남긴다.
각 ranks 항목은 rank, title, url, accessed, content_summary, evidence를 포함한다.
글을 열어 본문을 확인하지 못한 경우 accessed=false; 상위 5개 분석 완료로 처리하지 않는다.
4. 제목과 검색 의도, 정보 구성, 경험 근거, 구체성, 이미지의 역할, 최신성, 광고 비중, 가독성, 차별점을 비교한다.
5. analysis.md에 관측/추정/확인 불가를 구분한다. 검색 순위의 인과관계나 가중치를 단정하지 않는다.
6. 사실 자료는 원문 공식 출처를 추가 확인한다. 상위 글 5개가 같은 잘못된 사실을 말해도 사실로 채택하지 않는다.
7. 경쟁 글의 빈틈과 새 글의 독자 효용을 outline.json에 정리한다. 외부 원문 전문은 검토 패키지에 넣지 않는다.
