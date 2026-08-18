from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file
from flask_login import login_required, current_user
from models import db, Document, DocumentVersion, Approval, Department, AuditTrail
from datetime import datetime, date
import os

documents_bp = Blueprint('documents', __name__)

# 서식(양식)은 편집 가능한 파일이 필요하므로 Office/한글 등 허용,
# 그 외 표준서(매뉴얼·절차서·지침서)는 원본 위·변조 방지를 위해 PDF만 허용
FORM_EXTENSIONS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'hwp', 'hwpx'}


def _check_upload(file, doc_type):
    """문서 유형별 허용 확장자 검사. 통과하면 None, 아니면 오류 메시지 반환."""
    from utils import allowed_file
    if doc_type == '서식':
        if not allowed_file(file.filename, FORM_EXTENSIONS):
            return '서식은 PDF·Word·Excel·한글 파일만 등록할 수 있습니다.'
    else:
        if not allowed_file(file.filename, {'pdf'}):
            return f'{doc_type or "표준서"}는 PDF 파일만 등록할 수 있습니다. (서식만 Office·한글 파일 허용)'
    return None


@documents_bp.route('/next-number')
@login_required
def next_number():
    """등록 폼용 — 유형·약호·연번에 따른 문서번호 미리보기 및 중복확인 (JSON)."""
    from flask import jsonify
    from routes.doc_codes import build_number, next_serial, number_exists
    doc_type = request.args.get('doc_type', '')
    is_dept_doc = request.args.get('is_dept_doc') == '1'
    guide_code = request.args.get('guide_code') or None
    dept_code = request.args.get('dept_code') or None
    part_code = request.args.get('part_code') or None
    revision_no = request.args.get('revision_no', type=int) or 0
    related_id = request.args.get('related_procedure_id', type=int)
    serial = request.args.get('serial', type=int)
    related = Document.query.get(related_id) if related_id else None
    rp_number = related.doc_number if related else None
    auto = False
    if not serial:
        serial = next_serial(doc_type, guide_code, dept_code, part_code, is_dept_doc, rp_number)
        auto = True
    number = build_number(doc_type, serial, revision_no, guide_code, dept_code, part_code, is_dept_doc, rp_number)
    return jsonify(number=number, serial=serial, exists=number_exists(number), auto=auto)


CATEGORY_TYPES = {
    'manual_proc': ['매뉴얼', '절차서'],
    'guide': ['지침서'],
    'form': ['서식'],
}
CATEGORY_TITLE = {
    'manual_proc': ('매뉴얼 · 절차서', '📘', '통합경영시스템 매뉴얼과 절차서(규정류)'),
    'guide': ('지침서 · 지도서', '📗', '검사기준·제조공정도·작업지도서 등 지침서류'),
    'form': ('서식', '📄', '절차서에 연계된 양식(서식)'),
}


@documents_bp.route('/category/<cat>')
@login_required
def category(cat):
    """카테고리별 문서 확인 — 매뉴얼·절차서 / 지침서·지도서 / 서식"""
    if cat not in CATEGORY_TYPES:
        flash('알 수 없는 문서 분류입니다.', 'danger')
        return redirect(url_for('documents.index'))
    q = request.args.get('q', '')
    status = request.args.get('status', '')
    # 구버전(폐기대기)은 별도 '구버전 관리' 메뉴에서만 조회
    query = Document.query.filter(Document.doc_type.in_(CATEGORY_TYPES[cat]),
                                  Document.status != 'obsolete')
    if q:
        query = query.filter((Document.title.contains(q)) | (Document.doc_number.contains(q)))
    if status:
        query = query.filter_by(status=status)
    documents = query.order_by(Document.doc_number).all()
    title, icon, desc = CATEGORY_TITLE[cat]
    counts = {c: Document.query.filter(Document.doc_type.in_(t),
                                       Document.status != 'obsolete').count()
              for c, t in CATEGORY_TYPES.items()}
    obsolete_count = Document.query.filter_by(status='obsolete').count()
    return render_template('documents/category.html', documents=documents, cat=cat,
                           cat_title=title, cat_icon=icon, cat_desc=desc,
                           counts=counts, q=q, status=status,
                           obsolete_count=obsolete_count)


