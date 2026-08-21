from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file
from flask_login import login_required, current_user
from models import (db, QualificationType, Qualification, QualificationAttachment,
                    Department, User, AuditTrail)
from datetime import datetime, date, timedelta
import os

qualification_bp = Blueprint('qualification', __name__)

IMAGE_EXTS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

CATEGORIES = ['사내 자격인증', '법정 선임인력', '운전·취급 자격', '위원회·직책 지정']
CAT_COLOR = {
    '사내 자격인증': ('#2563eb', '#dbeafe'),
    '법정 선임인력': ('#b91c1c', '#fee2e2'),
    '운전·취급 자격': ('#a16207', '#fef9c3'),
    '위원회·직책 지정': ('#15803d', '#dcfce7'),
}
DOC_KINDS = ['교육수료증', '자격증', '적격성평가서', '선임계', '기타']

# ── 자격관리 현황표(2026.08.21) 기준 11종 시드 ──
QUAL_SEED = [
    ('사내 자격인증', '내부 심사원', 'NV-P-010 / NV-P-029', 'NV-P-010 4항·별첨1 / NV-P-029 3항',
     '품질·환경·안전보건 내부심사원',
     '① 내부품질·환경심사원 교육이수(사외, 필수) + ② 당사 경력 1년↑ 과장급 또는 ③ 외부지도사 8시간↑ 교육 또는 ④ ISO/TL9000 사내교육 20시간↑ 중 1개 만족',
     '대표이사 또는 경영대리인', 'ISO 9001/14001/45001(9.2 내부심사)',
     '자격부여 관리대장(P-010-3), 자격검토 및 자격인정서(P-010-4)', 24,
     '관리팀장이 매 2년마다 자격 유지 갱신평가'),
    ('사내 자격인증', '품질 검사원 및 시험원', 'NV-P-010', '4항·별첨1', '수입검사·출하검사·품질시험 담당자',
     '고졸 이상(색맹 아니고 교정시력 1.0↑), 당사 경력 6개월↑, QC분야 3개월↑ 경력, 검사원 적격성평가 70점↑(전항 만족)',
     '품질경영팀장', 'ISO 9001', '자격부여 관리대장, 검사원 적격성평가서(P-010-5)', 24, ''),
    ('사내 자격인증', '공정 검사원', 'NV-P-010', '4항·별첨1', '공정검사 담당자',
     '고졸 이상(색맹 아니고 교정시력 1.0↑), 당사 경력 3개월↑, QC분야 3개월↑ 경력, 검사원 적격성평가 70점↑(전항 만족)',
     '품질경영팀장', 'ISO 9001', '자격부여 관리대장, 검사원 적격성평가서(P-010-5)', 24, ''),
    ('사내 자격인증', '특별공정 작업자', 'NV-P-010', '4항·별첨1', '결과검증이 곤란한 특별공정(용접 등) 작업자',
     '고졸 이상, 당사 해당업무 1개월↑, 해당업무 교육이수, 전자·전기 관련 기사·기능사 2급 이상 자격증 소지(전항 만족)',
     '제조팀장', 'ISO 9001(8.5.1 특별공정)', '자격부여 관리대장', 24, ''),
    ('법정 선임인력', '안전관리자·보건관리자·안전보건관리담당자·관리감독자', 'NV-P-041', '4.1.1~4.1.2',
     '사업장 규모·업종별 법정 선임대상 인력',
     '매년 1회 이상 선임대상 해당여부 확인, 선임 필요 시 지체없이 선임 절차 진행',
     '안전보건관리책임자', '산업안전보건법',
     '안전보건관리책임자 등 선임계(NV-P-004-F1), 법규등록부(NV-P-008-F1)', 12, 'ISO 45001 5.3 연계'),
    ('법정 선임인력', '전기안전관리자', 'NV-P-011 / NV-P-041', 'NV-P-011 5.1.2.2 / NV-P-041 4.1.1',
     '전기설비 안전관리(선임대상 설비 보유 사업장)',
     '선임대상 시 매년 정기점검, 비대상 시 외부 전기안전 점검업체 점검으로 대체',
     '안전보건관리책임자', '전기안전관리법', '안전보건관리책임자 등 선임계(NV-P-004-F1)', 12, ''),
    ('법정 선임인력', '소방안전관리자', 'NV-P-025 / NV-P-041', 'NV-P-025 / NV-P-041 4.1.1',
     '소방시설 관리(선임대상 사업장)', '선임된 경우 소방시설 점검결과(월1회 이상) 통보 대상',
     '안전보건관리책임자', '화재의 예방 및 안전관리에 관한 법률',
     '안전보건관리책임자 등 선임계(NV-P-004-F1), 소방시설 점검표', 12, ''),
    ('운전·취급 자격', '지게차 운전자격', 'NV-P-043', '고위험작업 목록(지게차)', '지게차 운전자',
     '작업 전 운전자격 확인, 제동장치·경적·후진경보기 점검, 유도자 배치, 정격하중 준수',
     '관리감독자(작업허가권자)', '건설기계관리법 / 산업안전보건법', '고위험작업허가서', None, ''),
    ('위원회·직책 지정', '선임심사원 지정', 'NV-P-029', '5.1.3', '내부심사팀(다수 심사원 편성 시)',
     '심사계획 수립 시 선임심사원을 지정하여 심사내용을 심사원들과 협의·결정',
     '품질경영대리인', 'ISO 9001/14001/45001(9.2)', '내부심사 실시품의서(P-029-1)', None, ''),
    ('위원회·직책 지정', '응급처치 담당자', 'NV-P-025', '5.9.1', '부서별 1인 이상',
     '심폐소생술 등 응급처치 교육 이수 후 지정, 부상자 발생 시 응급처치 실시',
     '안전보건관리책임자', '산업안전보건법', '교육 이수기록', 24, ''),
    ('위원회·직책 지정', '비상대응팀원(지휘/통제, 방호복구, 의무/대피지원)', 'NV-P-025', '5.x 비상대응팀 편성',
     '비상대응팀 편성표상 지정 인원',
     '팀별 역할에 따른 개인보호구 지급, 연 1회 이상 역할별 교육훈련 이수',
     '안전보건관리책임자', '산업안전보건법 / ISO 45001', '비상대응팀 편성표, 교육 이수기록', 12, ''),
]


