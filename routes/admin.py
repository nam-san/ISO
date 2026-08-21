from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import db, User, Department, AuditTrail, Record, LegalRegister
from models import Training, CustomerComplaint, DesignChange
from functools import wraps
from datetime import date

admin_bp = Blueprint('admin', __name__)


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_admin():
            flash('관리자 권한이 필요합니다.', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated


def user_admin_required(f):
    """사용자 관리·권한 관리 접근 — 시스템 관리자 또는 위임받은 사용자"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.has_user_admin():
            flash('사용자·권한 관리 권한이 필요합니다.', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated


# 사용자 계정을 참조하는 테이블 (삭제 전 검사용)
USER_REF_MODELS = None


def _load_user_refs():
    """models.py 전체를 훑어 users.id 를 참조하는 (모델, 컬럼) 목록을 만든다."""
    global USER_REF_MODELS
    if USER_REF_MODELS is not None:
        return USER_REF_MODELS
    import models as M
    refs = []
    for obj in vars(M).values():
        if not (isinstance(obj, type) and issubclass(obj, db.Model) and obj is not db.Model):
            continue
        table = getattr(obj, '__table__', None)
        if table is None or table.name == 'users':
            continue
        for col in table.columns:
            for fk in col.foreign_keys:
                if fk.column.table.name == 'users':
                    refs.append((obj, col.name, table.name))
    USER_REF_MODELS = refs
    return refs


# 테이블 → 화면 표기용 한글 명칭
TABLE_LABELS = {
    'approvals': '결재', 'audit_auditors': '내부심사 심사원', 'audit_trail': '감사 로그',
    'audits': '내부심사', 'capa': '시정조치', 'capa_attachments': '시정조치 첨부',
    'change_attachments': '4M 변경 첨부', 'change_reviews': '4M 변경 부서검토',
    'complaint_attachments': '고객클레임 첨부', 'concurrences': '합의',
    'customer_complaints': '고객클레임', 'design_changes': '변경 관리',
    'document_versions': '문서 개정이력', 'documents': '기준문서',
    'grievances': '고충 처리', 'hse_environmental': '환경 관리', 'hse_risk': '위험성평가',
    'inspection_records': '검사 기록', 'legal_register': '법규 등록부',
    'management_reviews': '경영검토', 'meeting_record_attachments': '회의록 첨부',
    'meeting_records': '회의록', 'mr_actions': '경영검토 조치',
    'msds': 'MSDS', 'policies': '방침', 'policy_histories': '방침 개정이력',
    'qualification_attachments': '자격 증빙', 'qualifications': '자격인정',
    'rba_assessments': '자가진단', 'records': '기록문서',
    'risk_improvement_attachments': '개선조치 첨부', 'risk_improvements': '위험성 개선조치',
    'training_attendees': '교육 참석자', 'training_plans': '교육계획', 'trainings': '교육훈련',
}


def count_user_references(user_id):
    """해당 사용자가 남긴 데이터 건수를 테이블별로 집계"""
    result = {}
    for model, col_name, table_name in _load_user_refs():
        n = model.query.filter(getattr(model, col_name) == user_id).count()
        if n:
            result[f'{table_name}.{col_name}'] = n
    return result


def summarize_references(refs):
    """{'documents.created_by_id': 3} → {'기준문서': 3} 형태로 한글 집계"""
    out = {}
    for key, n in refs.items():
        table = key.split('.')[0]
        label = TABLE_LABELS.get(table, table)
        out[label] = out.get(label, 0) + n
    return out


def _may_manage(target):
    """대상 사용자를 관리할 수 있는지 — 위임 관리자는 시스템 관리자 계정을 건드릴 수 없다."""
    if current_user.is_admin():
        return True
    return target.role != 'admin' and not target.can_user_admin


@admin_bp.route('/')
@login_required
@user_admin_required
def index():
    user_count = User.query.count()
    dept_count = Department.query.count()
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/index.html', users=users, user_count=user_count, dept_count=dept_count)


@admin_bp.route('/users/new', methods=['GET', 'POST'])
@login_required
@user_admin_required
def new_user():
    if request.method == 'POST':
        employee_id = request.form.get('employee_id', '').strip()
        if User.query.filter_by(employee_id=employee_id).first():
            flash('이미 존재하는 사번입니다.', 'danger')
        else:
            new_role = request.form.get('role', 'staff')
            # 위임 관리자는 시스템 관리자 계정을 만들 수 없음
            if new_role == 'admin' and not current_user.is_admin():
                new_role = 'manager'
                flash('시스템 관리자 계정 생성은 시스템 관리자만 가능하여 [그룹장/PM/PL]로 등록했습니다.', 'warning')
            user = User(
                employee_id=employee_id,
                name=request.form.get('name'),
                email=request.form.get('email'),
                department_id=request.form.get('department_id', type=int),
                position=request.form.get('position'),
                role=new_role,
            )
            user.set_password(request.form.get('password', 'nurivoice2024!'))
            db.session.add(user)
            db.session.commit()
            flash(f'사용자 [{employee_id}] {user.name}이(가) 등록되었습니다. 초기 비밀번호: nurivoice2024!', 'success')
            return redirect(url_for('admin.index'))

    departments = Department.query.filter_by(is_active=True).all()
    return render_template('admin/new_user.html', departments=departments, item=None)


@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@user_admin_required
def edit_user(user_id):
    """사용자 기본정보 수정 — 사번(로그인 ID)은 고정, 시스템 권한은 변경 가능"""
    user = User.query.get_or_404(user_id)
    if not _may_manage(user):
        flash('시스템 관리자 계정은 시스템 관리자만 수정할 수 있습니다.', 'danger')
        return redirect(url_for('admin.index'))

    if request.method == 'POST':
        before_role = user.role
        user.name = request.form.get('name', user.name)
        user.email = request.form.get('email') or None
        user.department_id = request.form.get('department_id', type=int)
        user.position = request.form.get('position')

        # 시스템 권한(역할) 변경 — 승진·보직 변경 반영
        new_role = request.form.get('role')
        if new_role and new_role != user.role:
            if user.id == current_user.id:
                flash('본인 계정의 시스템 권한은 변경할 수 없습니다. (잠금 방지)', 'warning')
            elif new_role == 'admin' and not current_user.is_admin():
                flash('시스템 관리자 권한 부여는 시스템 관리자만 가능합니다.', 'warning')
            else:
                user.role = new_role

        role_label = {'admin': '시스템 관리자', 'manager': '그룹장/PM/PL',
                      'staff': '프로', 'viewer': '열람 전용'}
        detail = None
        if user.role != before_role:
            detail = f'시스템 권한 {role_label.get(before_role, before_role)} → {role_label.get(user.role, user.role)}'
        db.session.add(AuditTrail(user_id=current_user.id, action='사용자수정',
            target_type='user', target_id=user.id,
            target_name=f'{user.employee_id} {user.name}', detail=detail))
        db.session.commit()
        flash(f'{user.name} 님의 정보가 수정되었습니다.' + (f' ({detail})' if detail else ''), 'success')
        return redirect(url_for('admin.index'))

    departments = Department.query.filter_by(is_active=True).all()
    return render_template('admin/new_user.html', departments=departments, item=user)


@admin_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@user_admin_required
def reset_password(user_id):
    """비밀번호 초기화 (초기 비밀번호로)"""
    user = User.query.get_or_404(user_id)
    user.set_password('nurivoice2024!')
    db.session.add(AuditTrail(user_id=current_user.id, action='비밀번호초기화',
        target_type='user', target_id=user.id,
        target_name=f'{user.employee_id} {user.name}'))
    db.session.commit()
    flash(f'{user.name} 님의 비밀번호가 초기화되었습니다. (nurivoice2024!)', 'success')
    return redirect(url_for('admin.index'))


@admin_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@login_required
@user_admin_required
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('본인 계정은 비활성화할 수 없습니다. (잠금 방지)', 'danger')
        return redirect(url_for('admin.index'))
    if not _may_manage(user):
        flash('시스템 관리자 계정은 시스템 관리자만 변경할 수 있습니다.', 'danger')
        return redirect(url_for('admin.index'))
    user.is_active = not user.is_active
    db.session.commit()
    state = '활성화' if user.is_active else '비활성화'
    flash(f'{user.name} 계정이 {state}되었습니다.', 'info')
    return redirect(url_for('admin.index'))


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@user_admin_required
def delete_user(user_id):
    """사용자 계정 삭제 — 시스템에 남긴 기록이 없을 때만 완전 삭제"""
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash('본인 계정은 삭제할 수 없습니다. (잠금 방지)', 'danger')
        return redirect(url_for('admin.index'))
    if user.employee_id == 'admin':
        flash('기본 관리자 계정(admin)은 삭제할 수 없습니다.', 'danger')
        return redirect(url_for('admin.index'))
    if not _may_manage(user):
        flash('시스템 관리자 계정은 시스템 관리자만 삭제할 수 있습니다.', 'danger')
        return redirect(url_for('admin.index'))
    if user.role == 'admin' and User.query.filter_by(role='admin', is_active=True).count() <= 1:
        flash('마지막 시스템 관리자 계정은 삭제할 수 없습니다.', 'danger')
        return redirect(url_for('admin.index'))

    audit_table = AuditTrail.__tablename__
    refs = count_user_references(user.id)
    # 감사로그는 활동 이력이므로 삭제를 막지 않고 익명화하여 보존
    audit_count = refs.pop(f'{audit_table}.user_id', 0)

    if refs:
        summary = summarize_references(refs)
        total = sum(summary.values())
        top = ', '.join(f'{k} {v}건' for k, v in sorted(summary.items(), key=lambda x: -x[1])[:5])
        more = '' if len(summary) <= 5 else f' 외 {len(summary) - 5}종'
        flash(f'{user.name} 님은 시스템에 {total}건의 업무 데이터(작성·검토·승인 이력 등)가 연결되어 있어 '
              f'삭제할 수 없습니다. 기록 추적성을 위해 [비활성화]를 사용하세요. '
              f'— {top}{more}', 'danger')
        return redirect(url_for('admin.index'))

    label = f'{user.employee_id} {user.name}'
    if audit_count:
        # 사용자 id 재사용 시 이력이 뒤섞이지 않도록 연결을 끊고 행위자 정보를 본문에 남긴다
        for log in AuditTrail.query.filter_by(user_id=user.id).all():
            log.user_id = None
            log.detail = ((log.detail + ' / ') if log.detail else '') + f'행위자: {label} (삭제된 계정)'
    db.session.delete(user)
    db.session.add(AuditTrail(user_id=current_user.id, action='사용자삭제',
        target_type='user', target_name=label,
        detail=f'관리자 {current_user.name} 실행'))
    db.session.commit()
    flash(f'사용자 [{label}] 계정이 삭제되었습니다.', 'success')
    return redirect(url_for('admin.index'))


@admin_bp.route('/permissions', methods=['GET', 'POST'])
@login_required
@user_admin_required
def permissions():
    """조직도 기반 권한 관리 — 결재/수정 권한 및 역할 부여"""
    if request.method == 'POST':
        changed = 0
        blocked = 0
        for user in User.query.all():
            # 자기 자신(관리자)은 역할 변경 대상에서 제외하여 잠금 방지
            new_role = request.form.get(f'u_{user.id}_role')
            new_edit = request.form.get(f'u_{user.id}_edit') == 'on'
            new_review = request.form.get(f'u_{user.id}_review') == 'on'
            new_approve = request.form.get(f'u_{user.id}_approve') == 'on'
            new_auditor = request.form.get(f'u_{user.id}_auditor') == 'on'
            new_org = request.form.get(f'u_{user.id}_org') == 'on'
            new_training = request.form.get(f'u_{user.id}_training') == 'on'
            new_policy = request.form.get(f'u_{user.id}_policy') == 'on'
            new_useradmin = request.form.get(f'u_{user.id}_useradmin') == 'on'

            # 위임 관리자는 시스템 관리자 계정을 수정할 수 없음
            if not _may_manage(user):
                continue

            dirty = False
            if new_role and new_role != user.role and user.id != current_user.id:
                # 시스템 관리자 역할 부여는 시스템 관리자만 가능
                if new_role == 'admin' and not current_user.is_admin():
                    blocked += 1
                else:
                    user.role = new_role
                    dirty = True
            if user.can_edit != new_edit:
                user.can_edit = new_edit
                dirty = True
            if user.can_review != new_review:
                user.can_review = new_review
                dirty = True
            if user.can_approve != new_approve:
                user.can_approve = new_approve
                dirty = True
            if user.is_auditor != new_auditor:
                user.is_auditor = new_auditor
                dirty = True
            if user.can_org != new_org:
                user.can_org = new_org
                dirty = True
            if user.can_training != new_training:
                user.can_training = new_training
                dirty = True
            if user.can_policy != new_policy:
                user.can_policy = new_policy
                dirty = True
            # 사용자·권한 관리 위임은 시스템 관리자만 부여/회수 가능
            if user.can_user_admin != new_useradmin:
                if current_user.is_admin():
                    user.can_user_admin = new_useradmin
                    dirty = True
                else:
                    blocked += 1
            if dirty:
                changed += 1

        if changed:
            db.session.add(AuditTrail(
                user_id=current_user.id, action='권한변경',
                target_type='user', target_name=f'{changed}명 권한 수정',
                detail=f'관리자 {current_user.name} 실행'))
            db.session.commit()
            flash(f'{changed}명의 권한이 변경되었습니다.', 'success')
        else:
            flash('변경된 권한이 없습니다.', 'info')
        if blocked:
            flash(f'시스템 관리자 전용 항목 {blocked}건은 변경되지 않았습니다. '
                  f'(시스템 관리자 역할 부여·사용자관리 위임)', 'warning')
        return redirect(url_for('admin.permissions'))

    # 부서별로 그룹화 (조직도)
    departments = Department.query.filter_by(is_active=True).order_by(Department.id).all()
    org = []
    for d in departments:
        members = User.query.filter_by(department_id=d.id).order_by(User.role).all()
        org.append({'dept': d, 'members': members})
    # 부서 미지정 인원
    no_dept = User.query.filter_by(department_id=None).all()
    if no_dept:
        org.append({'dept': None, 'members': no_dept})

    return render_template('admin/permissions.html', org=org)


@admin_bp.route('/system')
@login_required
@admin_required
def system():
    """시스템 현황 및 관리 페이지"""
    from utils import get_disposal_alerts, get_overdue_disposals
    today = date.today()

    system_stats = {
        'total_users':    User.query.count(),
        'active_users':   User.query.filter_by(is_active=True).count(),
        'total_records':  Record.query.count(),
        'disposal_soon':  len(get_disposal_alerts(30)),
        'overdue_disposal': len(get_overdue_disposals()),
        'audit_logs_today': AuditTrail.query.filter(
            db.func.date(AuditTrail.created_at) == today
        ).count(),
        'training_total':  Training.query.count(),
        'complaint_open':  CustomerComplaint.query.filter(
            CustomerComplaint.status.in_(['open', 'investigating'])).count(),
        'design_review':   DesignChange.query.filter_by(status='review').count(),
        'legal_total':     LegalRegister.query.count(),
        'legal_non_compliant': LegalRegister.query.filter(
            LegalRegister.compliance_status.in_(['non_compliant', 'partial'])).count(),
    }
    overdue_records = get_overdue_disposals()
    alert_records = get_disposal_alerts(30)
    recent_logs = AuditTrail.query.order_by(AuditTrail.created_at.desc()).limit(20).all()

    return render_template('admin/system.html',
        system_stats=system_stats,
        overdue_records=overdue_records,
        alert_records=alert_records,
        recent_logs=recent_logs,
        today=today)


@admin_bp.route('/system/auto-dispose', methods=['POST'])
@login_required
@admin_required
def auto_dispose():
    """만료된 실행기록 일괄 폐기 처리"""
    from utils import run_auto_disposal
    count = run_auto_disposal()
    if count:
        log = AuditTrail(
            user_id=current_user.id,
            action='일괄자동폐기',
            target_type='record',
            target_name=f'{count}건 일괄 폐기 처리',
            detail=f'관리자 {current_user.name} 실행',
        )
        db.session.add(log)
        db.session.commit()
        flash(f'보존연한 만료 기록 {count}건이 폐기 처리되었습니다.', 'success')
    else:
        flash('폐기 처리할 만료 기록이 없습니다.', 'info')
    return redirect(url_for('admin.system'))
