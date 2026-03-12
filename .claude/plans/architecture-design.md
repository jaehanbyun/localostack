# LocalOStack Architecture Design Plan

> OpenStack API를 로컬에서 경량 에뮬레이션하는 오픈소스 프로젝트

## 1. 프로젝트 개요

### 목표
- Docker 컨테이너 하나로 OpenStack 핵심 API를 로컬에서 에뮬레이션
- python-openstackclient, openstacksdk, gophercloud, Terraform OpenStack Provider 호환
- CI/CD 파이프라인에서 실제 OpenStack 없이 통합 테스트 가능

### 핵심 원칙
- **API 피델리티 우선**: 실제 인프라 동작보다 API 응답의 정확성에 집중
- **점진적 확장**: Keystone부터 시작해서 서비스를 하나씩 추가
- **단일 컨테이너**: LocalStack처럼 하나의 Docker 컨테이너로 모든 서비스 실행
- **Zero Config**: `docker run localostack/localostack`으로 바로 시작 가능

---

## 2. 아키텍처 설계

### 2.1 두 가지 접근: 단일 포트 vs 멀티 포트

| 접근 | 장점 | 단점 |
|------|------|------|
| **단일 포트 (LocalStack 방식)** | 설정 단순, 포트 관리 쉬움 | OpenStack 클라이언트가 서비스별 포트를 기대 |
| **멀티 포트 (실제 OpenStack 방식)** | 클라이언트 호환성 높음, 설정 변경 불필요 | 포트 매핑 관리 필요 |

**결정: 멀티 포트 + 단일 프로세스**

OpenStack 클라이언트(openstackclient, Terraform 등)는 Keystone 서비스 카탈로그에서 각 서비스의 엔드포인트 URL을 동적으로 받아오므로, 서비스 카탈로그만 정확하면 어떤 포트든 상관없다. 하지만 **실제 OpenStack과 동일한 포트 매핑**을 기본값으로 사용하면:
- 기존 clouds.yaml 설정을 그대로 재사용 가능
- 디버깅/문서화가 직관적

단, 내부적으로는 **단일 ASGI 프로세스**가 여러 포트를 리슨하는 구조로 구현하여 리소스를 절약한다.

**멀티 포트 구현 방식 (확정):**

Uvicorn은 네이티브로 멀티 포트를 지원하지 않지만, `uvicorn.Server` 프로그래밍 API로 **같은 asyncio 이벤트 루프에서 여러 Server 인스턴스를 `asyncio.gather()`로 동시 실행**할 수 있다. 각 서비스별로 독립된 FastAPI 앱을 생성하고, 포트별로 별도 Uvicorn Server를 할당한다.

> 대안으로 검토한 Hypercorn(`config.bind` 리스트로 네이티브 멀티 바인드 지원, LocalStack이 프로덕션 사용)은
> 모든 포트에 같은 ASGI 앱이 서빙되므로 포트 라우팅 미들웨어가 추가로 필요하다.
> Uvicorn 방식이 서비스별 독립 앱(독립 OpenAPI 문서, 미들웨어)을 자연스럽게 지원하여 채택.

**시그널 핸들링 주의점:** Uvicorn의 `capture_signals()`는 마지막 호출된 서버만 시그널을 캡처한다. 따라서 커스텀 시그널 핸들러로 모든 서버에 `should_exit`를 일괄 전파해야 한다.

```python
# core/gateway.py 핵심 구조
class MultiPortServer:
    def __init__(self):
        self._servers: list[uvicorn.Server] = []

    def add(self, app: FastAPI, host: str, port: int, **kwargs):
        config = uvicorn.Config(app=app, host=host, port=port, **kwargs)
        self._servers.append(uvicorn.Server(config))

    async def serve(self):
        loop = asyncio.get_running_loop()

        def _signal_handler():
            for server in self._servers:
                server.should_exit = True

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _signal_handler)

        # 각 서버를 병렬로 실행
        await asyncio.gather(*(server.serve() for server in self._servers))

    def run(self):
        asyncio.run(self.serve())
```