def seed_qualification_types():
    if QualificationType.query.count() > 0:
        return
    for i, row in enumerate(QUAL_SEED):
        (cat, name, doc, clause, job, req, approver, legal, form, renew, note) = row
        db.session.add(QualificationType(
            category=cat, name=name, procedure_doc=doc, clause=clause, target_job=job,
            requirement=req, approver_role=approver, legal_basis=legal, record_form=form,
            renewal_months=renew, note=note, sort_order=i, is_active=True))
    db.session.commit()
    print(f"[시드] 자격 종류 {len(QUAL_SEED)}종 생성")


def _next_cert_number():
    year = datetime.now().year
    n = Qualification.query.filter(Qualification.cert_number.like(f'NV-QC-{year}-%')).count() + 1
    return f'NV-QC-{year}-{n:03d}'


def _parse_date(v):
    return datetime.strptime(v, '%Y-%m-%d').date() if v else None


def _add_months(d, months):
    if not d or not months:
        return None
    y, m = divmod(d.month - 1 + months, 12)
    day = min(d.day, [31, 29 if (d.year + y) % 4 == 0 else 28, 31, 30, 31, 30,
                      31, 31, 30, 31, 30, 31][m])
    return date(d.year + y, m + 1, day)


def _refresh_status(q):
    if q.status == 'revoked':
        return
    q.status = 'expired' if (q.expire_date and q.expire_date < date.today()) else 'valid'


@qualification_bp.route('/')
@login_required
def index():
    """자격인정 현황 — 자격별 인증인원 요약"""
    cat = request.args.get('cat', '')
    q = request.args.get('q', '')
    query = QualificationType.query.filter_by(is_active=True)
    if cat:
        query = query.filter_by(category=cat)
    if q:
        query = query.filter(QualificationType.name.contains(q))
    types = query.order_by(QualificationType.sort_order, QualificationType.id).all()

    # 자격별 인증 현황 집계
    status = {}
    for t in types:
        certs = t.certifications.all()
        for c in certs:
            _refresh_status(c)
        valid = [c for c in certs if c.status == 'valid']
        soon = [c for c in valid if c.expire_date and 0 <= (c.expire_date - date.today()).days <= 60]
        status[t.id] = {
            'total': len(certs),
            'valid': len(valid),
            'expired': len([c for c in certs if c.status == 'expired']),
            'soon': len(soon),
        }
    db.session.commit()

    all_certs = Qualification.query.all()
    stats = {
        'types': QualificationType.query.filter_by(is_active=True).count(),
        'certified': len([c for c in all_certs if c.status == 'valid']),
        'expiring': len([c for c in all_certs if c.status == 'valid' and c.expire_date
                         and 0 <= (c.expire_date - date.today()).days <= 60]),
        'expired': len([c for c in all_certs if c.status == 'expired']),
    }
    return render_template('qualification/index.html', types=types, status=status,
                           stats=stats, cat=cat, q=q, categories=CATEGORIES,
                           cat_color=CAT_COLOR, today=date.today())


@qualification_bp.route('/type/<int:type_id>')
@login_required
def type_detail(type_id):
    """자격 종류 상세 — 기준 + 인증자 명단"""
    t = QualificationType.query.get_or_404(type_id)
    certs = t.certifications.order_by(Qualification.certified_date.desc()).all()
    for c in certs:
        _refresh_status(c)
    db.session.commit()
    return render_template('qualification/type_detail.html', t=t, certs=certs,
                           cat_color=CAT_COLOR, today=date.today())


@qualification_bp.route('/type/save', methods=['POST'])
@login_required
def type_save():
    """자격 종류 추가·수정 (기준 관리)"""
    if not current_user.is_admin():
        flash('자격 기준 관리는 시스템 관리자만 가능합니다.', 'danger')
        return redirect(url_for('qualification.index'))
    tid = request.form.get('id', type=int)
    t = QualificationType.query.get(tid) if tid else QualificationType(
        sort_order=QualificationType.query.count())
    f = request.form
    t.category = f.get('category')
    t.name = f.get('name')
    t.procedure_doc = f.get('procedure_doc')
    t.clause = f.get('clause')
    t.target_job = f.get('target_job')
    t.requirement = f.get('requirement')
    t.approver_role = f.get('approver_role')
    t.legal_basis = f.get('legal_basis')
    t.record_form = f.get('record_form')
    t.renewal_months = f.get('renewal_months', type=int)
    t.note = f.get('note')
    if not tid:
        db.session.add(t)
    db.session.commit()
    flash('자격 기준이 저장되었습니다.', 'success')
    return redirect(url_for('qualification.index'))


@qualification_bp.route('/type/<int:type_id>/delete', methods=['POST'])
@login_required
def type_delete(type_id):
    if not current_user.is_admin():
        flash('관리자만 삭제할 수 있습니다.', 'danger')
        return redirect(url_for('qualification.index'))
    t = QualificationType.query.get_or_404(type_id)
    if t.certifications.count() > 0:
        flash('인증 내역이 있는 자격은 삭제할 수 없습니다. (비활성 처리하세요)', 'danger')
        return redirect(url_for('qualification.type_detail', type_id=type_id))
    name = t.name
    db.session.delete(t)
    db.session.commit()
    flash(f'자격 [{name}]이(가) 삭제되었습니다.', 'info')
    return redirect(url_for('qualification.index'))


@qualification_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    """자격 인증 등록"""
    if not current_user.is_admin():
        flash('자격인증 등록은 시스템 관리자만 가능합니다.', 'danger')
        return redirect(url_for('qualification.index'))
    type_id = request.args.get('type_id', type=int) or request.form.get('qtype_id', type=int)
    if request.method == 'POST':
        q = Qualification(cert_number=_next_cert_number(), created_by_id=current_user.id)
        _apply_form(q)
        db.session.add(q)
        db.session.flush()
        _save_attachments(q)
        db.session.add(AuditTrail(user_id=current_user.id, action='자격인증등록',
                                  target_type='qualification', target_id=q.id,
                                  target_name=f'{q.cert_number} {q.person_name}'))
        db.session.commit()
        flash(f'자격인증 [{q.cert_number}] {q.person_name}이(가) 등록되었습니다.', 'success')
        return redirect(url_for('qualification.detail', qid=q.id))

    types = QualificationType.query.filter_by(is_active=True).order_by(
        QualificationType.sort_order).all()
    users = User.query.filter_by(is_active=True).order_by(User.name).all()
    departments = Department.query.filter_by(is_active=True).all()
    return render_template('qualification/form.html', item=None, types=types, users=users,
                           departments=departments, sel_type=type_id, today=date.today(),
                           doc_kinds=DOC_KINDS, next_number=_next_cert_number())


