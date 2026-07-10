from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from models import db, OrgUnit, OrgMember, AuditTrail

org_bp = Blueprint('org', __name__)

# URL 슬러그 ↔ 조직도 종류
SLUGS = {'full': '전체', 'quality': '품질', 'env': '환경', 'safety': '안전보건'}
SLUG_OF = {v: k for k, v in SLUGS.items()}
CHART_META = {
    '전체':   ('🏢 전체 조직도', '주식회사 누리보이스 전사 조직 구성'),
    '품질':   ('✅ 품질경영 조직도', 'ISO 9001 품질경영시스템 조직 (문서·심사·품질관리)'),
    '환경':   ('🌿 환경경영 조직도', 'ISO 14001 환경경영시스템 조직 (환경측면·법규·비상대응)'),
    '안전보건': ('⛑️ 안전보건 조직도', 'ISO 45001 안전보건경영시스템 조직 (관리감독자·위원회·비상대응)'),
}


def _can_edit():
    return current_user.has_org_edit()


# ════════════════════════════════════════════════════════════
# 조직도 시드 (기본 틀)
# ════════════════════════════════════════════════════════════
def _build(chart_type, node, parent_id=None, order=0, inherit_site=None):
    """중첩 dict → OrgUnit/OrgMember 재귀 생성. site는 자식으로 상속."""
    site = node.get('site', inherit_site)
    u = OrgUnit(chart_type=chart_type, site=site, name=node['name'], leader=node.get('leader'),
                leader_title=node.get('leader_title'), leader_duty=node.get('leader_duty'),
                color=node.get('color'), parent_id=parent_id, sort_order=order)
    db.session.add(u)
    db.session.flush()
    for i, (mname, mrole, mduty) in enumerate(node.get('members', [])):
        db.session.add(OrgMember(unit_id=u.id, name=mname, role=mrole, duty=mduty, sort_order=i))
    for i, child in enumerate(node.get('children', [])):
        _build(chart_type, child, u.id, i, site)
    return u


def _env_tree():
    """환경경영 조직도 (ISO 14001) — 본사/제조센터 사업장별."""
    return {
        'name': '최고경영자', 'leader': '조송만', 'leader_title': '대표이사', 'color': '#1a3a5c',
        'leader_duty': '환경방침 승인, 환경경영시스템 자원 제공, 준수의무 이행 최종 책임',
        'children': [{
            'name': '환경경영대리인', 'leader': '신성호', 'leader_title': '환경경영대리인', 'color': '#2563eb',
            'leader_duty': '전사 EMS 확립·유지, 환경성과 보고, 사업장별 준수평가 총괄 (ISO 14001 5.3)',
            'children': [{
                'name': '환경관리책임자(총괄)', 'leader': '정원구', 'leader_title': '환경관리책임자', 'color': '#16a34a',
                'leader_duty': '전사 환경목표·법규 등록부 통합관리, 사업장별 환경측면 취합·경영검토 보고',
                'children': [
                    # ── 본사(서울) : 사무환경 ──
                    {'name': '본사(서울) 환경관리', 'leader': '최윤혜', 'leader_title': '본사 환경담당', 'site': '본사', 'color': '#0ea5e9',
                     'leader_duty': '본사 사무환경(에너지·용지·일반폐기물 분리배출) 관리, 온실가스·전력 모니터링',
                     'members': [('전현준','법규담당','환경법규 준수평가(본사)'),('신소정','자원담당','사무용품·재활용 관리')]},
                    # ── 제조센터(나주) : 배출시설·폐기물·화학물질 ──
                    {'name': '제조센터(나주) 환경관리', 'leader': '서두선', 'leader_title': '나주 환경담당', 'site': '제조센터', 'color': '#ea580c',
                     'leader_duty': '나주 배출시설·환경오염물질·지정폐기물·화학물질 관리 총괄',
                     'children': [
                        {'name': '환경측면·배출시설 관리', 'leader': '나대수', 'leader_title': '담당', 'site': '제조센터',
                         'members': [('서지용','환경담당','대기·수질·소음 배출시설 점검')]},
                        {'name': '폐기물·화학물질 관리', 'leader': '박태용', 'leader_title': '담당', 'site': '제조센터',
                         'members': [('성민건','담당','지정폐기물 위탁·MSDS 관리')]},
                        {'name': '환경 비상대응조직(나주)', 'leader': '임환희', 'leader_title': '비상대응', 'site': '제조센터', 'color': '#dc2626',
                         'leader_duty': '화학물질 누출·화재 등 환경 비상사태 대응·훈련',
                         'members': [('정윤구','방재','누출 차단·확산 방지'),('김명준','지원','방제물자·연락')]},
                    ]},
                ]},
            ]
        }]
    }


def _safety_tree():
    """안전보건 조직도 (ISO 45001·산업안전보건법) — 본사/제조센터 사업장별."""
    return {
        'name': '안전보건 최고책임자', 'leader': '조송만', 'leader_title': '대표이사', 'color': '#1a3a5c',
        'leader_duty': '전사 안전보건 방침 승인·자원 제공, 안전보건경영 최종 책임',
        'children': [{
            'name': '안전보건 총괄관리자', 'leader': '신성호', 'leader_title': '경영대리인', 'color': '#2563eb',
            'leader_duty': '전사 안전보건경영시스템 총괄, 사업장별 위험성평가·재해예방 성과 보고',
            'children': [
                # ── 본사(서울) 사업장 ──
                {'name': '본사(서울) 사업장', 'leader': '정원구', 'leader_title': '안전보건관리책임자(본사)', 'site': '본사', 'color': '#0ea5e9',
                 'leader_duty': '본사 사무직 안전보건 총괄(산안법 §15), VDT·전기·소방 등 사무환경 위험관리',
                 'children': [
                    {'name': '관리감독자(본사)', 'leader_title': '각 팀장', 'site': '본사',
                     'leader_duty': '담당 부서 근로자 안전보건 지도·점검 (산안법 §16)',
                     'members': [('최윤혜','관리감독자','경영관리팀'),('한종민','관리감독자','통신서비스그룹'),('최봉석','관리감독자','SoIP 개발팀')]},
                    {'name': '보건관리자(본사)', 'leader': '최윤혜', 'leader_title': '보건담당', 'site': '본사',
                     'leader_duty': '본사 근로자 건강진단·직무스트레스·근골격계 예방'},
                ]},
                # ── 제조센터(나주) 사업장 ──
                {'name': '제조센터(나주) 사업장', 'leader': '김남현', 'leader_title': '안전보건관리책임자(나주)', 'site': '제조센터', 'color': '#ea580c',
                 'leader_duty': '나주 제조 사업장 안전보건 총괄(산안법 §15), 위험기계·화학물질·중대재해 예방',
                 'children': [
                    {'name': '관리감독자(나주)', 'leader_title': '제조·품질 파트장', 'site': '제조센터', 'color': '#16a34a',
                     'leader_duty': '생산 현장 작업 안전점검·근로자 지도, 위험요인 개선 (산안법 §16)',
                     'members': [('한승수','관리감독자','품질관리파트'),('임환희','관리감독자','제조관리파트'),('정윤구','관리감독자','제조기술파트'),('김명준','관리감독자','자재운영파트')]},
                    {'name': '안전보건 담당자(나주)', 'leader': '박태용', 'leader_title': '안전보건담당', 'site': '제조센터',
                     'leader_duty': '위험성평가 주관, 작업환경측정·보호구·법정점검·소방 관리',
                     'members': [('성민건','안전담당','법정점검·소방'),('장다정','보건담당','건강관리·MSDS')]},
                    {'name': '산업안전보건위원회(나주)', 'leader_title': '노사 동수 구성', 'site': '제조센터', 'color': '#7c3aed',
                     'leader_duty': '안전보건 주요사항 심의·의결(분기 1회) — 상시근로자 다수 사업장 필수',
                     'members': [('김남현','사용자위원','위원장'),('임환희','사용자위원',''),('박인욱','근로자위원','근로자 대표'),('민병근','근로자위원','')]},
                    {'name': '비상대응조직(나주)', 'leader_title': '비상대응반', 'site': '제조센터', 'color': '#dc2626',
                     'leader_duty': '화재·감전·중대재해 비상대응 지휘, 대피·응급조치 훈련',
                     'members': [('정인호','초기대응','화재진화·전원차단'),('민병근','대피유도','근로자 대피'),('하기훈','응급처치','부상자 응급조치·후송')]},
                ]},
            ],
        }],
    }