### 2.2 전체 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Container                          │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              LocalOStack Supervisor                   │    │
│  │         (프로세스 관리, 초기화, 헬스체크)               │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                         │                                    │
│  ┌──────────────────────▼──────────────────────────────┐    │
│  │      단일 asyncio 이벤트 루프 (asyncio.gather)        │    │
│  │                                                       │    │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │    │
│  │  │Uvicorn  │ │Uvicorn  │ │Uvicorn  │ │Uvicorn  │   │    │
│  │  │Server   │ │Server   │ │Server   │ │Server   │   │    │
│  │  │:5000    │ │:8774    │ │:9696    │ │:9292    │   │    │
│  │  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘   │    │
│  │       │           │           │           │         │    │
│  │  ┌────▼────┐ ┌────▼────┐ ┌────▼────┐ ┌────▼────┐   │    │
│  │  │Keystone │ │  Nova   │ │Neutron  │ │ Glance  │   │    │
│  │  │FastAPI  │ │FastAPI  │ │FastAPI  │ │FastAPI  │   │    │
│  │  │  App    │ │  App    │ │  App    │ │  App    │   │    │
│  │  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘   │    │
│  │       │           │           │           │         │    │
│  │  ┌────▼───────────▼───────────▼───────────▼────┐    │    │
│  │  │            Shared State Store                │    │    │
│  │  │         (In-Memory + Optional SQLite)        │    │    │
│  │  └─────────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  Volume Mount: /var/lib/localostack (optional persistence)   │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 서비스 프로바이더 패턴

각 OpenStack 서비스는 독립적인 **Provider** 모듈로 구현한다.

```
localostack/
├── core/
│   ├── gateway.py          # ASGI app, 멀티포트 리스너
│   ├── handler_chain.py    # Chain of Responsibility
│   ├── auth.py             # Keystone 인증 미들웨어
│   ├── state.py            # 상태 저장소 (ProjectStore)
│   ├── config.py           # 설정 관리
│   └── models.py           # 공통 데이터 모델 (BaseResource)
│
├── providers/
│   ├── __init__.py         # Provider 레지스트리
│   ├── base.py             # BaseProvider ABC
│   ├── keystone/
│   │   ├── provider.py     # Keystone API 구현
│   │   ├── models.py       # User, Project, Token, Role 등
│   │   ├── routes.py       # FastAPI 라우터
│   │   └── store.py        # Keystone 전용 상태
│   ├── nova/
│   │   ├── provider.py     # Nova API 구현
│   │   ├── models.py       # Server, Flavor, Keypair 등
│   │   ├── routes.py       # FastAPI 라우터
│   │   ├── store.py        # Nova 전용 상태
│   │   └── state_machine.py # 서버 상태 전이 로직
│   ├── neutron/
│   │   ├── provider.py
│   │   ├── models.py       # Network, Subnet, Port, SecurityGroup 등
│   │   ├── routes.py
│   │   └── store.py
│   ├── glance/
│   │   ├── provider.py
│   │   ├── models.py       # Image
│   │   ├── routes.py
│   │   └── store.py
│   └── cinder/
│       ├── provider.py
│       ├── models.py       # Volume, Snapshot, VolumeType
│       ├── routes.py
│       └── store.py
│
├── cli/
│   └── main.py             # CLI 진입점 (localostack start)
│
├── docker/
│   ├── Dockerfile
│   └── docker-entrypoint.sh
│
└── tests/
    ├── integration/        # openstackclient로 실제 API 호출 테스트
    └── unit/               # 프로바이더 유닛 테스트
```

### 2.4 마이크로버전 전략 (확정)

**결정: 전략 B — 최소 버전 보고 (Nova 2.1, Cinder 3.0)**

openstackclient 기본값이 Nova 2.1이므로 기본 명령어(`server list/create/show/delete`)는 모두 동작한다.
openstacksdk는 `min(resource._max_microversion, server_max)` 협상을 하므로, 서버가 2.1을 보고하면 2.1로 폴백한다.

**MVP 필수 구현사항:**

1. **버전 디스커버리 엔드포인트** (`GET /`) — `version`과 `min_version` 필드 포함
2. **모든 응답에 마이크로버전 헤더** 에코
3. **요청 헤더 파싱** — `X-OpenStack-Nova-API-Version`과 `OpenStack-API-Version` 두 형식 인식
4. **범위 밖 요청 시 HTTP 406** 반환
5. **헤더 없는 요청**은 기본 버전으로 처리

