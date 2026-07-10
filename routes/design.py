from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file
from flask_login import login_required, current_user
from models import db, DesignChange, Department, User, AuditTrail
from datetime import datetime, date
import os, io
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

design_bp = Blueprint('design', __name__)


def _next_number():
    year = datetime.now().year
    last = DesignChange.query.filter(DesignChange.change_number.like(f'DCR-{year}-%')).count()
    return f'DCR-{year}-{last + 1:04d}'


@design_bp.route('/')
@login_required
def index():
    status = request.args.get('status', '')
    change_type = request.args.get('type', '')
    q = request.args.get('q', '')

    query = DesignChange.query
    if status:
        query = query.filter_by(status=status)
    if change_type:
        query = query.filter_by(change_type=change_type)
    if q:
        query = query.filter(
            DesignChange.product_name.contains(q) |
            DesignChange.change_title.contains(q) |
            DesignChange.change_number.contains(q)
        )

    changes = query.order_by(DesignChange.created_at.desc()).all()
    stats = {
        'draft': DesignChange.query.filter_by(status='draft').count(),
        'review': DesignChange.query.filter_by(status='review').count(),
        'approved': DesignChange.query.filter_by(status='approved').count(),
        'implemented': DesignChange.query.filter_by(status='implemented').count(),
    }
    return render_template('design/index.html',
        changes=changes, stats=stats,
        status=status, change_type=change_type, q=q)


@design_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    if not current_user.has_edit():
        flash('설계변경 등록 권한이 없습니다.', 'danger')
        return redirect(url_for('design.index'))
    if request.method == 'POST':
        request_date_str = request.form.get('request_date')
        apply_date_str = request.form.get('apply_date')

        dc = DesignChange(
            change_number=_next_number(),
            product_name=request.form.get('product_name'),
            change_type=request.form.get('change_type'),
            change_title=request.form.get('change_title'),
            change_reason=request.form.get('change_reason'),
            change_content=request.form.get('change_content'),
            before_spec=request.form.get('before_spec'),
            after_spec=request.form.get('after_spec'),
            verification_method=request.form.get('verification_method'),
            risk_assessment=request.form.get('risk_assessment'),
            request_date=datetime.strptime(request_date_str, '%Y-%m-%d').date() if request_date_str else date.today(),
            apply_date=datetime.strptime(apply_date_str, '%Y-%m-%d').date() if apply_date_str else None,
            department_id=request.form.get('department_id', type=int),
            requester_id=current_user.id,
            status='draft',
        )

        file = request.files.get('file')
        if file and file.filename:
            from config import Config
            from werkzeug.utils import secure_filename
            from utils import allowed_file
            if not allowed_file(file.filename, Config.ALLOWED_EXTENSIONS):
                flash('허용되지 않는 파일 형식입니다. (PDF/Office/한글/이미지만 가능)', 'danger')
                return redirect(request.url)
            fname = f"DCR_{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(file.filename)}"
            fpath = os.path.join(Config.UPLOAD_FOLDER, fname)
            file.save(fpath)
            dc.file_path = fpath
            dc.file_name = file.filename

        db.session.add(dc)
        db.session.flush()
        log = AuditTrail(user_id=current_user.id, action='설계변경등록',
                         target_type='design_change', target_id=dc.id,
                         target_name=f'{dc.change_number} {dc.change_title}')
        db.session.add(log)
        db.session.commit()
        flash(f'설계변경 요청 [{dc.change_number}]이(가) 등록되었습니다.', 'success')
        return redirect(url_for('design.detail', dcid=dc.id))

    departments = Department.query.filter_by(is_active=True).all()
    return render_template('design/new.html', departments=departments, today=date.today(), item=None)


@design_bp.route('/<int:dcid>/edit', methods=['GET', 'POST'])
@login_required
def edit(dcid):
    dc = DesignChange.query.get_or_404(dcid)
    if not current_user.has_edit() or not (current_user.is_admin() or dc.requester_id == current_user.id):
        flash('수정 권한이 없습니다. (작성자 또는 관리자만)', 'danger')
        return redirect(url_for('design.detail', dcid=dcid))
    if dc.status not in ('draft', 'review'):
        flash('승인·반영 단계의 설계변경은 수정할 수 없습니다.', 'danger')
        return redirect(url_for('design.detail', dcid=dcid))
    if request.method == 'POST':
        request_date_str = request.form.get('request_date')
        apply_date_str = request.form.get('apply_date')
        dc.product_name = request.form.get('product_name')
        dc.change_type = request.form.get('change_type')
        dc.change_title = request.form.get('change_title')
        dc.change_reason = request.form.get('change_reason')
        dc.change_content = request.form.get('change_content')
        dc.before_spec = request.form.get('before_spec')
        dc.after_spec = request.form.get('after_spec')
        dc.verification_method = request.form.get('verification_method')
        dc.risk_assessment = request.form.get('risk_assessment')
        dc.request_date = datetime.strptime(request_date_str, '%Y-%m-%d').date() if request_date_str else dc.request_date
        dc.apply_date = datetime.strptime(apply_date_str, '%Y-%m-%d').date() if apply_date_str else None
        dc.department_id = request.form.get('department_id', type=int)

        file = request.files.get('file')
        if file and file.filename:
            from config import Config
            from werkzeug.utils import secure_filename
            from utils import allowed_file
            if not allowed_file(file.filename, Config.ALLOWED_EXTENSIONS):
                flash('허용되지 않는 파일 형식입니다. (PDF/Office/한글/이미지만 가능)', 'danger')
                return redirect(request.url)
            fname = f"DCR_{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(file.filename)}"
            fpath = os.path.join(Config.UPLOAD_FOLDER, fname)
            file.save(fpath)
            dc.file_path = fpath
            dc.file_name = file.filename

        db.session.add(AuditTrail(user_id=current_user.id, action='설계변경수정',
            target_type='design_change', target_id=dc.id,
            target_name=f'{dc.change_number} {dc.change_title}'))
        db.session.commit()
        flash(f'설계변경 [{dc.change_number}]이(가) 수정되었습니다.', 'success')
        return redirect(url_for('design.detail', dcid=dc.id))

    departments = Department.query.filter_by(is_active=True).all()
    return render_template('design/new.html', departments=departments, today=date.today(), item=dc)


