# 05 로컬 프록시 설정

Proton VPN 앱 자체는 시스템 기본 경로 하나만 만든다. 여러 IP 경로를 함께 쓰려면 Proton 계정에서 경로마다 서로 다른 WireGuard 설정 파일을 내려받고, 각 파일을 별도 `wireproxy` 프로세스로 실행한다. 비밀키가 들어 있는 WireGuard 설정 파일은 프로젝트에 저장하거나 커밋하지 않는다.

WireGuard 설정을 직접 복사하지 않고 불러오는 최소 `wireproxy` 설정은 다음과 같다.

```ini
WGConfig = /absolute/path/to/proton-route-1.conf

[http]
BindAddress = 127.0.0.1:25001
```

두 번째 설정은 다른 Proton WireGuard 파일과 포트 `25002`를 사용한다. `com.finiq.wireproxy.routeN`은 포트 `25000 + N`을 사용하고 등록 범위는 1~7이다. FINIQ는 저장된 프록시 URL의 실제 포트로 이 범위에 해당하는 LaunchAgent만 실행한다. 다른 localhost 포트는 사용자가 관리하는 프록시로 보고 lifecycle 대상에 넣지 않는다.

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

설정 뒤의 04·05단계 저장 작업부터 직접 연결과 등록된 프록시를 함께 사용한다. FINIQ 백엔드는 시작할 때 설정 URL의 포트와 일치하는 `com.finiq.wireproxy.routeN` LaunchAgent를 실행하고 종료할 때 함께 정지한다. 시작 도중 한 경로라도 실패하면 앞서 실행한 경로를 정지하고 백엔드 시작을 중단한다. FINIQ는 WireGuard 비밀키를 읽지 않는다.