@qualification_bp.route('/<int:qid>')
@login_required
def detail(qid):
    q = Qualification.query.get_or_404(qid)
    _refresh_status(q)
    db.session.commit()
    atts = q.attachments.order_by(QualificationAttachment.id).all()
    return render_template('qualification/detail.html', q=q, atts=atts,
                           cat_color=CAT_COLOR, today=date.today())


@qualification_bp.route('/<int:qid>/edit', methods=['GET', 'POST'])
@login_required
def edit(qid):
    q = Qualification.query.get_or_404(qid)
    if not current_user.is_admin():
        flash('자격인증 수정은 시스템 관리자만 가능합니다.', 'danger')
        return redirect(url_for('qualification.detail', qid=qid))
    if request.method == 'POST':
        _apply_form(q)
        _save_attachments(q)
        db.session.add(AuditTrail(user_id=current_user.id, action='자격인증수정',
                                  target_type='qualification', target_id=q.id,
                                  target_name=f'{q.cert_number} {q.person_name}'))
        db.session.commit()
        flash('자격인증 정보가 수정되었습니다.', 'success')
        return redirect(url_for('qualification.detail', qid=qid))
    types = QualificationType.query.filter_by(is_active=True).order_by(
        QualificationType.sort_order).all()
    users = User.query.filter_by(is_active=True).order_by(User.name).all()
    departments = Department.query.filter_by(is_active=True).all()
    return render_template('qualification/form.html', item=q, types=types, users=users,
                           departments=departments, sel_type=q.qtype_id, today=date.today(),
                           doc_kinds=DOC_KINDS, next_number=q.cert_number)


@qualification_bp.route('/<int:qid>/renew', methods=['POST'])
@login_required
def renew(qid):
    """자격 갱신 — 인증일자·만료일 갱신"""
    q = Qualification.query.get_or_404(qid)
    if not current_user.is_admin():
        flash('자격 갱신은 시스템 관리자만 가능합니다.', 'danger')
        return redirect(url_for('qualification.detail', qid=qid))
    new_date = _parse_date(request.form.get('certified_date')) or date.today()
    q.certified_date = new_date
    months = q.qtype.renewal_months if q.qtype else None
    exp = _parse_date(request.form.get('expire_date'))
    q.expire_date = exp or _add_months(new_date, months)
    q.status = 'valid'
    q.approver_id = current_user.id
    db.session.add(AuditTrail(user_id=current_user.id, action='자격갱신',
                              target_type='qualification', target_id=q.id,
                              target_name=f'{q.cert_number} {q.person_name}'))
    db.session.commit()
    flash(f'자격이 갱신되었습니다. (만료일 {q.expire_date or "없음"})', 'success')
    return redirect(url_for('qualification.detail', qid=qid))


@qualification_bp.route('/<int:qid>/revoke', methods=['POST'])
@login_required
def revoke(qid):
    q = Qualification.query.get_or_404(qid)
    if not current_user.is_admin():
        flash('자격 취소는 시스템 관리자만 가능합니다.', 'danger')
        return redirect(url_for('qualification.detail', qid=qid))
    q.status = 'revoked'
    db.session.add(AuditTrail(user_id=current_user.id, action='자격취소',
                              target_type='qualification', target_id=q.id,
                              target_name=f'{q.cert_number} {q.person_name}'))
    db.session.commit()
    flash('자격이 취소 처리되었습니다.', 'info')
    return redirect(url_for('qualification.detail', qid=qid))


