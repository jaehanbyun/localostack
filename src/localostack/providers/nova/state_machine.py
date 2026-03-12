"""Nova server state machine."""

from __future__ import annotations

from typing import Optional


# vm_state -> API status 매핑
VM_STATE_TO_STATUS: dict[tuple[str, Optional[str]], str] = {
    ("active", None): "ACTIVE",
    ("building", None): "BUILD",
    ("building", "spawning"): "BUILD",
    ("stopped", None): "SHUTOFF",
    ("error", None): "ERROR",
    ("deleted", None): "DELETED",
    ("paused", None): "PAUSED",
    ("suspended", None): "SUSPENDED",
    ("rescued", None): "RESCUE",
    ("shelved_offloaded", None): "SHELVED_OFFLOADED",
}

# 상태 전이 테이블
# (current_vm_state, action) -> (new_vm_state, new_task_state, new_power_state)
TRANSITIONS: dict[tuple[Optional[str], str], tuple[str, Optional[str], int]] = {
    # 기본 lifecycle
    (None, "create"): ("active", None, 1),
    ("active", "stop"): ("stopped", None, 4),
    ("active", "reboot"): ("active", None, 1),
    ("active", "delete"): ("deleted", None, 0),
    ("stopped", "start"): ("active", None, 1),
    ("stopped", "delete"): ("deleted", None, 0),
    ("error", "delete"): ("deleted", None, 0),
    ("building", "delete"): ("deleted", None, 0),
    # pause / unpause
    ("active", "pause"): ("paused", None, 3),
    ("paused", "unpause"): ("active", None, 1),
    ("paused", "delete"): ("deleted", None, 0),
    # suspend / resume
    ("active", "suspend"): ("suspended", None, 7),
    ("suspended", "resume"): ("active", None, 1),
    ("suspended", "delete"): ("deleted", None, 0),
    # rescue / unrescue
    ("active", "rescue"): ("rescued", None, 1),
    ("stopped", "rescue"): ("rescued", None, 1),
    ("rescued", "unrescue"): ("active", None, 1),
    ("rescued", "delete"): ("deleted", None, 0),
    # shelve / unshelve
    ("active", "shelve"): ("shelved_offloaded", None, 0),
    ("stopped", "shelve"): ("shelved_offloaded", None, 0),
    ("shelved_offloaded", "unshelve"): ("active", None, 1),
    ("shelved_offloaded", "delete"): ("deleted", None, 0),
}

# power_state 값
POWER_STATE = {
    "NOSTATE": 0,
    "RUNNING": 1,
    "PAUSED": 3,
    "SHUTDOWN": 4,
    "CRASHED": 6,
    "SUSPENDED": 7,
}


def get_status(vm_state: Optional[str], task_state: Optional[str]) -> str:
    """vm_state + task_state 조합으로 API status 문자열을 반환한다."""
    if vm_state is None:
        return "UNKNOWN"
    key = (vm_state, task_state)
    status = VM_STATE_TO_STATUS.get(key)
    if status is not None:
        return status
    # task_state가 None이 아닌 경우, None 키로 폴백
    return VM_STATE_TO_STATUS.get((vm_state, None), "UNKNOWN")


def transition(
    current_vm_state: Optional[str], action: str
) -> tuple[str, Optional[str], int] | None:
    """현재 vm_state와 action으로 다음 상태를 반환한다.

    반환값: (new_vm_state, new_task_state, new_power_state) 또는 None(전이 불가)
    """
    return TRANSITIONS.get((current_vm_state, action))