def seed_org_charts():
    """조직도가 없으면 4종 기본 틀 시드."""
    if OrgUnit.query.count() > 0:
        return

    # ── 전체 조직도 (2026.04.01 기준 + 경영대리인 신성호 추가) ──
    # 기본 본사(서울), 제조팀·품질관리파트만 제조센터(나주) — site는 자식으로 상속
    full = {
        'name': '대표이사', 'leader': '조송만', 'leader_title': '대표이사', 'color': '#1a3a5c', 'site': '본사',
        'leader_duty': '경영 총괄 및 최종 의사결정, 경영방침·목표 승인, 경영검토 주관',
        'children': [{
            'name': '경영대리인', 'leader': '신성호', 'leader_title': '경영대리인', 'color': '#2563eb',
            'leader_duty': '통합경영시스템(품질·환경·안전보건) 총괄 관리대리인, 경영시스템 운영·성과 보고',
            'children': [
                {'name': '경영그룹', 'leader_title': '그룹', 'color': '#0e7490', 'children': [
                    {'name': '경영관리팀', 'leader': '최윤혜', 'leader_title': '팀장',
                     'members': [('최영미','사원',''),('전현준','사원',''),('신소정','사원',''),('김우진','사원','')]},
                ]},
                {'name': '통신서비스그룹', 'leader_title': '그룹', 'color': '#0e7490', 'children': [
                    {'name': 'VoIP사업팀', 'leader': '한종민', 'leader_title': '팀장',
                     'members': [('이호영','사원',''),('정임진','사원',''),('윤소희','사원','')]},
                    {'name': 'SI사업팀', 'leader': '고필석', 'leader_title': '팀장',
                     'members': [('권정재','사원','')]},
                    {'name': 'SWS사업팀', 'leader': '이완기', 'leader_title': '팀장', 'members': []},
                ]},
                {'name': '기술연구소', 'leader': '신성호', 'leader_title': '연구소장', 'color': '#0e7490', 'children': [
                    {'name': 'SoIP 개발팀', 'leader': '최봉석', 'leader_title': '팀장', 'children': [
                        {'name': 'SW파트', 'leader': '유영언', 'leader_title': '파트장',
                         'members': [('김은수','사원',''),('김호성','사원',''),('한현수','사원',''),('조진웅','사원',''),('장수빈','사원',''),('김영섭','사원',''),('손태영','사원','')]},
                        {'name': 'HW파트', 'leader': '유덕재', 'leader_title': '파트장',
                         'members': [('정인창','사원',''),('이문희','사원',''),('곽병기','사원','')]},
                        {'name': 'PA파트', 'leader': '정원구(겸)', 'leader_title': '파트장',
                         'members': [('양솔','사원',''),('박태준','사원',''),('정철민','사원',''),('김종완','사원','')]},
                    ]},
                    {'name': '품질경영팀', 'leader': '정원구', 'leader_title': '팀장', 'children': [
                        {'name': '품질관리파트', 'leader': '한승수', 'leader_title': '파트장', 'site': '제조센터',
                         'members': [('박태용','사원',''),('성민건','사원',''),('김민중','사원',''),('김지성','사원',''),('최승미','사원','')]},
                        {'name': '품질기술파트', 'leader': '서두선', 'leader_title': '파트장',
                         'members': [('서지용','사원',''),('나대수','사원',''),('김성철','사원',''),('김현중','사원','')]},
                        {'name': '콜센터', 'leader_title': '파트', 'members': []},
                    ]},
                    {'name': '제조팀', 'leader': '김남현', 'leader_title': '팀장', 'site': '제조센터',
                     'members': [('장다정','사원','')], 'children': [
                        {'name': '제조관리파트', 'leader': '임환희', 'leader_title': '파트장',
                         'members': [('정인호','사원',''),('민병근','사원',''),('정윤정','사원',''),('김미옥','사원',''),('윤정은','사원',''),('박숙현','사원',''),('양순례','사원',''),('안채원','사원',''),('박인욱','사원','')]},
                        {'name': '제조기술파트', 'leader': '정윤구', 'leader_title': '파트장',
                         'members': [('하기훈','사원',''),('장연지','사원','')]},
                        {'name': '자재운영파트', 'leader': '김명준', 'leader_title': '파트장',
                         'members': [('유성경','사원',''),('양영석','사원',''),('박창규','사원',''),('심우빈','사원',''),('조지우','사원',''),('유선화','사원',''),('조한영','사원',''),('김미선','사원',''),('김태윤','사원',''),('윤재민','사원',''),('박덕심','사원',''),('김도빈','사원',''),('곽동철','사원','')]},
                    ]},
                ]},
            ],
        }],
    }

    # ── 품질경영 조직도 (ISO 9001) ──
    quality = {
        'name': '최고경영자', 'leader': '조송만', 'leader_title': '대표이사', 'color': '#1a3a5c',
        'leader_duty': '품질방침·품질목표 승인, 품질경영시스템 자원 제공, 경영검토 주관',
        'children': [{
            'name': '품질경영대리인', 'leader': '신성호', 'leader_title': '품질경영대리인', 'color': '#2563eb',
            'leader_duty': 'QMS 프로세스 확립·유지, 품질성과 보고, 고객요구 인식 촉진 (ISO 9001 5.3)',
            'children': [
                {'name': '품질경영팀', 'leader': '정원구', 'leader_title': '팀장', 'color': '#16a34a',
                 'leader_duty': '품질시스템 운영 총괄, 내부심사 계획, 부적합·시정조치 관리',
                 'children': [
                    {'name': '품질관리파트', 'leader': '한승수', 'leader_title': '파트장',
                     'members': [('박태용','검사','수입·공정·최종검사 수행'),('성민건','검사','출하검사·성적서 관리'),('김민중','품질','고객불만 처리 지원')]},
                    {'name': '품질기술파트', 'leader': '서두선', 'leader_title': '파트장',
                     'members': [('서지용','기술','품질개선·공정능력 분석'),('나대수','기술','측정기 관리·MSA')]},
                ]},
                {'name': '내부품질심사팀', 'leader': '정원구', 'leader_title': '심사팀장', 'color': '#7c3aed',
                 'leader_duty': '연간 내부심사 계획·실시, 심사원 자격관리',
                 'members': [('서두선','내부심사원','프로세스 적합성 심사'),('한승수','내부심사원','제조·검사 부문 심사')]},
                {'name': '문서·기록 관리', 'leader': '최윤혜', 'leader_title': '문서관리자',
                 'leader_duty': '문서·기록의 작성·검토·배포·보존 관리 (문서관리 절차서)'},
                {'name': '고객대응(불만처리)', 'leader': '한종민', 'leader_title': '담당',
                 'leader_duty': '고객 클레임 접수·처리·재발방지, 고객만족 모니터링'},
            ],
        }],
    }

    env = _env_tree()
    safety = _safety_tree()

    for ctype, tree in [('전체', full), ('품질', quality), ('환경', env), ('안전보건', safety)]:
        _build(ctype, tree, None, 0)
    db.session.commit()
    print('[조직도] 4종 기본 조직도 시드 완료')


# ════════════════════════════════════════════════════════════
# 조회
# ════════════════════════════════════════════════════════════
@org_bp.route('/')
@login_required
def index():
    return redirect(url_for('org.chart', slug='full'))


@org_bp.route('/<slug>')
@login_required
def chart(slug):
    if slug not in SLUGS:
        abort(404)
    ctype = SLUGS[slug]
    roots = OrgUnit.query.filter_by(chart_type=ctype, parent_id=None)\
        .order_by(OrgUnit.sort_order, OrgUnit.id).all()
    title, desc = CHART_META[ctype]
    # 편집용: 전체 유닛 목록(부모 선택 등)
    all_units = OrgUnit.query.filter_by(chart_type=ctype).order_by(OrgUnit.sort_order).all()
    return render_template('org/chart.html', slug=slug, ctype=ctype, roots=roots,
                           title=title, desc=desc, all_units=all_units,
                           can_edit=_can_edit(), slugs=SLUGS)


# ════════════════════════════════════════════════════════════
# 편집 — 조직(Unit)
# ════════════════════════════════════════════════════════════
@org_bp.route('/<slug>/unit/add', methods=['POST'])
@login_required
def unit_add(slug):
    if slug not in SLUGS or not _can_edit():
        abort(403)
    ctype = SLUGS[slug]
    parent_id = request.form.get('parent_id', type=int)
    order = (db.session.query(db.func.max(OrgUnit.sort_order))
             .filter_by(chart_type=ctype, parent_id=parent_id).scalar() or 0) + 1
    u = OrgUnit(chart_type=ctype, name=request.form.get('name', '새 조직'),
                site=request.form.get('site') or None,
                leader=request.form.get('leader') or None,
                leader_title=request.form.get('leader_title') or None,
                parent_id=parent_id, sort_order=order)
    db.session.add(u)
    db.session.commit()
    flash('조직이 추가되었습니다.', 'success')
    return redirect(url_for('org.chart', slug=slug))


@org_bp.route('/<slug>/unit/<int:uid>/edit', methods=['POST'])
@login_required
def unit_edit(slug, uid):
    if slug not in SLUGS or not _can_edit():
        abort(403)
    u = OrgUnit.query.get_or_404(uid)
    u.name = request.form.get('name', u.name)
    u.site = request.form.get('site') or None
    u.leader = request.form.get('leader') or None
    u.leader_title = request.form.get('leader_title') or None
    u.leader_duty = request.form.get('leader_duty') or None
    u.color = request.form.get('color') or None
    db.session.commit()
    flash('조직 정보가 수정되었습니다.', 'success')
    return redirect(url_for('org.chart', slug=slug))


@org_bp.route('/<slug>/unit/<int:uid>/move', methods=['POST'])
@login_required
def unit_move(slug, uid):
    """상위 조직(라인) 변경 및 순서 이동."""
    if slug not in SLUGS or not _can_edit():
        abort(403)
    u = OrgUnit.query.get_or_404(uid)
    new_parent = request.form.get('parent_id', type=int)
    direction = request.form.get('dir')  # up/down
    if 'parent_id' in request.form:
        # 순환 방지: 자기 자신/후손을 부모로 지정 불가
        if new_parent:
            p = OrgUnit.query.get(new_parent)
            cur = p
            bad = False
            while cur:
                if cur.id == u.id:
                    bad = True; break
                cur = cur.parent
            if bad:
                flash('하위 조직을 상위로 지정할 수 없습니다.', 'danger')
                return redirect(url_for('org.chart', slug=slug))
        u.parent_id = new_parent
    if direction in ('up', 'down'):
        sibs = OrgUnit.query.filter_by(chart_type=u.chart_type, parent_id=u.parent_id)\
            .order_by(OrgUnit.sort_order, OrgUnit.id).all()
        idx = [s.id for s in sibs].index(u.id)
        swap = idx - 1 if direction == 'up' else idx + 1
        if 0 <= swap < len(sibs):
            u.sort_order, sibs[swap].sort_order = sibs[swap].sort_order, u.sort_order
    db.session.commit()
    flash('조직 위치가 변경되었습니다.', 'success')
    return redirect(url_for('org.chart', slug=slug))


@org_bp.route('/<slug>/unit/<int:uid>/delete', methods=['POST'])
@login_required
def unit_delete(slug, uid):
    if slug not in SLUGS or not _can_edit():
        abort(403)
    u = OrgUnit.query.get_or_404(uid)
    # 하위 조직을 부모로 승격(라인 유지) 후 삭제
    for child in u.children.all():
        child.parent_id = u.parent_id
    OrgMember.query.filter_by(unit_id=u.id).delete()
    db.session.delete(u)
    db.session.commit()
    flash('조직이 삭제되었습니다. (하위 조직은 상위로 승격)', 'info')
    return redirect(url_for('org.chart', slug=slug))


# ════════════════════════════════════════════════════════════
# 편집 — 구성원(Member) + 업무분장
# ════════════════════════════════════════════════════════════
@org_bp.route('/<slug>/member/add', methods=['POST'])
@login_required
def member_add(slug):
    if slug not in SLUGS or not _can_edit():
        abort(403)
    uid = request.form.get('unit_id', type=int)
    unit = OrgUnit.query.get_or_404(uid)
    order = (db.session.query(db.func.max(OrgMember.sort_order))
             .filter_by(unit_id=uid).scalar() or 0) + 1
    db.session.add(OrgMember(unit_id=uid, name=request.form.get('name', ''),
                             role=request.form.get('role') or None,
                             duty=request.form.get('duty') or None, sort_order=order))
    db.session.commit()
    flash('구성원이 추가되었습니다.', 'success')
    return redirect(url_for('org.chart', slug=slug))


@org_bp.route('/<slug>/member/<int:mid>/edit', methods=['POST'])
@login_required
def member_edit(slug, mid):
    if slug not in SLUGS or not _can_edit():
        abort(403)
    m = OrgMember.query.get_or_404(mid)
    m.name = request.form.get('name', m.name)
    m.role = request.form.get('role') or None
    m.duty = request.form.get('duty') or None
    db.session.commit()
    flash('구성원 정보가 수정되었습니다.', 'success')
    return redirect(url_for('org.chart', slug=slug))


def _is_descendant(unit, maybe_ancestor_id):
    """unit 이 maybe_ancestor_id 의 후손이면 True (순환 방지용). 여기선 반대로 검사 헬퍼."""
    cur = unit
    while cur:
        if cur.id == maybe_ancestor_id:
            return True
        cur = cur.parent
    return False


