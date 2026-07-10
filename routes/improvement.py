from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import db, RiskAssessment, RiskImprovement, RiskImprovementAttachment, User, AuditTrail
from datetime import datetime, date
import os

improvement_bp = Blueprint('improvement', __name__)

IMAGE_EXTS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
STATUS_KR = {'in_progress': '개선중', 'completed': '승인대기', 'approved': '승인완료'}


def _grade(level):
    return '상' if level >= 15 else ('중' if level >= 8 else '하')


def _next_number():
    year = datetime.now().year
    n = RiskImprovement.query.filter(
        RiskImprovement.improvement_number.like(f'RIMP-{year}-%')
    ).count() + 1
    return f'RIMP-{year}-{n:03d}'


def _save_attachments(imp):
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
        fname = f"RIMP_{imp.id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{secure_filename(file.filename)}"
        fpath = os.path.join(Config.UPLOAD_FOLDER, fname)
        file.save(fpath)
        db.session.add(RiskImprovementAttachment(
            improvement_id=imp.id, file_path=fpath, file_name=file.filename,
            is_image=(ext in IMAGE_EXTS), uploaded_by_id=current_user.id))


@improvement_bp.route('/')
@login_required
def index():
    status = request.args.get('status', '')
    query = RiskImprovement.query
    if status:
        query = query.filter_by(status=status)
    items = query.order_by(RiskImprovement.created_at.desc()).all()
    stats = {
        'in_progress': RiskImprovement.query.filter_by(status='in_progress').count(),
        'completed': RiskImprovement.query.filter_by(status='completed').count(),
        'approved': RiskImprovement.query.filter_by(status='approved').count(),
    }
    return render_template('improvement/index.html',
                           items=items, stats=stats, status=status,
                           status_kr=STATUS_KR, today=date.today())


@improvement_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    if not current_user.has_edit():
        flash('개선조치 작성 권한이 없습니다.', 'danger')
        return redirect(url_for('improvement.index'))

    risk = None
    risk_id = request.args.get('risk_id', type=int) or request.form.get('risk_id', type=int)
    if risk_id:
        risk = RiskAssessment.query.get(risk_id)

    if request.method == 'POST':
        if not risk:
            flash('원본 위험요인을 찾을 수 없습니다.', 'danger')
            return redirect(url_for('hse.risk'))
        due_str = request.form.get('due_date')
        imp = RiskImprovement(
            improvement_number=_next_number(),
            risk_id=risk.id,
            # 원본 스냅샷
            work_area=risk.work_area, work_type=risk.work_type, hazard=risk.hazard,
            current_control=risk.control_measure,
            before_probability=risk.probability, before_severity=risk.severity,
            before_level=risk.risk_level, before_grade=risk.risk_grade,
            # 작성 입력
            improvement_plan=request.form.get('improvement_plan'),
            responsible_id=request.form.get('responsible_id', type=int),
            due_date=datetime.strptime(due_str, '%Y-%m-%d').date() if due_str else None,
            status='in_progress',
            created_by_id=current_user.id,
        )
        db.session.add(imp)
        db.session.flush()
        db.session.add(AuditTrail(user_id=current_user.id, action='개선조치작성',
                                  target_type='improvement', target_id=imp.id,
                                  target_name=f'{imp.improvement_number} {imp.hazard}'))
        db.session.commit()
        flash(f'개선조치 [{imp.improvement_number}]이(가) 등록되었습니다.', 'success')
        return redirect(url_for('improvement.detail', imp_id=imp.id))

    if not risk:
        flash('개선할 위험요인을 위험성평가에서 선택해 주세요.', 'warning')
        return redirect(url_for('hse.risk'))
    users = User.query.filter_by(is_active=True).order_by(User.name).all()
    return render_template('improvement/form.html', risk=risk, item=None,
                           users=users, today=date.today())


@improvement_bp.route('/<int:imp_id>')
@login_required
def detail(imp_id):
    imp = RiskImprovement.query.get_or_404(imp_id)
    users = User.query.filter_by(is_active=True).order_by(User.name).all()
    return render_template('improvement/detail.html', imp=imp, users=users,
                           status_kr=STATUS_KR, today=date.today())


@improvement_bp.route('/<int:imp_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(imp_id):
    imp = RiskImprovement.query.get_or_404(imp_id)
    if not current_user.has_edit() or not (current_user.is_admin() or imp.created_by_id == current_user.id):
        flash('수정 권한이 없습니다. (작성자 또는 관리자만)', 'danger')
        return redirect(url_for('improvement.detail', imp_id=imp_id))
    if imp.status == 'approved':
        flash('승인완료된 개선조치는 수정할 수 없습니다.', 'danger')
        return redirect(url_for('improvement.detail', imp_id=imp_id))
    if request.method == 'POST':
        due_str = request.form.get('due_date')
        imp.improvement_plan = request.form.get('improvement_plan')
        imp.responsible_id = request.form.get('responsible_id', type=int)
        imp.due_date = datetime.strptime(due_str, '%Y-%m-%d').date() if due_str else None
        db.session.commit()
        flash('개선 계획이 수정되었습니다.', 'success')
        return redirect(url_for('improvement.detail', imp_id=imp_id))
    users = User.query.filter_by(is_active=True).order_by(User.name).all()
    return render_template('improvement/form.html', risk=imp.risk, item=imp,
                           users=users, today=date.today())


@improvement_bp.route('/<int:imp_id>/result', methods=['POST'])
@login_required
def result(imp_id):
    imp = RiskImprovement.query.get_or_404(imp_id)
    if not current_user.has_edit():
        flash('개선 결과 입력 권한이 없습니다.', 'danger')
        return redirect(url_for('improvement.detail', imp_id=imp_id))
    if imp.status == 'approved':
        flash('승인완료된 개선조치는 수정할 수 없습니다.', 'danger')
        return redirect(url_for('improvement.detail', imp_id=imp_id))
    ap = request.form.get('after_probability', type=int)
    as_ = request.form.get('after_severity', type=int)
    if ap and as_:
        imp.after_probability = ap
        imp.after_severity = as_
        imp.after_level = ap * as_
        imp.after_grade = _grade(ap * as_)
    imp.result = request.form.get('result', imp.result)
    imp.after_control = request.form.get('after_control', imp.after_control)
    comp = request.form.get('completed_date')
    imp.completed_date = datetime.strptime(comp, '%Y-%m-%d').date() if comp else (imp.completed_date or date.today())
    _save_attachments(imp)
    # 결과가 채워지면 승인대기로 상신
    if imp.after_level and imp.result:
        imp.status = 'completed'
    db.session.commit()
    flash('개선 후 결과가 저장되었습니다. (승인 대기)', 'success')
    return redirect(url_for('improvement.detail', imp_id=imp_id))


@improvement_bp.route('/<int:imp_id>/approve', methods=['POST'])
@login_required
def approve(imp_id):
    imp = RiskImprovement.query.get_or_404(imp_id)
    if not current_user.has_approve():
        flash('승인 권한이 없습니다.', 'danger')
        return redirect(url_for('improvement.detail', imp_id=imp_id))
    if imp.status != 'completed':
        flash('개선 결과가 입력된 뒤에 승인할 수 있습니다.', 'warning')
        return redirect(url_for('improvement.detail', imp_id=imp_id))
    imp.status = 'approved'
    imp.approved_by_id = current_user.id
    imp.approved_at = datetime.utcnow()
    # 승인 시 원본 위험성평가의 위험도·등급을 '개선 후' 값으로 자동 갱신
    # (개선 전 값은 개선조치 스냅샷 before_* 에 보존됨)
    if imp.risk and imp.after_level:
        imp.risk.probability = imp.after_probability
        imp.risk.severity = imp.after_severity
        imp.risk.risk_level = imp.after_level
        imp.risk.risk_grade = imp.after_grade
        imp.risk.residual_risk = imp.after_level
        # 개선 후 안전조치를 원본 위험의 '현재 안전조치'로 반영
        if imp.after_control:
            imp.risk.control_measure = imp.after_control
    db.session.add(AuditTrail(user_id=current_user.id, action='개선조치승인',
                              target_type='improvement', target_id=imp.id,
                              target_name=f'{imp.improvement_number} {imp.hazard}'))
    db.session.commit()
    flash(f'개선조치 [{imp.improvement_number}]이(가) 승인되었습니다.', 'success')
    return redirect(url_for('improvement.detail', imp_id=imp_id))


@improvement_bp.route('/<int:imp_id>/reject', methods=['POST'])
@login_required
def reject(imp_id):
    imp = RiskImprovement.query.get_or_404(imp_id)
    if not current_user.has_approve():
        flash('반려 권한이 없습니다.', 'danger')
        return redirect(url_for('improvement.detail', imp_id=imp_id))
    imp.status = 'in_progress'
    db.session.commit()
    flash('개선조치가 반려되어 개선중 상태로 되돌아갔습니다.', 'info')
    return redirect(url_for('improvement.detail', imp_id=imp_id))


@improvement_bp.route('/<int:imp_id>/delete', methods=['POST'])
@login_required
def delete(imp_id):
    imp = RiskImprovement.query.get_or_404(imp_id)
    if not (current_user.is_admin() or (imp.created_by_id == current_user.id and imp.status != 'approved')):
        flash('삭제 권한이 없습니다. (작성자는 승인 전까지, 관리자만 승인건 삭제)', 'danger')
        return redirect(url_for('improvement.detail', imp_id=imp_id))
    from deletion import remove_file
    for att in imp.attachments.all():
        remove_file(att.file_path)
    num = imp.improvement_number
    db.session.add(AuditTrail(user_id=current_user.id, action='개선조치삭제',
                              target_type='improvement', target_id=imp.id, target_name=num))
    db.session.delete(imp)
    db.session.commit()
    flash(f'개선조치 [{num}]이(가) 삭제되었습니다.', 'info')
    return redirect(url_for('improvement.index'))


@improvement_bp.route('/attachment/<int:att_id>/delete', methods=['POST'])
@login_required
def delete_attachment(att_id):
    att = RiskImprovementAttachment.query.get_or_404(att_id)
    imp = RiskImprovement.query.get_or_404(att.improvement_id)
    if not current_user.has_edit() or imp.status == 'approved':
        flash('첨부 삭제 권한이 없습니다.', 'danger')
        return redirect(url_for('improvement.detail', imp_id=imp.id))
    try:
        if att.file_path and os.path.exists(att.file_path):
            os.remove(att.file_path)
    except OSError:
        pass
    db.session.delete(att)
    db.session.commit()
    flash('증빙 첨부가 삭제되었습니다.', 'info')
    return redirect(url_for('improvement.detail', imp_id=imp.id))
