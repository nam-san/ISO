# -*- coding: utf-8 -*-
"""문서관리절차서(NV-P-001) 표준서 번호 부여 체계 — 참조 데이터 + 번호 발행 엔진."""
from collections import OrderedDict

# 표1. 지침서 약호
GUIDE_CODES = OrderedDict([
    ('II', '수입검사기준'),
    ('PI', '중간검사기준'),
    ('OI', '제품검사기준'),
    ('WC', '제조공정도'),
    ('WI', '작업지도서'),
])

# 표2. 부서·파트 약호
DEPT_CODES = OrderedDict([
    ('MGMT', {'name': '경영관리팀', 'parts': OrderedDict([('HRGA', '인사총무파트'), ('FA', '재무회계파트')])}),
    ('SM',   {'name': '영업관리파트', 'parts': OrderedDict()}),
    ('VOIP', {'name': 'VOIP사업팀', 'parts': OrderedDict()}),
    ('SI',   {'name': 'SI사업팀', 'parts': OrderedDict([('BD', '개발관리파트')])}),
    ('SWS',  {'name': 'SWS사업팀', 'parts': OrderedDict([('SWD', 'SW개발파트'), ('DEV', '개발팀'), ('HWD', 'HW개발파트')])}),
    ('QM',   {'name': '품질경영팀', 'parts': OrderedDict([('QE', '품질기술파트'), ('QC', '품질관리파트')])}),
    ('MFG',  {'name': '제조팀', 'parts': OrderedDict([('MFM', '제조관리파트'), ('MFE', '제조기술파트'), ('MO', '자재운영파트')])}),
    ('PUR',  {'name': '구매팀', 'parts': OrderedDict()}),
])

# 문서 유형 → 확인 카테고리
DOC_TYPES = ['매뉴얼', '절차서', '지침서', '서식']
CATEGORY = {
    '매뉴얼': 'manual_proc', '절차서': 'manual_proc',
    '지침서': 'guide', '서식': 'form',
}
CATEGORY_LABEL = OrderedDict([
    ('manual_proc', '매뉴얼·절차서'),
    ('guide', '지침서·지도서'),
    ('form', '서식'),
])


def _parent_code(parent_number):
    """서식의 상위문서 번호에서 서식번호 앞부분 추출.
    NV-P-001(절차서) → 'P-001' / NV-II-01(지침서) → 'II-01' / NV-QM-01 → 'QM-01'
    (성적서·작업일보 등 지침서·지도서 전용 서식도 동일 규칙 적용)
    """
    if parent_number:
        if parent_number.startswith('NV-'):
            return parent_number[3:]          # 회사약호 제거
        return parent_number
    return 'P-000'


def build_number(doc_type, serial, revision_no=0, guide_code=None,
                 dept_code=None, part_code=None, is_dept_doc=False,
                 related_proc_number=None):
    """유형·연번·약호로 표준 문서번호 생성."""
    try:
        serial = int(serial)
    except (TypeError, ValueError):
        serial = 1
    if is_dept_doc and dept_code:
        if part_code:
            return f'NV-{dept_code}-{part_code}-{serial:03d}'
        return f'NV-{dept_code}-{serial:03d}'
    if doc_type == '매뉴얼':
        return f'NV-QM-{serial:02d}'
    if doc_type == '절차서':
        return f'NV-P-{serial:03d}'
    if doc_type == '지침서':
        return f'NV-{(guide_code or "II")}-{serial:02d}'
    if doc_type == '서식':
        rev = revision_no or 0
        return f'{_parent_code(related_proc_number)}-{serial}-(REV{rev})'
    return f'NV-DOC-{serial:03d}'


def _prefix(doc_type, guide_code=None, dept_code=None, part_code=None,
            is_dept_doc=False, related_proc_number=None):
    """해당 유형 문서번호의 접두부(연번 앞부분)."""
    if is_dept_doc and dept_code:
        return f'NV-{dept_code}-{part_code}-' if part_code else f'NV-{dept_code}-'
    if doc_type == '매뉴얼':
        return 'NV-QM-'
    if doc_type == '절차서':
        return 'NV-P-'
    if doc_type == '지침서':
        return f'NV-{(guide_code or "II")}-'
    if doc_type == '서식':
        return f'{_parent_code(related_proc_number)}-'
    return 'NV-DOC-'


def next_serial(doc_type, guide_code=None, dept_code=None, part_code=None,
                is_dept_doc=False, related_proc_number=None):
    """해당 유형에서 사용 가능한 다음 연번 계산."""
    from models import Document
    prefix = _prefix(doc_type, guide_code, dept_code, part_code, is_dept_doc, related_proc_number)
    docs = Document.query.filter(Document.doc_number.like(f'{prefix}%')).all()
    mx = 0
    for d in docs:
        rest = d.doc_number[len(prefix):]
        # 연번 = 접두부 바로 뒤 숫자
        num = ''
        for ch in rest:
            if ch.isdigit():
                num += ch
            else:
                break
        if num:
            mx = max(mx, int(num))
    return mx + 1


def number_exists(number, exclude_id=None):
    """이미 등록된 문서번호인지 확인(개정본 REV 표기 제외한 기본번호 기준)."""
    from models import Document
    q = Document.query.filter(Document.doc_number == number)
    if exclude_id:
        q = q.filter(Document.id != exclude_id)
    return q.first() is not None
