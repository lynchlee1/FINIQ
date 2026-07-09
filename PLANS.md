# Completed Changes

## 2026-07-10 공시원문 변환 metadata SoC 분리

- Purpose: 공시원문 변환 metadata 로드에서 `filtered.json` 값을 읽은 뒤 `compressed-external-html.json` 값으로 덮어쓰는 숨은 fallback을 제거하고, 실제 resources 구조에 맞춰 필드별 SoC를 분리한다.
- Implementation: `filtered.json`은 `disclosures` 목록만 읽고 `company_name`/`market`만 제공하도록 제한했다. `compressed-external-html.json`은 `title`/`selected_main_doc_no`/정정 family만 제공하도록 분리했다. 공통 병합 helper를 제거하고, 서로 다른 필드 책임을 가진 metadata dict만 합치도록 바꿨다. 관련 테스트 fixture를 새 계약에 맞췄다. 사용자 승인 후 공통 parser 규칙 문서도 같은 SoC 계약에 맞췄다.
- Verification: `python3 -m py_compile src/finiq/market_desk/web/features/disclosures/html_parse_common.py src/finiq/market_desk/web/features/disclosures/html_parse_preview.py` 통과. metadata/후보 관련 `python3 -m pytest tests/market_desk/test_kind_web_service.py -q -k "parses_html_files_and_writes_result or metadata_market or metadata_display_title or compressed_title or external_html_main_docs or filtered_disclosures or filter_candidates"` 통과(10 passed, 393 deselected). 실제 `resources/KIND/bond_issuance` metadata index는 records 19,175건, title/doc_no 15,176건, company_name/market 19,175건으로 분리 로드됨을 확인했다. 실제 `resources/KIND/rights_issuance` metadata index는 records 27,461건, title/doc_no 19,975건, company_name/market 27,461건으로 분리 로드됨을 확인했다. 전체 `tests/market_desk/test_kind_web_service.py`는 402 passed, 1 failed이며, 잔여 실패는 기존 사채발행 `기업명(행사대상)` 추출 테스트다.

## 2026-07-10 공시원문 변환 필터 후보 fallback 제거

- Purpose: 공시원문 변환 실행 옵션 후보 생성에서 정식 parser와 다른 별도 HTML row scan 및 무상증자 `증자방식` `"-"` 생성 fallback을 제거해 오탐 가능성을 줄인다.
- Implementation: `build_parse_filter_candidates_payload`의 파일별 후보 추출이 선택된 parser를 실제 실행한 뒤 반환 record의 대상 필드만 사용하도록 바꿨다. 별도 `_structured_row_field_candidate` scanner와 제목 기반 무상증자 `"-"` 후보 생성 분기를 제거하고, 관련 테스트의 "full parser 미실행" 기대를 삭제했다.
- Verification: `python3 -m py_compile src/finiq/market_desk/web/features/disclosures/html_parse_preview.py` 통과. `python3 -m pytest tests/market_desk/test_kind_web_service.py -q -k "filter_candidates"` 통과(3 passed, 400 deselected). 실제 `resources/KIND/bond_issuance`와 `resources/KIND/rights_issuance`의 `filtered.json`/`compressed-external-html.json`을 읽어 metadata fallback 발생 여부를 확인했다.

## 2026-07-09 사채발행 행사 대상/가격 후보 순서 정리

- Purpose: 사채발행 공시원문 변환에서 행사 대상, 행사가액, 행사기간 후보 순서를 CB > EB > BW 및 대칭 단어 규칙에 맞추고, 조정 설명문 숫자가 행사가액으로 잡히는 오탐을 줄인다.
- Implementation: 행사 대상 후보를 `전환대상`/`교환대상`/`인수권행사대상`, `전환에 따라`/`교환에 따라`/`인수권행사에 따라`, `전환으로 발행할`/`교환으로 발행할`/`인수권행사로 발행할` 순서로 통일했다. 구조화된 행사 대상 행은 라벨 오른쪽 셀만 읽고, 긴 문단 안에서는 `주식의 종류:` 또는 `유가증권:` 뒤의 120자 이하 값만 읽도록 제한했다. 행사가액 후보는 `전환가액` -> `교환가액` -> `행사가액` -> `전환가격` -> `교환가격` -> `행사가격` 순서로 통일하고, 라벨 오른쪽 값이 숫자와 단위만으로 구성된 경우에만 읽도록 제한했다. 소수점 값은 `float`로 보존하도록 모델 타입을 확장했다.
- Verification: `python3 -m py_compile src/finiq/market_desk/web/html_parsers/bond_issuance/extractor.py src/finiq/market_desk/web/html_parsers/bond_issuance/models.py` 통과. 실제 `resources/KIND/bond_issuance/kind_html_contents_grouped_sections` 15,175건 재파싱 결과 errors 0건, `resources/KIND/rights_issuance/kind_html_contents_sections` 19,975건 재파싱 결과 errors 0건. 수정 전/후 순수 비교에서 `행사가액`은 2,077건 변경, 이 중 1,723건은 기존 10 이하 오탐성 숫자가 실제 가격으로 바뀌었고 309건은 숫자/단위만 있는 값이 없어 `source_not_found`로 드러났다. `행사시작일`/`행사종료일` 변화는 0건이었다.

