from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


# ============================================================
# 조직도 (Org Chart) — 전체/품질/환경/안전보건
# ============================================================
class OrgUnit(db.Model):
    __tablename__ = 'org_units'
    id = db.Column(db.Integer, primary_key=True)
    chart_type = db.Column(db.String(20), default='전체', index=True)  # 전체/품질/환경/안전보건
    site = db.Column(db.String(20))                      # 사업장: 본사 / 제조센터 / (없으면 전사·공통)
    name = db.Column(db.String(100), nullable=False)     # 조직/직위 명 (예: 기술연구소, 품질경영팀)
    leader = db.Column(db.String(50))                    # 책임자 이름 (선택)
    leader_title = db.Column(db.String(50))              # 책임자 직함 (대표이사/소장/팀장/파트장 등)
    leader_duty = db.Column(db.Text)                     # 책임자 업무분장
    parent_id = db.Column(db.Integer, db.ForeignKey('org_units.id'))
    sort_order = db.Column(db.Integer, default=0)
    color = db.Column(db.String(20))                     # 박스 강조색(선택)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    children = db.relationship('OrgUnit', backref=db.backref('parent', remote_side=[id]),
                               lazy='dynamic', order_by='OrgUnit.sort_order, OrgUnit.id')
    members = db.relationship('OrgMember', backref='unit', lazy='dynamic',
                              cascade='all, delete-orphan', order_by='OrgMember.sort_order, OrgMember.id')

    def __repr__(self):
        return f'<OrgUnit {self.chart_type}:{self.name}>'


class OrgMember(db.Model):
    __tablename__ = 'org_members'
    id = db.Column(db.Integer, primary_key=True)
    unit_id = db.Column(db.Integer, db.ForeignKey('org_units.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False)      # 이름
    role = db.Column(db.String(50))                      # 직책/역할 (파트장/사원/담당 등)
    duty = db.Column(db.Text)                            # 업무분장 (마우스 오버 팝업)
    sort_order = db.Column(db.Integer, default=0)


# ============================================================
# 부서 테이블
# ============================================================
class Department(db.Model):
    __tablename__ = 'departments'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)   # 예: QA, RD, MFG
    name = db.Column(db.String(100), nullable=False)               # 예: 품질팀
    location = db.Column(db.String(50), default='서울본사')         # 서울본사 / 나주지점
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    users = db.relationship('User', backref='department', lazy='dynamic')

    def __repr__(self):
        return f'<Department {self.name}>'


# ============================================================
# 사용자 테이블
# ============================================================
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.String(20), unique=True, nullable=False)  # 사번
    name = db.Column(db.String(50), nullable=False)                       # 이름
    email = db.Column(db.String(120), unique=True)
    password_hash = db.Column(db.String(256))
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    position = db.Column(db.String(50))                                   # 직책 (팀장, 사원 등)
    
    # 권한 역할
    # admin: 시스템관리자, manager: 팀장/경영진, staff: 일반직원, viewer: 열람만
    role = db.Column(db.String(20), default='staff')

    # 세부 권한 (역할과 별개로 부여 가능) — 결재 3단계: 작성(등록)→검토→승인
    can_edit = db.Column(db.Boolean, default=False)      # 작성(등록)/수정 권한
    can_review = db.Column(db.Boolean, default=False)    # 검토 권한
    can_approve = db.Column(db.Boolean, default=False)   # 승인 권한
    is_auditor = db.Column(db.Boolean, default=False)    # 내부심사자 자격
    can_org = db.Column(db.Boolean, default=False)       # 조직도 편집 권한
    can_training = db.Column(db.Boolean, default=False)  # 교육훈련 관리 권한

    is_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_admin(self):
        return self.role == 'admin'
    
    def is_manager(self):
        return self.role in ['admin', 'manager']

    def has_edit(self):
        """작성(등록)/수정 권한: 관리자/매니저는 기본 보유, 그 외는 can_edit 플래그"""
        return self.is_manager() or self.can_edit

    def has_review(self):
        """검토 권한: 관리자/매니저는 기본 보유, 그 외는 can_review 플래그"""
        return self.is_manager() or self.can_review

    def has_approve(self):
        """승인 권한: 관리자/매니저는 기본 보유, 그 외는 can_approve 플래그"""
        return self.is_manager() or self.can_approve

    def has_org_edit(self):
        """조직도 편집 권한: 관리자 + 명시적으로 부여된 사용자만 (매니저 기본 미포함)"""
        return self.is_admin() or self.can_org

    def has_training_edit(self):
        """교육훈련 관리 권한: 관리자 + 명시적으로 부여된 교육 담당자만"""
        return self.is_admin() or self.can_training

    def has_legal_edit(self):
        """법규 준수현황 변경 권한: 관리자 + 내부심사자(is_auditor)만"""
        return self.is_admin() or self.is_auditor

    def __repr__(self):
        return f'<User {self.name}({self.employee_id})>'


# ============================================================
# 문서 테이블 (기준문서 관리 M1)
# ============================================================
class Document(db.Model):
    __tablename__ = 'documents'
    id = db.Column(db.Integer, primary_key=True)
    doc_number = db.Column(db.String(30), nullable=False)       # 문서번호 (QP-001 등)
    title = db.Column(db.String(200), nullable=False)           # 문서명
    doc_type = db.Column(db.String(30), nullable=False)         # 매뉴얼/절차서/지침서/서식
    iso_standard = db.Column(db.String(50))                     # ISO9001/ISO14001/ISO45001/통합
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    
    # 버전 및 상태
    version = db.Column(db.String(10), default='1.0')
    status = db.Column(db.String(20), default='draft')
    # draft: 초안 / review: 검토중 / approved: 승인 / active: 배포중 / obsolete: 폐기
    
    # 작성자/승인자
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # 날짜
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved_at = db.Column(db.DateTime)
    effective_date = db.Column(db.Date)    # 시행일
    review_date = db.Column(db.Date)       # 다음 검토 예정일
    
    # 파일 첨부
    file_path = db.Column(db.String(500))
    file_name = db.Column(db.String(200))
    
    # 내용 (간략 설명)
    description = db.Column(db.Text)
    
    # 관계
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    approved_by = db.relationship('User', foreign_keys=[approved_by_id])
    department = db.relationship('Department', backref='documents')
    versions = db.relationship('DocumentVersion', backref='document', lazy='dynamic')
    approvals = db.relationship('Approval', backref='document', lazy='dynamic')

    def __repr__(self):
        return f'<Document {self.doc_number} v{self.version}>'


# ============================================================
# 문서 버전 이력 테이블
# ============================================================
class DocumentVersion(db.Model):
    __tablename__ = 'document_versions'
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'))
    version = db.Column(db.String(10))
    change_reason = db.Column(db.Text)           # 개정 사유
    changed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)
    file_path = db.Column(db.String(500))
    
    changed_by = db.relationship('User')


# ============================================================
# 전자결재 테이블 (M3)
# ============================================================
class Approval(db.Model):
    __tablename__ = 'approvals'
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'))
    approver_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    step = db.Column(db.Integer)              # 결재 순서 (1, 2, 3...)
    role_label = db.Column(db.String(50))     # 담당자/팀장/경영진
    status = db.Column(db.String(20), default='pending')
    # pending: 대기 / approved: 승인 / rejected: 반려
    comment = db.Column(db.Text)              # 결재 의견
    acted_at = db.Column(db.DateTime)

    approver = db.relationship('User')


# ============================================================
# 관계부서 합의 결재 (문서 절차서 / 내부심사 계획 — 다부서 병렬 합의)
# ============================================================
class Concurrence(db.Model):
    __tablename__ = 'concurrences'
    id = db.Column(db.Integer, primary_key=True)
    target_type = db.Column(db.String(20), nullable=False)   # 'document' | 'audit'
    target_id = db.Column(db.Integer, nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')     # pending / agreed / disagreed
    acted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    comment = db.Column(db.Text)
    acted_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    department = db.relationship('Department')
    acted_by = db.relationship('User')

    def __repr__(self):
        return f'<Concurrence {self.target_type}#{self.target_id} {self.department_id}={self.status}>'


# ============================================================
# 실행기록 테이블 (M2)
# ============================================================
class Record(db.Model):
    __tablename__ = 'records'
    id = db.Column(db.Integer, primary_key=True)
    record_number = db.Column(db.String(30))         # 기록번호 (자동채번)
    title = db.Column(db.String(200), nullable=False)
    record_type = db.Column(db.String(50))           # 기록 유형 (검사기록/교육기록 등)
    iso_standard = db.Column(db.String(50))
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    related_doc_id = db.Column(db.Integer, db.ForeignKey('documents.id'))
    
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    record_date = db.Column(db.Date)                 # 기록 발생일
    
    # 보존연한 관리
    retention_years = db.Column(db.Integer, default=3)  # 보존 기간(년)
    disposal_date = db.Column(db.Date)                   # 폐기 예정일
    
    status = db.Column(db.String(20), default='active')  # active / disposed
    content = db.Column(db.Text)
    file_path = db.Column(db.String(500))
    file_name = db.Column(db.String(200))
    
    created_by = db.relationship('User')
    department = db.relationship('Department')


# ============================================================
# 내부심사 테이블 (M5)
# ============================================================
class Audit(db.Model):
    __tablename__ = 'audits'
    id = db.Column(db.Integer, primary_key=True)
    audit_number = db.Column(db.String(30))
    title = db.Column(db.String(200), nullable=False)
    audit_type = db.Column(db.String(20))     # internal: 내부심사 / external: 외부심사
    iso_standard = db.Column(db.String(50))
    
    planned_date = db.Column(db.Date)
    actual_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='planned')
    # planned: 계획 / in_progress: 진행중 / completed: 완료
    
    auditor_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    scope = db.Column(db.Text)          # 심사 범위
    findings = db.Column(db.Text)       # 심사 결과 요약

    # ── 심사 계획 추가 정보 ──
    audit_criteria = db.Column(db.Text)     # 심사 기준(적용 표준·문서)
    period_start = db.Column(db.Date)       # 심사 기간 시작
    period_end = db.Column(db.Date)         # 심사 기간 종료

    # ── 계획 승인 워크플로우 (작성/검토/승인) ──
    plan_status = db.Column(db.String(20), default='draft')  # draft/review/approved
    plan_reviewed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    plan_approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    plan_approved_at = db.Column(db.DateTime)

    # ── 결과보고서 (작성/검토/승인) ──
    report_summary = db.Column(db.Text)      # 종합 의견
    report_conclusion = db.Column(db.Text)   # 결론(적합성 판정 사유)
    report_result = db.Column(db.String(20)) # conform/conditional/nonconform
    report_status = db.Column(db.String(20), default='draft')
    report_reviewed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    report_approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    report_approved_at = db.Column(db.DateTime)

    auditor = db.relationship('User', foreign_keys=[auditor_id])
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    plan_reviewed_by = db.relationship('User', foreign_keys=[plan_reviewed_by_id])
    plan_approved_by = db.relationship('User', foreign_keys=[plan_approved_by_id])
    report_reviewed_by = db.relationship('User', foreign_keys=[report_reviewed_by_id])
    report_approved_by = db.relationship('User', foreign_keys=[report_approved_by_id])
    department = db.relationship('Department')
    capas = db.relationship('CAPA', backref='audit', lazy='dynamic')
    auditors = db.relationship('AuditAuditor', backref='audit',
                               lazy='dynamic', cascade='all, delete-orphan')
    targets = db.relationship('AuditTarget', backref='audit',
                              lazy='dynamic', cascade='all, delete-orphan')
    checklist_items = db.relationship('AuditChecklistItem', backref='audit',
                                      lazy='dynamic', cascade='all, delete-orphan')


# ============================================================
# 심사원 지정 (Audit Auditor) — 심사별 다중 심사원
# ============================================================
class AuditAuditor(db.Model):
    __tablename__ = 'audit_auditors'
    id = db.Column(db.Integer, primary_key=True)
    audit_id = db.Column(db.Integer, db.ForeignKey('audits.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    is_lead = db.Column(db.Boolean, default=False)   # 선임심사원 여부

    user = db.relationship('User')


# ============================================================
# 심사 대상 부서 (Audit Target) — 부서별 체크리스트 시트 단위
# ============================================================
class AuditTarget(db.Model):
    __tablename__ = 'audit_targets'
    id = db.Column(db.Integer, primary_key=True)
    audit_id = db.Column(db.Integer, db.ForeignKey('audits.id'), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    auditee_name = db.Column(db.String(100))         # 피심사자(부서 대표)
    auditor_name = db.Column(db.String(100))         # 심사자(해당 부서 심사 수행자)
    audit_date = db.Column(db.Date)                  # 부서별 심사일
    conformity = db.Column(db.String(20))            # 종합판정 conform/conditional/nonconform
    note = db.Column(db.Text)

    department = db.relationship('Department')


# ============================================================
# 체크리스트 마스터 템플릿 (ISO 규격별 필수·중요 점검항목)
# ============================================================
class ChecklistTemplate(db.Model):
    __tablename__ = 'checklist_templates'
    id = db.Column(db.Integer, primary_key=True)
    iso_standard = db.Column(db.String(20))          # ISO9001/ISO14001/ISO45001
    clause = db.Column(db.String(20))                # 조항 (예: 7.5)
    category = db.Column(db.String(60))              # 영역 (예: 문서화된 정보)
    content = db.Column(db.Text)                     # 점검 내용(질문)
    is_mandatory = db.Column(db.Boolean, default=False)  # 필수 항목 여부
    sort_order = db.Column(db.Integer, default=0)


# ============================================================
# 심사 체크리스트 항목 (audit × department 시트)
# ============================================================
class AuditChecklistItem(db.Model):
    __tablename__ = 'audit_checklist_items'
    id = db.Column(db.Integer, primary_key=True)
    audit_id = db.Column(db.Integer, db.ForeignKey('audits.id'), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    iso_standard = db.Column(db.String(20))
    clause = db.Column(db.String(20))
    category = db.Column(db.String(60))
    content = db.Column(db.Text)
    is_mandatory = db.Column(db.Boolean, default=False)
    result = db.Column(db.String(20), default='pending')
    # pending: 미점검 / conform: 적합 / nonconform: 부적합 / observation: 관찰 / na: 해당없음
    evidence = db.Column(db.Text)        # 객관적 증거
    finding = db.Column(db.Text)         # 지적/관찰 내용
    capa_id = db.Column(db.Integer, db.ForeignKey('capa.id'))  # 부적합 시 연계 CAPA
    sort_order = db.Column(db.Integer, default=0)

    department = db.relationship('Department')


# ============================================================
# 시정조치(CAPA) 테이블 (M5)
# ============================================================
class CAPA(db.Model):
    __tablename__ = 'capa'
    id = db.Column(db.Integer, primary_key=True)
    capa_number = db.Column(db.String(30))
    audit_id = db.Column(db.Integer, db.ForeignKey('audits.id'))
    
    nc_type = db.Column(db.String(20))         # major: 중부적합 / minor: 경부적합 / obs: 관찰사항
    nc_description = db.Column(db.Text)        # 부적합 내용
    iso_clause = db.Column(db.String(20))      # ISO 조항 (예: 8.4.1)
    
    root_cause = db.Column(db.Text)            # 근본원인 분석
    corrective_action = db.Column(db.Text)     # 시정조치
    preventive_action = db.Column(db.Text)     # 예방조치
    
    responsible_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    due_date = db.Column(db.Date)
    completed_date = db.Column(db.Date)
    
    effectiveness = db.Column(db.Text)         # 유효성 검증
    status = db.Column(db.String(20), default='open')
    # open: 미결 / in_progress: 진행중 / verified: 검증완료 / closed: 종결

    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))  # 발생 부서

    # ── 시정조치 검토/승인 (작성/검토/승인) ──
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    responsible = db.relationship('User', foreign_keys=[responsible_id])
    reviewed_by = db.relationship('User', foreign_keys=[reviewed_by_id])
    approved_by = db.relationship('User', foreign_keys=[approved_by_id])
    department = db.relationship('Department')
    attachments = db.relationship('CAPAAttachment', backref='capa',
                                  lazy='dynamic', cascade='all, delete-orphan')


class CAPAAttachment(db.Model):
    """시정조치 증빙 첨부 (사진/문서, 여러 개 가능)"""
    __tablename__ = 'capa_attachments'
    id = db.Column(db.Integer, primary_key=True)
    capa_id = db.Column(db.Integer, db.ForeignKey('capa.id'), nullable=False)
    file_path = db.Column(db.String(500))
    file_name = db.Column(db.String(200))
    is_image = db.Column(db.Boolean, default=False)   # 이미지면 썸네일+클릭확대
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    uploaded_by = db.relationship('User')


# ============================================================
# 환경측면 영향평가 테이블 (M8 - ISO 14001)
# ============================================================
class EnvironmentalAspect(db.Model):
    __tablename__ = 'hse_environmental'
    id = db.Column(db.Integer, primary_key=True)
    aspect_number = db.Column(db.String(30))
    site = db.Column(db.String(20), default='제조공장')   # 사업장: 본사 / 제조공장
    process = db.Column(db.String(100))          # 공정/활동
    aspect = db.Column(db.String(200))           # 환경측면
    impact = db.Column(db.String(200))           # 환경영향
    
    # 중요성 평가 (빈도 × 심각도)
    frequency = db.Column(db.Integer)            # 빈도 (1-5)
    severity = db.Column(db.Integer)             # 심각도 (1-5)
    significance = db.Column(db.Integer)         # 중요성 점수 (자동계산)
    is_significant = db.Column(db.Boolean, default=False)
    
    control_measure = db.Column(db.Text)         # 관리 방안
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    evaluation_date = db.Column(db.Date)
    next_review_date = db.Column(db.Date)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ============================================================
# 위험성평가 테이블 (M8 - ISO 45001)
# ============================================================
class RiskAssessment(db.Model):
    __tablename__ = 'hse_risk'
    id = db.Column(db.Integer, primary_key=True)
    risk_number = db.Column(db.String(30))
    site = db.Column(db.String(20), default='제조공장')   # 사업장: 본사 / 제조공장
    work_area = db.Column(db.String(100))        # 작업 장소
    work_type = db.Column(db.String(100))        # 작업 유형
    hazard = db.Column(db.String(200))           # 유해위험요인
    risk_scenario = db.Column(db.Text)           # 위험 시나리오
    
    # 위험성 추정 (가능성 × 중대성)
    probability = db.Column(db.Integer)          # 가능성 (1-5)
    severity = db.Column(db.Integer)             # 중대성 (1-5)
    risk_level = db.Column(db.Integer)           # 위험성 수준 (자동계산)
    risk_grade = db.Column(db.String(10))        # 상/중/하
    
    control_measure = db.Column(db.Text)         # 감소대책
    residual_risk = db.Column(db.Integer)        # 잔류위험
    
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    assessment_date = db.Column(db.Date)
    next_review_date = db.Column(db.Date)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    improvements = db.relationship('RiskImprovement', backref='risk',
                                   lazy='dynamic', cascade='all, delete-orphan')


# ============================================================
# 위험성평가 개선조치 테이블 (작성 → 승인 2단계)
# ============================================================
class RiskImprovement(db.Model):
    __tablename__ = 'risk_improvements'
    id = db.Column(db.Integer, primary_key=True)
    improvement_number = db.Column(db.String(30))          # RIMP-YYYY-NNN
    risk_id = db.Column(db.Integer, db.ForeignKey('hse_risk.id'))

    # ── 원본 위험 스냅샷 (개선 버튼 클릭 시 자동 매핑) ──
    work_area = db.Column(db.String(100))
    work_type = db.Column(db.String(100))
    hazard = db.Column(db.String(200))
    current_control = db.Column(db.Text)                   # 개선 전 현재안전조치
    before_probability = db.Column(db.Integer)
    before_severity = db.Column(db.Integer)
    before_level = db.Column(db.Integer)
    before_grade = db.Column(db.String(10))

    # ── 작성: 개선 계획 ──
    improvement_plan = db.Column(db.Text)                  # 개선 대책/계획
    responsible_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    due_date = db.Column(db.Date)

    # ── 개선 후(결과) ──
    after_probability = db.Column(db.Integer)
    after_severity = db.Column(db.Integer)
    after_level = db.Column(db.Integer)
    after_grade = db.Column(db.String(10))
    after_control = db.Column(db.Text)                     # 개선 후 안전조치(승인 시 원본 위험의 현재안전조치로 반영)
    result = db.Column(db.Text)                            # 개선 결과/실시 내용
    completed_date = db.Column(db.Date)

    # ── 상태/승인 ──
    status = db.Column(db.String(20), default='in_progress')
    # in_progress: 개선중 / completed: 승인대기(개선완료) / approved: 승인완료
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)

    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    responsible = db.relationship('User', foreign_keys=[responsible_id])
    approved_by = db.relationship('User', foreign_keys=[approved_by_id])
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    attachments = db.relationship('RiskImprovementAttachment', backref='improvement',
                                  lazy='dynamic', cascade='all, delete-orphan')


class RiskImprovementAttachment(db.Model):
    """개선조치 증빙 첨부 (개선 전/후 사진·문서, 여러 개 가능)"""
    __tablename__ = 'risk_improvement_attachments'
    id = db.Column(db.Integer, primary_key=True)
    improvement_id = db.Column(db.Integer, db.ForeignKey('risk_improvements.id'), nullable=False)
    file_path = db.Column(db.String(500))
    file_name = db.Column(db.String(200))
    is_image = db.Column(db.Boolean, default=False)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)


# ============================================================
# 연간 교육훈련 계획 테이블 (Annual Training Plan)
# ============================================================
class TrainingPlan(db.Model):
    __tablename__ = 'training_plans'
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False, index=True)   # 계획 연도
    category = db.Column(db.String(20), default='일반교육')    # 법정교육/직무교육/품질교육/환경교육/일반교육/기타
    host = db.Column(db.String(50))                            # 주관 (인사/총무, 품질관리 등)
    title = db.Column(db.String(200), nullable=False)          # 교육과정명
    legal_basis = db.Column(db.String(200))                    # 근거 (법령/절차서)
    iso_standard = db.Column(db.String(50))                    # 관련 ISO 규격
    target_desc = db.Column(db.String(120))                    # 교육대상 (전사/현장직/팀별1명 등)
    cycle = db.Column(db.String(30))                           # 실시주기 (연1회/반기1회/월1회/발생시)
    institution = db.Column(db.String(120))                    # 교육기관
    plan_months = db.Column(db.String(60))                     # 계획 월 (쉼표구분 1~12, 예: '4,9')
    planned_hours = db.Column(db.Float)                        # 계획 교육시간
    target_count = db.Column(db.Integer)                       # 계획 인원(선택)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    is_default = db.Column(db.Boolean, default=False)          # 기본 시드 항목 여부
    is_active = db.Column(db.Boolean, default=True)
    note = db.Column(db.Text)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    department = db.relationship('Department')
    executions = db.relationship('Training', backref='plan', lazy='dynamic')

    @property
    def planned_month_list(self):
        """계획 월 리스트 (int)."""
        if not self.plan_months:
            return []
        return [int(x) for x in self.plan_months.split(',') if x.strip().isdigit()]

    @property
    def exec_count(self):
        return self.executions.count()

    @property
    def done_count(self):
        """이수(완료) 실행 건수."""
        return self.executions.count()

    @property
    def total_attendees(self):
        return sum(t.attendee_total for t in self.executions.all())

    @property
    def last_date(self):
        t = self.executions.order_by(Training.training_date.desc()).first()
        return t.training_date if t else None

    @property
    def is_done(self):
        return self.executions.count() > 0


# ============================================================
# 교육훈련 이수 기록 테이블 (Training Records - 경영지원팀)
# ============================================================
class Training(db.Model):
    __tablename__ = 'trainings'
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('training_plans.id'))   # 연간계획 연결(선택)
    training_number = db.Column(db.String(30))           # 자동채번 TRN-YYYY-NNNN
    title = db.Column(db.String(200), nullable=False)    # 교육명
    training_type = db.Column(db.String(30))             # 내부/외부/법정의무/OJT
    iso_standard = db.Column(db.String(50))              # ISO9001/ISO14001/ISO45001/통합
    training_date = db.Column(db.Date, nullable=False)   # 교육일
    end_date = db.Column(db.Date)                        # 종료일 (다일 과정)
    hours = db.Column(db.Float, default=0)               # 교육 시간
    institution = db.Column(db.String(100))              # 교육기관/강사
    location = db.Column(db.String(100))                 # 교육 장소
    content = db.Column(db.Text)                         # 교육 내용/목표
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    file_path = db.Column(db.String(500))
    file_name = db.Column(db.String(200))

    # 참석자 입력 방식: individual=개별 이름 등록 / company=전사·단체(인원수만)
    attendee_mode = db.Column(db.String(20), default='individual')
    headcount = db.Column(db.Integer)                    # 전사/단체 교육 시 참석 인원수

    department = db.relationship('Department')
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    attendees = db.relationship('TrainingAttendee', backref='training', lazy='dynamic', cascade='all, delete-orphan')

    @property
    def attendee_total(self):
        """참석 인원수 — 전사 교육은 headcount, 개별 교육은 등록된 참석자 수."""
        if self.attendee_mode == 'company':
            return self.headcount or 0
        return self.attendees.count()


