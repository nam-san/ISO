"""IMS 공통 유틸리티"""
from datetime import date, timedelta


def get_disposal_alerts(days: int = 30):
    """보존연한 만료 임박 실행기록 조회"""
    from models import Record
    today = date.today()
    cutoff = today + timedelta(days=days)
    return Record.query.filter(
        Record.disposal_date.between(today, cutoff),
        Record.status == 'active'
    ).order_by(Record.disposal_date.asc()).all()


def get_overdue_disposals():
    """보존연한 이미 만료된 실행기록 조회 (자동 폐기 대상)"""
    from models import Record
    today = date.today()
    return Record.query.filter(
        Record.disposal_date < today,
        Record.status == 'active'
    ).all()


def run_auto_disposal():
    """만료 기록 자동 폐기 처리 (상태를 'disposed'로 변경)"""
    from models import db, Record, AuditTrail
    today = date.today()
    overdue = get_overdue_disposals()
    count = 0
    for r in overdue:
        r.status = 'disposed'
        log = AuditTrail(
            user_id=None,
            action='자동폐기',
            target_type='record',
            target_id=r.id,
            target_name=r.title,
            detail=f'보존연한 만료 자동 폐기: {r.disposal_date}'
        )
        db.session.add(log)
        count += 1
    if count:
        db.session.commit()
    return count


def allowed_file(filename: str, allowed_extensions: set) -> bool:
    """파일 확장자 허용 여부 검사"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions
