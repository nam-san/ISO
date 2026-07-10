"""관계부서 합의 결재 공통 로직 — 문서(절차서)·내부심사 계획에 다부서 병렬 합의 적용.

흐름: 작성자가 합의(검토)부서를 지정 → 각 부서의 검토/승인 권한자가 합의(agree)/반려(disagree)
     → 반려 0 & 미처리 0 이어야 최종 승인 가능(하드 게이트). 합의부서 미지정 시 게이트는 통과.
"""
from datetime import datetime
from models import db, Concurrence, Department


def get_list(target_type, target_id):
    """대상의 합의 목록 (부서 순)."""
    return (Concurrence.query
            .filter_by(target_type=target_type, target_id=target_id)
            .join(Department, Concurrence.department_id == Department.id)
            .order_by(Department.id).all())


def set_departments(target_type, target_id, dept_ids):
    """지정 합의부서 동기화 — 신규 부서는 pending 생성, 해제된 미처리 부서는 삭제."""
    existing = {c.department_id: c for c in Concurrence.query.filter_by(
        target_type=target_type, target_id=target_id).all()}
    want = {int(d) for d in dept_ids if d}
    for did in want:
        if did not in existing:
            db.session.add(Concurrence(target_type=target_type, target_id=target_id,
                                       department_id=did, status='pending'))
    for did, c in existing.items():
        if did not in want and c.status == 'pending':
            db.session.delete(c)


def reset(target_type, target_id):
    """모든 합의를 pending 으로 초기화 (반려 후 재상신용)."""
    for c in Concurrence.query.filter_by(target_type=target_type, target_id=target_id).all():
        c.status = 'pending'
        c.acted_by_id = None
        c.comment = None
        c.acted_at = None


def status_counts(target_type, target_id):
    rows = Concurrence.query.filter_by(target_type=target_type, target_id=target_id).all()
    return {
        'total': len(rows),
        'agreed': sum(1 for r in rows if r.status == 'agreed'),
        'disagreed': sum(1 for r in rows if r.status == 'disagreed'),
        'pending': sum(1 for r in rows if r.status == 'pending'),
    }


def can_finalize(target_type, target_id):
    """최종 승인 가능 = 반려 0 & 미처리 0 (전원 동의 또는 합의부서 없음)."""
    c = status_counts(target_type, target_id)
    return c['disagreed'] == 0 and c['pending'] == 0


def can_concur(user, department_id):
    """해당 부서 소속의 검토/승인 권한자(또는 관리자)만 합의 결재 가능."""
    if user.is_admin():
        return True
    return (user.department_id == department_id
            and (user.has_review() or user.has_approve()))


def act(concurrence, user, action, comment=None):
    """합의(agree)/반려(disagree) 처리."""
    concurrence.status = 'agreed' if action == 'agree' else 'disagreed'
    concurrence.acted_by_id = user.id
    concurrence.comment = comment
    concurrence.acted_at = datetime.utcnow()
