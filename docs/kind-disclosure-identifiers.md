# KIND 공시 식별자 규칙

작성일: 2026-07-02

## 결론

- KIND record의 기본 식별자는 `acpt_no`다.
- KIND 데이터만으로 DART `rcept_no`를 임의 생성하지 않는다. 값은 `None`으로 둔다.
- `doc_no`는 KIND viewer의 문서 선택용 식별자로만 사용한다.
- `correction_families`는 `filtered.json`의 공시 행을 기준으로 `acpt_no` 체인으로 구성한다.
- `compressed-external-html.json`의 `selected_main_doc_no`와 `docs`는 현재 record의 `doc_no` 보강에만 사용한다.

## 문제

공시원문 변환 preview에서 일부 KIND 공시의 `correction_families`,
`rcept_no`, `corp_name`이 비어 있었다. 특히 `20080825000089`에서
`rcept_no`로 `00000000835386`, `00000000846733` 같은 값이 들어가는 문제가
확인되었다.

## 확인한 사실

`20080825000089`를 임시 디렉터리에 다시 다운로드해 확인했다.

- 다운로드 위치: `tmp/kind_recheck_20080825000089/`
- URL: `https://kind.krx.co.kr/common/disclsviewer.do?method=search&acptno=20080825000089&docno=&viewerhost=&viewerport=`
- 기존 `resources/` 데이터는 변경하지 않았다.

Fresh viewer HTML의 식별자 의미:

- `_TRK_PN`과 hidden `acptNo`: `20080825000089`
- `mainDoc` option 값: `00000000835386|N`, `00000000846733|N`, `20080825000247|Y`

따라서 `mainDoc` 값은 DART `rcept_no`가 아니라 KIND viewer의 문서 선택용
`doc_no`다.

## Source 역할

| Source | 역할 | 금지 사항 |
| --- | --- | --- |
| `filtered.json` | 회사명, 상장구분, 정정 family 보강 | `doc_no` source로 보지 않음 |
| `compressed-external-html.json` | 현재 record의 `doc_no`, `selected_main_doc_no`, `docs` 보강 | `rcept_no`나 정정 family 생성에 쓰지 않음 |
| viewer `mainDoc` | viewer 안의 문서 선택 목록 | 정정 family로 해석하지 않음 |
| KIND HTML/viewer HTML | KIND `acpt_no`, 본문 | DART `rcept_no` 복원에 쓰지 않음 |

## 한계

- KIND `acpt_no`와 DART `rcept_no`는 같은 개념이 아니다.
- KIND HTML 워크플로우에서는 DART `rcept_no`를 복원하지 않는다.

## 관련 코드

- `src/finiq/market_desk/web/html_parsers/common/metadata.py`
  - KIND 기본 record에서 `rcept_no=None` 유지
  - `mainDoc` 기반 `rcept_no`/정정 family 합성 제거
- `src/finiq/market_desk/web/disclosure_html_parse.py`
  - `filtered.json` 기반 정정 family 보강
  - `compressed-external-html.json` 기반 현재 record의 `doc_no`, `selected_main_doc_no`, `docs` 보강
- `tests/market_desk/test_kind_web_service.py`
  - `rcept_no`를 임의 생성하지 않는 동작 검증
  - preview에서 현재 record의 `doc_no`가 보강되는 동작 검증

## 검증

```bash
.venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py -k "parse_preview or correction_family or parse_bond_issuance_does_not_fetch_selected_viewer_body"
```

결과: 4 passed.

샘플 확인:

- `20080825000024`: `rcept_no=None`, `doc_no=20080825000037`, `selected_main_doc_no=20080825000037`, `docs_len=4`
- `20080825000089`: `rcept_no=None`, `doc_no=20080825000247`, `selected_main_doc_no=20080825000247`, `docs_len=7`
