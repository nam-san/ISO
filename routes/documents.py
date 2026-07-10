from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file
from flask_login import login_required, current_user
from models import db, Document, DocumentVersion, Approval, Department, AuditTrail
from datetime import datetime, date
import os

documents_bp = Blueprint('documents', __name__)


def _next_doc_number(doc_type, sub_type=None, parent_doc_id=None):
    """
    주식회사 누리보이스 표준서 번호 부여 기준 적용
    10.1.1 품질매뉴얼: NV-QM-00
    10.1.2 절차서(규정류): NV-P-000
    10.1.3 지침서: NV-[지침서약호]-00 (II, PI, OI, WC, WI)
    10.1.4 서식(양식): P-000-0-(REV0)
    """
    if doc_type == '매뉴얼':
        last = Document.query.filter(
            Document.doc_number.like('NV-QM-%')
        ).order_by(Document.id.desc()).first()
        if last:
            try:
                num = int(last.doc_number.split('-')[-1]) + 1
            except Exception:
                num = 1
        else:
            num = 1
        return f'NV-QM-{num:02d}'

    elif doc_type == '절차서':
        last = Document.query.filter(
            Document.doc_number.like('NV-P-%')
        ).order_by(Document.id.desc()).first()
        if last:
            try:
                num = int(last.doc_number.split('-')[-1]) + 1
            except Exception:
                num = 1
        else:
            num = 1
        return f'NV-P-{num:03d}'

    elif doc_type == '지침서':
        prefix = sub_type or 'II'
        last = Document.query.filter(
            Document.doc_number.like(f'NV-{prefix}-%')
        ).order_by(Document.id.desc()).first()
        if last:
            try:
                num = int(last.doc_number.split('-')[-1]) + 1
            except Exception:
                num = 1
        else:
            num = 1
        return f'NV-{prefix}-{num:02d}'

    elif doc_type == '서식':
        parent_doc = Document.query.get(parent_doc_id) if parent_doc_id else None
        if parent_doc:
            parent_no = parent_doc.doc_number
            if 'NV-P-' in parent_no:
                p_code = parent_no.replace('NV-', '')  # P-001
            else:
                p_code = 'P-000'
        else:
            p_code = 'P-000'

        last_form = Document.query.filter(
            Document.doc_type == '서식',
            Document.doc_number.like(f'{p_code}-%')
        ).order_by(Document.id.desc()).first()
        
        if last_form:
            try:
                parts = last_form.doc_number.split('-')
                num = int(parts[2]) + 1
            except Exception:
                num = 1
        else:
            num = 1
            
        return f'{p_code}-{num}-(REV0)'

    return 'NV-DOC-001'


@documents_bp.route('/')
@login_required
def index():
    q = request.args.get('q', '')
    iso = request.args.get('iso', '')
    dept_id = request.args.get('dept', '')
    status = request.args.get('status', '')
    doc_type = request.args.get('type', '')

    query = Document.query
    if q:
        query = query.filter(
            (Document.title.contains(q)) | (Document.doc_number.contains(q))
        )
    if iso:
        query = query.filter_by(iso_standard=iso)
    if dept_id:
        query = query.filter_by(department_id=int(dept_id))
    if status:
        query = query.filter_by(status=status)
    if doc_type:
        query = query.filter_by(doc_type=doc_type)

    documents = query.order_by(Document.created_at.desc()).all()
    departments = Department.query.filter_by(is_active=True).all()

    return render_template('documents/index.html',
        documents=documents,
        departments=departments,
        q=q, iso=iso, dept_id=dept_id, status=status, doc_type=doc_type
    )


