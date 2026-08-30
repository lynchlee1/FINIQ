# 06 파일과 저장 형식

- `<data_root>/05-internal-html-download/<mode>/<YYYY>/<acpt_no>.html`을 입력으로 받아 `<data_root>/06-sections/<mode>/<YYYY>/<acpt_no>.html`에 저장한다.
- 파생 필터 `<parent_mode>/<mode>`는 상위 `<data_root>/05-internal-html-download/<parent_mode>`를 읽고 `<data_root>/06-sections/<parent_mode>`에 저장한다. 자식 `mode`나 `subfilters/<mode>`의 06단계 출력 폴더는 만들지 않는다.

## `<data_root>/05-internal-html-download/<mode>/<YYYY>/<acpt_no>.html`

- 입력 형식은 [05단계](../05-internal-html/storage.md)의 본문 HTML 계약을 따른다.

## `<data_root>/06-sections/<mode>/<YYYY>/<acpt_no>.html`

- 구조로 완전히 분리한 뒤 정정 section만 제외한 모든 목차 범위를 보존한 출력 HTML 파일이다.
- parser JSON은 만들지 않는다.

## 목차 metadata

- `toc_id`: 원본 `toc_N`, 또는 비목차 영역의 `preamble`·`document`.
- `kind`: `preamble`, `correction`, `cover`, `part`, `section`, `document` 중 하나.
- `level`: `PART`는 0, `SECTION-N`은 N이다. 표지·preamble·단일 문서 본문은 0이다.
- `parent_toc_id`: 앞선 더 낮은 level 중 가장 가까운 목차 ID. 부모가 없으면 `null`이다.
- `is_toc`: 정정 목차와 외부 목차에 연결되는 구조 경계만 `true`다. XForms 문서 제목은 `false`다.
- API의 `section_count`는 preamble·document를 포함한 전체 분리 구간 수이고, `toc_count`는 `is_toc=true`인 실제 목차 수다.
