# Internal HTML Download Reference

## Paths

- `<data_root>/04-external-html-compress/<mode>/compressed-external-html.json`을 입력으로 받아 `<data_root>/05-internal-html-download/<mode>/<YYYY>/<acpt_no>.html`에 본문 HTML을, `<data_root>/05-internal-html-download/<mode>/kind_disclosure_html_manifest.json`에 원본 연결 정보를 저장한다.
- 파생 필터 `<parent_mode>/<mode>`는 상위 `<data_root>/04-external-html-compress/<parent_mode>/compressed-external-html.json`과 `<data_root>/05-internal-html-download/<parent_mode>` 산출물을 사용한다. 자식 `mode`나 `subfilters/<mode>`의 05단계 출력 폴더는 만들지 않는다.

### `<data_root>/04-external-html-compress/<mode>/compressed-external-html.json`

#### I/O Structure

- 접수번호, 공시일 metadata와 선택한 본문 문서 번호를 담은 입력 파일이다.
- `records[].acpt_no`는 저장할 공시를 식별한다.
- `records[].selected_main_doc_no`는 선택한 본문 문서 번호다.
- `records[].metadata.disclosed_at`은 ISO 날짜로 시작한다.
- `kind_proxy_urls`는 localhost HTTP 프록시 URL을 현재 CPU 개수보다 하나 적게 저장한다. 직접 연결을 0번 경로로 사용하고 설정 순서대로 프록시 경로를 추가한다.
- `max_workers`는 모든 연결의 동시 처리 공시 대상 수를 정한다. 경로별 worker 합계는 이 값을 넘지 않으며, 분당 요청 한도와 요청 간격은 연결마다 따로 적용한다.

## Local Proxy Setup

Proton VPN 앱 자체는 시스템 기본 경로 하나만 만든다. 여러 IP 경로를 함께 쓰려면 Proton 계정에서 경로마다 서로 다른 WireGuard 설정 파일을 내려받고, 각 파일을 별도 `wireproxy` 프로세스로 실행한다. 비밀키가 들어 있는 WireGuard 설정 파일은 프로젝트에 저장하거나 커밋하지 않는다.

WireGuard 설정을 직접 복사하지 않고 불러오는 최소 `wireproxy` 설정은 다음과 같다.

```ini
WGConfig = /absolute/path/to/proton-route-1.conf

[http]
BindAddress = 127.0.0.1:25001
```

두 번째 설정은 다른 Proton WireGuard 파일과 포트 `25002`를 사용한다. `com.finiq.wireproxy.routeN`은 포트 `25000 + N`을 사용하고 등록 범위는 1~7이다. FINIQ는 저장된 프록시 URL의 실제 포트로 이 범위에 해당하는 LaunchAgent만 실행한다. 다른 localhost 포트는 사용자가 관리하는 프록시로 보고 lifecycle 대상에 넣지 않는다. 같은 방식으로 현재 CPU 개수보다 하나 적은 수까지 프록시를 추가할 수 있다. 직접 연결을 포함한 전체 경로와 worker 상한은 실행 중 확인한 CPU 개수를 따른다.

```shell
wireproxy -c /absolute/path/to/wireproxy-route-1.conf
wireproxy -c /absolute/path/to/wireproxy-route-2.conf
```

준비된 프록시는 실행 중인 FINIQ 서버에 저장한다.

```shell
curl -X POST http://127.0.0.1:8765/api/settings \
  -H 'Content-Type: application/json' \
  -d '{"kind_proxy_urls":["http://127.0.0.1:25001","http://127.0.0.1:25002"]}'
```

설정 뒤의 04·05단계 저장 작업부터 직접 연결과 등록된 프록시를 함께 사용한다. FINIQ 백엔드는 시작할 때 설정 URL의 포트와 일치하는 `com.finiq.wireproxy.routeN` LaunchAgent를 실행하고 종료할 때 함께 정지한다. 시작 도중 한 경로라도 실패하면 앞서 실행한 경로를 정지하고 백엔드 시작을 중단한다. FINIQ는 WireGuard 비밀키를 읽지 않는다. 04단계는 프록시가 중단된 경로의 대상을 직접 연결로 보내지 않는다. 05단계는 프록시 경로에서 완료하지 못한 대상만 같은 실행의 요청 제한을 이어받은 직접 연결로 한 번 더 보낸다.

### `<data_root>/05-internal-html-download/<mode>/<YYYY>/<acpt_no>.html`

#### I/O Structure

- KIND에서 받은 공시 본문 HTML을 원본 구조로 보존한 출력 파일이다.
- `<YYYY>`는 입력 record의 `metadata.disclosed_at` 연도다.

### `<data_root>/05-internal-html-download/<mode>/kind_disclosure_html_manifest.json`

#### I/O Structure

- 본문 HTML을 원본 공시 metadata와 연결하는 출력 파일이다.
- 파일마다 `source_size_bytes`와 `source_sha256`을 기록한다.
- `format`은 `finiq_disclosure_html_manifest_v2`이며 입력 JSON 전체를 대상으로 한 `source_fingerprint`는 기록하지 않는다. 재사용 판정은 접수번호별 `source_sha256`만으로 하므로 필터를 다시 실행해도 기존 HTML이 무효화되지 않는다.
- 구버전 `finiq_disclosure_html_manifest_v1`은 읽기만 지원하며, 이 경우에만 `source_fingerprint` 비교를 유지한다.
- 파생 필터 작업은 상위 manifest와 HTML 중 자식 `filtered.json`의 `acpt_no` 부분집합만 검증해 사용하며 `selected_main_doc_no`도 상위 04단계 record와 일치해야 한다.