class TrainingAttendee(db.Model):
    __tablename__ = 'training_attendees'
    id = db.Column(db.Integer, primary_key=True)
    training_id = db.Column(db.Integer, db.ForeignKey('trainings.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    name = db.Column(db.String(50))                      # 직접 입력 시 (외부인)
    department_name = db.Column(db.String(100))
    position = db.Column(db.String(50))
    completed = db.Column(db.Boolean, default=True)      # 이수 여부
    score = db.Column(db.Float)                          # 평가 점수 (선택)

    user = db.relationship('User')


# ============================================================
# 고객 클레임/불만 처리 기록 테이블 (사업부)
# ============================================================
class CustomerComplaint(db.Model):
    __tablename__ = 'customer_complaints'
    id = db.Column(db.Integer, primary_key=True)
    complaint_number = db.Column(db.String(30))          # 자동채번 CLM-YYYY-NNNN
    receipt_date = db.Column(db.Date, nullable=False)    # 접수일
    customer_name = db.Column(db.String(100), nullable=False)  # 고객사명
    contact_person = db.Column(db.String(50))            # 담당자
    contact_info = db.Column(db.String(100))             # 연락처
    product_model = db.Column(db.String(100))            # 제품/모델명
    complaint_type = db.Column(db.String(30))            # 품질불량/납기/서비스/기타
    complaint_content = db.Column(db.Text, nullable=False)  # 불만 내용
    iso_clause = db.Column(db.String(30))                # 관련 ISO 조항
    priority = db.Column(db.String(10), default='normal')  # high/normal/low
    status = db.Column(db.String(20), default='open')
    # open: 접수 / investigating: 조사중 / resolved: 처리완료 / closed: 종결
    root_cause = db.Column(db.Text)                      # 원인 분석
    action_taken = db.Column(db.Text)                    # 조치 내용
    preventive_measure = db.Column(db.Text)              # 재발방지 조치
    due_date = db.Column(db.Date)                        # 처리 기한
    resolved_date = db.Column(db.Date)                   # 처리 완료일
    responsible_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    file_path = db.Column(db.String(500))
    file_name = db.Column(db.String(200))

    responsible = db.relationship('User', foreign_keys=[responsible_id])
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    attachments = db.relationship('ComplaintAttachment', backref='complaint',
                                  lazy='dynamic', cascade='all, delete-orphan')


class ComplaintAttachment(db.Model):
    """고객 클레임 처리 증빙 첨부 (사진/문서, 여러 개 가능)"""
    __tablename__ = 'complaint_attachments'
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey('customer_complaints.id'), nullable=False)
    file_path = db.Column(db.String(500))
    file_name = db.Column(db.String(200))
    is_image = db.Column(db.Boolean, default=False)   # 이미지면 썸네일+클릭확대
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    uploaded_by = db.relationship('User')


# ============================================================
# 설계/개발 변경 관리 기록 테이블 (연구소)
# ============================================================
class DesignChange(db.Model):
    __tablename__ = 'design_changes'
    id = db.Column(db.Integer, primary_key=True)
    change_number = db.Column(db.String(30))             # 자동채번 DCR-YYYY-NNNN
    product_name = db.Column(db.String(100), nullable=False)  # 제품명/모델
    change_type = db.Column(db.String(30))               # 설계변경/공정변경/자재변경/소프트웨어변경
    change_title = db.Column(db.String(200), nullable=False)  # 변경 제목
    change_reason = db.Column(db.Text, nullable=False)   # 변경 사유
    change_content = db.Column(db.Text, nullable=False)  # 변경 내용
    before_spec = db.Column(db.Text)                     # 변경 전 사양
    after_spec = db.Column(db.Text)                      # 변경 후 사양
    verification_method = db.Column(db.Text)             # 검증 방법
    risk_assessment = db.Column(db.Text)                 # 리스크 평가
    status = db.Column(db.String(20), default='draft')
    # draft: 초안 / review: 검토중 / approved: 승인 / implemented: 반영완료 / rejected: 기각
    request_date = db.Column(db.Date)                    # 변경 요청일
    approved_date = db.Column(db.Date)                   # 승인일
    apply_date = db.Column(db.Date)                      # 적용 예정일
    requester_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    approver_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    file_path = db.Column(db.String(500))
    file_name = db.Column(db.String(200))

    requester = db.relationship('User', foreign_keys=[requester_id])
    approver = db.relationship('User', foreign_keys=[approver_id])
    department = db.relationship('Department')


# ============================================================
# 법규 등록부 테이블 (Legal Register - ISO 14001/45001)
# ============================================================
class LegalRegister(db.Model):
    __tablename__ = 'legal_register'
    id = db.Column(db.Integer, primary_key=True)
    reg_number = db.Column(db.String(30))              # 등록번호 (자동채번)
    law_name = db.Column(db.String(200), nullable=False)  # 법규명
    law_type = db.Column(db.String(50))                # 법률/시행령/고시/기준
    iso_standard = db.Column(db.String(50))            # ISO14001/ISO45001/통합
    applicable_clause = db.Column(db.String(100))      # 해당 조항 (예: 제14조 제2항)
    applicable_dept = db.Column(db.String(200))        # 적용 부서
    compliance_status = db.Column(db.String(20), default='compliant')
    # compliant: 준수 / non_compliant: 미준수 / partial: 부분준수 / na: 해당없음
    compliance_note = db.Column(db.Text)               # 준수 방법 및 비고
    last_review_date = db.Column(db.Date)              # 최종 검토일
    next_review_date = db.Column(db.Date)              # 차기 검토일
    enacted_date = db.Column(db.Date)                  # 제·개정일
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    department = db.relationship('Department')
    created_by = db.relationship('User')
    clauses = db.relationship('LegalClause', backref='legal',
                              lazy='dynamic', cascade='all, delete-orphan')


# ============================================================
# 법령 조항별 상세 (Legal Clause) — 몇조 몇항 + 실제 법 내용
# ============================================================
class LegalClause(db.Model):
    __tablename__ = 'legal_clauses'
    id = db.Column(db.Integer, primary_key=True)
    legal_id = db.Column(db.Integer, db.ForeignKey('legal_register.id'), nullable=False)
    article = db.Column(db.String(40))           # 조 (예: 제125조)
    paragraph = db.Column(db.String(40))         # 항/호 (예: 제1항)
    clause_title = db.Column(db.String(200))     # 조항 제목 (예: 작업환경측정)
    content = db.Column(db.Text)                 # 실제 법령 내용(조문)
    our_obligation = db.Column(db.Text)          # 당사 적용 의무·조치사항
    reference_url = db.Column(db.String(500))    # 법령 원문 링크(국가법령정보센터)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ============================================================
# 경영검토 테이블 (Management Review - ISO 9001/14001/45001 clause 9.3)
# ============================================================
class ManagementReview(db.Model):
    __tablename__ = 'management_reviews'
    id = db.Column(db.Integer, primary_key=True)
    review_number = db.Column(db.String(30))              # MR-YYYY-NN
    title = db.Column(db.String(200), nullable=False)     # 예: 2025년 상반기 경영검토
    period_start = db.Column(db.Date, nullable=False)     # 검토 대상 기간 시작
    period_end = db.Column(db.Date, nullable=False)       # 검토 대상 기간 종료
    review_date = db.Column(db.Date, nullable=False)      # 경영검토 개최일
    next_review_date = db.Column(db.Date)                 # 차기 검토 예정일
    venue = db.Column(db.String(100))                     # 장소
    chairman_id = db.Column(db.Integer, db.ForeignKey('users.id'))  # 의장(대표이사)
    status = db.Column(db.String(20), default='draft')
    # draft: 작성중 / in_review: 검토중 / approved: 승인완료

    # ── 인풋 항목 (Input) ──
    agenda_prev_actions = db.Column(db.Text)   # 전기 경영검토 후속조치 이행 현황
    agenda_policy = db.Column(db.Text)         # 경영방침 및 목표 달성 현황
    agenda_audit = db.Column(db.Text)          # 내부심사 결과 및 시사점
    agenda_capa = db.Column(db.Text)           # 시정조치(CAPA) 현황
    agenda_customer = db.Column(db.Text)       # 고객 피드백 및 클레임 현황
    agenda_process = db.Column(db.Text)        # 프로세스 성과 및 제품/서비스 적합성
    agenda_supplier = db.Column(db.Text)       # 외부공급자 및 협력업체 성과
    agenda_legal = db.Column(db.Text)          # 법규 및 규제 준수 현황
    agenda_risk = db.Column(db.Text)           # 리스크 및 기회 현황
    agenda_resources = db.Column(db.Text)      # 자원 충족성 평가
    agenda_hse = db.Column(db.Text)            # 환경·안전 성과 (HSE)

    # ── 아웃풋 항목 (Output) ──
    output_improvements = db.Column(db.Text)   # 개선 기회 및 결정사항
    output_changes = db.Column(db.Text)        # 경영시스템 변경 필요사항
    output_resources = db.Column(db.Text)      # 자원 필요사항

    # ── 전체 회의록 ──
    minutes = db.Column(db.Text)               # 종합 회의록

    # ── 승인 ──
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)
    approval_comment = db.Column(db.Text)

    # ── 집계 스냅샷 (생성 시점의 수치 보존, JSON 문자열) ──
    snapshot_json = db.Column(db.Text)

    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    chairman = db.relationship('User', foreign_keys=[chairman_id])
    approved_by = db.relationship('User', foreign_keys=[approved_by_id])
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    actions = db.relationship('ManagementReviewAction', backref='review',
                              lazy='dynamic', cascade='all, delete-orphan')