@documents_bp.route('/obsolete')
@login_required
def obsolete():
    """구버전(폐기대기) 문서 관리 — 개정본 승인으로 효력을 잃은 구문서 모음."""
    q = request.args.get('q', '')
    query = Document.query.filter_by(status='obsolete')
    if q:
        query = query.filter((Document.title.contains(q)) | (Document.doc_number.contains(q)))
    documents = query.order_by(Document.doc_number, Document.revision_no).all()
    # 각 구버전을 대체한 현행 문서 매핑
    current_map = {}
    for d in documents:
        cur = Document.query.filter_by(supersedes_id=d.id).first()
        current_map[d.id] = cur
    return render_template('documents/obsolete.html', documents=documents,
                           current_map=current_map, q=q)


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
    from routes.doc_codes import (build_number, next_serial, number_exists,
                                   GUIDE_CODES, DEPT_CODES, DOC_TYPES)
    if request.method == 'POST':
        doc_type = request.form.get('doc_type')
        is_dept_doc = request.form.get('is_dept_doc') == 'on'
        guide_code = request.form.get('guide_code') or None
        dept_code = request.form.get('dept_code') or None
        part_code = request.form.get('part_code') or None
        related_id = request.form.get('related_procedure_id', type=int)
        related_guide_id = request.form.get('related_guide_id', type=int)
        revision_no = request.form.get('revision_no', type=int) or 0
        serial = request.form.get('serial', type=int)

        # 서식은 관련 절차서 지정 필수 (지침서는 선택)
        if doc_type == '서식' and not related_id:
            flash('서식은 관련 절차서를 반드시 선택해야 합니다.', 'danger')
            return redirect(request.url)

        related = Document.query.get(related_id) if related_id else None
        rp_number = related.doc_number if related else None
        if not serial:
            serial = next_serial(doc_type, guide_code, dept_code, part_code, is_dept_doc, rp_number)
        doc_number = build_number(doc_type, serial, revision_no, guide_code,
                                  dept_code, part_code, is_dept_doc, rp_number)

        # 중복 문서번호 차단
        if number_exists(doc_number):
            flash(f'이미 등록된 문서번호입니다: {doc_number} — 연번을 변경해 주세요.', 'danger')
            return redirect(request.url)

        enact = request.form.get('enactment_date')
        eff = request.form.get('effective_date')
        doc = Document(
            doc_number=doc_number,
            title=request.form.get('title'),
            doc_type=doc_type,
            iso_standard=request.form.get('iso_standard'),
            department_id=request.form.get('department_id', type=int),
            version=f'REV{revision_no}',
            revision_no=revision_no,
            status='draft',
            description=request.form.get('description'),
            enactment_date=datetime.strptime(enact, '%Y-%m-%d').date() if enact else None,
            effective_date=datetime.strptime(eff, '%Y-%m-%d').date() if eff else None,
            guide_code=guide_code,
            is_dept_doc=is_dept_doc,
            dept_code=dept_code, part_code=part_code,
            related_procedure_id=related_id,
            related_guide_id=related_guide_id,
            created_by_id=current_user.id,
            created_at=datetime.utcnow(),
        )

        # 파일 업로드 처리
        file = request.files.get('file')
        if file and file.filename:
            from config import Config
            from werkzeug.utils import secure_filename
            err = _check_upload(file, doc_type)
            if err:
                flash(err, 'danger')
                return redirect(request.url)
            filename = f"{doc_number}_{secure_filename(file.filename)}"
            filepath = os.path.join(Config.UPLOAD_FOLDER, filename)
            file.save(filepath)
            doc.file_path = filepath
            doc.file_name = file.filename

        db.session.add(doc)
        db.session.flush()
        db.session.add(AuditTrail(user_id=current_user.id, action='문서등록',
            target_type='document', target_id=doc.id,
            target_name=f'{doc.doc_number} {doc.title}'))
        db.session.commit()
        flash(f'문서 [{doc_number}] {doc.title}이(가) 등록되었습니다.', 'success')
        return redirect(url_for('documents.detail', doc_id=doc.id))

    departments = Department.query.filter_by(is_active=True).all()
    # 서식 연계 대상 (구버전 제외) — 절차서·매뉴얼(필수) / 지침서(선택)
    procedures = (Document.query
                  .filter(Document.doc_type.in_(['매뉴얼', '절차서']),
                          Document.status != 'obsolete')
                  .order_by(Document.doc_type, Document.doc_number).all())
    guides = (Document.query
              .filter(Document.doc_type == '지침서', Document.status != 'obsolete')
              .order_by(Document.doc_number).all())
    return render_template('documents/new.html', departments=departments, procedures=procedures, guides=guides,
                           item=None, guide_codes=GUIDE_CODES, dept_codes=DEPT_CODES, doc_types=DOC_TYPES)


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
        enact = request.form.get('enactment_date')
        doc.enactment_date = datetime.strptime(enact, '%Y-%m-%d').date() if enact else None
        rev = request.form.get('revision_no', type=int)
        if rev is not None:
            doc.revision_no = rev
        # 서식의 관련 지침서(선택) 변경 허용 — 절차서는 번호 채번과 연동되어 고정
        if doc.doc_type == '서식':
            doc.related_guide_id = request.form.get('related_guide_id', type=int)
        doc.description = request.form.get('description')

        file = request.files.get('file')
        if file and file.filename:
            from config import Config
            from werkzeug.utils import secure_filename
            err = _check_upload(file, doc.doc_type)
            if err:
                flash(err, 'danger')
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

    from routes.doc_codes import GUIDE_CODES, DEPT_CODES, DOC_TYPES
    departments = Department.query.filter_by(is_active=True).all()
    # 서식 연계 대상 (구버전 제외) — 절차서·매뉴얼(필수) / 지침서(선택)
    procedures = (Document.query
                  .filter(Document.doc_type.in_(['매뉴얼', '절차서']),
                          Document.status != 'obsolete')
                  .order_by(Document.doc_type, Document.doc_number).all())
    guides = (Document.query
              .filter(Document.doc_type == '지침서', Document.status != 'obsolete')
              .order_by(Document.doc_number).all())
    return render_template('documents/new.html', departments=departments, procedures=procedures, guides=guides,
                           item=doc, guide_codes=GUIDE_CODES, dept_codes=DEPT_CODES, doc_types=DOC_TYPES)


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


