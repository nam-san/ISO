"""삭제 권한 공통 로직 — 정책: 작성자 + 관리자.
관리자(admin)는 상태 무관 전부 삭제, 작성자는 '승인 전' 상태에서만 삭제.
"""
import os
from flask_login import current_user


def can_delete(obj, author_attr='created_by_id', finalized_statuses=()):
    """삭제 가능 여부.
    - admin: 항상 True
    - 작성자 본인: status가 finalized_statuses(승인·완료 등)에 없을 때만 True
    - 그 외: False
    """
    if current_user.is_admin():
        return True
    if getattr(obj, author_attr, None) != current_user.id:
        return False
    status = getattr(obj, 'status', None)
    return status not in finalized_statuses


def remove_file(path):
    """첨부 파일 안전 삭제 (없거나 실패해도 무시)."""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass
