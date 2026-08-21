from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import db, Policy, PolicyHistory, AuditTrail
from datetime import datetime, date

policy_bp = Blueprint('policy', __name__)

SLUGS = ['management', 'quality', 'env', 'safety']
SLUG_META = {
    'management': ('경영방침', 'Management Policy', '🎯', '#1a3a5c', '#e0e7ff'),
    'quality':    ('품질방침', 'Quality Policy', '✅', '#2563eb', '#dbeafe'),
    'env':        ('환경방침', 'Environmental Policy', '🌿', '#16a34a', '#dcfce7'),
    'safety':     ('안전보건방침', 'Safety & Health Policy', '⛑️', '#ea580c', '#ffedd5'),
}

# ── 방침 전문 시드 ──
POLICY_SEED = [
    dict(slug='management', title='경영방침', subtitle='Management Policy',
         intro='',
         body='''우리는 미래를 지향합니다.|회사의 발전과 우리의 발전을 위하여 창의와 도전으로 지속적인 변화를 추구합니다.
기술주도로 인재를 육성합니다.|전문성과 도전정신으로 창의력이 뛰어난 인재를 육성하며 서로 화합합니다.
고객의 옆에 있습니다.|고객의 목소리에 귀 기울여 고객이 원하는 바를 정확히 파악하고 기술에 적용합니다.
우리는 끊임없이 학습합니다.|지속적인 자기개발을 통하여 담당분야의 최고가 됩니다.
우리는 서로 아끼고 사랑합니다.|모두가 한 가족으로 상호 의존적 자세로서 활기찬 직장분위기를 조성합니다.''',
         outro=''),
    dict(slug='quality', title='품질방침', subtitle='Quality Policy',
         intro='',
         body='''품질 요구 사항 준수|회사에서 정한 품질 절차 및 표준을 준수하고 실천한다.
좋은 제품과 서비스 제공|양질의 제품을 생산하며 고객과의 약속을 최우선시 한다.
임직원의 역량 향상|모든 임직원이 품질에 관심을 가지고 각자의 능력을 배양한다.
전 직원은 회사가 정한 품질 요구 사항을 준수하고 좋은 제품과 서비스를 고객에게 제공한다.''',
         outro=''),
    dict(slug='env', title='환경방침', subtitle='Environmental Policy',
         intro='당사는 환경보전과 기업활동의 조화를 통하여 지구 환경 보전에 이바지한다는 투철한 사명감으로 다음과 같은 환경방침을 수립한다.',
         body='''당사에 관련되는 환경관련 법규 및 규정을 준수하고 이해관계자들의 요구 사항을 만족시킨다.
당사는 제조과정의 환경부하 및 제품의 품질에 의한 환경부하를 지속적으로 개선함으로써 환경오염 방지에 최선을 다한다.
당사는 모든 조직의 활동, 제품 및 서비스의 과정에서 에너지의 절약과 수질오염, 폐기물 발생 및 소음진동 발생을 최소화하며, 온실가스 배출량을 지속적으로 모니터링하고 감축을 위해 노력한다.
환경의 투명성과 공정성을 이해관계자에게 공개함으로써 신뢰감을 형성하며, 매년 환경성과(에너지, 폐기물, 온실가스 배출 등)를 경영검토를 통해 점검하고 개선한다.''',
         outro='당사는 환경방침의 실현을 위하여 환경목표를 설정하고 이를 점검하는 효율적인 환경 경영체제를 구축하고 전 임직원의 적극적이고 자발적인 참여를 통하여 환경방침을 반드시 달성하도록 노력한다.'),
    dict(slug='safety', title='안전보건방침', subtitle='Safety & Health Policy',
         intro='당사는 모든 임직원과 협력업체 근로자, 방문자 등 이해관계자의 안전과 건강을 기업경영의 최우선 가치로 삼아 안전하고 쾌적한 근로환경을 조성하기 위하여 다음과 같이 안전보건방침을 수립하고 성실히 이행한다.',
         body='''산업안전보건법 등 관련 법적 요구사항 및 당사가 동의한 기타 요구사항을 준수한다.
위험성평가를 통해 유해·위험요인을 지속적으로 발굴하고 제거·대체·감소함으로써 산업재해와 중대재해를 예방한다.
안전보건경영시스템의 지속적 개선을 위한 자원을 제공하고, 안전보건 목표를 수립하여 이행한다.
근로자 및 근로자대표(있는 경우)의 협의와 참여를 보장하고, 안전보건 관련 의견 개진이나 고충 제기를 이유로 어떠한 불이익도 주지 않는다.
임산부, 산후 1년 미만 여성 등 모성보호가 필요한 근로자를 위험작업으로부터 보호하고, 근로시간 단축 등 필요한 조치를 취한다.
화재, 화학물질 누출 등 비상상황 발생에 대비하여 초기대응체계를 갖추고 정기적으로 훈련하며, 신규 화학물질·설비·공정 도입 시 사전에 안전성을 평가한다.
전 임직원, 협력업체 및 방문자에게 본 방침을 알리고 안전보건 교육훈련을 통해 안전문화를 정착시킨다.''',
         outro='당사는 본 방침의 실현을 위하여 안전보건목표를 설정하고 이를 점검하는 효율적인 안전보건경영체제를 구축하며, 전 임직원의 적극적인 참여를 통해 무재해 사업장 구현을 위해 노력한다.'),
]


def seed_policies():
    if Policy.query.count() > 0:
        return
    for i, p in enumerate(POLICY_SEED):
        db.session.add(Policy(sort_order=i, revision_no=0,
                              effective_date=date(2026, 7, 1),
                              approver_name='대표이사', **p))
    db.session.commit()
    print(f"[시드] 방침 {len(POLICY_SEED)}종 생성")


def _can_edit():
    return current_user.has_policy_edit()


@policy_bp.route('/')
@login_required
def index():
    return redirect(url_for('policy.view', slug='management'))


@policy_bp.route('/<slug>')
@login_required
def view(slug):
    if slug not in SLUGS:
        flash('알 수 없는 방침입니다.', 'danger')
        return redirect(url_for('policy.view', slug='management'))
    p = Policy.query.filter_by(slug=slug).first_or_404()
    items = []
    for line in (p.body or '').split('\n'):
        line = line.strip()
        if not line:
            continue
        if '|' in line:
            head, desc = line.split('|', 1)
            items.append((head.strip(), desc.strip()))
        else:
            items.append((line, ''))
    histories = p.histories.order_by(PolicyHistory.id.desc()).all()
    return render_template('policy/view.html', p=p, slug=slug, items=items,
                           histories=histories, slug_meta=SLUG_META, slugs=SLUGS,
                           can_edit=_can_edit(), today=date.today())


@policy_bp.route('/<slug>/edit', methods=['GET', 'POST'])
@login_required
def edit(slug):
    if slug not in SLUGS:
        return redirect(url_for('policy.view', slug='management'))
    if not _can_edit():
        flash('방침 수정 권한이 없습니다. (관리자·품질팀·경영지원팀 또는 권한 부여자)', 'danger')
        return redirect(url_for('policy.view', slug=slug))
    p = Policy.query.filter_by(slug=slug).first_or_404()

    if request.method == 'POST':
        # 변경 전 내용을 이력으로 보존
        db.session.add(PolicyHistory(
            policy_id=p.id, revision_no=p.revision_no, title=p.title,
            intro=p.intro, body=p.body, outro=p.outro,
            effective_date=p.effective_date,
            change_reason=request.form.get('change_reason'),
            changed_by_id=current_user.id))

        p.title = request.form.get('title') or p.title
        p.subtitle = request.form.get('subtitle')
        p.intro = request.form.get('intro')
        p.body = request.form.get('body')
        p.outro = request.form.get('outro')
        p.approver_name = request.form.get('approver_name')
        eff = request.form.get('effective_date')
        p.effective_date = datetime.strptime(eff, '%Y-%m-%d').date() if eff else p.effective_date
        rev = request.form.get('revision_no', type=int)
        p.revision_no = rev if rev is not None else (p.revision_no or 0) + 1
        p.updated_by_id = current_user.id
        p.updated_at = datetime.utcnow()

        db.session.add(AuditTrail(user_id=current_user.id, action='방침개정',
                                  target_type='policy', target_id=p.id,
                                  target_name=f'{p.title} (Rev.{p.revision_no})'))
        db.session.commit()
        flash(f'{p.title}이(가) 개정되었습니다. (Rev.{p.revision_no})', 'success')
        return redirect(url_for('policy.view', slug=slug))

    return render_template('policy/edit.html', p=p, slug=slug, slug_meta=SLUG_META,
                           slugs=SLUGS, today=date.today())


@policy_bp.route('/<slug>/print')
@login_required
def print_view(slug):
    """방침 게시용 인쇄 (A4 세로, 로고·직인 포함)"""
    p = Policy.query.filter_by(slug=slug).first_or_404()
    items = []
    for line in (p.body or '').split('\n'):
        line = line.strip()
        if not line:
            continue
        if '|' in line:
            head, desc = line.split('|', 1)
            items.append((head.strip(), desc.strip()))
        else:
            items.append((line, ''))
    db.session.add(AuditTrail(user_id=current_user.id, action='방침출력',
                              target_type='policy', target_id=p.id, target_name=p.title))
    db.session.commit()
    return render_template('policy/print.html', p=p, slug=slug, items=items,
                           slug_meta=SLUG_META, today=date.today())