@org_bp.route('/<slug>/bulk_save', methods=['POST'])
@login_required
def bulk_save(slug):
    """인라인 일괄 편집 저장 — 수정·이동·삭제·신규(조직/구성원)를 한 번에 반영."""
    if slug not in SLUGS or not _can_edit():
        abort(403)
    ctype = SLUGS[slug]
    F = request.form
    u_upd, m_upd, newu, newm = {}, {}, {}, {}
    del_u, del_m = set(), set()
    for key, val in F.items():
        if key == 'csrf_token':
            continue
        parts = key.split('|')
        if len(parts) < 2:
            continue
        k = parts[0]
        if k in ('u', 'm', 'newu', 'newm') and len(parts) == 3 and parts[1].lstrip('-').isdigit():
            sid, f = int(parts[1]), parts[2]
            {'u': u_upd, 'm': m_upd, 'newu': newu, 'newm': newm}[k].setdefault(sid, {})[f] = val.strip()
        elif k == 'del_u' and parts[1].isdigit() and val == '1':
            del_u.add(int(parts[1]))
        elif k == 'del_m' and parts[1].isdigit() and val == '1':
            del_m.add(int(parts[1]))

    uc = mc = nu = nm = dc = 0

    # 1) 기존 조직 필드 수정 + 상위조직(라인) 이동 + 순서
    for uid, fields in u_upd.items():
        if uid in del_u:
            continue
        u = OrgUnit.query.filter_by(id=uid, chart_type=ctype).first()
        if not u:
            continue
        if fields.get('name'):
            u.name = fields['name']
        if 'leader' in fields:
            u.leader = fields['leader'] or None
        if 'leader_duty' in fields:
            u.leader_duty = fields['leader_duty'] or None
        if 'site' in fields:
            u.site = fields['site'] or None
        if 'order' in fields and fields['order'].lstrip('-').isdigit():
            u.sort_order = int(fields['order'])
        if 'parent' in fields:
            pv = fields['parent']
            new_pid = int(pv) if pv.isdigit() else None
            if new_pid != u.parent_id:
                # 순환 방지: 새 부모가 자기 자신/후손이면 무시
                if new_pid:
                    p = OrgUnit.query.get(new_pid)
                    if p and p.chart_type == ctype and not _is_descendant(p, u.id):
                        u.parent_id = new_pid
                else:
                    u.parent_id = None
        uc += 1

    # 2) 기존 구성원 수정
    for mid, fields in m_upd.items():
        if mid in del_m:
            continue
        m = OrgMember.query.get(mid)
        if not m or m.unit.chart_type != ctype:
            continue
        if fields.get('name'):
            m.name = fields['name']
        if 'role' in fields:
            m.role = fields['role'] or None
        if 'duty' in fields:
            m.duty = fields['duty'] or None
        mc += 1

    # 3) 신규 조직 추가
    for idx, fields in newu.items():
        if not fields.get('name'):
            continue
        pv = fields.get('parent', '')
        pid = int(pv) if pv.isdigit() else None
        order = (db.session.query(db.func.max(OrgUnit.sort_order))
                 .filter_by(chart_type=ctype, parent_id=pid).scalar() or 0) + 1
        db.session.add(OrgUnit(chart_type=ctype, parent_id=pid, name=fields['name'],
                               leader=fields.get('leader') or None,
                               leader_title=fields.get('title') or None,
                               site=fields.get('site') or None, sort_order=order))
        nu += 1

    # 4) 신규 구성원 추가
    for idx, fields in newm.items():
        uid = fields.get('unit', '')
        if not uid.isdigit() or not fields.get('name'):
            continue
        unit = OrgUnit.query.filter_by(id=int(uid), chart_type=ctype).first()
        if not unit:
            continue
        order = (db.session.query(db.func.max(OrgMember.sort_order))
                 .filter_by(unit_id=unit.id).scalar() or 0) + 1
        db.session.add(OrgMember(unit_id=unit.id, name=fields['name'],
                                 role=fields.get('role') or None,
                                 duty=fields.get('duty') or None, sort_order=order))
        nm += 1

    # 5) 삭제 (구성원 → 조직 순, 조직은 하위를 상위로 승격)
    for mid in del_m:
        m = OrgMember.query.get(mid)
        if m and m.unit.chart_type == ctype:
            db.session.delete(m); dc += 1
    for uid in del_u:
        u = OrgUnit.query.filter_by(id=uid, chart_type=ctype).first()
        if not u:
            continue
        for child in u.children.all():
            child.parent_id = u.parent_id
        OrgMember.query.filter_by(unit_id=u.id).delete()
        db.session.delete(u); dc += 1

    db.session.commit()
    flash(f'일괄 저장 완료 — 수정 {uc + mc} · 추가 {nu + nm} · 삭제 {dc}건 반영되었습니다.', 'success')
    return redirect(url_for('org.chart', slug=slug, edit=1))


@org_bp.route('/<slug>/member/<int:mid>/delete', methods=['POST'])
@login_required
def member_delete(slug, mid):
    if slug not in SLUGS or not _can_edit():
        abort(403)
    m = OrgMember.query.get_or_404(mid)
    db.session.delete(m)
    db.session.commit()
    flash('구성원이 삭제되었습니다.', 'info')
    return redirect(url_for('org.chart', slug=slug))
