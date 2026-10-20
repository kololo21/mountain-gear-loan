"""
山岳部 備品貸出管理 Webアプリケーション本体.

データモデリング 最終課題.
第3課題で作成したデータベース(members / equipment / trips / loans + 2ビュー)を
利用する Python + Flask + SQLite3 のWebアプリケーションでORマッパーは使用せず、
すべて sqlite3 モジュールと SQL 文で操作する。

サンプルアプリ(https://github.com/trueroad/dm_app)の get_db / close_connection を
流用し、それ以外は本アプリ向けに作成した。
"""

from typing import Optional

from flask import (Flask, g, redirect, render_template, request, url_for)
import sqlite3

app = Flask(__name__)

# 使用するデータベースファイル(app.py と同じディレクトリに置く)
DATABASE = 'database.db'


# データベース接続(サンプルアプリより流用)
def get_db() -> sqlite3.Connection:
    """
    データベース接続を得る.

    Flask の g にデータベース接続が保存されていたらその接続を返す。
    そうでなければ接続して g に保存しつつ返す。
    外部キー制約を有効化し、カラム名でアクセスできるように設定する。

    Returns:
        sqlite3.Connection: データベース接続
    """
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.execute('PRAGMA foreign_keys = ON')  # 外部キー制約を有効化
        db.row_factory = sqlite3.Row            # カラム名でアクセスできるよう設定
    return db


