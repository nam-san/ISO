from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate
from models import db, User
from config import Config
import os

login_manager = LoginManager()
csrf = CSRFProtect()
# DB 스키마 버전 관리 (Flask-Migrate/Alembic)
# render_as_batch=True → SQLite에서도 컬럼 변경/삭제가 안전하게 동작
migrate = Migrate()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # 확장 초기화
    db.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = '로그인이 필요한 페이지입니다.'
    login_manager.login_message_category = 'warning'

    # 업로드 폴더 및 DB(instance) 폴더 생성 (신규 서버 배포 시 폴더가 없어 발생하는 오류 방지)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance'), exist_ok=True)

    # 블루프린트 등록
    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.documents import documents_bp
    from routes.records import records_bp
    from routes.audit import audit_bp
    from routes.hse import hse_bp
    from routes.admin import admin_bp
    from routes.training import training_bp
    from routes.complaint import complaint_bp
    from routes.design import design_bp
    from routes.review import review_bp
    from routes.rba import rba_bp
    from routes.inspection import inspection_bp
    from routes.grievance import grievance_bp
    from routes.org import org_bp
    from routes.improvement import improvement_bp
    from routes.meeting import meeting_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(documents_bp, url_prefix='/documents')
    app.register_blueprint(records_bp, url_prefix='/records')
    app.register_blueprint(audit_bp, url_prefix='/audit')
    app.register_blueprint(hse_bp, url_prefix='/hse')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(training_bp, url_prefix='/training')
    app.register_blueprint(complaint_bp, url_prefix='/complaint')
    app.register_blueprint(design_bp, url_prefix='/design')
    app.register_blueprint(review_bp, url_prefix='/review')
    app.register_blueprint(rba_bp, url_prefix='/rba')
    app.register_blueprint(inspection_bp, url_prefix='/inspection')
    app.register_blueprint(grievance_bp, url_prefix='/grievance')
    app.register_blueprint(org_bp, url_prefix='/org')
    app.register_blueprint(improvement_bp, url_prefix='/hse/improvement')
    app.register_blueprint(meeting_bp, url_prefix='/meeting')

    # 전역 템플릿 변수 주입
    @app.context_processor
    def inject_globals():
        from models import Department
        return dict(all_departments=Department.query.filter_by(is_active=True).order_by(Department.id).all())

    # DB 스키마·초기데이터 부트스트랩
    # (flask db 마이그레이션 CLI 실행 시엔 IMS_SKIP_DB_BOOTSTRAP=1 로 이 단계를 건너뜀)
    with app.app_context():
        if not os.environ.get('IMS_SKIP_DB_BOOTSTRAP'):
            _bootstrap_database()

    return app


def _bootstrap_database():
    """앱 기동 시 스키마를 최신 마이그레이션까지 자동 적용하고, 초기·기준 데이터를 시드한다.
    - 신규 설치: 마이그레이션이 전체 테이블을 생성
    - 기존 DB: 새로 추가된 마이그레이션(스키마 변경분)만 적용
    - 최신 상태: 아무 작업도 하지 않음(무동작)
    """
    from flask_migrate import upgrade
    migrations_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'migrations')
    if os.path.isdir(migrations_dir):
        upgrade()          # 대기 중인 마이그레이션 자동 적용
    else:
        db.create_all()    # (예외) 마이그레이션 폴더가 없을 때만 직접 생성
    _init_data()
    from routes.rba import seed_rba_items
    seed_rba_items()
    from routes.inspection import seed_inspection_types
    seed_inspection_types()
    from routes.checklist_data import seed_checklist_templates
    seed_checklist_templates()
    from routes.training import seed_training_plans
    seed_training_plans()
    from routes.org import seed_org_charts
    seed_org_charts()
    from routes.meeting import seed_meeting_types
    seed_meeting_types()


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def _init_data():
    """초기 데이터 삽입 (최초 1회 실행)"""
    from models import Department, User
    from datetime import date

    # 부서 초기 데이터
    if Department.query.count() == 0:
        departments = [
            Department(code='IMS',  name='품질팀', location='서울본사'),
            Department(code='RD',   name='연구소',           location='서울본사'),
            Department(code='MFG',  name='제조팀',           location='나주지점'),
            Department(code='BIZ',  name='사업부',           location='서울본사'),
            Department(code='PUR',  name='구매',             location='서울본사'),
            Department(code='MGT',  name='경영지원팀',        location='서울본사'),
            Department(code='CEO',  name='경영진',           location='서울본사'),
        ]
        db.session.add_all(departments)
        db.session.commit()

    # 관리자 계정 초기 생성
    if User.query.count() == 0:
        ims_dept = Department.query.filter_by(code='IMS').first()
        admin = User(
            employee_id='admin',
            name='시스템관리자',
            email='admin@nurivoice.com',
            department_id=ims_dept.id if ims_dept else None,
            position='IMS 사무국장',
            role='admin',
        )
        admin.set_password('nurivoice2024!')
        db.session.add(admin)
        db.session.commit()
        print("[성공] 관리자 계정 생성: ID=admin, PW=nurivoice2024!")


# 앱 실행
app = create_app()

if __name__ == '__main__':
    import socket
    port = int(os.environ.get('PORT', 5000))
    # 내부 네트워크 IP 자동 감지
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = '127.0.0.1'
    print("=" * 60)
    print("  주식회사 누리보이스 ISO 통합경영시스템 (IMS)")
    print(f"  로컬 접속 : http://localhost:{port}")
    print(f"  외부 접속 : http://{local_ip}:{port}")
    print("  초기 관리자: ID=admin / PW=nurivoice2024!")
    print("  종료: Ctrl+C")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=port)
