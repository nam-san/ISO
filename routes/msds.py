from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file
from flask_login import login_required, current_user
from models import db, MSDS, Department, AuditTrail
from datetime import datetime, date
import os

msds_bp = Blueprint('msds', __name__)

# 사용 공정·장소 (제조센터 라인 기준)
USE_AREAS = ['자동화라인', '매뉴얼라인', 'Rework라인', '수리실', '입고/보관', '기타']

RSL_LABEL = {'none': '해당없음', 'restricted': '제한물질', 'prohibited': '금지물질'}

# ── GHS 그림문자 9종 (산안법 제115조 경고표지) ──
# code: (명칭, 표시기호, 설명)
GHS_PICTOGRAMS = {
    'GHS01': ('폭발성·자기반응성', '', '폭발성 물질, 자기반응성 물질, 유기과산화물'),
    'GHS02': ('인화성·자연발화성', '', '인화성 가스·액체·고체, 자연발화성'),
    'GHS03': ('산화성', '', '산화성 가스·액체·고체'),
    'GHS04': ('고압가스', '', '고압가스(압축·액화·용해가스)'),
    'GHS05': ('금속·피부 부식성', '', '금속부식성, 피부부식성, 심한 눈 손상'),
    'GHS06': ('급성독성', '', '급성독성(구분1~3)'),
    'GHS07': ('경고', '', '피부·눈 자극성, 피부과민성, 급성독성(구분4)'),
    'GHS08': ('호흡기과민성·발암성', '', '발암성, 생식독성, 표적장기독성, 흡인유해성'),
    'GHS09': ('수생환경유해성', '', '수생환경 유해성'),
}

# 라벨 용지 규격 (mm)
LABEL_SIZES = {
    'small':  ('소형 (50×70mm)', 50, 70),
    'medium': ('중형 (70×100mm)', 70, 100),
    'large':  ('대형 (100×150mm)', 100, 150),
}

# ── 현재 등록된 MSDS 5건 (MSDS 등록부 기준) ──
MSDS_SEED = [
    dict(product_name='245 Lead-free Alloy Solder Wire', reg_date=date(2020, 12, 29),
         src_revision='3', src_revision_date=date(2017, 10, 30), manufacturer='Kester Inc.',
         tel='', fax='', use_areas='매뉴얼라인,Rework라인,수리실',
         ghs_class='금속 납 함유 — 생식독성, 특정표적장기독성(반복노출)',
         needs_lev=True, protective_gear='방진마스크, 보안경, 내열장갑',
         storage_place='제조센터 자재창고(납땜자재 구역)'),
    dict(product_name='그린소독용에탄올', reg_date=date(2020, 12, 29),
         src_revision='0', src_revision_date=date(2013, 6, 12), manufacturer='(주)그린제약',
         tel='043-534-1144', fax='043-534-1146',
         use_areas='자동화라인,매뉴얼라인,Rework라인,수리실',
         ghs_class='인화성 액체(구분2), 심한 눈 손상성',
         needs_lev=False, protective_gear='보안경, 내화학장갑',
         storage_place='제조센터 인화성물질 보관함(분리보관)'),
    dict(product_name='B128 (Thermal Transfer Ribbon)', reg_date=date(2020, 12, 29),
         src_revision='0', src_revision_date=date(2019, 4, 26), manufacturer='ITW Thermal Films',
         tel='041-559-4120', fax='041-622-0889',
         use_areas='자동화라인,매뉴얼라인,Rework라인,수리실',
         ghs_class='비위험물(GHS 분류 대상 아님)',
         needs_lev=False, protective_gear='일반 작업장갑',
         storage_place='제조센터 부자재 보관대'),
    dict(product_name='B324 (Thermal Transfer Ribbon)', reg_date=date(2020, 12, 29),
         src_revision='0', src_revision_date=date(2017, 4, 25), manufacturer='ITW Thermal Films',
         tel='041-559-4120', fax='041-622-0889',
         use_areas='자동화라인,매뉴얼라인,Rework라인,수리실',
         ghs_class='비위험물(GHS 분류 대상 아님)',
         needs_lev=False, protective_gear='일반 작업장갑',
         storage_place='제조센터 부자재 보관대'),
    dict(product_name='열전사 잉크리본 (thermal transfer inked ribbon)', reg_date=date(2020, 12, 29),
         src_revision='-', src_revision_date=date(2018, 7, 11), manufacturer='ARMOR S.A.S',
         tel='', fax='', use_areas='자동화라인,매뉴얼라인,Rework라인,수리실',
         ghs_class='비위험물(GHS 분류 대상 아님)',
         needs_lev=False, protective_gear='일반 작업장갑',
         storage_place='제조센터 부자재 보관대'),
]


def seed_msds():
    if MSDS.query.count() > 0:
        return
    mfg = Department.query.filter_by(code='MFG').first()
    for i, s in enumerate(MSDS_SEED, start=6):   # 기존 대장 번호(MS-006~010) 연번 유지
        db.session.add(MSDS(reg_number=f'NV-MSDS-{i:03d}',
                            department_id=mfg.id if mfg else None,
                            rsl_status='none', is_active=True, **s))
    db.session.commit()
    print(f"[시드] MSDS 등록부 {len(MSDS_SEED)}건 생성")


def _next_number():
    items = MSDS.query.filter(MSDS.reg_number.like('NV-MSDS-%')).all()
    mx = 0
    for m in items:
        try:
            mx = max(mx, int(m.reg_number.rsplit('-', 1)[-1]))
        except ValueError:
            continue
    return f'NV-MSDS-{mx + 1:03d}'


def _parse_date(v):
    return datetime.strptime(v, '%Y-%m-%d').date() if v else None


@msds_bp.route('/')
@login_required
def index():
    q = request.args.get('q', '')
    area = request.args.get('area', '')
    rsl = request.args.get('rsl', '')
    query = MSDS.query
    if q:
        query = query.filter((MSDS.product_name.contains(q)) |
                             (MSDS.reg_number.contains(q)) |
                             (MSDS.manufacturer.contains(q)))
    if area:
        query = query.filter(MSDS.use_areas.contains(area))
    if rsl:
        query = query.filter_by(rsl_status=rsl)
    items = query.order_by(MSDS.reg_number).all()
    stats = {
        'total': MSDS.query.count(),
        'active': MSDS.query.filter_by(is_active=True).count(),
        'rsl': MSDS.query.filter(MSDS.rsl_status.in_(['restricted', 'prohibited'])).count(),
        'no_file': MSDS.query.filter((MSDS.file_path.is_(None)) | (MSDS.file_path == '')).count(),
    }
    return render_template('msds/index.html', items=items, stats=stats,
                           q=q, area=area, rsl=rsl,
                           use_areas=USE_AREAS, rsl_label=RSL_LABEL)


@msds_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    if not current_user.has_edit():
        flash('MSDS 등록 권한이 없습니다.', 'danger')
        return redirect(url_for('msds.index'))
    if request.method == 'POST':
        m = MSDS(reg_number=_next_number(), created_by_id=current_user.id)
        _apply_form(m)
        db.session.add(m)
        db.session.flush()
        _save_file(m)
        db.session.add(AuditTrail(user_id=current_user.id, action='MSDS등록',
                                  target_type='msds', target_id=m.id,
                                  target_name=f'{m.reg_number} {m.product_name}'))
        db.session.commit()
        flash(f'MSDS [{m.reg_number}] {m.product_name}이(가) 등록되었습니다.', 'success')
        return redirect(url_for('msds.detail', msds_id=m.id))
    departments = Department.query.filter_by(is_active=True).all()
    return render_template('msds/form.html', item=None, departments=departments,
                           use_areas=USE_AREAS, next_number=_next_number(), today=date.today(),
                           pictograms=GHS_PICTOGRAMS)


@msds_bp.route('/<int:msds_id>')
@login_required
def detail(msds_id):
    m = MSDS.query.get_or_404(msds_id)
    file_url = None
    if m.file_path:
        file_url = url_for('static', filename=f'uploads/{os.path.basename(m.file_path)}')
    picto = [p for p in (m.ghs_pictograms or '').split(',') if p in GHS_PICTOGRAMS]
    return render_template('msds/detail.html', m=m, file_url=file_url, rsl_label=RSL_LABEL,
                           picto=picto, pictograms=GHS_PICTOGRAMS, label_sizes=LABEL_SIZES)