class ManagementReviewAction(db.Model):
    __tablename__ = 'mr_actions'
    id = db.Column(db.Integer, primary_key=True)
    review_id = db.Column(db.Integer, db.ForeignKey('management_reviews.id'), nullable=False)
    category = db.Column(db.String(30))        # 개선/변경/자원/HSE/기타
    action_item = db.Column(db.Text, nullable=False)  # 실행항목
    responsible_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    due_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='pending')
    # pending: 대기 / in_progress: 진행중 / completed: 완료 / overdue: 기한초과
    result = db.Column(db.Text)                # 완료 결과/비고
    capa_id = db.Column(db.Integer, db.ForeignKey('capa.id'))  # 연계 CAPA
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)

    responsible = db.relationship('User', foreign_keys=[responsible_id])
    capa = db.relationship('CAPA', foreign_keys=[capa_id])


# ============================================================
# 삼성 RBA EHS 41대 항목 마스터 (RBA Checklist Item)
# ============================================================
class RBAItem(db.Model):
    __tablename__ = 'rba_items'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)  # BH101
    category_code = db.Column(db.String(10))     # BH1
    category_name = db.Column(db.String(60))     # 산업안전보건
    domain = db.Column(db.String(20))            # 안전보건 / 환경
    section = db.Column(db.String(20))           # 운영 / 경영시스템
    name = db.Column(db.String(200))             # 항목명
    score = db.Column(db.Integer, default=1)     # 배점
    evidence_hint = db.Column(db.String(120))    # 권장 증빙 모듈
    sort_order = db.Column(db.Integer, default=0)


# ============================================================
# RBA 자가진단 회차 (RBA Assessment Round)
# ============================================================
class RBAAssessment(db.Model):
    __tablename__ = 'rba_assessments'
    id = db.Column(db.Integer, primary_key=True)
    assessment_number = db.Column(db.String(30))         # RBA-YYYY-NN
    title = db.Column(db.String(200), nullable=False)    # 2026년 삼성 RBA 자가진단
    customer = db.Column(db.String(100), default='삼성전자')
    assess_date = db.Column(db.Date, nullable=False)     # 진단일
    assessor_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    status = db.Column(db.String(20), default='draft')   # draft / completed
    # 산정 결과 (저장)
    total_score = db.Column(db.Integer, default=0)       # 획득 배점
    applicable_score = db.Column(db.Integer, default=0)  # 적용 배점(NA 제외)
    conformance_rate = db.Column(db.Float, default=0)    # 준수율 %
    priority_count = db.Column(db.Integer, default=0)
    major_count = db.Column(db.Integer, default=0)
    minor_count = db.Column(db.Integer, default=0)
    note = db.Column(db.Text)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    assessor = db.relationship('User', foreign_keys=[assessor_id])
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    results = db.relationship('RBAResult', backref='assessment',
                              lazy='dynamic', cascade='all, delete-orphan')