@qualification_bp.route('/<int:qid>/certificate')
@login_required
def certificate(qid):
    """자격인증서 발급 (인쇄용)"""
    q = Qualification.query.get_or_404(qid)
    _refresh_status(q)
    if q.status != 'valid':
        flash('유효한 자격만 인증서를 발급할 수 있습니다.', 'warning')
        return redirect(url_for('qualification.detail', qid=qid))
    q.issued_at = datetime.utcnow()
    q.issue_count = (q.issue_count or 0) + 1
    db.session.add(AuditTrail(user_id=current_user.id, action='자격인증서발급',
                              target_type='qualification', target_id=q.id,
                              target_name=f'{q.cert_number} {q.person_name}'))
    db.session.commit()
    return render_template('qualification/certificate.html', q=q, today=date.today())


@qualification_bp.route('/<int:qid>/delete', methods=['POST'])
@login_required
def delete(qid):
    q = Qualification.query.get_or_404(qid)
    if not current_user.is_admin():
        flash('자격인증 삭제는 시스템 관리자만 가능합니다.', 'danger')
        return redirect(url_for('qualification.detail', qid=qid))
    from deletion import remove_file
    for a in q.attachments.all():
        remove_file(a.file_path)
    num, tid = q.cert_number, q.qtype_id
    db.session.add(AuditTrail(user_id=current_user.id, action='자격인증삭제',
                              target_type='qualification', target_id=q.id, target_name=num))
    db.session.delete(q)
    db.session.commit()
    flash(f'자격인증 [{num}]이(가) 삭제되었습니다.', 'info')
    return redirect(url_for('qualification.type_detail', type_id=tid))


@qualification_bp.route('/attachment/<int:att_id>/delete', methods=['POST'])
@login_required
def delete_attachment(att_id):
    att = QualificationAttachment.query.get_or_404(att_id)
    q = Qualification.query.get_or_404(att.qualification_id)
    if not current_user.is_admin():
        flash('증빙 삭제는 시스템 관리자만 가능합니다.', 'danger')
        return redirect(url_for('qualification.detail', qid=q.id))
    try:
        if att.file_path and os.path.exists(att.file_path):
            os.remove(att.file_path)
    except OSError:
        pass
    db.session.delete(att)
    db.session.commit()
    flash('증빙자료가 삭제되었습니다.', 'info')
    return redirect(url_for('qualification.detail', qid=q.id))


def _apply_form(q):
    f = request.form
    q.qtype_id = f.get('qtype_id', type=int)
    uid = f.get('user_id', type=int)
    q.user_id = uid
    if uid:
        u = User.query.get(uid)
        if u:
            q.person_name = u.name
            q.employee_no = u.employee_id
            q.department_id = u.department_id
            q.position = u.position
    if f.get('person_name'):
        q.person_name = f.get('person_name')
    if f.get('employee_no'):
        q.employee_no = f.get('employee_no')
    if f.get('department_id', type=int):
        q.department_id = f.get('department_id', type=int)
    if f.get('position'):
        q.position = f.get('position')
    q.certified_date = _parse_date(f.get('certified_date'))
    exp = _parse_date(f.get('expire_date'))
    if not exp and q.certified_date:
        t = QualificationType.query.get(q.qtype_id) if q.qtype_id else None
        exp = _add_months(q.certified_date, t.renewal_months if t else None)
    q.expire_date = exp
    q.approver_id = f.get('approver_id', type=int)
    q.approver_name = f.get('approver_name')
    q.eval_score = f.get('eval_score')
    q.basis_note = f.get('basis_note')
    _refresh_status(q)


def _save_attachments(q):
    files = request.files.getlist('attachments')
    kind = request.form.get('doc_kind') or '기타'
    if not files:
        return
    from config import Config
    from werkzeug.utils import secure_filename
    from utils import allowed_file
    for f in files:
        if not f or not f.filename:
            continue
        if not allowed_file(f.filename, Config.ALLOWED_EXTENSIONS):
            flash(f'허용되지 않는 파일 형식: {f.filename}', 'warning')
            continue
        ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
        fname = f"QC_{q.id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{secure_filename(f.filename)}"
        fpath = os.path.join(Config.UPLOAD_FOLDER, fname)
        f.save(fpath)
        db.session.add(QualificationAttachment(
            qualification_id=q.id, file_path=fpath, file_name=f.filename,
            is_image=(ext in IMAGE_EXTS), doc_kind=kind, uploaded_by_id=current_user.id))
