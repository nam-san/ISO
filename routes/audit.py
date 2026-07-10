from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from models import (db, Audit, CAPA, CAPAAttachment, Department, User, AuditTrail,
                    AuditAuditor, AuditTarget, ChecklistTemplate, AuditChecklistItem)
from routes.checklist_data import seed_checklist_templates, standards_for
from datetime import datetime, date
import os

audit_bp = Blueprint('audit', __name__)

RESULT_KR = {'pending': '미점검', 'conform': '적합', 'nonconform': '부적합',
             'observation': '관찰', 'na': '해당없음'}
STAGE_KR = {'draft': '작성중', 'review': '검토중', 'reviewed': '검토완료(승인대기)', 'approved': '승인완료'}


def _can_review():
    return current_user.has_review()


def _can_approve():
    return current_user.has_approve()


# ════════════════════════════════════════════════════════════
# 목록
# ════════════════════════════════════════════════════════════
@audit_bp.route('/')
@login_required
def index():
    audits = Audit.query.order_by(Audit.planned_date.desc()).all()
    open_capas = CAPA.query.filter(CAPA.status.in_(['open', 'in_progress'])).count()
    return render_template('audit/index.html', audits=audits, open_capas=open_capas,
                           stage_kr=STAGE_KR)


# ════════════════════════════════════════════════════════════
# 신규 심사계획 (심사원·대상부서 지정 포함)
# ════════════════════════════════════════════════════════════
@audit_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_audit():
    if not current_user.has_edit():
        flash('심사계획 작성 권한이 없습니다.', 'danger')
        return redirect(url_for('audit.index'))

    if request.method == 'POST':
        planned_date = datetime.strptime(request.form['planned_date'], '%Y-%m-%d').date()
        year = planned_date.year
        count = Audit.query.filter(Audit.audit_number.like(f'AUD-{year}-%')).count() + 1

        ps = request.form.get('period_start')
        pe = request.form.get('period_end')

        audit = Audit(
            audit_number=f'AUD-{year}-{count:03d}',
            title=request.form['title'],
            audit_type=request.form.get('audit_type', 'internal'),
            iso_standard=request.form.get('iso_standard'),
            planned_date=planned_date,
            period_start=datetime.strptime(ps, '%Y-%m-%d').date() if ps else None,
            period_end=datetime.strptime(pe, '%Y-%m-%d').date() if pe else None,
            audit_criteria=request.form.get('audit_criteria'),
            scope=request.form.get('scope'),
            status='planned',
            plan_status='draft',
            created_by_id=current_user.id,
        )
        db.session.add(audit)
        db.session.flush()

        # 심사원 지정 (다중, 선임 1명)
        lead_id = request.form.get('lead_auditor_id', type=int)
        auditor_ids = request.form.getlist('auditor_ids')
        added_auditors = set()
        if lead_id:
            db.session.add(AuditAuditor(audit_id=audit.id, user_id=lead_id, is_lead=True))
            added_auditors.add(lead_id)
        for aid in auditor_ids:
            aid = int(aid)
            if aid not in added_auditors:
                db.session.add(AuditAuditor(audit_id=audit.id, user_id=aid, is_lead=False))
                added_auditors.add(aid)

        # 심사 대상 부서 지정 (다중)
        target_ids = request.form.getlist('target_dept_ids')
        for did in target_ids:
            db.session.add(AuditTarget(audit_id=audit.id, department_id=int(did),
                                       audit_date=planned_date))

        db.session.add(AuditTrail(user_id=current_user.id, action='심사계획등록',
                                  target_type='audit', target_id=audit.id, target_name=audit.title))
        db.session.commit()
        flash(f'심사계획 [{audit.audit_number}]이 등록되었습니다. 체크리스트를 생성하세요.', 'success')
        return redirect(url_for('audit.audit_detail', audit_id=audit.id))

    departments = Department.query.filter_by(is_active=True).all()
    # 심사원 후보: 내부심사자로 지정된 활성 사용자만 (권한관리에서 지정)
    auditors = User.query.filter_by(is_active=True, is_auditor=True).order_by(User.name).all()
    return render_template('audit/new_audit.html', departments=departments, users=auditors,
                           today=date.today())


# ════════════════════════════════════════════════════════════
# 심사 상세 (단계 개요)
# ════════════════════════════════════════════════════════════
@audit_bp.route('/<int:audit_id>')
@login_required
def audit_detail(audit_id):
    audit = Audit.query.get_or_404(audit_id)
    auditors = audit.auditors.all()
    targets = audit.targets.all()
    capas = audit.capas.all()

    # 부서별 체크리스트 진행률
    sheet_progress = []
    for t in targets:
        items = AuditChecklistItem.query.filter_by(audit_id=audit.id,
                                                   department_id=t.department_id).all()
        total = len(items)
        checked = sum(1 for i in items if i.result != 'pending')
        nc = sum(1 for i in items if i.result == 'nonconform')
        sheet_progress.append({
            'target': t, 'total': total, 'checked': checked, 'nc': nc,
            'pct': int(checked / total * 100) if total else 0,
        })

    has_checklist = AuditChecklistItem.query.filter_by(audit_id=audit.id).count() > 0
    users = User.query.filter_by(is_active=True).order_by(User.name).all()

    # 관계부서 합의 결재 현황
    from concurrence import get_list, status_counts, can_finalize, can_concur
    concurrences = get_list('audit', audit.id)
    for cc in concurrences:
        cc.can_act = can_concur(current_user, cc.department_id)
    concur_counts = status_counts('audit', audit.id)
    concur_can_final = can_finalize('audit', audit.id)
    concur_dept_options = Department.query.filter_by(is_active=True).order_by(Department.id).all()

    return render_template('audit/detail.html',
        audit=audit, auditors=auditors, targets=targets, capas=capas,
        sheet_progress=sheet_progress, has_checklist=has_checklist,
        users=users, stage_kr=STAGE_KR, result_kr=RESULT_KR,
        can_review=_can_review(), can_approve=_can_approve(), today=date.today(),
        concurrences=concurrences, concur_counts=concur_counts,
        concur_can_final=concur_can_final, concur_dept_options=concur_dept_options)


@audit_bp.route('/<int:audit_id>/delete', methods=['POST'])
@login_required
def delete_audit(audit_id):
    from deletion import can_delete
    from models import Concurrence
    audit = Audit.query.get_or_404(audit_id)
    # 작성자는 완료 전만, 관리자는 전부
    if not can_delete(audit, 'created_by_id', finalized_statuses=('completed',)):
        flash('삭제 권한이 없습니다. (작성자는 완료 전까지만, 관리자만 완료건 삭제 가능)', 'danger')
        return redirect(url_for('audit.audit_detail', audit_id=audit_id))
    # 하위 데이터 정리 (연결 CAPA는 보존하고 심사연결만 해제)
    AuditChecklistItem.query.filter_by(audit_id=audit.id).delete()
    AuditTarget.query.filter_by(audit_id=audit.id).delete()
    AuditAuditor.query.filter_by(audit_id=audit.id).delete()
    Concurrence.query.filter_by(target_type='audit', target_id=audit.id).delete()
    for capa in CAPA.query.filter_by(audit_id=audit.id).all():
        capa.audit_id = None
    db.session.add(AuditTrail(user_id=current_user.id, action='심사삭제',
        target_type='audit', target_id=audit.id, target_name=audit.title))
    db.session.delete(audit)
    db.session.commit()
    flash(f'내부심사 [{audit.audit_number}]이(가) 삭제되었습니다.', 'info')
    return redirect(url_for('audit.index'))


# ════════════════════════════════════════════════════════════
# 계획 워크플로우 (작성→검토→승인)
# ════════════════════════════════════════════════════════════
@audit_bp.route('/<int:audit_id>/plan/<action>', methods=['POST'])
@login_required
def plan_action(audit_id, action):
    audit = Audit.query.get_or_404(audit_id)

    if action == 'submit':           # 작성완료 → 검토요청 (+ 관계부서 합의 지정)
        if not current_user.has_edit():
            abort(403)
        from concurrence import set_departments, reset
        dept_ids = request.form.getlist('concur_depts')
        set_departments('audit', audit.id, dept_ids)
        reset('audit', audit.id)
        audit.plan_status = 'review'
        if dept_ids:
            flash(f'심사계획을 검토 요청했습니다. (관계부서 {len(dept_ids)}개 합의 진행)', 'success')
        else:
            flash('심사계획을 검토 요청했습니다.', 'success')
    elif action == 'review':         # 검토완료
        if not _can_review():
            abort(403)
        audit.plan_status = 'reviewed'
        audit.plan_reviewed_by_id = current_user.id
        flash('심사계획을 검토했습니다. 승인 대기 상태입니다.', 'success')
    elif action == 'approve':        # 승인 (관계부서 합의 완료 필요)
        if not _can_approve():
            abort(403)
        from concurrence import can_finalize
        if not can_finalize('audit', audit.id):
            flash('관계부서 합의가 완료되지 않아 승인할 수 없습니다. (모든 합의부서 동의 필요)', 'danger')
            return redirect(url_for('audit.audit_detail', audit_id=audit_id))
        audit.plan_status = 'approved'
        audit.plan_approved_by_id = current_user.id
        audit.plan_approved_at = datetime.utcnow()
        if audit.status == 'planned':
            audit.status = 'in_progress'
        flash('심사계획이 승인되었습니다.', 'success')
    elif action == 'reopen':         # 작성중으로 되돌림 (작성자 또는 승인권자)
        if not (current_user.has_edit() or _can_approve()):
            abort(403)
        audit.plan_status = 'draft'
        audit.plan_approved_by_id = None
        audit.plan_approved_at = None
        flash('심사계획을 작성중으로 되돌렸습니다.', 'info')
    db.session.commit()
    return redirect(url_for('audit.audit_detail', audit_id=audit_id))


@audit_bp.route('/<int:audit_id>/concur', methods=['POST'])
@login_required
def plan_concur(audit_id):
    """심사계획 관계부서 합의/반려 처리"""
    from models import Concurrence
    from concurrence import can_concur, act
    audit = Audit.query.get_or_404(audit_id)
    dept_id = request.form.get('department_id', type=int)
    c = Concurrence.query.filter_by(target_type='audit', target_id=audit.id,
                                    department_id=dept_id).first_or_404()
    if not can_concur(current_user, c.department_id):
        flash('해당 부서의 합의 권한이 없습니다. (소속 부서의 검토·승인 권한자만 가능)', 'danger')
        return redirect(url_for('audit.audit_detail', audit_id=audit_id))
    action = request.form.get('action')   # agree / disagree
    act(c, current_user, action, request.form.get('comment'))
    db.session.add(AuditTrail(user_id=current_user.id,
        action='심사계획합의' if action == 'agree' else '심사계획합의반려',
        target_type='audit', target_id=audit.id,
        target_name=f'{audit.audit_number} ({c.department.name})'))
    db.session.commit()
    flash(f'{c.department.name}의 합의 의견이 등록되었습니다.', 'success')
    return redirect(url_for('audit.audit_detail', audit_id=audit_id))


