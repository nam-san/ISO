from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import db, MeetingType, MeetingRecord, MeetingRecordAttachment, User, AuditTrail
from datetime import datetime, date
import os

meeting_bp = Blueprint('meeting', __name__)

IMAGE_EXTS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# ── ISO 절차서 기준 필수 개최 회의 마스터 시드 ──
MEETING_SEED = [
    ('안전보건 간담회', 'NV-P-014(5.1) NV-P-039(4.1 a)', '분기 1회 이상',
     '안전보건 관리책임자', '전 근로자',
     '위험성평가 결과, 사건·사고 현황, 개선요청사항 논의 (근로자 협의·참여 채널로서 산업안전보건위원회 대체)'),
    ('사내도급 안전보건협의체', 'NV-P-041(4.5)', '월 1회 이상 (상시 사내도급이 있는 경우)',
     '당사 관리감독자 + 도급업체 책임자', '당사·도급업체 관계자',
     '작업일정, 유해·위험요인, 순회점검 결과 등 안전보건 정보 공유'),
    ('내부심사 (심사 전 회의 포함)', 'NV-P-029 (5.1, 6.2)', '연 1회 이상 (4/4분기 중), 임시심사는 수시',
     '내부심사원 / 관리부서장', '심사원, 수감부서장',
     '심사 일정·범위·협조사항 확인 및 통합경영시스템(9001/14001/45001) 이행 여부 심사'),
    ('비상사태 대책위원회', 'NV-P-025 (5.3, 5.4)', '비상사태 발생 시 수시 소집',
     '지휘/통제실장', '방호복구팀, 의무/대피지원팀 등 비상대응팀',
     '비상사태 상황 판단·전파, 대응 지휘, 복구조치 총괄'),
    ('품질경영위원회', 'NV-P-003(4항) NV-P-006(5.2)', '연 1회 이상 (연도방침 수립 시), 중대 리스크 발생 시 수시',
     '대표이사 / 품질환경경영대리인', '관련 부서장',
     '연도방침(안) 심의, 자체 제거·경감이 곤란한 중대 리스크 요소 심의·보고'),
    ('고객만족도 조사부서 회의', 'NV-P-028 (5.2, 5.3)', '연 1회(정기조사), 특별조사는 수시',
     '품질경영팀장 (QA팀장)', '고객관련 부서 조사부서원',
     '정기/특별 조사계획 수립, 조사항목·방법·일정 결정'),
]


def seed_meeting_types():
    if MeetingType.query.count() > 0:
        return
    for i, (name, basis, cycle, host, target, agenda) in enumerate(MEETING_SEED):
        db.session.add(MeetingType(
            name=name, basis=basis, cycle=cycle, host=host,
            attendees_target=target, agenda_note=agenda, sort_order=i, is_active=True))
    db.session.commit()
    print(f"[시드] 필수회의 마스터 {len(MEETING_SEED)}종 생성")


def _next_number():
    year = datetime.now().year
    n = MeetingRecord.query.filter(MeetingRecord.record_number.like(f'MTG-{year}-%')).count() + 1
    return f'MTG-{year}-{n:03d}'


def _save_attachments(rec):
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
        fname = f"MTG_{rec.id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{secure_filename(file.filename)}"
        fpath = os.path.join(Config.UPLOAD_FOLDER, fname)
        file.save(fpath)
        db.session.add(MeetingRecordAttachment(
            record_id=rec.id, file_path=fpath, file_name=file.filename,
            is_image=(ext in IMAGE_EXTS), uploaded_by_id=current_user.id))


@meeting_bp.route('/')
@login_required
def index():
    """필수회의 대장 — 마스터 목록 + 회의별 개최 현황"""
    types = MeetingType.query.filter_by(is_active=True).order_by(MeetingType.sort_order, MeetingType.id).all()
    year = date.today().year
    status = {}
    for t in types:
        recs = t.records.order_by(MeetingRecord.meeting_date.desc()).all()
        this_year = [r for r in recs if r.meeting_date and r.meeting_date.year == year]
        status[t.id] = {
            'last': recs[0].meeting_date if recs else None,
            'this_year': len(this_year),
            'total': len(recs),
        }
    stats = {
        'types': len(types),
        'total_records': MeetingRecord.query.count(),
        'this_year': MeetingRecord.query.filter(
            db.extract('year', MeetingRecord.meeting_date) == year).count(),
        'not_held': sum(1 for t in types if status[t.id]['this_year'] == 0),
    }
    return render_template('meeting/index.html', types=types, status=status,
                           stats=stats, year=year)


@meeting_bp.route('/records')
@login_required
def records():
    type_id = request.args.get('type_id', type=int)
    q = MeetingRecord.query
    if type_id:
        q = q.filter_by(meeting_type_id=type_id)
    items = q.order_by(MeetingRecord.meeting_date.desc(), MeetingRecord.id.desc()).all()
    types = MeetingType.query.order_by(MeetingType.sort_order).all()
    return render_template('meeting/records.html', items=items, types=types, type_id=type_id)


@meeting_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    if not current_user.has_edit():
        flash('회의록 작성 권한이 없습니다.', 'danger')
        return redirect(url_for('meeting.index'))
    mtype = None
    type_id = request.args.get('type_id', type=int) or request.form.get('meeting_type_id', type=int)
    if type_id:
        mtype = MeetingType.query.get(type_id)

    if request.method == 'POST':
        mdate = request.form.get('meeting_date')
        ndate = request.form.get('next_date')
        rec = MeetingRecord(
            record_number=_next_number(),
            meeting_type_id=request.form.get('meeting_type_id', type=int),
            title=request.form.get('title'),
            meeting_date=datetime.strptime(mdate, '%Y-%m-%d').date() if mdate else date.today(),
            location=request.form.get('location'),
            chair=request.form.get('chair'),
            attendees=request.form.get('attendees'),
            agenda=request.form.get('agenda'),
            discussion=request.form.get('discussion'),
            action_items=request.form.get('action_items'),
            next_date=datetime.strptime(ndate, '%Y-%m-%d').date() if ndate else None,
            created_by_id=current_user.id,
        )
        db.session.add(rec)
        db.session.flush()
        _save_attachments(rec)
        db.session.add(AuditTrail(user_id=current_user.id, action='회의록작성',
                                  target_type='meeting', target_id=rec.id,
                                  target_name=f'{rec.record_number} {rec.title}'))
        db.session.commit()
        flash(f'회의록 [{rec.record_number}]이(가) 등록되었습니다.', 'success')
        return redirect(url_for('meeting.detail', rec_id=rec.id))

    types = MeetingType.query.filter_by(is_active=True).order_by(MeetingType.sort_order).all()
    users = User.query.filter_by(is_active=True).order_by(User.name).all()
    return render_template('meeting/form.html', item=None, mtype=mtype, types=types,
                           users=users, today=date.today())


@meeting_bp.route('/<int:rec_id>')
@login_required
def detail(rec_id):
    rec = MeetingRecord.query.get_or_404(rec_id)
    return render_template('meeting/detail.html', rec=rec)