```
# Nova 디스커버리 응답 (GET /)
{
  "versions": [{
    "id": "v2.1",
    "status": "CURRENT",
    "version": "2.1",
    "min_version": "2.1",
    "links": [{"href": "http://localhost:8774/v2.1/", "rel": "self"}]
  }]
}

# 모든 Nova 응답 헤더
X-OpenStack-Nova-API-Version: 2.1
OpenStack-API-Version: compute 2.1
Vary: X-OpenStack-Nova-API-Version, OpenStack-API-Version
```

**주요 마이크로버전 영향 분석:**

| 버전 | 변경 | MVP 영향 |
|------|------|----------|
| 2.1 | 기준선 (v2.0 + 입력 검증) | MVP 타겟 |
| 2.37 | `networks` 파라미터 필수화 | 2.1이면 선택사항이므로 MVP에서 문제 없음 |
| 2.47 | flavor가 ID → 전체 객체 | 2.1이면 ID만 반환, 문제 없음 |

**Phase 2 마이크로버전 확장 우선순위:**
1. Nova 2.37 — `networks` 필수 (Terraform Provider가 높은 버전 사용 가능)
2. Nova 2.47 — flavor 전체 객체 응답
3. Cinder 3.67 — URL에서 project_id 불필요

### 2.5 인증 플로우

Keystone 토큰 기반 인증을 최소한으로 에뮬레이션한다.

```
1. 클라이언트 → POST /v3/auth/tokens (password 인증)
   ├── username/password 검증 (인메모리 사용자 DB)
   ├── UUID 토큰 생성 → 인메모리 맵에 저장
   ├── 서비스 카탈로그 포함하여 응답
   └── X-Subject-Token 헤더로 토큰 반환

2. 클라이언트 → GET /servers (X-Auth-Token: <token>)
   ├── AuthMiddleware: 토큰 맵에서 조회
   ├── 토큰에서 project_id, user_id, roles 추출
   ├── RequestContext에 주입
   └── Nova Provider에 전달 → project_id 기반 리소스 필터링
```

**간소화 결정:**
- Fernet/JWS 대신 UUID 토큰 사용 (인메모리 저장)
- 비밀번호는 평문 비교 (보안은 스코프 밖)
- 토큰 만료는 설정 가능하나 기본 24시간
- 멀티 도메인은 "default" 도메인만 지원 (MVP)

### 2.6 상태 관리

LocalStack의 `AccountRegionBundle` 패턴을 OpenStack에 맞게 변형한다.

```python
# ProjectStore: project_id 기반 리소스 격리
class ProjectStore:
    """
    {
      "project-uuid-1": {
        "servers": {"server-uuid-1": Server(...), ...},
        "networks": {"net-uuid-1": Network(...), ...},
        ...
      },
      "project-uuid-2": { ... }
    }
    """

# 영속성 모드
class PersistenceMode(Enum):
    IN_MEMORY = "memory"       # 기본값, 재시작 시 초기화
    SQLITE = "sqlite"          # SQLite에 저장
    FILE = "file"              # JSON 파일로 덤프/로드
```

### 2.7 서비스 간 의존성 처리

에뮬레이터 내부에서 서비스 간 통신은 **직접 함수 호출**로 처리한다 (HTTP 호출 불필요).

```python
# Nova가 Glance 이미지를 조회할 때
class NovaProvider:
    def __init__(self, glance: GlanceProvider, neutron: NeutronProvider):
        self.glance = glance
        self.neutron = neutron

    def create_server(self, context, request):
        # Glance에서 이미지 존재 여부 확인 (직접 호출)
        image = self.glance.get_image(context, request.image_ref)
        if not image:
            raise ImageNotFound(request.image_ref)

        # Neutron에서 포트 생성 (직접 호출)
        port = self.neutron.create_port(context, network_id=request.network_id)

        # 서버 생성
        server = Server(image_ref=image.id, port_id=port.id, ...)
        return server
```

### 2.8 초기 데이터 (Bootstrap)

컨테이너 시작 시 자동 생성되는 기본 데이터:

```yaml
bootstrap:
  domain:
    id: "default"
    name: "Default"

  project:
    id: "auto-generated"
    name: "admin"
    domain_id: "default"

  user:
    name: "admin"
    password: "password"  # 환경변수로 오버라이드 가능
    domain_id: "default"
    project_id: <admin project>

  roles:
    - { name: "admin" }
    - { name: "member" }
    - { name: "reader" }

  role_assignments:
    - { user: "admin", project: "admin", role: "admin" }

  services:
    - { type: "identity",    name: "keystone",  port: 5000, path: "/v3" }
    - { type: "compute",     name: "nova",      port: 8774, path: "/v2.1" }
    - { type: "network",     name: "neutron",   port: 9696, path: "/v2.0" }
    - { type: "image",       name: "glance",    port: 9292, path: "/v2" }
    - { type: "volumev3",    name: "cinderv3",  port: 8776, path: "/v3" }

  flavors:
    - { name: "m1.tiny",   vcpus: 1, ram: 512,   disk: 1 }
    - { name: "m1.small",  vcpus: 1, ram: 2048,  disk: 20 }
    - { name: "m1.medium", vcpus: 2, ram: 4096,  disk: 40 }
    - { name: "m1.large",  vcpus: 4, ram: 8192,  disk: 80 }
    - { name: "m1.xlarge", vcpus: 8, ram: 16384, disk: 160 }
```

### 2.9 Nova 서버 상태 머신 (확정)

**결정: 기본 동기 모드 + 설정 가능한 비동기 모드**

moto(AWS EC2 mock)와 LocalStack이 모두 동기 방식(즉시 ACTIVE)을 기본으로 사용하며, 모든 주요 클라이언트가 "이미 ACTIVE" 상태를 정상 처리한다.

| 클라이언트 | 동기 모드 호환 |
|-----------|-------------|
| openstacksdk `create_server(wait=True)` | 즉시 ACTIVE → 폴링 없이 반환, 동작함 |
| openstacksdk `create_server(wait=False)` | 즉시 ACTIVE → 동작함 |
| Terraform `openstack_compute_instance_v2` | StateChangeConf 첫 체크에서 ACTIVE 확인, 동작함 |
| openstackclient `server create --wait` | 즉시 ACTIVE → 동작함 |

**서버 빌드 모드 (환경변수 설정):**

```
LOCALOSTACK_SERVER_BUILD_MODE=sync|async|counted
LOCALOSTACK_SERVER_BUILD_DELAY=5     # async 모드: 초 단위 지연
LOCALOSTACK_SERVER_BUILD_STEPS=2     # counted 모드: GET N번 후 ACTIVE
```

- `sync` (기본): create 즉시 `vm_state=active`, GET 시 `status=ACTIVE`
- `async`: 지정 시간 후 BUILD → ACTIVE (asyncio.create_task로 백그라운드 전이)
- `counted`: N번 GET 후 ACTIVE (타이머 불필요, 결정론적)

**MVP 상태 전이 테이블:**

```python
TRANSITIONS = {
    # (current_status, action) -> (new_vm_state, new_task_state, new_power_state)
    (None,       "create"):   ("active",   None,          1),  # ACTIVE (sync)
    ("active",   "stop"):     ("stopped",  None,          4),  # SHUTOFF
    ("active",   "reboot"):   ("active",   None,          1),  # ACTIVE (동기 리부트)
    ("active",   "delete"):   ("deleted",  None,          0),  # DELETED
    ("stopped",  "start"):    ("active",   None,          1),  # ACTIVE
    ("stopped",  "delete"):   ("deleted",  None,          0),  # DELETED
    ("error",    "delete"):   ("deleted",  None,          0),  # DELETED
}
```

**API 응답에 포함되는 상태 필드:**

```json
{
  "server": {
    "status": "ACTIVE",
    "OS-EXT-STS:vm_state": "active",
    "OS-EXT-STS:task_state": null,
    "OS-EXT-STS:power_state": 1,
    "OS-EXT-SRV-ATTR:host": "localostack",
    "OS-EXT-AZ:availability_zone": "nova"
  }
}
```

**vm_state → status 매핑 (Nova 소스 `_STATE_MAP` 기반):**

| vm_state | task_state | → status |
|----------|-----------|----------|
| active | None | ACTIVE |
| building | * | BUILD |
| stopped | None | SHUTOFF |
| error | None | ERROR |
| deleted | * | DELETED |
| paused | None | PAUSED |
| suspended | * | SUSPENDED |

**power_state 값:**

