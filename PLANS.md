# Completed Changes

## 2026-07-09 Parse preview title injection

- Purpose: 공시원문 preview와 filter candidate 파싱도 저장 파싱과 같은 manifest `title` 주입 경로를 사용하게 맞춘다.
- Implementation: preview helper가 parser 호출 전에 metadata `title`을 찾아 `title=`을 지원하는 parser에만 전달하도록 추가했다. preview 결과 기대값을 주입 제목 기준으로 갱신하고, filter candidate에서 제목 파생 필드가 주입 제목을 쓰는 회귀 테스트를 추가했다. 주입 제목 누락 경고는 의도된 선행 경고로 테스트 기대 순서를 갱신했다. parser 작업과 무관한 `next-env.d.ts`의 dev routes 참조는 기존 stable routes 참조로 되돌렸다.
- Verification: `.venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py` 통과.

## 2026-07-09 Correction family member title source

- Purpose: 외부 압축 HTML 정정 family member 제목 산출에서 `metadata.title -> record.title -> doc.text` fallback을 제거하고, KIND viewer의 `mainDoc.text`만 사용하도록 고정한다.
- Implementation: `_external_html_correction_family()`가 member `title`을 `doc["text"]`에서만 읽도록 변경했다. 기존 회귀 테스트 기대값을 `mainDoc.text` 형식으로 갱신하고, 공통 HTML parser 규칙의 Fallback 최소화 원칙에 동일 계약을 추가했다.
- Verification: `.venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py -k "external_html_main_docs_for_corrections or does_not_fallback_to_metadata_display_title"` 통과. `.venv/bin/python -m py_compile src/finiq/market_desk/web/features/disclosures/html_parse_common.py` 통과.

## 2026-07-09 Parse metadata title fill removal

- Purpose: 공시원문 변환 공통 metadata 보강 단계가 빈 `title`을 다시 채우지 않도록, 제목 원천을 parser 호출 시 주입값 하나로 제한한다.
- Implementation: `_apply_manifest_metadata()`에서 metadata `title` 읽기와 후단 title 채우기를 제거했다. manifest 제목이 있어도 parser 결과의 빈 `title`을 공통 보강 단계가 채우지 않는 회귀 테스트와 공통 parser 문서를 추가했다.
- Verification: `.venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py -k "recover_title or injects_manifest_title_for_bond_parser or injects_manifest_title_for_rights_parser"` 통과. `.venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py -k "parse_bond_issuance or parse_rights_issuance or recover_title"` 통과.

## 2026-07-09 Missing injected title warning

- Purpose: 주입 제목이 없는 비정상 입력을 조용히 정상처럼 저장하지 않고, `title`은 빈 문자열로 두되 강한 경고로 드러낸다.
- Implementation: `bond_issuance`, `rights_issuance` parser가 주입 제목만 저장하도록 유지하면서 제목이 비어 있으면 `strong_warning`과 `parse_warnings`에 `주입 제목이 없습니다.`를 추가한다. 관련 테스트와 parser 문서를 갱신했다.
- Verification: `.venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py -k "parse_bond_issuance or parse_rights_issuance or recover_title or parses_html_files_and_writes_result"` 통과.
