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


@admin_bp.route('/')
@login_required
@admin_required
def index():
    user_count = User.query.count()
    dept_count = Department.query.count()
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/index.html', users=users, user_count=user_count, dept_count=dept_count)


@admin_bp.route('/users/new', methods=['GET', 'POST'])
@login_required
@admin_required
def new_user():
    if request.method == 'POST':
        employee_id = request.form.get('employee_id', '').strip()
        if User.query.filter_by(employee_id=employee_id).first():
            flash('이미 존재하는 사번입니다.', 'danger')
        else:
            user = User(
                employee_id=employee_id,
                name=request.form.get('name'),
                email=request.form.get('email'),
                department_id=request.form.get('department_id', type=int),
                position=request.form.get('position'),
                role=request.form.get('role', 'staff'),
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
@admin_required
def edit_user(user_id):
    """사용자 기본정보 수정 (사번·역할 제외 — 역할은 권한관리에서)"""
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        user.name = request.form.get('name', user.name)
        user.email = request.form.get('email') or None
        user.department_id = request.form.get('department_id', type=int)
        user.position = request.form.get('position')
        db.session.add(AuditTrail(user_id=current_user.id, action='사용자수정',
            target_type='user', target_id=user.id,
            target_name=f'{user.employee_id} {user.name}'))
        db.session.commit()
        flash(f'{user.name} 님의 정보가 수정되었습니다.', 'success')
        return redirect(url_for('admin.index'))

    departments = Department.query.filter_by(is_active=True).all()
    return render_template('admin/new_user.html', departments=departments, item=user)


@admin_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@admin_required
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
@admin_required
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('본인 계정은 비활성화할 수 없습니다. (잠금 방지)', 'danger')
        return redirect(url_for('admin.index'))
    user.is_active = not user.is_active
    db.session.commit()
    state = '활성화' if user.is_active else '비활성화'
    flash(f'{user.name} 계정이 {state}되었습니다.', 'info')
    return redirect(url_for('admin.index'))


@admin_bp.route('/permissions', methods=['GET', 'POST'])
@login_required
@admin_required
def permissions():
    """조직도 기반 권한 관리 — 결재/수정 권한 및 역할 부여"""
    if request.method == 'POST':
        changed = 0
        for user in User.query.all():
            # 자기 자신(관리자)은 역할 변경 대상에서 제외하여 잠금 방지
            new_role = request.form.get(f'u_{user.id}_role')
            new_edit = request.form.get(f'u_{user.id}_edit') == 'on'
            new_review = request.form.get(f'u_{user.id}_review') == 'on'
            new_approve = request.form.get(f'u_{user.id}_approve') == 'on'
            new_auditor = request.form.get(f'u_{user.id}_auditor') == 'on'
            new_org = request.form.get(f'u_{user.id}_org') == 'on'
            new_training = request.form.get(f'u_{user.id}_training') == 'on'

            dirty = False
            if new_role and new_role != user.role and user.id != current_user.id:
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