@documents_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    if not current_user.has_edit():
        flash('문서 등록 권한이 없습니다.', 'danger')
        return redirect(url_for('documents.index'))
    if request.method == 'POST':
        iso_standard = request.form.get('iso_standard')
        doc_type = request.form.get('doc_type')
        
        sub_type = request.form.get('sub_type')
        parent_doc_id = request.form.get('parent_doc_id', type=int)
        
        doc_number = _next_doc_number(doc_type, sub_type, parent_doc_id)

        doc = Document(
            doc_number=doc_number,
            title=request.form.get('title'),
            doc_type=doc_type,
            iso_standard=iso_standard,
            department_id=request.form.get('department_id', type=int),
            version='1.0',
            status='draft',
            description=request.form.get('description'),
            effective_date=datetime.strptime(request.form.get('effective_date'), '%Y-%m-%d').date()
                           if request.form.get('effective_date') else None,
            created_by_id=current_user.id,
            created_at=datetime.utcnow(),
        )

        # 파일 업로드 처리
        file = request.files.get('file')
        if file and file.filename:
            from config import Config
            from werkzeug.utils import secure_filename
            from utils import allowed_file
            if not allowed_file(file.filename, Config.ALLOWED_EXTENSIONS):
                flash('허용되지 않는 파일 형식입니다. (PDF/Office/한글/이미지만 가능)', 'danger')
                return redirect(request.url)
            filename = f"{doc_number}_v1.0_{secure_filename(file.filename)}"
            filepath = os.path.join(Config.UPLOAD_FOLDER, filename)
            file.save(filepath)
            doc.file_path = filepath
            doc.file_name = file.filename

        db.session.add(doc)
        db.session.flush()  # ID 확보

        # 감사 로그
        log = AuditTrail(
            user_id=current_user.id,
            action='문서등록',
            target_type='document',
            target_id=doc.id,
            target_name=f'{doc.doc_number} {doc.title}',
        )
        db.session.add(log)
        db.session.commit()

        flash(f'문서 [{doc_number}] {doc.title}이(가) 등록되었습니다.', 'success')
        return redirect(url_for('documents.detail', doc_id=doc.id))

    departments = Department.query.filter_by(is_active=True).all()
    procedures = Document.query.filter_by(doc_type='절차서').all()
    return render_template('documents/new.html', departments=departments, procedures=procedures, item=None)