@documents_bp.route('/<int:doc_id>/download')
@login_required
def download(doc_id):
    """문서 파일 다운로드 — 구문서(폐기대기)는 배포 금지로 차단."""
    doc = Document.query.get_or_404(doc_id)
    if doc.status == 'obsolete':
        flash(f'구문서 [{doc.doc_number} REV{doc.revision_no or 0}]는 업무 사용·배포가 금지되어 다운로드할 수 없습니다.', 'danger')
        return redirect(url_for('documents.detail', doc_id=doc_id))
    if not doc.file_path or not os.path.exists(doc.file_path):
        flash('첨부 파일을 찾을 수 없습니다.', 'warning')
        return redirect(url_for('documents.detail', doc_id=doc_id))
    db.session.add(AuditTrail(user_id=current_user.id, action='문서다운로드',
        target_type='document', target_id=doc.id,
        target_name=f'{doc.doc_number} {doc.title}'))
    db.session.commit()
    return send_file(doc.file_path, as_attachment=True,
                     download_name=doc.file_name or os.path.basename(doc.file_path))


@documents_bp.route('/<int:doc_id>')
@login_required
def detail(doc_id):
    doc = Document.query.get_or_404(doc_id)

    # ── 개정 이력 누적 조회 ──
    # 같은 문서 계보(구버전 체인) 전체의 개정 이력을 모아 개정차수 오름차순으로 표시
    chain = [doc]
    cur = doc
    while cur.supersedes_id:                    # 과거 방향(구버전)으로 거슬러 올라감
        cur = Document.query.get(cur.supersedes_id)
        if not cur or cur in chain:
            break
        chain.append(cur)
    nxt = Document.query.filter_by(supersedes_id=doc.id).first()
    while nxt and nxt not in chain:             # 미래 방향(개정본)으로 내려감
        chain.append(nxt)
        nxt = Document.query.filter_by(supersedes_id=nxt.id).first()
    chain_ids = [d.id for d in chain]
    versions = (DocumentVersion.query
                .filter(DocumentVersion.document_id.in_(chain_ids))
                .all())
    # 개정차수 기준 정렬 (버전 문자열 'REV숫자'에서 숫자 추출)
    def _rev_key(v):
        try:
            return int(str(v.version).upper().replace('REV', '').strip() or 0)
        except ValueError:
            return 0
    versions.sort(key=_rev_key)
    chain_map = {d.id: d for d in chain}
    for v in versions:                          # 템플릿에서 해당 시점 문서 참조용
        v.src_doc = chain_map.get(v.document_id)

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
        # 개정본 승인 시 — 대체 대상(구버전)을 '구버전(폐기대기)'로 전환
        if doc.supersedes_id and doc.supersedes:
            old = doc.supersedes
            old.status = 'obsolete'
            db.session.add(AuditTrail(user_id=current_user.id, action='구버전전환',
                target_type='document', target_id=old.id,
                target_name=f'{old.doc_number} {old.title}',
                detail=f'개정본 {doc.doc_number}(REV{doc.revision_no}) 승인에 따른 구버전 전환'))
            flash(f'개정본 [{doc.doc_number}]이(가) 승인되어 현행이 되었습니다. 구버전은 폐기대기 상태이며 승인권자가 최종 삭제할 수 있습니다.', 'success')
        else:
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

    if doc.revised_child:
        flash('이미 개정본이 발행되어 승인 진행 중입니다.', 'warning')
        return redirect(url_for('documents.detail', doc_id=doc.revised_child.id))

    if request.method == 'POST':
        change_reason = request.form.get('change_reason')
        new_rev = request.form.get('revision_no', type=int)
        if new_rev is None:
            new_rev = (doc.revision_no or 0) + 1

        # 서식은 번호에 (REVn)이 포함되므로 새 개정번호로 번호를 재생성
        new_number = doc.doc_number
        if doc.doc_type == '서식':
            from routes.doc_codes import build_number
            try:
                serial = int(doc.doc_number.split('-')[2])
            except Exception:
                serial = 1
            rp = doc.related_procedure.doc_number if doc.related_procedure else None
            new_number = build_number('서식', serial, new_rev, related_proc_number=rp)

        # 개정본 = 현행을 유지한 채 '별도 문서'로 신규 생성 (승인대기 상태)
        rev_doc = Document(
            doc_number=new_number, title=doc.title, doc_type=doc.doc_type,
            iso_standard=request.form.get('iso_standard') or doc.iso_standard,
            department_id=doc.department_id,
            version=f'REV{new_rev}', revision_no=new_rev,
            status='draft', description=doc.description,
            enactment_date=doc.enactment_date,
            effective_date=doc.effective_date,
            guide_code=doc.guide_code, is_dept_doc=doc.is_dept_doc,
            dept_code=doc.dept_code, part_code=doc.part_code,
            related_procedure_id=doc.related_procedure_id,
            supersedes_id=doc.id,                     # 대체 대상(구버전) 연결
            created_by_id=current_user.id, created_at=datetime.utcnow(),
        )
        file = request.files.get('file')
        if file and file.filename:
            from config import Config
            from werkzeug.utils import secure_filename
            err = _check_upload(file, doc.doc_type)
            if err:
                flash(err, 'danger')
                return redirect(request.url)
            filename = f"{new_number}_REV{new_rev}_{secure_filename(file.filename)}"
            filepath = os.path.join(Config.UPLOAD_FOLDER, filename)
            file.save(filepath)
            rev_doc.file_path = filepath
            rev_doc.file_name = file.filename
        else:
            rev_doc.file_path = doc.file_path
            rev_doc.file_name = doc.file_name

        db.session.add(rev_doc)
        db.session.flush()
        # 버전 이력은 '구문서(원본)'에 그 문서의 개정차수로 기록한다.
        # (개정본이 아니라 대체되는 원본의 이력이므로 doc.id / REV{doc.revision_no})
        db.session.add(DocumentVersion(
            document_id=doc.id, version=f'REV{doc.revision_no or 0}',
            change_reason=f'[REV{new_rev} 개정본 발행] {change_reason or ""}'.strip(),
            changed_by_id=current_user.id,
            changed_at=datetime.utcnow(), file_path=doc.file_path))
        db.session.add(AuditTrail(user_id=current_user.id, action='개정본발행',
            target_type='document', target_id=rev_doc.id,
            target_name=f'{rev_doc.doc_number} {rev_doc.title} (REV{new_rev})',
            detail=change_reason))
        db.session.commit()
        flash(f'개정본(REV{new_rev})이 별도 문서로 발행되었습니다. 기존 문서는 승인 전까지 현행으로 유지됩니다.', 'success')
        return redirect(url_for('documents.detail', doc_id=rev_doc.id))

    next_rev = (doc.revision_no or 0) + 1
    return render_template('documents/revision.html', doc=doc, next_rev=next_rev)


