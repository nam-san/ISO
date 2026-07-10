from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, AuditTrail
from datetime import datetime

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        employee_id = request.form.get('employee_id', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(employee_id=employee_id, is_active=True).first()

        if user and user.check_password(password):
            login_user(user, remember=True)
            user.last_login = datetime.utcnow()
            
            # 감사 로그 기록
            log = AuditTrail(
                user_id=user.id,
                action='로그인',
                target_type='auth',
                target_name=f'{user.name}({user.employee_id})',
                ip_address=request.remote_addr
            )
            db.session.add(log)
            db.session.commit()

            next_page = request.args.get('next')
            flash(f'안녕하세요, {user.name}님! 환영합니다.', 'success')
            return redirect(next_page or url_for('dashboard.index'))
        else:
            flash('사번 또는 비밀번호가 올바르지 않습니다.', 'danger')

    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    log = AuditTrail(
        user_id=current_user.id,
        action='로그아웃',
        target_type='auth',
        target_name=f'{current_user.name}({current_user.employee_id})',
        ip_address=request.remote_addr
    )
    db.session.add(log)
    db.session.commit()
    logout_user()
    flash('로그아웃 되었습니다.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_pw = request.form.get('current_password')
        new_pw = request.form.get('new_password')
        confirm_pw = request.form.get('confirm_password')

        if not current_user.check_password(current_pw):
            flash('현재 비밀번호가 올바르지 않습니다.', 'danger')
        elif new_pw != confirm_pw:
            flash('새 비밀번호가 일치하지 않습니다.', 'danger')
        elif len(new_pw) < 8:
            flash('비밀번호는 8자 이상이어야 합니다.', 'danger')
        else:
            current_user.set_password(new_pw)
            db.session.commit()
            flash('비밀번호가 변경되었습니다.', 'success')
            return redirect(url_for('dashboard.index'))

    return render_template('change_password.html')