@documents_bp.route('/<int:doc_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(doc_id):
    """초안 문서 기본정보 수정 (승인 전까지만)"""
    doc = Document.query.get_or_404(doc_id)
    if not current_user.has_edit() or not (current_user.is_admin() or doc.created_by_id == current_user.id):
        flash('수정 권한이 없습니다. (작성자 또는 관리자만)', 'danger')
        return redirect(url_for('documents.detail', doc_id=doc_id))
    if doc.status != 'draft':
        flash('초안 상태의 문서만 수정할 수 있습니다. 승인된 문서는 개정 기능을 이용하세요.', 'danger')
        return redirect(url_for('documents.detail', doc_id=doc_id))
    if request.method == 'POST':
        doc.title = request.form.get('title')
        doc.iso_standard = request.form.get('iso_standard')
        doc.department_id = request.form.get('department_id', type=int)
        eff = request.form.get('effective_date')
        doc.effective_date = datetime.strptime(eff, '%Y-%m-%d').date() if eff else None
        doc.description = request.form.get('description')

        file = request.files.get('file')
        if file and file.filename:
            from config import Config
            from werkzeug.utils import secure_filename
            from utils import allowed_file
            if not allowed_file(file.filename, Config.ALLOWED_EXTENSIONS):
                flash('허용되지 않는 파일 형식입니다. (PDF/Office/한글/이미지만 가능)', 'danger')
                return redirect(request.url)
            filename = f"{doc.doc_number}_v{doc.version}_{secure_filename(file.filename)}"
            filepath = os.path.join(Config.UPLOAD_FOLDER, filename)
            file.save(filepath)
            doc.file_path = filepath
            doc.file_name = file.filename

        db.session.add(AuditTrail(user_id=current_user.id, action='문서수정',
            target_type='document', target_id=doc.id,
            target_name=f'{doc.doc_number} {doc.title}'))
        db.session.commit()
        flash(f'문서 [{doc.doc_number}] 정보가 수정되었습니다.', 'success')
        return redirect(url_for('documents.detail', doc_id=doc.id))

    departments = Department.query.filter_by(is_active=True).all()
    procedures = Document.query.filter_by(doc_type='절차서').all()
    return render_template('documents/new.html', departments=departments, procedures=procedures, item=doc)


@documents_bp.route('/<int:doc_id>/delete', methods=['POST'])
@login_required
def delete(doc_id):
    from deletion import can_delete, remove_file
    from models import Concurrence
    doc = Document.query.get_or_404(doc_id)
    # 작성자는 초안만, 관리자는 전부
    if not can_delete(doc, 'created_by_id', finalized_statuses=('review', 'approved', 'active', 'obsolete')):
        flash('삭제 권한이 없습니다. (작성자는 초안만, 관리자만 상신·승인건 삭제 가능)', 'danger')
        return redirect(url_for('documents.detail', doc_id=doc_id))
    # 첨부·버전 파일 및 하위 데이터 정리
    remove_file(doc.file_path)
    for v in DocumentVersion.query.filter_by(document_id=doc.id).all():
        remove_file(v.file_path)
        db.session.delete(v)
    Approval.query.filter_by(document_id=doc.id).delete()
    Concurrence.query.filter_by(target_type='document', target_id=doc.id).delete()
    db.session.add(AuditTrail(user_id=current_user.id, action='문서삭제',
        target_type='document', target_id=doc.id,
        target_name=f'{doc.doc_number} {doc.title}'))
    db.session.delete(doc)
    db.session.commit()
    flash(f'문서 [{doc.doc_number}]이(가) 삭제되었습니다.', 'info')
    return redirect(url_for('documents.index'))


@documents_bp.route('/<int:doc_id>')
@login_required
def detail(doc_id):
    doc = Document.query.get_or_404(doc_id)
    versions = DocumentVersion.query.filter_by(document_id=doc_id).order_by(DocumentVersion.id.desc()).all()
    approvals = Approval.query.filter_by(document_id=doc_id).order_by(Approval.step).all()

    # 절대 경로를 웹용 상대 URL로 안전하게 가공
    file_url = None
    if doc.file_path:
        filename = os.path.basename(doc.file_path)
        file_url = url_for('static', filename=f'uploads/{filename}')

    # 감사 로그 (열람)
    log = AuditTrail(
        user_id=current_user.id,
        action='문서열람',
        target_type='document',
        target_id=doc.id,
        target_name=f'{doc.doc_number} {doc.title}',
    )
    db.session.add(log)
    db.session.commit()

    # 관계부서 합의 결재 현황
    from concurrence import get_list, status_counts, can_finalize, can_concur
    concurrences = get_list('document', doc.id)
    for c in concurrences:
        c.can_act = can_concur(current_user, c.department_id)   # 템플릿용 임시 플래그
    concur_counts = status_counts('document', doc.id)
    concur_can_final = can_finalize('document', doc.id)
    concur_dept_options = Department.query.filter_by(is_active=True).order_by(Department.id).all()

    return render_template('documents/detail.html', doc=doc, versions=versions,
        approvals=approvals, file_url=file_url,
        concurrences=concurrences, concur_counts=concur_counts,
        concur_can_final=concur_can_final, concur_dept_options=concur_dept_options)


@documents_bp.route('/<int:doc_id>/submit', methods=['POST'])
@login_required
def submit_approval(doc_id):
    """결재 상신 — 관계부서 합의 지정 포함"""
    doc = Document.query.get_or_404(doc_id)
    if doc.created_by_id != current_user.id and not current_user.is_admin():
        flash('권한이 없습니다.', 'danger')
        return redirect(url_for('documents.detail', doc_id=doc_id))

    from concurrence import set_departments, reset
    dept_ids = request.form.getlist('concur_depts')
    set_departments('document', doc.id, dept_ids)
    reset('document', doc.id)   # 재상신 시 기존 합의 의견 초기화
    doc.status = 'review'
    db.session.add(AuditTrail(user_id=current_user.id, action='합의결재상신',
        target_type='document', target_id=doc.id,
        target_name=f'{doc.doc_number} {doc.title}',
        detail=f'합의부서 {len(dept_ids)}개 지정'))
    db.session.commit()
    if dept_ids:
        flash(f'문서 [{doc.doc_number}]이(가) 관계부서 합의({len(dept_ids)}개 부서) 후 결재 진행됩니다.', 'success')
    else:
        flash(f'문서 [{doc.doc_number}]이(가) 결재 상신되었습니다.', 'success')
    return redirect(url_for('documents.detail', doc_id=doc_id))


@documents_bp.route('/<int:doc_id>/concur', methods=['POST'])
@login_required
def concur(doc_id):
    """관계부서 합의/반려 처리"""
    from models import Concurrence
    from concurrence import can_concur, act
    doc = Document.query.get_or_404(doc_id)
    dept_id = request.form.get('department_id', type=int)
    c = Concurrence.query.filter_by(target_type='document', target_id=doc.id,
                                    department_id=dept_id).first_or_404()
    if not can_concur(current_user, c.department_id):
        flash('해당 부서의 합의 권한이 없습니다. (소속 부서의 검토·승인 권한자만 가능)', 'danger')
        return redirect(url_for('documents.detail', doc_id=doc_id))

    action = request.form.get('action')   # agree / disagree
    act(c, current_user, action, request.form.get('comment'))
    db.session.add(AuditTrail(user_id=current_user.id,
        action='합의' if action == 'agree' else '합의반려',
        target_type='document', target_id=doc.id,
        target_name=f'{doc.doc_number} ({c.department.name})'))
    db.session.commit()
    flash(f'{c.department.name}의 합의 의견이 등록되었습니다.', 'success')
    return redirect(url_for('documents.detail', doc_id=doc_id))


@documents_bp.route('/<int:doc_id>/reopen', methods=['POST'])
@login_required
def reopen(doc_id):
    """작성중으로 되돌림 (합의 반려 시 작성자 수정용)"""
    doc = Document.query.get_or_404(doc_id)
    if doc.created_by_id != current_user.id and not current_user.is_admin():
        flash('권한이 없습니다.', 'danger')
        return redirect(url_for('documents.detail', doc_id=doc_id))
    doc.status = 'draft'
    db.session.commit()
    flash('작성중으로 되돌렸습니다. 수정 후 다시 상신하세요.', 'info')
    return redirect(url_for('documents.detail', doc_id=doc_id))


@documents_bp.route('/<int:doc_id>/approve', methods=['POST'])
@login_required
def approve(doc_id):
    """문서 승인"""
    if not current_user.has_approve():
        flash('승인 권한이 없습니다.', 'danger')
        return redirect(url_for('documents.detail', doc_id=doc_id))

    doc = Document.query.get_or_404(doc_id)
    if doc.created_by_id == current_user.id and not current_user.is_admin():
        flash('본인이 작성한 문서는 승인할 수 없습니다. (직무분리)', 'danger')
        return redirect(url_for('documents.detail', doc_id=doc_id))

    action = request.form.get('action')  # approve / reject
    comment = request.form.get('comment', '')

    # 관계부서 합의 미완료 시 최종 승인 차단 (반려는 허용)
    if action == 'approve':
        from concurrence import can_finalize
        if not can_finalize('document', doc.id):
            flash('관계부서 합의가 완료되지 않아 승인할 수 없습니다. (모든 합의부서 동의 필요)', 'danger')
            return redirect(url_for('documents.detail', doc_id=doc_id))

    approval = Approval(
        document_id=doc_id,
        approver_id=current_user.id,
        step=1,
        role_label=current_user.position or current_user.role,
        comment=comment,
        acted_at=datetime.utcnow(),
    )

    if action == 'approve':
        approval.status = 'approved'
        doc.status = 'active'
        doc.approved_by_id = current_user.id
        doc.approved_at = datetime.utcnow()
        flash(f'문서 [{doc.doc_number}]이(가) 승인되었습니다.', 'success')
    else:
        approval.status = 'rejected'
        doc.status = 'draft'
        flash(f'문서 [{doc.doc_number}]이(가) 반려되었습니다.', 'warning')

    db.session.add(approval)
    log = AuditTrail(
        user_id=current_user.id,
        action='문서결재',
        target_type='document',
        target_id=doc.id,
        target_name=f'{doc.doc_number} {doc.title}',
        detail=f'{action} / {comment}'
    )
    db.session.add(log)
    db.session.commit()

    return redirect(url_for('documents.detail', doc_id=doc_id))


@documents_bp.route('/<int:doc_id>/revision', methods=['GET', 'POST'])
@login_required
def revision(doc_id):
    """문서 개정 등록"""
    if not current_user.has_edit():
        flash('문서 개정 권한이 없습니다.', 'danger')
        return redirect(url_for('documents.detail', doc_id=doc_id))

    doc = Document.query.get_or_404(doc_id)
    if doc.status != 'active':
        flash('배포 중인 문서만 개정할 수 있습니다.', 'danger')
        return redirect(url_for('documents.detail', doc_id=doc_id))

    if request.method == 'POST':
        new_version = request.form.get('version')
        change_reason = request.form.get('change_reason')
        iso_standard = request.form.get('iso_standard')  # 적용 규격 개정 기능 추가

        # 1. 기존 활성화 버전을 역사(DocumentVersion)에 기록 보관
        old_version = DocumentVersion(
            document_id=doc.id,
            version=doc.version,
            change_reason=change_reason,
            changed_by_id=current_user.id,
            changed_at=datetime.utcnow(),
            file_path=doc.file_path
        )
        db.session.add(old_version)

        # 2. Document 본체의 버전, 상태, 규격, 첨부파일 정보 업데이트
        doc.version = new_version
        doc.status = 'draft'  # 개정 초안 상태로 설정 (다시 승인을 받아야 함)
        doc.iso_standard = iso_standard  # 신규 규격 반영
        doc.created_by_id = current_user.id
        doc.created_at = datetime.utcnow()
        doc.approved_by_id = None
        doc.approved_at = None

        # 새 파일 업로드 처리
        file = request.files.get('file')
        if file and file.filename:
            from config import Config
            from werkzeug.utils import secure_filename
            from utils import allowed_file
            if not allowed_file(file.filename, Config.ALLOWED_EXTENSIONS):
                flash('허용되지 않는 파일 형식입니다. (PDF/Office/한글/이미지만 가능)', 'danger')
                return redirect(request.url)
            filename = f"{doc.doc_number}_v{new_version}_{secure_filename(file.filename)}"
            filepath = os.path.join(Config.UPLOAD_FOLDER, filename)
            file.save(filepath)
            doc.file_path = filepath
            doc.file_name = file.filename

        # 3. 기존 결재 이력 초기화 (새로운 개정본 결재 프로세스 돌리기 위함)
        Approval.query.filter_by(document_id=doc.id).delete()

        # 감사 로그 기록
        log = AuditTrail(
            user_id=current_user.id,
            action='문서개정',
            target_type='document',
            target_id=doc.id,
            target_name=f'{doc.doc_number} {doc.title} (v{new_version})',
            detail=change_reason
        )
        db.session.add(log)
        db.session.commit()

        flash(f'문서 [{doc.doc_number}] 개정본(v{new_version}) 초안이 등록되었습니다. 결재를 상신해 주세요.', 'success')
        return redirect(url_for('documents.detail', doc_id=doc.id))

    # 기본 추천 새 버전 계산 (예: 1.0 -> 2.0 또는 1.1)
    try:
        parts = doc.version.split('.')
        major = int(parts[0])
        minor = int(parts[1])
        rec_major = f"{major + 1}.0"
        rec_minor = f"{major}.{minor + 1}"
    except Exception:
        rec_major = "2.0"
        rec_minor = "1.1"

    return render_template('documents/revision.html', doc=doc, rec_major=rec_major, rec_minor=rec_minor)