## 2026-07-09 공시원문 변환 source fallback 정리

- Purpose: 공시원문 변환에서 wrapper/body 복원과 source preview 파일 탐색 fallback을 줄이고, 테스트 fixture를 metadata 부모 디렉토리 계약에 맞춘다.
- Implementation: common HTML parser의 wrapper body lookup/preserve helper export를 제거하고, summary source lookup은 `source_directory/<acpt_no>.html` 또는 `source_directory/<YYYY>/<acpt_no>.html`의 정확한 파일명만 확인하도록 제한했다. 공통 parser 규칙 문서를 현재 source preview 계약에 맞추고, 관련 테스트 fixture의 `filtered.json`/`compressed-external-html.json` 위치를 입력 디렉토리 부모로 옮겼다.
- Verification: `python3 -m pytest tests/market_desk/test_kind_web_service.py -q` 통과(401 passed).

## 2026-07-09 공시원문 변환 회사명 SoC 고정

- Purpose: `corp_name` 보강을 `filtered.json.company_name` 단일 출처로 고정하고, `compressed-external-html.json` 또는 `header` 기반 회사명 fallback을 제거한다.
- Implementation: HTML parse metadata 탐색을 입력 디렉토리의 한 단계 위 디렉토리로 고정하고, `filtered.json` 로드에서만 `company_name`을 읽도록 분리했다. `compressed-external-html.json` 로드는 정정 family/doc metadata만 보강하며 회사명은 읽지 않는다. preview/filter 후보 metadata 로드 호출부와 공통 파서 규칙 문서를 같은 계약으로 맞췄다.
- Verification: `python3 -m py_compile src/finiq/market_desk/web/features/disclosures/html_parse_common.py src/finiq/market_desk/web/features/disclosures/html_parse_preview.py` 통과. 실제 `resources/KIND/bond_issuance/kind_html_contents_grouped_sections` 15,175건과 `resources/KIND/rights_issuance/kind_html_contents_sections` 19,975건 기준으로 metadata 회사명이 모두 채워지는 것을 확인했고, 문제 예시 `20080924000347`, `20111216000861`, `20150513000264`, `20171228000858`의 `corp_name`이 각각 `filtered.json.company_name` 값으로 반영되는 것을 확인했다.

## 2026-07-09 공시원문 변환 fallback 최소화

- Purpose: 결과 영향이 없는 것으로 확인된 metadata 병합 우선순위와 change-log record 전체 필드 탐색 fallback을 제거하고, 정정공시 묶음 저장 구조를 record 반복 저장에서 최상위 저장으로 바꾼다.
- Implementation: `_merge_metadata_index`의 병합 우선순위 옵션을 제거하고, change-log 비교 필드는 모드별 `CHANGE_LOG_COMPARISON_FIELDS`만 사용하도록 정리했다. parsed JSON은 정정공시 묶음 전체를 최상위 `families`에 저장하고, 각 record에는 `family_id`/`current_sequence`/`family_member_count` 참조 필드만 저장하도록 변경했다. summary, change-log, preview, export, 공통 HTML 파서 규칙 문서, 관련 테스트 fixture를 새 저장 계약에 맞췄다.
- Verification: `python3 -m pytest tests/market_desk/test_kind_web_service.py -q` 통과(401 passed). 병합 우선순위 옵션, 동적 필드 탐색 helper, record 전체 필드 탐색 fallback, 과거 change-log 상수명이 관련 코드에 남지 않았음을 확인했다.