# ════════════════════════════════════════════════════════════
# 체크리스트 생성 (대상 부서 × ISO 규격 → 시트별 항목)
# ════════════════════════════════════════════════════════════
@audit_bp.route('/<int:audit_id>/checklist/generate', methods=['POST'])
@login_required
def generate_checklist(audit_id):
    audit = Audit.query.get_or_404(audit_id)
    if not current_user.has_edit():
        abort(403)

    targets = audit.targets.all()
    if not targets:
        flash('심사 대상 부서가 지정되지 않았습니다.', 'warning')
        return redirect(url_for('audit.audit_detail', audit_id=audit_id))

    stds = standards_for(audit.iso_standard)
    templates = ChecklistTemplate.query.filter(
        ChecklistTemplate.iso_standard.in_(stds)
    ).order_by(ChecklistTemplate.sort_order).all()

    created = 0
    for t in targets:
        # 이미 생성된 부서 시트는 건너뜀
        if AuditChecklistItem.query.filter_by(audit_id=audit.id,
                                              department_id=t.department_id).count() > 0:
            continue
        for tpl in templates:
            db.session.add(AuditChecklistItem(
                audit_id=audit.id, department_id=t.department_id,
                iso_standard=tpl.iso_standard, clause=tpl.clause,
                category=tpl.category, content=tpl.content,
                is_mandatory=tpl.is_mandatory, result='pending',
                sort_order=tpl.sort_order))
            created += 1

    db.session.commit()
    flash(f'체크리스트가 생성되었습니다. (부서별 시트, 총 {created}개 항목 추가)', 'success')
    return redirect(url_for('audit.audit_detail', audit_id=audit_id))


# ════════════════════════════════════════════════════════════
# 부서별 체크리스트 시트 (점검 수행)
# ════════════════════════════════════════════════════════════
@audit_bp.route('/<int:audit_id>/sheet/<int:dept_id>', methods=['GET', 'POST'])
@login_required
def checklist_sheet(audit_id, dept_id):
    audit = Audit.query.get_or_404(audit_id)
    dept = Department.query.get_or_404(dept_id)
    target = AuditTarget.query.filter_by(audit_id=audit_id, department_id=dept_id).first_or_404()

    if request.method == 'POST':
        if not current_user.has_edit():
            abort(403)
        items = AuditChecklistItem.query.filter_by(audit_id=audit_id, department_id=dept_id).all()
        for it in items:
            pre = f'i_{it.id}_'
            if (pre + 'result') in request.form:
                it.result = request.form.get(pre + 'result')
                it.evidence = request.form.get(pre + 'evidence')
                it.finding = request.form.get(pre + 'finding')
        # 부서 종합판정·피심사자·심사자
        target.auditee_name = request.form.get('auditee_name')
        target.auditor_name = request.form.get('auditor_name')
        target.conformity = request.form.get('conformity')
        target.note = request.form.get('note')
        ad = request.form.get('audit_date')
        if ad:
            target.audit_date = datetime.strptime(ad, '%Y-%m-%d').date()
        db.session.commit()
        flash(f'{dept.name} 체크리스트가 저장되었습니다.', 'success')
        return redirect(url_for('audit.checklist_sheet', audit_id=audit_id, dept_id=dept_id))

    items = AuditChecklistItem.query.filter_by(audit_id=audit_id, department_id=dept_id)\
        .order_by(AuditChecklistItem.sort_order).all()
    # ISO 규격별 그룹화
    grouped = {}
    for it in items:
        grouped.setdefault(it.iso_standard, []).append(it)

    stats = {
        'total': len(items),
        'conform': sum(1 for i in items if i.result == 'conform'),
        'nonconform': sum(1 for i in items if i.result == 'nonconform'),
        'observation': sum(1 for i in items if i.result == 'observation'),
        'na': sum(1 for i in items if i.result == 'na'),
        'pending': sum(1 for i in items if i.result == 'pending'),
    }
    users = User.query.filter_by(is_active=True).order_by(User.name).all()
    # 심사자 후보: 계획 단계에서 지정된 심사원 (연동) + 로그인 인원
    assigned = audit.auditors.all()
    auditor_options = []
    seen = set()
    for a in assigned:
        if a.user and a.user.name not in seen:
            label = ('[선임] ' if a.is_lead else '') + a.user.name
            auditor_options.append({'name': a.user.name, 'label': label})
            seen.add(a.user.name)
    # 로그인 인원이 지정 심사원에 없으면 추가 (현재 점검 수행자)
    if current_user.name not in seen:
        auditor_options.append({'name': current_user.name,
                                'label': current_user.name + ' (로그인)'})

    # 피심사자 후보: 해당 피심사 부서 소속 인원 (연동)
    dept_members = User.query.filter_by(department_id=dept_id, is_active=True)\
        .order_by(User.name).all()

    return render_template('audit/sheet.html',
        audit=audit, dept=dept, target=target, grouped=grouped, stats=stats,
        users=users, auditor_options=auditor_options, dept_members=dept_members,
        result_kr=RESULT_KR, today=date.today())


