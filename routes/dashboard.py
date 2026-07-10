from flask import Blueprint, render_template
from flask_login import login_required, current_user
from models import db, Document, Record, Audit, CAPA
from models import Training, CustomerComplaint, DesignChange
from datetime import datetime, date, timedelta
from sqlalchemy import func
from utils import get_disposal_alerts

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@dashboard_bp.route('/dashboard')
@login_required
def index():
    today = date.today()
    thirty_days_later = today + timedelta(days=30)

    # ── ISO 현황 요약 ──────────────────────────────────
    doc_stats = {
        'total':    Document.query.filter_by(status='active').count(),
        'draft':    Document.query.filter_by(status='draft').count(),
        'review':   Document.query.filter_by(status='review').count(),
        'q9001':    Document.query.filter(Document.iso_standard.in_(['ISO9001','통합']), Document.status=='active').count(),
        'e14001':   Document.query.filter(Document.iso_standard.in_(['ISO14001','통합']), Document.status=='active').count(),
        's45001':   Document.query.filter(Document.iso_standard.in_(['ISO45001','통합']), Document.status=='active').count(),
    }

    # ── CAPA 현황 ─────────────────────────────────────
    capa_stats = {
        'open':        CAPA.query.filter_by(status='open').count(),
        'in_progress': CAPA.query.filter_by(status='in_progress').count(),
        'overdue':     CAPA.query.filter(CAPA.due_date < today, CAPA.status.in_(['open','in_progress'])).count(),
    }

    # ── 심사 현황 ─────────────────────────────────────
    audit_stats = {
        'planned':    Audit.query.filter_by(status='planned').count(),
        'upcoming':   Audit.query.filter(
                          Audit.planned_date.between(today, thirty_days_later),
                          Audit.status=='planned'
                      ).count(),
        'completed_year': Audit.query.filter(
                              func.strftime('%Y', Audit.actual_date) == str(today.year),
                              Audit.status=='completed'
                          ).count(),
    }

    # ── 긴급 처리 필요 항목 ───────────────────────────
    urgent_items = []

    # 기한 초과 CAPA
    overdue_capas = CAPA.query.filter(
        CAPA.due_date < today,
        CAPA.status.in_(['open', 'in_progress'])
    ).limit(5).all()
    for c in overdue_capas:
        urgent_items.append({
            'type': 'capa',
            'icon': '⚠️',
            'color': 'danger',
            'title': f'[CAPA 기한초과] {c.capa_number}',
            'detail': c.nc_description[:50] + '...' if c.nc_description and len(c.nc_description) > 50 else (c.nc_description or ''),
            'url': f'/audit/capa/{c.id}'
        })

    # 결재 대기 문서 (팀장/관리자인 경우 review 상태 문서, 일반 직원은 본인 작성 문서 중 review)
    from models import Approval
    if current_user.is_manager():
        pending_docs = Document.query.filter_by(status='review').limit(5).all()
    else:
        pending_docs = Document.query.filter_by(status='review', created_by_id=current_user.id).limit(5).all()
    for d in pending_docs:
        urgent_items.append({
            'type': 'approval',
            'icon': '📋',
            'color': 'warning',
            'title': f'[결재대기] {d.doc_number} {d.title}',
            'detail': f'v{d.version}',
            'url': f'/documents/{d.id}'
        })

    # 30일 내 검토 예정 문서
    review_due = Document.query.filter(
        Document.review_date.between(today, thirty_days_later),
        Document.status == 'active'
    ).limit(3).all()
    for d in review_due:
        urgent_items.append({
            'type': 'review',
            'icon': '📅',
            'color': 'info',
            'title': f'[검토예정] {d.doc_number} {d.title}',
            'detail': f'검토일: {d.review_date}',
            'url': f'/documents/{d.id}'
        })

    # 보존연한 만료 임박 실행기록
    disposal_alerts = get_disposal_alerts(30)
    for r in disposal_alerts[:3]:
        days_left = (r.disposal_date - today).days
        urgent_items.append({
            'type': 'disposal',
            'icon': '🗑️',
            'color': 'warning' if days_left > 7 else 'danger',
            'title': f'[폐기임박] {r.record_number}',
            'detail': f'{r.title} · {days_left}일 후 폐기',
            'url': '/records/'
        })

    # 미처리 고객 클레임 기한 초과
    overdue_complaints = CustomerComplaint.query.filter(
        CustomerComplaint.due_date < today,
        CustomerComplaint.status.in_(['open', 'investigating'])
    ).limit(3).all()
    for c in overdue_complaints:
        urgent_items.append({
            'type': 'complaint',
            'icon': '📞',
            'color': 'danger',
            'title': f'[클레임 기한초과] {c.complaint_number}',
            'detail': f'{c.customer_name} · {c.complaint_type}',
            'url': f'/complaint/{c.id}'
        })

    # 검토 대기 중인 설계변경 요청
    pending_dcr = DesignChange.query.filter_by(status='review').limit(3).all()
    if current_user.is_manager():
        for dc in pending_dcr:
            urgent_items.append({
                'type': 'design',
                'icon': '🔬',
                'color': 'info',
                'title': f'[설계변경 검토요청] {dc.change_number}',
                'detail': f'{dc.product_name} · {dc.change_title[:30]}',
                'url': f'/design/{dc.id}'
            })

    # 법정점검 도래/초과 알림
    from routes.inspection import get_inspection_alerts
    insp_overdue, insp_soon = get_inspection_alerts()
    for t, days in insp_overdue[:4]:
        urgent_items.append({
            'type': 'inspection',
            'icon': '🚨',
            'color': 'danger',
            'title': f'[법정점검 기한초과] {t.name}',
            'detail': f'{t.category} · 예정일 {t.next_due_date} ({-days}일 경과)',
            'url': '/inspection/'
        })
    for t, days in insp_soon[:3]:
        urgent_items.append({
            'type': 'inspection',
            'icon': '🗓️',
            'color': 'warning',
            'title': f'[법정점검 임박] {t.name}',
            'detail': f'{t.category} · {days}일 후 도래 (예정일 {t.next_due_date})',
            'url': '/inspection/'
        })

    # ── 부서별 기록 현황 ──────────────────────────────────
    dept_stats = {
        'training_total': Training.query.count(),
        'training_legal': Training.query.filter_by(training_type='법정의무').count(),
        'complaint_open': CustomerComplaint.query.filter(
            CustomerComplaint.status.in_(['open', 'investigating'])).count(),
        'design_pending': DesignChange.query.filter(
            DesignChange.status.in_(['draft', 'review'])).count(),
        'disposal_soon': len(disposal_alerts),
    }

    return render_template('dashboard.html',
        doc_stats=doc_stats,
        capa_stats=capa_stats,
        audit_stats=audit_stats,
        dept_stats=dept_stats,
        urgent_items=urgent_items,
        today=today,
    )