@msds_bp.route('/<int:msds_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(msds_id):
    m = MSDS.query.get_or_404(msds_id)
    if not current_user.has_edit():
        flash('수정 권한이 없습니다.', 'danger')
        return redirect(url_for('msds.detail', msds_id=msds_id))
    if request.method == 'POST':
        _apply_form(m)
        _save_file(m)
        db.session.add(AuditTrail(user_id=current_user.id, action='MSDS수정',
                                  target_type='msds', target_id=m.id,
                                  target_name=f'{m.reg_number} {m.product_name}'))
        db.session.commit()
        flash('MSDS 정보가 수정되었습니다.', 'success')
        return redirect(url_for('msds.detail', msds_id=msds_id))
    departments = Department.query.filter_by(is_active=True).all()
    return render_template('msds/form.html', item=m, departments=departments,
                           use_areas=USE_AREAS, next_number=m.reg_number, today=date.today(),
                           pictograms=GHS_PICTOGRAMS)


@msds_bp.route('/<int:msds_id>/delete', methods=['POST'])
@login_required
def delete(msds_id):
    m = MSDS.query.get_or_404(msds_id)
    if not (current_user.is_admin() or m.created_by_id == current_user.id):
        flash('삭제 권한이 없습니다. (작성자 또는 관리자만)', 'danger')
        return redirect(url_for('msds.detail', msds_id=msds_id))
    from deletion import remove_file
    remove_file(m.file_path)
    num = m.reg_number
    db.session.add(AuditTrail(user_id=current_user.id, action='MSDS삭제',
                              target_type='msds', target_id=m.id, target_name=num))
    db.session.delete(m)
    db.session.commit()
    flash(f'MSDS [{num}]이(가) 삭제되었습니다.', 'info')
    return redirect(url_for('msds.index'))


@msds_bp.route('/<int:msds_id>/label')
@login_required
def label(msds_id):
    """소분용기 GHS 경고표지 라벨 출력 (브라우저 인쇄)."""
    m = MSDS.query.get_or_404(msds_id)
    size = request.args.get('size', 'medium')
    if size not in LABEL_SIZES:
        size = 'medium'
    count = request.args.get('count', type=int) or 1
    count = max(1, min(count, 40))
    label_name, w, h = LABEL_SIZES[size]
    picto = [p for p in (m.ghs_pictograms or '').split(',') if p in GHS_PICTOGRAMS]
    supplier = m.supplier_info or ' / '.join(x for x in [m.manufacturer, m.tel] if x)
    db.session.add(AuditTrail(user_id=current_user.id, action='MSDS라벨출력',
                              target_type='msds', target_id=m.id,
                              target_name=f'{m.reg_number} {m.product_name} ({label_name} {count}매)'))
    db.session.commit()
    return render_template('msds/label.html', m=m, size=size, size_label=label_name,
                           width=w, height=h, count=count, picto=picto,
                           pictograms=GHS_PICTOGRAMS, supplier=supplier,
                           label_sizes=LABEL_SIZES, today=date.today())


@msds_bp.route('/<int:msds_id>/download')
@login_required
def download(msds_id):
    m = MSDS.query.get_or_404(msds_id)
    if not m.file_path or not os.path.exists(m.file_path):
        flash('MSDS 파일이 등록되어 있지 않습니다.', 'warning')
        return redirect(url_for('msds.detail', msds_id=msds_id))
    db.session.add(AuditTrail(user_id=current_user.id, action='MSDS다운로드',
                              target_type='msds', target_id=m.id,
                              target_name=f'{m.reg_number} {m.product_name}'))
    db.session.commit()
    return send_file(m.file_path, as_attachment=True,
                     download_name=m.file_name or os.path.basename(m.file_path))


def _apply_form(m):
    f = request.form
    m.product_name = f.get('product_name')
    m.reg_date = _parse_date(f.get('reg_date'))
    m.src_revision = f.get('src_revision')
    m.src_revision_date = _parse_date(f.get('src_revision_date'))
    m.manufacturer = f.get('manufacturer')
    m.tel = f.get('tel')
    m.fax = f.get('fax')
    m.use_areas = ','.join(f.getlist('use_areas'))
    m.storage_place = f.get('storage_place')
    m.ghs_class = f.get('ghs_class')
    m.needs_lev = f.get('needs_lev') == 'on'
    m.protective_gear = f.get('protective_gear')
    # GHS 경고표지(라벨) 항목
    m.ghs_pictograms = ','.join(f.getlist('ghs_pictograms'))
    m.signal_word = f.get('signal_word') or None
    m.hazard_statements = f.get('hazard_statements')
    m.precaution_statements = f.get('precaution_statements')
    m.supplier_info = f.get('supplier_info')
    m.rsl_status = f.get('rsl_status', 'none')
    m.rsl_note = f.get('rsl_note')
    m.note = f.get('note')
    m.is_active = f.get('is_active', 'on') == 'on'
    m.department_id = f.get('department_id', type=int)


def _save_file(m):
    file = request.files.get('file')
    if not file or not file.filename:
        return
    from config import Config
    from werkzeug.utils import secure_filename
    from utils import allowed_file
    if not allowed_file(file.filename, Config.ALLOWED_EXTENSIONS):
        flash('허용되지 않는 파일 형식입니다.', 'warning')
        return
    fname = f"MSDS_{m.reg_number}_{secure_filename(file.filename)}"
    fpath = os.path.join(Config.UPLOAD_FOLDER, fname)
    file.save(fpath)
    m.file_path = fpath
    m.file_name = file.filename