# ════════════════════════════════════════════════════════════
# 부적합 → 시정조치(CAPA) 등록
# ════════════════════════════════════════════════════════════
@audit_bp.route('/checklist-item/<int:item_id>/raise-nc', methods=['POST'])
@login_required
def raise_nc(item_id):
    item = AuditChecklistItem.query.get_or_404(item_id)
    if not current_user.has_edit():
        abort(403)
    if item.capa_id:
        flash('이미 시정조치가 등록된 항목입니다.', 'info')
        return redirect(url_for('audit.capa_detail', capa_id=item.capa_id))

    year = datetime.now().year
    count = CAPA.query.filter(CAPA.capa_number.like(f'CAPA-{year}-%')).count() + 1
    capa = CAPA(
        capa_number=f'CAPA-{year}-{count:03d}',
        audit_id=item.audit_id,
        nc_type=request.form.get('nc_type', 'minor'),
        nc_description=item.finding or item.content,
        iso_clause=f'{item.iso_standard} {item.clause}',
        department_id=item.department_id,
        due_date=datetime.strptime(request.form['due_date'], '%Y-%m-%d').date()
                 if request.form.get('due_date') else None,
        responsible_id=request.form.get('responsible_id', type=int),
        status='open',
    )
    db.session.add(capa)
    db.session.flush()
    item.capa_id = capa.id
    item.result = 'nonconform'
    db.session.add(AuditTrail(user_id=current_user.id, action='부적합등록',
                              target_type='capa', target_id=capa.id, target_name=capa.capa_number))
    db.session.commit()
    flash(f'부적합 시정조치 [{capa.capa_number}]가 등록되었습니다.', 'success')
    return redirect(url_for('audit.capa_detail', capa_id=capa.id))


# ════════════════════════════════════════════════════════════
# 결과보고서 (작성→검토→승인)
# ════════════════════════════════════════════════════════════
@audit_bp.route('/<int:audit_id>/report', methods=['POST'])
@login_required
def report_action(audit_id):
    audit = Audit.query.get_or_404(audit_id)
    action = request.form.get('action_type')

    if action == 'save':
        if not current_user.has_edit():
            abort(403)
        audit.report_summary = request.form.get('report_summary')
        audit.report_conclusion = request.form.get('report_conclusion')
        audit.report_result = request.form.get('report_result')
        if audit.report_status == 'draft':
            audit.report_status = 'draft'
        flash('결과보고서가 저장되었습니다.', 'success')
    elif action == 'submit':
        if not current_user.has_edit():
            abort(403)
        audit.report_status = 'review'
        flash('결과보고서를 검토 요청했습니다.', 'success')
    elif action == 'review':
        if not _can_review():
            abort(403)
        audit.report_status = 'reviewed'
        audit.report_reviewed_by_id = current_user.id
        flash('결과보고서를 검토했습니다. 승인 대기 상태입니다.', 'success')
    elif action == 'approve':
        if not _can_approve():
            abort(403)
        audit.report_status = 'approved'
        audit.report_approved_by_id = current_user.id
        audit.report_approved_at = datetime.utcnow()
        audit.status = 'completed'
        audit.actual_date = date.today()
        db.session.add(AuditTrail(user_id=current_user.id, action='심사보고서승인',
                                  target_type='audit', target_id=audit.id, target_name=audit.title))
        flash('결과보고서가 승인되어 심사가 완료되었습니다.', 'success')
    elif action == 'reopen':
        if not _can_approve():
            abort(403)
        audit.report_status = 'draft'
        audit.report_approved_by_id = None
        audit.report_approved_at = None
        if audit.status == 'completed':
            audit.status = 'in_progress'
        flash('결과보고서를 작성중으로 되돌렸습니다.', 'info')
    db.session.commit()
    return redirect(url_for('audit.audit_detail', audit_id=audit_id) + '#report')