# ============================================================
# RBA 항목별 평가 결과 (회차 × 항목)
# ============================================================
class RBAResult(db.Model):
    __tablename__ = 'rba_results'
    id = db.Column(db.Integer, primary_key=True)
    assessment_id = db.Column(db.Integer, db.ForeignKey('rba_assessments.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('rba_items.id'), nullable=False)
    result = db.Column(db.String(20), default='pending')
    # pending: 미평가 / conformance: 충족 / minor: 경미 / major: 중대 / priority: 최우선 / na: 해당없음
    evidence_note = db.Column(db.Text)            # 증빙 설명(어떤 기록으로 충족하는지)
    finding = db.Column(db.Text)                  # 위반/관찰 내용
    action = db.Column(db.Text)                   # 개선 조치
    responsible_dept_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    capa_id = db.Column(db.Integer, db.ForeignKey('capa.id'))
    reviewed_date = db.Column(db.Date)

    item = db.relationship('RBAItem')
    responsible_dept = db.relationship('Department')
    capa = db.relationship('CAPA')


# ============================================================
# 근로자 고충·불만 처리 (Worker Grievance) — RBA BM302/CM302
#   ※ 익명 제기 가능, 비밀유지(접근 제한) 대상
# ============================================================
class Grievance(db.Model):
    __tablename__ = 'grievances'
    id = db.Column(db.Integer, primary_key=True)
    grievance_number = db.Column(db.String(30))          # GRV-YYYY-NNNN
    receipt_date = db.Column(db.Date, nullable=False)    # 접수일
    category = db.Column(db.String(30))                  # 임금/근로시간/직장내괴롭힘/성희롱/안전보건/복리후생/인사/기타
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)         # 고충 내용

    # 제기자 (익명 가능)
    is_anonymous = db.Column(db.Boolean, default=False)
    reporter_id = db.Column(db.Integer, db.ForeignKey('users.id'))  # 익명이면 NULL
    reporter_name = db.Column(db.String(50))             # 비로그인/직접입력 시
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    contact_info = db.Column(db.String(120))             # 회신 받을 연락처(선택)

    severity = db.Column(db.String(10), default='normal')  # high/normal/low
    status = db.Column(db.String(20), default='open')
    # open: 접수 / investigating: 조사중 / resolved: 처리완료 / closed: 종결

    handler_id = db.Column(db.Integer, db.ForeignKey('users.id'))  # 처리 담당자
    due_date = db.Column(db.Date)                        # 처리 기한
    investigation = db.Column(db.Text)                   # 조사/확인 내용
    action_taken = db.Column(db.Text)                    # 조치 내용
    result = db.Column(db.Text)                          # 처리 결과(제기자 회신)
    resolved_date = db.Column(db.Date)
    satisfaction = db.Column(db.Integer)                 # 처리 만족도 1~5 (선택)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    reporter = db.relationship('User', foreign_keys=[reporter_id])
    handler = db.relationship('User', foreign_keys=[handler_id])
    department = db.relationship('Department')


# ============================================================
# 법정점검 항목 마스터 (Legal Inspection Type) — 주기 관리자 변경 가능
# ============================================================
class InspectionType(db.Model):
    __tablename__ = 'inspection_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)      # 소방 작동점검
    category = db.Column(db.String(30))                   # 소방/안전보건/환경/전기·가스/기타
    legal_basis = db.Column(db.String(200))               # 근거 법령
    cycle_months = db.Column(db.Integer, default=12)      # 점검 주기(개월) — 관리자 변경 가능
    lead_alert_days = db.Column(db.Integer, default=30)   # 도래 알림 시작일(D-N)
    default_dept_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    responsible_org = db.Column(db.String(120))           # 점검기관/담당
    # 현재 일정 상태 (최신 기록 기준 자동 갱신)
    last_performed_date = db.Column(db.Date)
    next_due_date = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=True)
    note = db.Column(db.Text)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    default_dept = db.relationship('Department')
    records = db.relationship('InspectionRecord', backref='inspection_type',
                              lazy='dynamic', cascade='all, delete-orphan')


# ============================================================
# 법정점검 실시 기록 (Legal Inspection Record)
# ============================================================
class InspectionRecord(db.Model):
    __tablename__ = 'inspection_records'
    id = db.Column(db.Integer, primary_key=True)
    inspection_type_id = db.Column(db.Integer, db.ForeignKey('inspection_types.id'), nullable=False)
    performed_date = db.Column(db.Date, nullable=False)   # 실시일
    next_due_date = db.Column(db.Date)                    # 차기 예정일(자동계산, 수정가능)
    result = db.Column(db.String(20), default='적합')      # 적합/부적합/조건부
    performer = db.Column(db.String(120))                 # 점검자/점검기관
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    finding = db.Column(db.Text)                          # 지적/특이사항
    action = db.Column(db.Text)                           # 조치 내용
    file_path = db.Column(db.String(500))
    file_name = db.Column(db.String(200))
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    department = db.relationship('Department')
    created_by = db.relationship('User')


# ============================================================
# 필수회의 마스터 (Meeting Type) — ISO 절차서 기준 필수 개최 회의
# ============================================================
class MeetingType(db.Model):
    __tablename__ = 'meeting_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)      # 회의명
    basis = db.Column(db.String(200))                     # 근거 절차서(조항)
    cycle = db.Column(db.String(100))                     # 개최 주기/시기
    host = db.Column(db.String(120))                      # 주관
    attendees_target = db.Column(db.String(200))          # 참석 대상
    agenda_note = db.Column(db.Text)                      # 주요 안건/비고
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    records = db.relationship('MeetingRecord', backref='meeting_type', lazy='dynamic')


# ============================================================
# 회의록 (Meeting Record)
# ============================================================
class MeetingRecord(db.Model):
    __tablename__ = 'meeting_records'
    id = db.Column(db.Integer, primary_key=True)
    record_number = db.Column(db.String(30))              # MTG-YYYY-NNN
    meeting_type_id = db.Column(db.Integer, db.ForeignKey('meeting_types.id'))  # 없으면 수시/기타
    title = db.Column(db.String(200))                     # 회의 제목
    meeting_date = db.Column(db.Date)                     # 개최 일자
    location = db.Column(db.String(120))                  # 장소
    chair = db.Column(db.String(120))                     # 주재자
    attendees = db.Column(db.Text)                        # 참석자
    agenda = db.Column(db.Text)                           # 안건
    discussion = db.Column(db.Text)                       # 논의 및 결정사항
    action_items = db.Column(db.Text)                     # 조치사항
    next_date = db.Column(db.Date)                        # 차기 예정일
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    created_by = db.relationship('User')
    attachments = db.relationship('MeetingRecordAttachment', backref='record',
                                  lazy='dynamic', cascade='all, delete-orphan')


class MeetingRecordAttachment(db.Model):
    """회의록 첨부 (회의자료·사진, 여러 개)"""
    __tablename__ = 'meeting_record_attachments'
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey('meeting_records.id'), nullable=False)
    file_path = db.Column(db.String(500))
    file_name = db.Column(db.String(200))
    is_image = db.Column(db.Boolean, default=False)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)


# ============================================================
# 감사 추적 로그 테이블 (Audit Trail)
# ============================================================
class AuditTrail(db.Model):
    __tablename__ = 'audit_trail'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    action = db.Column(db.String(50))           # 조회/등록/수정/삭제/다운로드/결재
    target_type = db.Column(db.String(50))      # 대상 유형 (document, record 등)
    target_id = db.Column(db.Integer)           # 대상 ID
    target_name = db.Column(db.String(200))     # 대상명 (로그 가독성용)
    detail = db.Column(db.Text)                 # 상세 내용
    ip_address = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User')
