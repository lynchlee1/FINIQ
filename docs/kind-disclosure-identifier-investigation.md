# KIND 공시 식별자 검증 정리

작성일: 2026-07-02

## 배경

공시원문 변환 preview에서 일부 KIND 공시의 `correction_families`, `rcept_no`, `기업명(발행사)`가 비어 보였다. 특히 `20080825000089`에서 `rcept_no`로 `00000000835386`, `00000000846733` 같은 값이 들어가는 문제가 확인되었다.

## 시도한 것

1. Preview 입력 디렉터리 파싱 시 주변 메타데이터를 함께 읽도록 확인했다.
   - 대상: `filtered.json`, `compressed-external-html.json`, manifest.
   - 목적: HTML 본문만으로 알 수 없는 `기업명(발행사)`, 상장구분, 정정 family 정보를 preview record에 보강.

2. `20080825000089`를 별도 임시 디렉터리에 다시 다운로드해서 검증했다.
   - 다운로드 위치: `tmp/kind_recheck_20080825000089/`
   - URL: `https://kind.krx.co.kr/common/disclsviewer.do?method=search&acptno=20080825000089&docno=&viewerhost=&viewerport=`
   - 기존 `resources/` 아래 데이터는 오염시키지 않았다.

3. fresh viewer HTML에서 식별자 의미를 확인했다.
   - `_TRK_PN`과 hidden `acptNo`는 `20080825000089`.
   - `mainDoc` option 값은 `00000000835386|N`, `00000000846733|N`, `20080825000247|Y`.
   - 따라서 `00000000835386`, `00000000846733`, `20080825000247`은 DART `rcept_no`가 아니라 KIND viewer의 문서 선택용 `doc_no`이다.

4. 정정 family source of truth를 분리했다.
   - `mainDoc` 목록은 viewer 안의 문서 선택 목록일 뿐, 정정공시 family를 만들 source로 쓰지 않는다.
   - 정정 family는 `filtered.json`의 공시 행을 기준으로 `company_key`/제목 base/공시시각/정정 여부를 이용해 `acpt_no` 체인으로 구성한다.

5. `doc_no` 보강 경로를 복구했다.
   - `filtered.json`의 `doc_no`는 현재 데이터에서 비어 있다.
   - `compressed-external-html.json`에는 `selected_main_doc_no`와 `docs`가 있으므로, 현재 record의 `doc_no`/`selected_main_doc_no`/`docs` 보강에만 사용한다.
   - 이 값은 `rcept_no`나 정정 family 생성에는 사용하지 않는다.

## 확인된 한계

1. KIND 저장본만으로 DART `rcept_no`는 알 수 없다.
   - KIND `acpt_no`와 DART `rcept_no`는 같은 개념이 아니다.
   - KIND viewer의 `mainDoc` 값도 DART `rcept_no`가 아니다.
   - 따라서 현재 KIND HTML, viewer HTML, `filtered.json`, `compressed-external-html.json`만으로 DART `rcept_no`를 복원하면 안 된다.

2. `mainDoc`를 정정 family로 쓰면 오염된다.
   - `mainDoc`는 viewer에서 선택 가능한 본문 문서 목록이다.
   - 과거 문서가 섞여 있어 정정공시 체인처럼 보일 수 있지만, 이것을 `correction_families`로 해석하면 잘못된 family가 만들어진다.

3. `filtered.json`에는 family member별 `doc_no`가 없다.
   - 현재 확인한 `filtered.json`의 `doc_no`는 비어 있다.
   - 그래서 정정 family member의 `doc_no`는 현재 데이터 기준으로 `None`이 맞다.
   - 단, 현재 preview record 자체의 `doc_no`는 `compressed-external-html.json`의 `selected_main_doc_no`로 보강 가능하다.

4. DART `rcept_no`가 꼭 필요하면 별도 매핑 source가 필요하다.
   - 가능한 후보는 DART API, DART 원문 다운로드 이력, 또는 KIND-DART 식별자 매핑을 가진 별도 데이터셋이다.
   - 현재 KIND viewer 재다운로드만으로는 그 매핑이 나오지 않았다.

## 최종 처리 방향

1. KIND record의 기본 식별자는 `acpt_no`로 둔다.
2. KIND에서 DART `rcept_no`를 임의 생성하지 않는다. 값은 `None`으로 둔다.
3. `doc_no`는 KIND viewer 문서 선택용 식별자로만 사용한다.
4. `correction_families`는 `filtered.json`의 공시 행 기반 `acpt_no` 체인으로 구성한다.
5. `compressed-external-html.json`의 `selected_main_doc_no`/`docs`는 현재 record의 `doc_no` 보강에만 사용한다.

## 검증 결과

Targeted test:

```bash
.venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py -k "parse_preview or correction_family or parse_bond_issuance_does_not_fetch_selected_viewer_body"
```

결과: 4 passed.

샘플 확인:

- `20080825000024`: `rcept_no=None`, `doc_no=20080825000037`, `selected_main_doc_no=20080825000037`, `docs_len=4`
- `20080825000089`: `rcept_no=None`, `doc_no=20080825000247`, `selected_main_doc_no=20080825000247`, `docs_len=7`

## 관련 코드

- `src/finiq/market_desk/web/html_parsers/common/metadata.py`
  - KIND 기본 record에서 `rcept_no=None` 유지.
  - `mainDoc` 기반 `rcept_no`/정정 family 합성 제거.

- `src/finiq/market_desk/web/disclosure_html_parse.py`
  - `filtered.json` 기반 정정 family 보강.
  - `compressed-external-html.json` 기반 현재 record `doc_no`/`selected_main_doc_no`/`docs` 보강.

- `tests/market_desk/test_kind_web_service.py`
  - `rcept_no`를 임의 생성하지 않는 동작 검증.
  - preview에서 현재 record의 `doc_no`가 보강되는 동작 검증.