@app.teardown_appcontext
def close_connection(exception: Optional[BaseException]) -> None:
    """リクエスト終了時に Flask が自動的に呼び、DB接続を閉じる(サンプルより流用)."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


# バリデーション用のヘルパ関数
# フォームのプルダウンで選ばせる選択肢(自由入力させず不正値を防ぐ)
CATEGORIES = ['テント', '炊事具', '登攀具', '安全具', 'ナビ']
CONDITIONS = ['良好', '要修理', '廃棄']
STYLES = ['日帰り', '合宿', '縦走']
ROLES = ['部長', '装備係', '会計', '一般']


def is_valid_date(s: str) -> bool:
    """空文字、または YYYY-MM-DD(ISO 8601)形式のときに True を返す."""
    if s == '':
        return True
    import datetime
    try:
        datetime.date.fromisoformat(s)
        return True
    except ValueError:
        return False


def to_int_or_none(s: str) -> Optional[int]:
    """空文字なら None、整数に変換できれば int、できなければ ValueError."""
    if s is None or s.strip() == '':
        return None
    return int(s)


# 入口のページ
@app.route('/')
def index() -> str:
    """入口のページ. 各機能へのリンクを持つ index.html を返す."""
    return render_template('index.html')


# 備品 equipment (一覧・詳細・追加・編集・削除)
@app.route('/equipment')
def equipment_list() -> str:
    """備品一覧(全件). SELECT 文で全備品を取得して一覧表示する."""
    cur = get_db().cursor()
    e_list = cur.execute(
        'SELECT equip_id, equip_name, category, maker_name, condition '
        'FROM equipment ORDER BY equip_id').fetchall()
    return render_template('equipment_list.html', e_list=e_list,
                           categories=CATEGORIES, keyword='', category='')


@app.route('/equipment', methods=['POST'])
def equipment_list_filtered() -> str:
    """
    備品一覧(絞り込み).

    フォームの keyword(名前 LIKE 検索)と category(カテゴリ完全一致)で絞り込む。
    可変値はすべてパラメータ化(?)して SQL インジェクションを防ぐ。
    """
    keyword = request.form.get('keyword', '')
    category = request.form.get('category', '')

    # 入力に応じて WHERE 条件を組み立てる(カラム名は固定、値のみパラメータ化)
    conditions = []
    params = []
    if keyword != '':
        conditions.append('equip_name LIKE ?')
        params.append('%' + keyword + '%')
    if category != '':
        conditions.append('category = ?')
        params.append(category)
    where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''

    cur = get_db().cursor()
    e_list = cur.execute(
        'SELECT equip_id, equip_name, category, maker_name, condition '
        'FROM equipment ' + where + ' ORDER BY equip_id', params).fetchall()
    return render_template('equipment_list.html', e_list=e_list,
                           categories=CATEGORIES, keyword=keyword,
                           category=category)


@app.route('/equipment/<id>')
def equipment_detail(id: str) -> str:
    """
    備品詳細. 指定備品の情報と、その備品の貸出履歴(複数表JOIN)を表示する.
    """
    cur = get_db().cursor()
    try:
        id_num = int(id)
    except ValueError:
        return render_template('not-found.html', target='備品')

    equip = cur.execute('SELECT * FROM equipment WHERE equip_id = ?',
                        (id_num,)).fetchone()
    if equip is None:
        return render_template('not-found.html', target='備品')

    # その備品の貸出履歴(loans に trips と members を JOIN)
    history = cur.execute(
        'SELECT t.trip_name, m.name AS member_name, '
        '       l.lent_on, l.due_on, l.returned_on '
        'FROM loans l '
        'JOIN trips   t ON l.trip_id   = t.trip_id '
        'JOIN members m ON l.member_id = m.member_id '
        'WHERE l.equip_id = ? ORDER BY l.lent_on DESC', (id_num,)).fetchall()
    return render_template('equipment_detail.html', equip=equip,
                           history=history)


@app.route('/equipment-add')
def equipment_add() -> str:
    """備品追加フォームを表示."""
    return render_template('equipment_add.html', categories=CATEGORIES,
                           conditions=CONDITIONS, form={}, errors=[])


@app.route('/equipment-add', methods=['POST'])
def equipment_add_execute() -> str:
    """
    備品追加を実行. バリデーション→INSERT→コミット→PRGでリダイレクト.
    """
    form = {
        'equip_name': request.form.get('equip_name', '').strip(),
        'category': request.form.get('category', ''),
        'maker_name': request.form.get('maker_name', '').strip(),
        'purchased_on': request.form.get('purchased_on', '').strip(),
        'condition': request.form.get('condition', ''),
    }
    errors = []
    if form['equip_name'] == '':
        errors.append('備品名は必須です。')
    if form['category'] not in CATEGORIES + ['']:
        errors.append('カテゴリの値が不正です。')
    if form['condition'] not in CONDITIONS + ['']:
        errors.append('状態の値が不正です。')
    if not is_valid_date(form['purchased_on']):
        errors.append('購入日は YYYY-MM-DD 形式で入力してください。')

    if errors:
        # 入力し直しのため、入力値とエラーを付けてフォームを再表示
        return render_template('equipment_add.html', categories=CATEGORIES,
                               conditions=CONDITIONS, form=form, errors=errors)

    con = get_db()
    try:
        con.execute(
            'INSERT INTO equipment '
            '(equip_name, category, maker_name, purchased_on, condition) '
            'VALUES (?, ?, ?, ?, ?)',
            (form['equip_name'], form['category'] or None,
             form['maker_name'] or None, form['purchased_on'] or None,
             form['condition'] or None))
        con.commit()
    except sqlite3.Error:
        con.rollback()
        return redirect(url_for('equipment_add_results', code='error'))
    return redirect(url_for('equipment_add_results', code='ok'))


@app.route('/equipment-add-results/<code>')
def equipment_add_results(code: str) -> str:
    """備品追加結果を表示(PRGパターンの GET 側)."""
    return render_template('equipment_add_results.html', code=code)


@app.route('/equipment-edit/<id>')
def equipment_edit(id: str) -> str:
    """備品編集フォームを表示(現在値を初期表示)."""
    cur = get_db().cursor()
    try:
        id_num = int(id)
    except ValueError:
        return render_template('not-found.html', target='備品')
    equip = cur.execute('SELECT * FROM equipment WHERE equip_id = ?',
                        (id_num,)).fetchone()
    if equip is None:
        return render_template('not-found.html', target='備品')
    return render_template('equipment_edit.html', equip=equip,
                           categories=CATEGORIES, conditions=CONDITIONS,
                           errors=[])


@app.route('/equipment-edit/<id>', methods=['POST'])
def equipment_edit_update(id: str) -> str:
    """備品編集を実行. バリデーション→UPDATE→コミット→PRG."""
    cur = get_db().cursor()
    try:
        id_num = int(id)
    except ValueError:
        return render_template('not-found.html', target='備品')

    equip = cur.execute('SELECT * FROM equipment WHERE equip_id = ?',
                        (id_num,)).fetchone()
    if equip is None:
        return render_template('not-found.html', target='備品')

    form = {
        'equip_id': id_num,
        'equip_name': request.form.get('equip_name', '').strip(),
        'category': request.form.get('category', ''),
        'maker_name': request.form.get('maker_name', '').strip(),
        'purchased_on': request.form.get('purchased_on', '').strip(),
        'condition': request.form.get('condition', ''),
    }
    errors = []
    if form['equip_name'] == '':
        errors.append('備品名は必須です。')
    if not is_valid_date(form['purchased_on']):
        errors.append('購入日は YYYY-MM-DD 形式で入力してください。')
    if errors:
        return render_template('equipment_edit.html', equip=form,
                               categories=CATEGORIES, conditions=CONDITIONS,
                               errors=errors)

    con = get_db()
    try:
        con.execute(
            'UPDATE equipment SET equip_name=?, category=?, maker_name=?, '
            'purchased_on=?, condition=? WHERE equip_id=?',
            (form['equip_name'], form['category'] or None,
             form['maker_name'] or None, form['purchased_on'] or None,
             form['condition'] or None, id_num))
        con.commit()
    except sqlite3.Error:
        con.rollback()
        return redirect(url_for('equipment_edit_results', code='error'))
    return redirect(url_for('equipment_edit_results', code='ok'))


@app.route('/equipment-edit-results/<code>')
def equipment_edit_results(code: str) -> str:
    """備品編集結果を表示."""
    return render_template('equipment_edit_results.html', code=code)


@app.route('/equipment-del/<id>')
def equipment_del(id: str) -> str:
    """備品削除確認フォームを表示."""
    cur = get_db().cursor()
    try:
        id_num = int(id)
    except ValueError:
        return render_template('not-found.html', target='備品')
    equip = cur.execute('SELECT * FROM equipment WHERE equip_id = ?',
                        (id_num,)).fetchone()
    if equip is None:
        return render_template('not-found.html', target='備品')
    return render_template('equipment_del.html', equip=equip)


@app.route('/equipment-del/<id>', methods=['POST'])
def equipment_del_execute(id: str) -> str:
    """
    備品削除を実行. DELETE→コミット→PRG.
    貸出(loans)から参照されている場合は外部キー制約で失敗するので、
    例外を捕捉してロールバックし、失敗コードでリダイレクトする.
    """
    try:
        id_num = int(id)
    except ValueError:
        return render_template('not-found.html', target='備品')
    con = get_db()
    try:
        cur = con.execute('DELETE FROM equipment WHERE equip_id = ?',
                          (id_num,))
        if cur.rowcount == 0:
            con.rollback()
            return redirect(url_for('equipment_del_results', code='notfound'))
        con.commit()
    except sqlite3.IntegrityError:
        # 貸出履歴から参照されている(外部キー制約違反)
        con.rollback()
        return redirect(url_for('equipment_del_results', code='referenced'))
    except sqlite3.Error:
        con.rollback()
        return redirect(url_for('equipment_del_results', code='error'))
    return redirect(url_for('equipment_del_results', code='ok'))


@app.route('/equipment-del-results/<code>')
def equipment_del_results(code: str) -> str:
    """備品削除結果を表示."""
    return render_template('equipment_del_results.html', code=code)


# 部員 members (一覧・詳細・追加・編集・削除)
@app.route('/members')
def members_list() -> str:
    """部員一覧(全件)."""
    cur = get_db().cursor()
    m_list = cur.execute(
        'SELECT member_id, name, grade, role FROM members '
        'ORDER BY member_id').fetchall()
    return render_template('members_list.html', m_list=m_list, keyword='')


@app.route('/members', methods=['POST'])
def members_list_filtered() -> str:
    """部員一覧(氏名で絞り込み)."""
    keyword = request.form.get('keyword', '')
    cur = get_db().cursor()
    m_list = cur.execute(
        'SELECT member_id, name, grade, role FROM members '
        'WHERE name LIKE ? ORDER BY member_id',
        ('%' + keyword + '%',)).fetchall()
    return render_template('members_list.html', m_list=m_list, keyword=keyword)


@app.route('/members/<id>')
def members_detail(id: str) -> str:
    """部員詳細. 本人情報と、その部員が借りた貸出履歴(JOIN)を表示."""
    cur = get_db().cursor()
    try:
        id_num = int(id)
    except ValueError:
        return render_template('not-found.html', target='部員')
    member = cur.execute('SELECT * FROM members WHERE member_id = ?',
                        (id_num,)).fetchone()
    if member is None:
        return render_template('not-found.html', target='部員')
    history = cur.execute(
        'SELECT e.equip_name, t.trip_name, l.lent_on, l.returned_on '
        'FROM loans l '
        'JOIN equipment e ON l.equip_id = e.equip_id '
        'JOIN trips     t ON l.trip_id  = t.trip_id '
        'WHERE l.member_id = ? ORDER BY l.lent_on DESC', (id_num,)).fetchall()
    return render_template('members_detail.html', member=member,
                           history=history)


@app.route('/members-add')
def members_add() -> str:
    """部員追加フォーム."""
    return render_template('members_add.html', roles=ROLES, form={}, errors=[])


@app.route('/members-add', methods=['POST'])
def members_add_execute() -> str:
    """部員追加を実行."""
    form = {
        'name': request.form.get('name', '').strip(),
        'grade': request.form.get('grade', '').strip(),
        'role': request.form.get('role', ''),
        'phone': request.form.get('phone', '').strip(),
        'email': request.form.get('email', '').strip(),
    }
    errors = []
    if form['name'] == '':
        errors.append('氏名は必須です。')
    grade_val = None
    if form['grade'] != '':
        try:
            grade_val = int(form['grade'])
            if grade_val < 1 or grade_val > 4:
                errors.append('学年は 1〜4 で入力してください。')
        except ValueError:
            errors.append('学年は整数で入力してください。')
    if errors:
        return render_template('members_add.html', roles=ROLES, form=form,
                               errors=errors)

    con = get_db()
    try:
        con.execute(
            'INSERT INTO members (name, grade, role, phone, email) '
            'VALUES (?, ?, ?, ?, ?)',
            (form['name'], grade_val, form['role'] or None,
             form['phone'] or None, form['email'] or None))
        con.commit()
    except sqlite3.Error:
        con.rollback()
        return redirect(url_for('members_add_results', code='error'))
    return redirect(url_for('members_add_results', code='ok'))


@app.route('/members-add-results/<code>')
def members_add_results(code: str) -> str:
    return render_template('members_add_results.html', code=code)


@app.route('/members-edit/<id>')
def members_edit(id: str) -> str:
    """部員編集フォーム."""
    cur = get_db().cursor()
    try:
        id_num = int(id)
    except ValueError:
        return render_template('not-found.html', target='部員')
    member = cur.execute('SELECT * FROM members WHERE member_id = ?',
                        (id_num,)).fetchone()
    if member is None:
        return render_template('not-found.html', target='部員')
    return render_template('members_edit.html', member=member, roles=ROLES,
                           errors=[])


@app.route('/members-edit/<id>', methods=['POST'])
def members_edit_update(id: str) -> str:
    """部員編集を実行."""
    cur = get_db().cursor()
    try:
        id_num = int(id)
    except ValueError:
        return render_template('not-found.html', target='部員')
    member = cur.execute('SELECT * FROM members WHERE member_id = ?',
                        (id_num,)).fetchone()
    if member is None:
        return render_template('not-found.html', target='部員')

    form = {
        'member_id': id_num,
        'name': request.form.get('name', '').strip(),
        'grade': request.form.get('grade', '').strip(),
        'role': request.form.get('role', ''),
        'phone': request.form.get('phone', '').strip(),
        'email': request.form.get('email', '').strip(),
    }
    errors = []
    if form['name'] == '':
        errors.append('氏名は必須です。')
    grade_val = None
    if form['grade'] != '':
        try:
            grade_val = int(form['grade'])
            if grade_val < 1 or grade_val > 4:
                errors.append('学年は 1〜4 で入力してください。')
        except ValueError:
            errors.append('学年は整数で入力してください。')
    if errors:
        return render_template('members_edit.html', member=form, roles=ROLES,
                               errors=errors)

    con = get_db()
    try:
        con.execute(
            'UPDATE members SET name=?, grade=?, role=?, phone=?, email=? '
            'WHERE member_id=?',
            (form['name'], grade_val, form['role'] or None,
             form['phone'] or None, form['email'] or None, id_num))
        con.commit()
    except sqlite3.Error:
        con.rollback()
        return redirect(url_for('members_edit_results', code='error'))
    return redirect(url_for('members_edit_results', code='ok'))


@app.route('/members-edit-results/<code>')
def members_edit_results(code: str) -> str:
    return render_template('members_edit_results.html', code=code)


@app.route('/members-del/<id>')
def members_del(id: str) -> str:
    """部員削除確認."""
    cur = get_db().cursor()
    try:
        id_num = int(id)
    except ValueError:
        return render_template('not-found.html', target='部員')
    member = cur.execute('SELECT * FROM members WHERE member_id = ?',
                        (id_num,)).fetchone()
    if member is None:
        return render_template('not-found.html', target='部員')
    return render_template('members_del.html', member=member)


@app.route('/members-del/<id>', methods=['POST'])
def members_del_execute(id: str) -> str:
    """部員削除を実行(貸出参照時は外部キー制約で失敗)."""
    try:
        id_num = int(id)
    except ValueError:
        return render_template('not-found.html', target='部員')
    con = get_db()
    try:
        cur = con.execute('DELETE FROM members WHERE member_id = ?', (id_num,))
        if cur.rowcount == 0:
            con.rollback()
            return redirect(url_for('members_del_results', code='notfound'))
        con.commit()
    except sqlite3.IntegrityError:
        con.rollback()
        return redirect(url_for('members_del_results', code='referenced'))
    except sqlite3.Error:
        con.rollback()
        return redirect(url_for('members_del_results', code='error'))
    return redirect(url_for('members_del_results', code='ok'))


@app.route('/members-del-results/<code>')
def members_del_results(code: str) -> str:
    return render_template('members_del_results.html', code=code)


# 山行 trips (一覧・詳細・追加・編集・削除)
@app.route('/trips')
def trips_list() -> str:
    """山行一覧(全件)."""
    cur = get_db().cursor()
    t_list = cur.execute(
        'SELECT trip_id, trip_name, destination, depart_on, style '
        'FROM trips ORDER BY trip_id').fetchall()
    return render_template('trips_list.html', t_list=t_list, keyword='')


@app.route('/trips', methods=['POST'])
def trips_list_filtered() -> str:
    """山行一覧(山行名で絞り込み)."""
    keyword = request.form.get('keyword', '')
    cur = get_db().cursor()
    t_list = cur.execute(
        'SELECT trip_id, trip_name, destination, depart_on, style '
        'FROM trips WHERE trip_name LIKE ? ORDER BY trip_id',
        ('%' + keyword + '%',)).fetchall()
    return render_template('trips_list.html', t_list=t_list, keyword=keyword)


@app.route('/trips/<id>')
def trips_detail(id: str) -> str:
    """山行詳細. 山行情報と、その山行で貸し出された備品一覧(JOIN)を表示."""
    cur = get_db().cursor()
    try:
        id_num = int(id)
    except ValueError:
        return render_template('not-found.html', target='山行')
    trip = cur.execute('SELECT * FROM trips WHERE trip_id = ?',
                      (id_num,)).fetchone()
    if trip is None:
        return render_template('not-found.html', target='山行')
    loans = cur.execute(
        'SELECT e.equip_name, m.name AS member_name, l.returned_on '
        'FROM loans l '
        'JOIN equipment e ON l.equip_id  = e.equip_id '
        'JOIN members   m ON l.member_id = m.member_id '
        'WHERE l.trip_id = ? ORDER BY e.equip_name', (id_num,)).fetchall()
    return render_template('trips_detail.html', trip=trip, loans=loans)


@app.route('/trips-add')
def trips_add() -> str:
    """山行追加フォーム."""
    return render_template('trips_add.html', styles=STYLES, form={}, errors=[])


@app.route('/trips-add', methods=['POST'])
def trips_add_execute() -> str:
    """山行追加を実行."""
    form = _read_trip_form()
    errors = _validate_trip(form)
    if errors:
        return render_template('trips_add.html', styles=STYLES, form=form,
                               errors=errors)
    con = get_db()
    try:
        con.execute(
            'INSERT INTO trips '
            '(trip_name, destination, depart_on, return_on, style) '
            'VALUES (?, ?, ?, ?, ?)',
            (form['trip_name'], form['destination'] or None,
             form['depart_on'] or None, form['return_on'] or None,
             form['style'] or None))
        con.commit()
    except sqlite3.Error:
        con.rollback()
        return redirect(url_for('trips_add_results', code='error'))
    return redirect(url_for('trips_add_results', code='ok'))


@app.route('/trips-add-results/<code>')
def trips_add_results(code: str) -> str:
    return render_template('trips_add_results.html', code=code)


@app.route('/trips-edit/<id>')
def trips_edit(id: str) -> str:
    """山行編集フォーム."""
    cur = get_db().cursor()
    try:
        id_num = int(id)
    except ValueError:
        return render_template('not-found.html', target='山行')
    trip = cur.execute('SELECT * FROM trips WHERE trip_id = ?',
                      (id_num,)).fetchone()
    if trip is None:
        return render_template('not-found.html', target='山行')
    return render_template('trips_edit.html', trip=trip, styles=STYLES,
                           errors=[])


@app.route('/trips-edit/<id>', methods=['POST'])
def trips_edit_update(id: str) -> str:
    """山行編集を実行."""
    cur = get_db().cursor()
    try:
        id_num = int(id)
    except ValueError:
        return render_template('not-found.html', target='山行')
    trip = cur.execute('SELECT * FROM trips WHERE trip_id = ?',
                      (id_num,)).fetchone()
    if trip is None:
        return render_template('not-found.html', target='山行')
    form = _read_trip_form()
    form['trip_id'] = id_num
    errors = _validate_trip(form)
    if errors:
        return render_template('trips_edit.html', trip=form, styles=STYLES,
                               errors=errors)
    con = get_db()
    try:
        con.execute(
            'UPDATE trips SET trip_name=?, destination=?, depart_on=?, '
            'return_on=?, style=? WHERE trip_id=?',
            (form['trip_name'], form['destination'] or None,
             form['depart_on'] or None, form['return_on'] or None,
             form['style'] or None, id_num))
        con.commit()
    except sqlite3.Error:
        con.rollback()
        return redirect(url_for('trips_edit_results', code='error'))
    return redirect(url_for('trips_edit_results', code='ok'))


@app.route('/trips-edit-results/<code>')
def trips_edit_results(code: str) -> str:
    return render_template('trips_edit_results.html', code=code)


@app.route('/trips-del/<id>')
def trips_del(id: str) -> str:
    """山行削除確認."""
    cur = get_db().cursor()
    try:
        id_num = int(id)
    except ValueError:
        return render_template('not-found.html', target='山行')
    trip = cur.execute('SELECT * FROM trips WHERE trip_id = ?',
                      (id_num,)).fetchone()
    if trip is None:
        return render_template('not-found.html', target='山行')
    return render_template('trips_del.html', trip=trip)


@app.route('/trips-del/<id>', methods=['POST'])
def trips_del_execute(id: str) -> str:
    """山行削除を実行(貸出参照時は外部キー制約で失敗)."""
    try:
        id_num = int(id)
    except ValueError:
        return render_template('not-found.html', target='山行')
    con = get_db()
    try:
        cur = con.execute('DELETE FROM trips WHERE trip_id = ?', (id_num,))
        if cur.rowcount == 0:
            con.rollback()
            return redirect(url_for('trips_del_results', code='notfound'))
        con.commit()
    except sqlite3.IntegrityError:
        con.rollback()
        return redirect(url_for('trips_del_results', code='referenced'))
    except sqlite3.Error:
        con.rollback()
        return redirect(url_for('trips_del_results', code='error'))
    return redirect(url_for('trips_del_results', code='ok'))


@app.route('/trips-del-results/<code>')
def trips_del_results(code: str) -> str:
    return render_template('trips_del_results.html', code=code)


def _read_trip_form() -> dict:
    """山行フォームの入力値を読み取る."""
    return {
        'trip_name': request.form.get('trip_name', '').strip(),
        'destination': request.form.get('destination', '').strip(),
        'depart_on': request.form.get('depart_on', '').strip(),
        'return_on': request.form.get('return_on', '').strip(),
        'style': request.form.get('style', ''),
    }


def _validate_trip(form: dict) -> list:
    """山行フォームのバリデーション."""
    errors = []
    if form['trip_name'] == '':
        errors.append('山行名は必須です。')
    if not is_valid_date(form['depart_on']):
        errors.append('出発日は YYYY-MM-DD 形式で入力してください。')
    if not is_valid_date(form['return_on']):
        errors.append('帰着日は YYYY-MM-DD 形式で入力してください。')
    if (form['depart_on'] and form['return_on']
            and form['depart_on'] > form['return_on']):
        errors.append('帰着日は出発日以降にしてください。')
    return errors


# 貸出 loans (台帳・登録・返却)  ※ビューとトランザクションのショーケース
@app.route('/loans')
def loans() -> str:
    """貸出台帳(全件). ビュー v_loan_status を使用."""
    cur = get_db().cursor()
    l_list = cur.execute(
        'SELECT * FROM v_loan_status ORDER BY loan_id').fetchall()
    return render_template('loans.html', l_list=l_list, only_outstanding=False)


@app.route('/loans', methods=['POST'])
def loans_filtered() -> str:
    """
    貸出台帳(絞り込み). 未返却のみのときはビュー v_outstanding を使用.
    (第12回p.12: ビュー定義に条件を入れず、使う側で切り替える方針)
    """
    only = request.form.get('only_outstanding', '')
    cur = get_db().cursor()
    if only == 'on':
        l_list = cur.execute(
            'SELECT * FROM v_outstanding ORDER BY loan_id').fetchall()
    else:
        l_list = cur.execute(
            'SELECT * FROM v_loan_status ORDER BY loan_id').fetchall()
    return render_template('loans.html', l_list=l_list,
                           only_outstanding=(only == 'on'))


@app.route('/loan-add')
def loan_add() -> str:
    """貸出登録フォーム. プルダウン用に備品・部員・山行の一覧を渡す."""
    cur = get_db().cursor()
    equipments = cur.execute(
        'SELECT equip_id, equip_name, condition FROM equipment '
        'ORDER BY equip_id').fetchall()
    members = cur.execute(
        'SELECT member_id, name FROM members ORDER BY member_id').fetchall()
    trips = cur.execute(
        'SELECT trip_id, trip_name FROM trips ORDER BY trip_id').fetchall()
    return render_template('loan_add.html', equipments=equipments,
                           members=members, trips=trips, form={}, errors=[])


@app.route('/loan-add', methods=['POST'])
def loan_add_execute() -> str:
    """
    貸出登録を実行. 存在チェック・状態チェック・二重貸出チェックの後、
    トランザクションで INSERT してコミット(失敗時ロールバック).
    """
    con = get_db()
    cur = con.cursor()
    form = {
        'equip_id': request.form.get('equip_id', '').strip(),
        'member_id': request.form.get('member_id', '').strip(),
        'trip_id': request.form.get('trip_id', '').strip(),
        'lent_on': request.form.get('lent_on', '').strip(),
        'due_on': request.form.get('due_on', '').strip(),
    }
    errors = []

    # 数値変換とバリデーション
    try:
        equip_id = int(form['equip_id'])
    except ValueError:
        equip_id = None
        errors.append('備品を選択してください。')
    try:
        member_id = int(form['member_id'])
    except ValueError:
        member_id = None
        errors.append('部員を選択してください。')
    try:
        trip_id = int(form['trip_id'])
    except ValueError:
        trip_id = None
        errors.append('山行を選択してください。')
    if not is_valid_date(form['lent_on']):
        errors.append('貸出日は YYYY-MM-DD 形式で入力してください。')
    if not is_valid_date(form['due_on']):
        errors.append('返却期限は YYYY-MM-DD 形式で入力してください。')

    # 存在チェックと業務ルール(廃棄備品は貸せない/二重貸出禁止)
    if equip_id is not None:
        equip = cur.execute(
            'SELECT condition FROM equipment WHERE equip_id = ?',
            (equip_id,)).fetchone()
        if equip is None:
            errors.append('指定された備品が存在しません。')
        elif equip['condition'] == '廃棄':
            errors.append('廃棄された備品は貸し出せません。')
    if member_id is not None:
        if cur.execute('SELECT 1 FROM members WHERE member_id = ?',
                       (member_id,)).fetchone() is None:
            errors.append('指定された部員が存在しません。')
    if trip_id is not None:
        if cur.execute('SELECT 1 FROM trips WHERE trip_id = ?',
                       (trip_id,)).fetchone() is None:
            errors.append('指定された山行が存在しません。')
    if equip_id is not None and trip_id is not None:
        dup = cur.execute(
            'SELECT 1 FROM loans WHERE equip_id = ? AND trip_id = ?',
            (equip_id, trip_id)).fetchone()
        if dup is not None:
            errors.append('この備品はこの山行に既に貸し出されています。')

    if errors:
        equipments = cur.execute(
            'SELECT equip_id, equip_name, condition FROM equipment '
            'ORDER BY equip_id').fetchall()
        members = cur.execute(
            'SELECT member_id, name FROM members '
            'ORDER BY member_id').fetchall()
        trips = cur.execute(
            'SELECT trip_id, trip_name FROM trips ORDER BY trip_id').fetchall()
        return render_template('loan_add.html', equipments=equipments,
                               members=members, trips=trips, form=form,
                               errors=errors)

    # トランザクション: 挿入してコミット
    try:
        con.execute(
            'INSERT INTO loans '
            '(equip_id, member_id, trip_id, lent_on, due_on) '
            'VALUES (?, ?, ?, ?, ?)',
            (equip_id, member_id, trip_id,
             form['lent_on'] or None, form['due_on'] or None))
        con.commit()
    except sqlite3.Error:
        con.rollback()
        return redirect(url_for('loan_add_results', code='error'))
    return redirect(url_for('loan_add_results', code='ok'))


@app.route('/loan-add-results/<code>')
def loan_add_results(code: str) -> str:
    return render_template('loan_add_results.html', code=code)


@app.route('/loan-return/<id>')
def loan_return(id: str) -> str:
    """返却確認フォーム. 未返却の貸出のみ返却できる."""
    cur = get_db().cursor()
    try:
        id_num = int(id)
    except ValueError:
        return render_template('not-found.html', target='貸出')
    loan = cur.execute(
        'SELECT * FROM v_loan_status WHERE loan_id = ?', (id_num,)).fetchone()
    if loan is None:
        return render_template('not-found.html', target='貸出')
    return render_template('loan_return.html', loan=loan)


@app.route('/loan-return/<id>', methods=['POST'])
def loan_return_execute(id: str) -> str:
    """
    返却処理を実行. returned_on を更新するトランザクション.
    未返却(returned_on IS NULL)の行だけを対象にし、既に返却済みなら失敗扱い.
    """
    try:
        id_num = int(id)
    except ValueError:
        return render_template('not-found.html', target='貸出')
    returned_on = request.form.get('returned_on', '').strip()
    if not is_valid_date(returned_on) or returned_on == '':
        return redirect(url_for('loan_return_results', code='invaliddate'))

    con = get_db()
    try:
        cur = con.execute(
            'UPDATE loans SET returned_on = ? '
            'WHERE loan_id = ? AND returned_on IS NULL',
            (returned_on, id_num))
        if cur.rowcount == 0:
            # 存在しない or 既に返却済み
            con.rollback()
            return redirect(url_for('loan_return_results', code='already'))
        con.commit()
    except sqlite3.Error:
        con.rollback()
        return redirect(url_for('loan_return_results', code='error'))
    return redirect(url_for('loan_return_results', code='ok'))


@app.route('/loan-return-results/<code>')
def loan_return_results(code: str) -> str:
    return render_template('loan_return_results.html', code=code)


# ダッシュボード(集約関数のショーケース)
@app.route('/dashboard')
def dashboard() -> str:
    """統計画面. COUNT / GROUP BY など集約関数を使った各種集計を表示."""
    cur = get_db().cursor()
    total_equip = cur.execute('SELECT COUNT(*) AS n FROM equipment').fetchone()['n']
    total_member = cur.execute('SELECT COUNT(*) AS n FROM members').fetchone()['n']
    total_trip = cur.execute('SELECT COUNT(*) AS n FROM trips').fetchone()['n']
    outstanding = cur.execute(
        'SELECT COUNT(*) AS n FROM loans WHERE returned_on IS NULL'
    ).fetchone()['n']

    by_category = cur.execute(
        'SELECT category, COUNT(*) AS n FROM equipment '
        'GROUP BY category ORDER BY n DESC').fetchall()
    by_member = cur.execute(
        'SELECT m.name, COUNT(*) AS n '
        'FROM loans l JOIN members m ON l.member_id = m.member_id '
        'GROUP BY m.member_id ORDER BY n DESC, m.member_id').fetchall()

    return render_template('dashboard.html', total_equip=total_equip,
                           total_member=total_member, total_trip=total_trip,
                           outstanding=outstanding, by_category=by_category,
                           by_member=by_member)


if __name__ == '__main__':
    app.run(debug=True)