@design_bp.route('/<int:dcid>')
@login_required
def detail(dcid):
    dc = DesignChange.query.get_or_404(dcid)
    file_url = None
    if dc.file_path:
        fname = os.path.basename(dc.file_path)
        file_url = url_for('static', filename=f'uploads/{fname}')
    users = User.query.filter_by(is_active=True).order_by(User.name).all()
    return render_template('design/detail.html', dc=dc, file_url=file_url, users=users)


@design_bp.route('/<int:dcid>/approve', methods=['POST'])
@login_required
def approve(dcid):
    if not current_user.has_approve():
        flash('승인 권한이 없습니다.', 'danger')
        return redirect(url_for('design.detail', dcid=dcid))
    dc = DesignChange.query.get_or_404(dcid)
    action = request.form.get('action')
    # 본인 요청 건은 본인이 승인/기각 불가 (직무분리)
    if dc.requester_id == current_user.id and not current_user.is_admin() and action in ('approve', 'reject'):
        flash('본인이 요청한 설계변경은 승인/기각할 수 없습니다. (직무분리)', 'danger')
        return redirect(url_for('design.detail', dcid=dcid))
    if action == 'approve':
        dc.status = 'approved'
        dc.approver_id = current_user.id
        dc.approved_date = date.today()
        flash(f'설계변경 [{dc.change_number}]이(가) 승인되었습니다.', 'success')
    elif action == 'reject':
        dc.status = 'rejected'
        flash(f'설계변경 [{dc.change_number}]이(가) 기각되었습니다.', 'warning')
    elif action == 'implement':
        dc.status = 'implemented'
        flash(f'설계변경 [{dc.change_number}]이(가) 반영완료 처리되었습니다.', 'success')
    elif action == 'submit':
        dc.status = 'review'
        flash(f'설계변경 [{dc.change_number}]이(가) 검토 요청되었습니다.', 'info')
    db.session.commit()
    return redirect(url_for('design.detail', dcid=dcid))


@design_bp.route('/<int:dcid>/delete', methods=['POST'])
@login_required
def delete(dcid):
    from deletion import can_delete, remove_file
    dc = DesignChange.query.get_or_404(dcid)
    if not can_delete(dc, 'requester_id', finalized_statuses=('approved', 'implemented', 'rejected')):
        flash('삭제 권한이 없습니다. (작성자는 승인 전까지만, 관리자만 승인건 삭제 가능)', 'danger')
        return redirect(url_for('design.detail', dcid=dcid))
    remove_file(dc.file_path)
    db.session.add(AuditTrail(user_id=current_user.id, action='설계변경삭제',
        target_type='design_change', target_id=dc.id,
        target_name=f'{dc.change_number} {dc.change_title}'))
    db.session.delete(dc)
    db.session.commit()
    flash(f'설계변경 [{dc.change_number}]이(가) 삭제되었습니다.', 'info')
    return redirect(url_for('design.index'))


@design_bp.route('/export-excel')
@login_required
def export_excel():
    changes = DesignChange.query.order_by(DesignChange.created_at.desc()).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = '설계변경 관리 대장'

    hf = PatternFill("solid", fgColor="1a3a5c")
    hfont = Font(bold=True, color="FFFFFF", size=11)
    center = Alignment(horizontal='center', vertical='center', wrap_text=True)
    thin = Border(left=Side(style='thin'), right=Side(style='thin'),
                  top=Side(style='thin'), bottom=Side(style='thin'))

    ws.merge_cells('A1:J1')
    ws['A1'] = '주식회사 누리보이스 설계/개발 변경 관리 대장'
    ws['A1'].font = Font(bold=True, size=14, color="1a3a5c")
    ws['A1'].alignment = center
    ws.row_dimensions[1].height = 30

    headers = ['변경번호', '제품명', '변경유형', '변경제목', '변경사유(요약)', '요청일', '적용예정일', '요청자', '승인자', '상태']
    for col, h in enumerate(headers, 1):
        c = ws.cell(row=2, column=col, value=h)
        c.fill = hf; c.font = hfont; c.alignment = center; c.border = thin

    status_map = {'draft': '초안', 'review': '검토중', 'approved': '승인', 'implemented': '반영완료', 'rejected': '기각'}

    for ri, dc in enumerate(changes, 3):
        row_data = [
            dc.change_number, dc.product_name, dc.change_type or '',
            dc.change_title,
            (dc.change_reason or '')[:60],
            str(dc.request_date) if dc.request_date else '',
            str(dc.apply_date) if dc.apply_date else '',
            dc.requester.name if dc.requester else '',
            dc.approver.name if dc.approver else '',
            status_map.get(dc.status, dc.status),
        ]
        for col, val in enumerate(row_data, 1):
            cell = ws.cell(row=ri, column=col, value=val)
            cell.alignment = center; cell.border = thin

    for i, w in enumerate([14, 20, 14, 30, 40, 12, 12, 12, 12, 10], 1):
        ws.column_dimensions[ws.cell(row=2, column=i).column_letter].width = w

    out = io.BytesIO()
    wb.save(out); out.seek(0)
    return send_file(out,
        download_name=f'설계변경관리대장_{datetime.now().strftime("%Y%m%d")}.xlsx',
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