| 값 | 의미 |
|-----|------|
| 0 | NOSTATE (pending) |
| 1 | RUNNING |
| 3 | PAUSED |
| 4 | SHUTDOWN |
| 6 | CRASHED |
| 7 | SUSPENDED |

---

## 3. 기술 스택

| 레이어 | 선택 | 이유 |
|--------|------|------|
| **언어** | Python 3.11+ | OpenStack 생태계와 일치, 빠른 프로토타이핑 |
| **웹 프레임워크** | FastAPI | ASGI, 자동 OpenAPI 문서, 타입 힌트, 비동기 지원 |
| **ASGI 서버** | Uvicorn | FastAPI 권장 서버, asyncio.gather로 멀티 포트 구현 |
| **데이터 모델** | Pydantic v2 | FastAPI 네이티브, 자동 직렬화/검증 |
| **상태 저장** | 인메모리 dict + (옵션) SQLite | 기본은 가볍게, 필요 시 영속성 |
| **컨테이너** | Docker (단일 컨테이너) | LocalStack과 동일한 DX |
| **패키지 관리** | uv | 빠른 의존성 해결 |
| **테스트** | pytest + openstacksdk | 실제 SDK로 통합 테스트 |
| **CI** | GitHub Actions | 오픈소스 표준 |

---

## 4. MVP 범위 (Phase 1)

### 4.1 서비스별 구현 범위

#### Keystone (Identity) — 필수, 최우선
| 엔드포인트 | 설명 |
|-----------|------|
| `POST /v3/auth/tokens` | 토큰 발급 (password 인증) |
| `GET /v3/auth/tokens` | 토큰 검증 (X-Subject-Token) |
| `HEAD /v3/auth/tokens` | 토큰 유효성 확인 |
| `DELETE /v3/auth/tokens` | 토큰 폐기 |
| `GET /v3/auth/catalog` | 서비스 카탈로그 |
| `GET /v3/users` | 사용자 목록 |
| `POST /v3/users` | 사용자 생성 |
| `GET /v3/users/{id}` | 사용자 상세 |
| `GET /v3/projects` | 프로젝트 목록 |
| `POST /v3/projects` | 프로젝트 생성 |
| `GET /v3/projects/{id}` | 프로젝트 상세 |
| `GET /v3/roles` | 역할 목록 |
| `GET /v3/services` | 서비스 목록 |
| `GET /v3/endpoints` | 엔드포인트 목록 |

#### Nova (Compute) — 핵심 가치
| 엔드포인트 | 설명 |
|-----------|------|
| `GET /v2.1/servers` | 서버 목록 |
| `GET /v2.1/servers/detail` | 서버 목록 (상세) |
| `POST /v2.1/servers` | 서버 생성 |
| `GET /v2.1/servers/{id}` | 서버 상세 |
| `DELETE /v2.1/servers/{id}` | 서버 삭제 |
| `POST /v2.1/servers/{id}/action` | os-start, os-stop, reboot |
| `GET /v2.1/flavors` | 플레이버 목록 |
| `GET /v2.1/flavors/detail` | 플레이버 상세 목록 |
| `GET /v2.1/flavors/{id}` | 플레이버 상세 |
| `GET /v2.1/os-keypairs` | 키페어 목록 |
| `POST /v2.1/os-keypairs` | 키페어 생성 |
| `GET /v2.1/limits` | 리소스 제한 |

#### Neutron (Network) — Nova 의존성
| 엔드포인트 | 설명 |
|-----------|------|
| `GET/POST /v2.0/networks` | 네트워크 CRUD |
| `GET/POST /v2.0/subnets` | 서브넷 CRUD |
| `GET/POST /v2.0/ports` | 포트 CRUD |
| `GET/POST /v2.0/security-groups` | 보안 그룹 CRUD |
| `GET/POST /v2.0/security-group-rules` | 보안 그룹 규칙 |

#### Glance (Image) — Nova 의존성
| 엔드포인트 | 설명 |
|-----------|------|
| `GET /v2/images` | 이미지 목록 |
| `POST /v2/images` | 이미지 생성 (메타데이터) |
| `GET /v2/images/{id}` | 이미지 상세 |
| `DELETE /v2/images/{id}` | 이미지 삭제 |
| `PUT /v2/images/{id}/file` | 이미지 파일 업로드 |
| `GET /v2/images/{id}/file` | 이미지 파일 다운로드 |

### 4.2 MVP에서 제외
- Cinder (Block Storage) — Phase 2
- Swift (Object Storage) — Phase 2
- Heat (Orchestration) — Phase 3
- Placement — Phase 3
- 마이크로버전 분기 동작 — Phase 2 (MVP는 2.1/3.0 기본만, 버전별 응답 분기 없음)
- 멀티 리전 — Phase 2
- RBAC (역할 기반 접근 제어) — Phase 2

---

## 5. 구현 순서

### Phase 1: MVP (Keystone + Glance + Neutron + Nova)

```
Step 1: 프로젝트 스캐폴딩
  - uv 프로젝트 초기화
  - FastAPI 앱 설정
  - 멀티 포트 Uvicorn 서버
  - Docker 설정

Step 2: Keystone 구현
  - 토큰 발급/검증 (POST, GET, HEAD, DELETE /v3/auth/tokens)
  - 서비스 카탈로그 (GET /v3/auth/catalog)
  - 사용자/프로젝트/역할 CRUD
  - 인증 미들웨어

Step 3: Glance 구현
  - 이미지 메타데이터 CRUD
  - 이미지 파일 업로드/다운로드 (로컬 파일시스템)
  - 기본 이미지 (cirros) 프리로드

Step 4: Neutron 구현
  - 네트워크/서브넷/포트 CRUD
  - 보안 그룹/규칙 CRUD
  - 기본 네트워크/서브넷 프리로드

Step 5: Nova 구현
  - 서버 CRUD + 상태 머신 (BUILD → ACTIVE → SHUTOFF 등)
  - 플레이버 CRUD
  - 키페어 CRUD
  - 서버 액션 (start, stop, reboot)
  - Glance/Neutron 연동

Step 6: 통합 테스트
  - openstackclient로 전체 워크플로우 테스트
  - openstacksdk로 프로그래밍 방식 테스트
  - Docker 이미지 빌드 및 퍼블리시
```

### Phase 2: 확장 (추후)
- Cinder (Block Storage)
- Swift (Object Storage)
- 마이크로버전 확장 (Nova 2.37 → 2.47, Cinder 3.67)
- 멀티 리전
- Terraform Provider 호환 테스트
- 상태 영속성 (SQLite)
- Nova 비동기 상태 전이 모드 (async, counted)

### Phase 3: 고급 기능 (추후)
- 에러 주입 (Mimic 패턴: 메타데이터 기반 장애 시뮬레이션)
- Placement 서비스
- Heat (Orchestration)
- 웹 대시보드 (Horizon 대체 경량 UI)
- pause/suspend/rescue/shelve 등 확장 상태 전이

---

## 6. 포트 매핑

| 서비스 | 포트 | API 경로 |
|--------|------|----------|
| Keystone | 5000 | `/v3` |
| Nova | 8774 | `/v2.1` |
| Neutron | 9696 | `/v2.0` |
| Glance | 9292 | `/v2` |
| Cinder | 8776 | `/v3/{project_id}` |

---

## 7. 사용 예시 (목표)

```bash
# 시작
docker run -d -p 5000:5000 -p 8774:8774 -p 9696:9696 -p 9292:9292 \
  --name localostack localostack/localostack

# 환경변수 설정
export OS_AUTH_URL=http://localhost:5000/v3
export OS_USERNAME=admin
export OS_PASSWORD=password
export OS_PROJECT_NAME=admin
export OS_USER_DOMAIN_NAME=Default
export OS_PROJECT_DOMAIN_NAME=Default

# openstackclient 사용
openstack server list
openstack server create --flavor m1.small --image cirros my-server
openstack server show my-server
openstack server delete my-server
```

```python
# openstacksdk 사용
import openstack
conn = openstack.connect(
    auth_url='http://localhost:5000/v3',
    project_name='admin',
    username='admin',
    password='password',
    user_domain_name='Default',
    project_domain_name='Default',
)
server = conn.compute.create_server(
    name='test-vm',
    flavor_id='m1.small',
    image_id='cirros',
)
```

---

## 8. 주요 설계 결정 기록