@documents_bp.route('/<int:doc_id>/dispose-old', methods=['POST'])
@login_required
def dispose_old(doc_id):
    """개정본 승인 후 남은 구버전 문서를 승인권자가 최종 삭제."""
    from deletion import remove_file
    from models import Concurrence
    doc = Document.query.get_or_404(doc_id)
    if not current_user.has_approve():
        flash('구버전 삭제는 승인권자만 가능합니다.', 'danger')
        return redirect(url_for('documents.detail', doc_id=doc_id))
    if doc.status != 'obsolete':
        flash('구버전(폐기대기) 상태의 문서만 삭제할 수 있습니다.', 'danger')
        return redirect(url_for('documents.detail', doc_id=doc_id))
    child = doc.revised_child
    remove_file(doc.file_path)
    for v in DocumentVersion.query.filter_by(document_id=doc.id).all():
        remove_file(v.file_path)
        db.session.delete(v)
    Approval.query.filter_by(document_id=doc.id).delete()
    Concurrence.query.filter_by(target_type='document', target_id=doc.id).delete()
    if child:
        child.supersedes_id = None
    num = doc.doc_number
    db.session.add(AuditTrail(user_id=current_user.id, action='구버전폐기',
        target_type='document', target_id=doc.id, target_name=f'{num} {doc.title}'))
    db.session.delete(doc)
    db.session.commit()
    flash(f'구버전 문서 [{num}]이(가) 최종 폐기되었습니다.', 'info')
    return redirect(url_for('documents.detail', doc_id=child.id) if child else url_for('documents.index'))
