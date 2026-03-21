# TODOS

## P1: Phase 6 — Plugin System MVP
**What:** entry_points 기반 Provider 플러그인 시스템 도입 + 기존 10개 서비스 마이그레이션
**Why:** 커뮤니티가 새 OpenStack 서비스를 쉽게 추가할 수 있는 확장 인프라. DRY 개선 효과.
**Pros:** 생태계 성장 기반, 기존 서비스 등록 패턴 통합, 코드 중복 제거
**Cons:** 기존 10개 서비스 리팩토링 필요 (파일 20+개 터치), 하위 호환성 위험
**Context:** CEO Review에서 수락 → Eng Review에서 Phase 6으로 분리 (complexity smell: 파일 20+개).
Phase 5(PyPI, pytest, Terraform, CLI UX) 안정화 후 진행.
entry_points group: "localostack.providers", BaseProvider.create_app() → (FastAPI, port, service_name).
방어적 로딩: try/except per plugin, 실패 시 log + skip.
**Effort:** L (human ~2주 / CC ~4시간)
**Priority:** P1
**Depends on:** Phase 5 완료 + 안정화

## P2: CONTRIBUTING.md + Plugin Development Guide
**What:** CONTRIBUTING.md 작성 + 플러그인 개발자를 위한 가이드 문서
**Why:** Plugin system 도입 후 커뮤니티 기여자가 새 Provider를 쉽게 추가할 수 있어야 함
**Pros:** 기여 장벽 감소, 커뮤니티 성장 가속
**Cons:** 문서 유지보수 부담 (Plugin interface 변경 시 동기화 필요)
**Context:** Phase 5에서 Plugin system(entry_points 기반)이 도입됨. BaseProvider interface 문서화, 예제 플러그인, 테스트 방법 포함.
**Effort:** S (human ~1일 / CC ~30분)
**Priority:** P2
**Depends on:** Phase 5 Step 5 (Plugin system) 완료

## P3: Plugin Advanced Features (Phase 6)
**What:** Plugin 설정 주입, 서비스 간 의존성 해결, hot-reload
**Why:** MVP plugin system은 등록만 지원. 고급 플러그인은 설정과 의존성이 필요
**Context:** Phase 5 Plugin MVP가 안정화된 후 진행
**Effort:** M (human ~1주 / CC ~2시간)
**Priority:** P3
**Depends on:** Phase 5 완료 + 실제 3rd party plugin 수요 확인

## P3: gophercloud Version Compatibility Matrix
**What:** gophercloud (Go OpenStack SDK) 버전별 호환성 매트릭스 자동 테스트
**Why:** Go 기반 도구(Terraform, packer) 사용자를 위한 신뢰 구축
**Context:** Terraform Provider가 gophercloud를 사용. 버전별 동작 차이 문서화.
**Effort:** M (human ~1주 / CC ~2시간)
**Priority:** P3
**Depends on:** Phase 5 Step 4 (Terraform 호환 테스트) 완료

## P3: Performance Benchmark vs DevStack
**What:** LocalOStack vs DevStack 시작 시간, 메모리 사용량, API 응답 시간 벤치마크
**Why:** 마케팅 자료로 활용. "DevStack 대비 100x 빠른 시작"
**Context:** DevStack은 32GB+ RAM, 30분+ 설치 시간. LocalOStack은 ~100MB, ~2초 시작.
**Effort:** S (human ~3일 / CC ~1시간)
**Priority:** P3
**Depends on:** PyPI 배포 완료