| 결정 | 선택 | 대안 | 이유 |
|------|------|------|------|
| 포트 전략 | 멀티 포트 (실제 OpenStack 호환) | 단일 포트 (LocalStack 방식) | 클라이언트 호환성, 기존 설정 재사용 |
| 멀티 포트 구현 | Uvicorn 멀티 Server (asyncio.gather) | Hypercorn 네이티브 멀티 바인드 | 서비스별 독립 FastAPI 앱, 독립 OpenAPI 문서 |
| 언어 | Python | Go, Rust | OpenStack 생태계와 일치, 프로토타입 속도 |
| 프레임워크 | FastAPI | Flask, Starlette, aiohttp | 자동 문서, 타입 힌트, 비동기 |
| 토큰 형식 | UUID (인메모리) | Fernet, JWS | 구현 단순성, 보안은 스코프 밖 |
| 상태 저장 | 인메모리 dict | Redis, PostgreSQL | 단일 컨테이너 원칙, 외부 의존성 제거 |
| 서비스 간 통신 | 직접 함수 호출 | 내부 HTTP 호출 | 성능, 단순성 |
| 마이크로버전 | 최소 보고 (Nova 2.1, Cinder 3.0) | 높은 버전 보고 + 기본만 구현 | 정직한 보고로 클라이언트가 기대치 조정, 기본 CRUD 모두 호환 |
| Nova 상태 머신 | 기본 동기 (즉시 ACTIVE) + 설정 가능 비동기 | 항상 비동기 (BUILD → 지연 → ACTIVE) | moto/LocalStack 검증 패턴, 모든 클라이언트 호환 |
| 패키지 관리 | uv | pip, poetry | 속도, 현대적 |

---

## Status

- [x] Phase 1 Step 1: 아키텍처 설계
- [x] Phase 1 Step 1: 프로젝트 스캐폴딩 (uv sync, 서버 기동 확인 완료)
- [x] Phase 1 Step 2: Keystone 구현 (토큰 CRUD, 서비스 카탈로그, 사용자/프로젝트/역할 CRUD, 인증 미들웨어)
- [x] Phase 1 Step 3: Glance 구현 (이미지 CRUD, 파일 업로드/다운로드, cirros bootstrap)
- [x] Phase 1 Step 4: Neutron 구현 (네트워크/서브넷/포트/보안그룹 CRUD, MAC/IP 자동할당)
- [x] Phase 1 Step 5: Nova 구현 (서버 CRUD, 상태 머신, 플레이버, 키페어, limits)
- [x] Phase 1 Step 6: 통합 테스트 (22/22 통과, 소스 수정 없음)

---

## Resolved Uncertainties (리서치로 해소됨)

| 항목 | 해소 내용 |
|------|-----------|
| ~~Uvicorn 멀티 포트~~ | 네이티브 미지원이나 `asyncio.gather` + 커스텀 시그널 핸들러로 해결. 코드 패턴 확정 |
| ~~마이크로버전 무시 가능 여부~~ | Nova 2.1, Cinder 3.0 보고 시 기본 CRUD 모두 호환. 디스커버리 엔드포인트 + 응답 헤더만 구현하면 됨 |
| ~~Nova 상태 머신 동기/비동기~~ | 기본 동기(즉시 ACTIVE)가 moto/LocalStack 검증 패턴. 모든 주요 클라이언트 호환 확인 |

## Remaining Risks (실제 구현 시 확인 필요)

| 항목 | 위험도 | 대응 방안 |
|------|--------|-----------|
| Uvicorn `server.serve()` 내부 시그널 충돌 | 낮음 | 커스텀 시그널 핸들러가 모든 서버에 `should_exit` 전파. 통합 테스트로 검증 |
| openstacksdk의 `_max_microversion` 내부 값 | 중간 | 기본 Server 리소스는 2.1로 동작 확인. QuotaSet(2.56), ServerMigration(2.80) 등 고급 리소스는 MVP 스코프 밖 |
| Terraform OpenStack Provider 기본 마이크로버전 | 중간 | gophercloud 기반이며 높은 버전을 기본 요청할 수 있음. Phase 1 통합 테스트에서 실제 확인 필요 |
| keystoneauth 디스커버리 폴백 동작 | 낮음 | `allow_version_hack` 설정 존재. LocalOStack 환경에서의 동작은 통합 테스트로 확인 |
