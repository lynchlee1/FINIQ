# HTML Section Split Reference

## Paths

- `<data_root>/05-internal-html-download/<mode>/<YYYY>/<acpt_no>.html`을 입력으로 받아 `<data_root>/06-sections/<mode>/<YYYY>/<acpt_no>.html`에 저장한다.
- 허용하는 상대 배치는 `<mode>/<YYYY>/<acpt_no>.html`뿐이다. `06-sections/<YYYY>/`는 만들지 않고, 그 모양을 읽거나 보정하지도 않는다.
- 조건검색 필터를 바꾸면 현재 소유 모드 폴더에 저장한다. 직전에 쓴 `06-sections/<다른 mode>` 경로가 남아 있어도 그 폴더에 이어 쓰지 않는다.
- 파생 필터 `<parent_mode>/<mode>`는 상위 `<data_root>/05-internal-html-download/<parent_mode>`를 읽고 `<data_root>/06-sections/<parent_mode>`에 저장한다. 자식 `mode`나 `subfilters/<mode>`의 06단계 출력 폴더는 만들지 않는다.

### `<data_root>/05-internal-html-download/<mode>/<YYYY>/<acpt_no>.html`

#### I/O Structure

- KIND 본문과 생성 형식별 구조 경계를 원본 구조로 보존한 입력 HTML 파일이다.
- `id="toc_N"`이 있는 문서는 해당 ID가 외부 목차와 내부 본문을 연결하는 원본 식별자다. `COVER-TITLE`, `PART`, `SECTION-N` class가 표지·부·section 깊이를 정한다.
- `workers`는 목차 조합 요약, 분리 저장과 결과 검사에서 동시에 처리할 HTML 파일 수를 정한다.
- `progress_interval`은 전체 검사와 분리 저장 중 몇 건마다 우측 `실행 현황` 로그를 갱신할지 정하는 1 이상의 정수다.

### `<data_root>/06-sections/<mode>/<YYYY>/<acpt_no>.html`

#### I/O Structure

- 구조로 완전히 분리한 뒤 정정 section만 제외한 모든 목차 범위를 보존한 출력 HTML 파일이다.
- 실행 완료 응답의 `section_patterns`는 전체 실행 입력에서 확인한 고유 목차 구조와 구조별 구간·공시 수를 담으며, 06단계 화면의 `목차 구조 종류`에 모두 표시한다. 화면은 `sections[].kind`, `level`, `is_toc`으로 사람이 읽을 수 있는 줄 단위 위계와 실제 목차 수를 만들고, `will_remove=true`인 구간에는 `제거 예정`을 표시한다. `signature`, `toc_id`는 사용자용 구조 문장으로 노출하지 않는다.
- 정정 판별은 분리된 section이 둘 이상일 때만 첫 section 제목의 공백을 제거하고 단일 토큰 `정정`을 확인한다. 첫 section이 정정이면 그것만 제외하고, section이 하나뿐인 정정공시와 두 번째 이후 section은 검사하거나 제외하지 않는다. 목차 경계 탐지에는 문자열을 사용하지 않는다.
- Manual selection이나 목차 선택용 모드별 저장 규칙은 사용하지 않는다.
- HTML은 `<mode>/<YYYY>/<acpt_no>.html`만 사용한다. `06-sections` 바로 아래 연도 폴더, 다른 모드 폴더, 더 깊은 임의 배치는 허용하지 않는다.
- parser JSON은 만들지 않는다.

### Section metadata

- `toc_id`: 원본 `toc_N`, 또는 비목차 영역의 `preamble`·`document`.
- `kind`: `preamble`, `cover`, `part`, `section`, `document` 중 하나.
- `level`: `PART`는 0, `SECTION-N`은 N이다. 표지·preamble·단일 문서 본문은 0이다.
- `parent_toc_id`: 앞선 더 낮은 level 중 가장 가까운 목차 ID. 부모가 없으면 `null`이다.
- `is_toc`: 외부 목차와 연결되는 구조 경계만 `true`다. XForms 문서 제목은 `false`다.
- API의 `section_count`는 preamble·document를 포함한 전체 분리 구간 수이고, `toc_count`는 `is_toc=true`인 실제 목차 수다.
