# Flask CLI 전용 설정 (flask db ... 명령에만 적용됨)
# 일반 실행(run.bat / python app.py)에는 영향 없음
FLASK_APP=app.py
# 마이그레이션 CLI 실행 중에는 앱 기동용 자동 부트스트랩(시드)을 건너뜀
IMS_SKIP_DB_BOOTSTRAP=1