# ════════════════════════════════════════════════════════════
# CAPA (시정조치) — 목록·상세·워크플로우
# ════════════════════════════════════════════════════════════
@audit_bp.route('/capa')
@login_required
def capa_list():
    status = request.args.get('status', '')
    query = CAPA.query
    if status:
        query = query.filter_by(status=status)
    capas = query.order_by(CAPA.created_at.desc()).all()
    return render_template('audit/capa_list.html', capas=capas, today=date.today(), status=status)


@audit_bp.route('/capa/new', methods=['GET', 'POST'])
@login_required
def new_capa():
    if not current_user.has_edit():
        flash('시정조치 발행 권한이 없습니다.', 'danger')
        return redirect(url_for('audit.capa_list'))
    if request.method == 'POST':
        year = datetime.now().year
        count = CAPA.query.filter(CAPA.capa_number.like(f'CAPA-{year}-%')).count() + 1
        capa = CAPA(
            capa_number=f'CAPA-{year}-{count:03d}',
            audit_id=request.form.get('audit_id', type=int),
            nc_type=request.form.get('nc_type'),
            nc_description=request.form.get('nc_description'),
            iso_clause=request.form.get('iso_clause'),
            root_cause=request.form.get('root_cause'),
            corrective_action=request.form.get('corrective_action'),
            due_date=datetime.strptime(request.form['due_date'], '%Y-%m-%d').date()
                     if request.form.get('due_date') else None,
            responsible_id=request.form.get('responsible_id', type=int),
            department_id=request.form.get('department_id', type=int),
            status='open',
        )
        db.session.add(capa)
        db.session.commit()
        flash(f'시정조치 [{capa.capa_number}]가 등록되었습니다.', 'success')
        return redirect(url_for('audit.capa_detail', capa_id=capa.id))

    audits = Audit.query.order_by(Audit.planned_date.desc()).all()
    users = User.query.filter_by(is_active=True).all()
    departments = Department.query.filter_by(is_active=True).all()
    return render_template('audit/new_capa.html', audits=audits, users=users,
                           departments=departments)


IMAGE_EXTS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def _save_capa_attachments(capa):
    """업로드된 증빙 파일들을 CAPAAttachment로 저장 (이미지는 is_image=True)."""
    files = request.files.getlist('attachments')
    if not files:
        return
    from config import Config
    from werkzeug.utils import secure_filename
    from utils import allowed_file
    for file in files:
        if not file or not file.filename:
            continue
        if not allowed_file(file.filename, Config.ALLOWED_EXTENSIONS):
            flash(f'허용되지 않는 파일 형식: {file.filename}', 'warning')
            continue
        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        fname = f"CAPA_{capa.id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{secure_filename(file.filename)}"
        fpath = os.path.join(Config.UPLOAD_FOLDER, fname)
        file.save(fpath)
        db.session.add(CAPAAttachment(
            capa_id=capa.id, file_path=fpath, file_name=file.filename,
            is_image=(ext in IMAGE_EXTS), uploaded_by_id=current_user.id))


@audit_bp.route('/capa/attachment/<int:att_id>/delete', methods=['POST'])
@login_required
def delete_capa_attachment(att_id):
    att = CAPAAttachment.query.get_or_404(att_id)
    capa = CAPA.query.get_or_404(att.capa_id)
    if not current_user.has_edit():
        abort(403)
    if capa.status == 'closed':
        flash('종결된 시정조치의 첨부는 삭제할 수 없습니다.', 'danger')
        return redirect(url_for('audit.capa_detail', capa_id=capa.id))
    try:
        if att.file_path and os.path.exists(att.file_path):
            os.remove(att.file_path)
    except OSError:
        pass
    db.session.delete(att)
    db.session.commit()
    flash('증빙 첨부가 삭제되었습니다.', 'info')
    return redirect(url_for('audit.capa_detail', capa_id=capa.id))


@audit_bp.route('/capa/<int:capa_id>', methods=['GET', 'POST'])
@login_required
def capa_detail(capa_id):
    capa = CAPA.query.get_or_404(capa_id)

    if request.method == 'POST':
        action = request.form.get('action_type', 'save')
        if action == 'save':
            if not current_user.has_edit():
                abort(403)
            capa.root_cause = request.form.get('root_cause')
            capa.corrective_action = request.form.get('corrective_action')
            capa.preventive_action = request.form.get('preventive_action')
            capa.effectiveness = request.form.get('effectiveness')
            capa.nc_type = request.form.get('nc_type', capa.nc_type)
            capa.responsible_id = request.form.get('responsible_id', type=int) or capa.responsible_id
            due = request.form.get('due_date')
            capa.due_date = datetime.strptime(due, '%Y-%m-%d').date() if due else capa.due_date
            new_status = request.form.get('status')
            if new_status:
                capa.status = new_status
                if new_status == 'closed' and not capa.completed_date:
                    capa.completed_date = date.today()
            # 증빙 첨부 (다중) 처리
            _save_capa_attachments(capa)
            flash('시정조치 내용이 저장되었습니다.', 'success')
        elif action == 'review':       # 검토(유효성 확인)
            if not _can_review():
                abort(403)
            capa.reviewed_by_id = current_user.id
            if capa.status in ('open', 'in_progress'):
                capa.status = 'verified'
            flash('시정조치를 검토(유효성 확인)했습니다.', 'success')
        elif action == 'approve':      # 승인(종결)
            if not _can_approve():
                abort(403)
            capa.approved_by_id = current_user.id
            capa.approved_at = datetime.utcnow()
            capa.status = 'closed'
            if not capa.completed_date:
                capa.completed_date = date.today()
            flash('시정조치가 승인·종결되었습니다.', 'success')
        db.session.commit()
        return redirect(url_for('audit.capa_detail', capa_id=capa.id))

    users = User.query.filter_by(is_active=True).order_by(User.name).all()
    return render_template('audit/capa_detail.html', capa=capa, users=users,
                           today=date.today(), can_review=_can_review(), can_approve=_can_approve())


@audit_bp.route('/capa/<int:capa_id>/delete', methods=['POST'])
@login_required
def delete_capa(capa_id):
    from deletion import can_delete, remove_file
    capa = CAPA.query.get_or_404(capa_id)
    # 작성자(담당자)는 종결 전만, 관리자는 전부
    if not can_delete(capa, 'responsible_id', finalized_statuses=('closed',)):
        flash('삭제 권한이 없습니다. (담당자는 종결 전까지만, 관리자만 종결건 삭제 가능)', 'danger')
        return redirect(url_for('audit.capa_detail', capa_id=capa_id))
    for att in capa.attachments.all():
        remove_file(att.file_path)
    # 체크리스트 항목 연결 해제
    for item in AuditChecklistItem.query.filter_by(capa_id=capa.id).all():
        item.capa_id = None
    db.session.add(AuditTrail(user_id=current_user.id, action='시정조치삭제',
        target_type='capa', target_id=capa.id, target_name=capa.capa_number))
    db.session.delete(capa)   # 첨부는 cascade 삭제
    db.session.commit()
    flash(f'시정조치 [{capa.capa_number}]가 삭제되었습니다.', 'info')
    return redirect(url_for('audit.capa_list'))


# (목록 인라인 빠른수정 update_capa 라우트 제거됨 — 상태·유효성 수정은 권한 검증이 적용된 상세 화면에서만 가능)