@meeting_bp.route('/<int:rec_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(rec_id):
    rec = MeetingRecord.query.get_or_404(rec_id)
    if not current_user.has_edit() or not (current_user.is_admin() or rec.created_by_id == current_user.id):
        flash('수정 권한이 없습니다. (작성자 또는 관리자만)', 'danger')
        return redirect(url_for('meeting.detail', rec_id=rec_id))
    if request.method == 'POST':
        mdate = request.form.get('meeting_date')
        ndate = request.form.get('next_date')
        rec.meeting_type_id = request.form.get('meeting_type_id', type=int)
        rec.title = request.form.get('title')
        rec.meeting_date = datetime.strptime(mdate, '%Y-%m-%d').date() if mdate else rec.meeting_date
        rec.location = request.form.get('location')
        rec.chair = request.form.get('chair')
        rec.attendees = request.form.get('attendees')
        rec.agenda = request.form.get('agenda')
        rec.discussion = request.form.get('discussion')
        rec.action_items = request.form.get('action_items')
        rec.next_date = datetime.strptime(ndate, '%Y-%m-%d').date() if ndate else None
        _save_attachments(rec)
        db.session.commit()
        flash('회의록이 수정되었습니다.', 'success')
        return redirect(url_for('meeting.detail', rec_id=rec_id))
    types = MeetingType.query.filter_by(is_active=True).order_by(MeetingType.sort_order).all()
    users = User.query.filter_by(is_active=True).order_by(User.name).all()
    return render_template('meeting/form.html', item=rec, mtype=rec.meeting_type,
                           types=types, users=users, today=date.today())


@meeting_bp.route('/<int:rec_id>/delete', methods=['POST'])
@login_required
def delete(rec_id):
    rec = MeetingRecord.query.get_or_404(rec_id)
    if not (current_user.is_admin() or rec.created_by_id == current_user.id):
        flash('삭제 권한이 없습니다. (작성자 또는 관리자만)', 'danger')
        return redirect(url_for('meeting.detail', rec_id=rec_id))
    from deletion import remove_file
    for att in rec.attachments.all():
        remove_file(att.file_path)
    num = rec.record_number
    db.session.add(AuditTrail(user_id=current_user.id, action='회의록삭제',
                              target_type='meeting', target_id=rec.id, target_name=num))
    db.session.delete(rec)
    db.session.commit()
    flash(f'회의록 [{num}]이(가) 삭제되었습니다.', 'info')
    return redirect(url_for('meeting.records'))


@meeting_bp.route('/attachment/<int:att_id>/delete', methods=['POST'])
@login_required
def delete_attachment(att_id):
    att = MeetingRecordAttachment.query.get_or_404(att_id)
    rec = MeetingRecord.query.get_or_404(att.record_id)
    if not current_user.has_edit() or not (current_user.is_admin() or rec.created_by_id == current_user.id):
        flash('첨부 삭제 권한이 없습니다.', 'danger')
        return redirect(url_for('meeting.detail', rec_id=rec.id))
    try:
        if att.file_path and os.path.exists(att.file_path):
            os.remove(att.file_path)
    except OSError:
        pass
    db.session.delete(att)
    db.session.commit()
    flash('첨부가 삭제되었습니다.', 'info')
    return redirect(url_for('meeting.detail', rec_id=rec.id))


# ── 필수회의 마스터 관리 (has_edit) ──
@meeting_bp.route('/type/save', methods=['POST'])
@login_required
def type_save():
    if not current_user.has_edit():
        flash('권한이 없습니다.', 'danger')
        return redirect(url_for('meeting.index'))
    tid = request.form.get('id', type=int)
    t = MeetingType.query.get(tid) if tid else MeetingType(sort_order=MeetingType.query.count())
    t.name = request.form.get('name')
    t.basis = request.form.get('basis')
    t.cycle = request.form.get('cycle')
    t.host = request.form.get('host')
    t.attendees_target = request.form.get('attendees_target')
    t.agenda_note = request.form.get('agenda_note')
    if not tid:
        db.session.add(t)
    db.session.commit()
    flash('필수회의 항목이 저장되었습니다.', 'success')
    return redirect(url_for('meeting.index'))


@meeting_bp.route('/type/<int:type_id>/delete', methods=['POST'])
@login_required
def type_delete(type_id):
    if not current_user.is_admin():
        flash('관리자만 삭제할 수 있습니다.', 'danger')
        return redirect(url_for('meeting.index'))
    t = MeetingType.query.get_or_404(type_id)
    # 기존 회의록은 보존(기타로) — 종류 연결만 해제
    for r in t.records.all():
        r.meeting_type_id = None
    name = t.name
    db.session.delete(t)
    db.session.commit()
    flash(f'필수회의 항목 [{name}]이(가) 삭제되었습니다. (연결 회의록은 기타로 보존)', 'info')
    return redirect(url_for('meeting.index'))
