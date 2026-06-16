"""
Venlo Sports Platform - Backend API
Flask + SQLite REST API 服务
运行: python app.py
端口: 5000
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import os
import hashlib
import secrets
import json
from datetime import datetime, date

app = Flask(__name__, static_folder='..', static_url_path='')
CORS(app)  # 允许跨域（前端开发用）

# ── 数据库路径 ──────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'venlo.db')

# 确保数据库文件在可写目录（避免沙箱权限问题）
_alt_db = os.path.join(os.path.expanduser('~'), '.workbuddy', 'venlo.db')

def _check_db_writable(path):
    """尝试在指定路径创建/打开数据库文件，验证可写性"""
    try:
        test_conn = sqlite3.connect(path)
        test_conn.execute("SELECT 1")
        test_conn.close()
        return True
    except (sqlite3.OperationalError, PermissionError, OSError):
        return False

if not _check_db_writable(DB_PATH):
    os.makedirs(os.path.dirname(_alt_db), exist_ok=True)
    DB_PATH = _alt_db

# ── 数据库工具 ──────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # 返回字典形式
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# ── 数据库初始化 ────────────────────────────────────────────
def init_db():
    """建表 + 写入示例数据"""
    conn = get_db()
    c = conn.cursor()

    # ---- 用户表 ----
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        username    TEXT UNIQUE NOT NULL,
        password    TEXT NOT NULL,
        role        TEXT NOT NULL CHECK(role IN ('student','teacher','parent','admin')),
        name        TEXT NOT NULL,
        school      TEXT,
        grade       TEXT,
        phone       TEXT,
        email       TEXT,
        avatar_url  TEXT,
        linked_student_id INTEGER REFERENCES users(id),
        created_at  TEXT DEFAULT (datetime('now','localtime'))
    )""")
    # 迁移：如缺少 linked_student_id 字段则添加
    cols = [r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()]
    if 'linked_student_id' not in cols:
        c.execute("ALTER TABLE users ADD COLUMN linked_student_id INTEGER REFERENCES users(id)")
    if 'student_class' not in cols:
        c.execute("ALTER TABLE users ADD COLUMN student_class TEXT")
    if 'student_id_number' not in cols:
        c.execute("ALTER TABLE users ADD COLUMN student_id_number TEXT")
    if 'avatar_url' not in cols:
        c.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT")

    # ---- 赛事表 ----
    c.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        title           TEXT NOT NULL,
        sport           TEXT NOT NULL,
        level           TEXT DEFAULT 'All Levels',
        event_date      TEXT NOT NULL,
        event_time      TEXT DEFAULT '09:00',
        venue           TEXT NOT NULL,
        max_capacity    INTEGER DEFAULT 32,
        description     TEXT,
        cover_url       TEXT,
        status          TEXT DEFAULT 'open' CHECK(status IN ('open','closed','cancelled','done')),
        organizer_id    INTEGER,
        created_at      TEXT DEFAULT (datetime('now','localtime')),
        FOREIGN KEY(organizer_id) REFERENCES users(id)
    )""")

    # ---- 报名表 ----
    c.execute("""
    CREATE TABLE IF NOT EXISTS registrations (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id        INTEGER NOT NULL,
        user_id         INTEGER NOT NULL,
        real_name       TEXT NOT NULL,
        student_id      TEXT,
        school          TEXT,
        grade_class     TEXT,
        phone           TEXT,
        emergency_contact TEXT,
        medical_info    TEXT,
        status          TEXT DEFAULT 'pending' CHECK(status IN ('pending','confirmed','cancelled')),
        registered_at   TEXT DEFAULT (datetime('now','localtime')),
        FOREIGN KEY(event_id) REFERENCES events(id),
        FOREIGN KEY(user_id) REFERENCES users(id),
        UNIQUE(event_id, user_id)
    )""")

    # ---- 通知/公告表 ----
    c.execute("""
    CREATE TABLE IF NOT EXISTS announcements (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        title       TEXT NOT NULL,
        content     TEXT NOT NULL,
        type        TEXT DEFAULT 'info' CHECK(type IN ('info','warning','success','danger')),
        target_role TEXT DEFAULT 'all',
        event_id    INTEGER,
        author_id   INTEGER,
        created_at  TEXT DEFAULT (datetime('now','localtime')),
        FOREIGN KEY(event_id) REFERENCES events(id)
    )""")

    # ---- 成绩/比赛结果表 ----
    c.execute("""
    CREATE TABLE IF NOT EXISTS results (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id        INTEGER NOT NULL,
        registration_id INTEGER NOT NULL,
        rank            INTEGER,
        score           TEXT,
        notes           TEXT,
        recorded_at     TEXT DEFAULT (datetime('now','localtime')),
        FOREIGN KEY(event_id) REFERENCES events(id),
        FOREIGN KEY(registration_id) REFERENCES registrations(id)
    )""")

    # ---- 队伍表 ----
    c.execute("""
    CREATE TABLE IF NOT EXISTS teams (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id      INTEGER NOT NULL REFERENCES events(id),
        name          TEXT NOT NULL,
        captain_id    INTEGER NOT NULL REFERENCES users(id),
        sport         TEXT,
        school        TEXT,
        level         TEXT DEFAULT 'All Levels',
        max_members   INTEGER DEFAULT 5,
        invite_code   TEXT UNIQUE,
        status        TEXT DEFAULT 'recruiting' CHECK(status IN ('recruiting','full','disbanded')),
        created_at    TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE(event_id, name)
    )""")

    # ---- 队伍成员表 ----
    c.execute("""
    CREATE TABLE IF NOT EXISTS team_members (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        team_id       INTEGER NOT NULL REFERENCES teams(id),
        user_id       INTEGER NOT NULL REFERENCES users(id),
        role          TEXT DEFAULT 'member' CHECK(role IN ('captain','member')),
        joined_at     TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE(team_id, user_id)
    )""")

    # ---- 队伍请求表（申请/邀请） ----
    c.execute("""
    CREATE TABLE IF NOT EXISTS team_requests (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        team_id       INTEGER NOT NULL REFERENCES teams(id),
        user_id       INTEGER NOT NULL REFERENCES users(id),
        type          TEXT NOT NULL CHECK(type IN ('invite','apply')),
        status        TEXT DEFAULT 'pending' CHECK(status IN ('pending','accepted','rejected','cancelled')),
        message       TEXT,
        created_at    TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE(team_id, user_id, type)
    )""")

    # ---- 练习赛约战表 ----
    c.execute("""
    CREATE TABLE IF NOT EXISTS practice_challenges (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id          INTEGER REFERENCES events(id),
        sport             TEXT,
        challenger_type   TEXT NOT NULL CHECK(challenger_type IN ('team','individual')),
        challenger_id     INTEGER NOT NULL,
        challenged_type   TEXT NOT NULL CHECK(challenged_type IN ('team','individual')),
        challenged_id     INTEGER NOT NULL,
        proposed_time     TEXT,
        proposed_venue    TEXT,
        level             TEXT DEFAULT 'All Levels',
        status            TEXT DEFAULT 'pending' CHECK(status IN ('pending','accepted','declined','completed','cancelled')),
        message           TEXT,
        created_at        TEXT DEFAULT (datetime('now','localtime'))
    )""")

    conn.commit()

    # ── 写入示例数据（仅首次） ──
    if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        _seed_data(c)
        conn.commit()

    conn.close()
    print(f"[DB] 初始化完成: {DB_PATH}")


def _seed_data(c):
    """插入初始示例数据"""
    # 管理员账号
    users = [
        ('admin',   hash_password('admin123'),   'admin',   'Admin',         'Venlo HQ',         None,      None,          '13800000000', 'admin@venlo.cn',     None),
        ('teacher1',hash_password('teacher123'), 'teacher', 'Mr. Wang Fang', 'RDFZ Xishan',      None,      None,          '13811111111', 'wang@rdfzxs.cn',    None),
        ('teacher2',hash_password('teacher123'), 'teacher', 'Ms. Li Hong',   'Beijing 101 School',None,     None,          '13822222222', 'li@101.cn',        None),
        ('student1',hash_password('student123'), 'student', 'Zhang Wei',     'RDFZ Xishan',      'Grade 10','Class 2',     '13833333333', 'zhangwei@stu.cn', None),
        ('student2',hash_password('student123'), 'student', 'Liu Yang',      'Beijing 101 School','Grade 11','Class 1',    '13844444444', 'liuyang@stu.cn',  None),
        ('student3',hash_password('student123'), 'student', 'Chen Xiao',     'Beijing No.4 HS',  'Grade 10','Class 3',     '13855555555', 'chenx@stu.cn',    None),
        ('parent1', hash_password('parent123'),  'parent',  'Mr. Zhang Ming','',               None,      None,          '13866666666', 'zhangming@parent.cn', 4),
    ]
    c.executemany("""
        INSERT INTO users(username,password,role,name,school,grade,phone,email,linked_student_id)
        VALUES(?,?,?,?,?,?,?,?,?)
    """, [(u[0],u[1],u[2],u[3],u[4],u[5],u[7],u[8],u[9]) for u in users])

    # 赛事
    events = [
        ('Inter-School Basketball League',      'Basketball',  'Intermediate', '2026-07-13', '14:00', 'Haidian Sports Center',       16,  'Annual inter-school 5v5 basketball league. Teams of 5 compete in round-robin format.',
         'https://images.unsplash.com/photo-1546519638-68e109498ffc?w=600&h=400&fit=crop', 'open',  2),
        ('Beijing High School Badminton Cup',   'Badminton',   'All Levels',   '2026-07-20', '09:00', 'Chaoyang Gymnasium',           32,  'Singles and doubles categories. Open to all skill levels.',
         'https://images.unsplash.com/photo-1613918431703-aa50889e3be9?w=600&h=400&fit=crop','open', 2),
        ('Summer Track and Field Meet',         'Track & Field','Beginner',    '2026-07-27', '08:00', 'National Olympic Sports Center', 100,'100m, 200m, 400m, long jump, shot put. All Grade 10-12 students welcome.',
         'https://images.unsplash.com/photo-1552674605-db6ffd4facb5?w=600&h=400&fit=crop', 'open',  3),
        ('Football 7-a-side Tournament',        'Football',    'Intermediate', '2026-08-03', '10:00', 'Shijingshan Football Park',    14,  '7-a-side football. Teams must include at least 2 students per grade.',
         'https://images.unsplash.com/photo-1574629810360-7efbbe195018?w=600&h=400&fit=crop','open', 3),
        ('Table Tennis Open Championship',      'Table Tennis','All Levels',   '2026-08-10', '09:00', 'Xicheng Sports Hall',          48,  'Round-robin + elimination. Separate male/female categories.',
         'https://images.unsplash.com/photo-1609710228159-0fa9bd7c0827?w=600&h=400&fit=crop','open', 2),
    ]
    c.executemany("""
        INSERT INTO events(title,sport,level,event_date,event_time,venue,max_capacity,description,cover_url,status,organizer_id)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)
    """, events)

    # 报名记录（示例）
    registrations = [
        (1, 4, 'Zhang Wei',  'S20230101', 'RDFZ Xishan',       'Grade 10 Class 2', '13833333333', 'Dad: 13866666666', '', 'confirmed'),
        (1, 5, 'Liu Yang',   'S20230202', 'Beijing 101 School', 'Grade 11 Class 1', '13844444444', 'Mom: 13877777777', '', 'confirmed'),
        (2, 4, 'Zhang Wei',  'S20230101', 'RDFZ Xishan',       'Grade 10 Class 2', '13833333333', 'Dad: 13866666666', '', 'confirmed'),
        (3, 6, 'Chen Xiao',  'S20230303', 'Beijing No.4 HS',   'Grade 10 Class 3', '13855555555', 'Mom: 13888888888', '', 'pending'),
    ]
    c.executemany("""
        INSERT INTO registrations(event_id,user_id,real_name,student_id,school,grade_class,phone,emergency_contact,medical_info,status)
        VALUES(?,?,?,?,?,?,?,?,?,?)
    """, registrations)

    # 通知公告
    announcements = [
        ('Basketball League Registration Opens!',
         'Registration for the Inter-School Basketball League is now open. Register before July 5 to secure your spot. Teams must submit full rosters.',
         'success', 'all', 1, 2),
        ('Venue Update: Track & Field Meet',
         'The Summer Track and Field Meet venue has been confirmed as the National Olympic Sports Center Track. Participants please bring valid student ID.',
         'info', 'all', 3, 2),
        ('Safety Reminder for All Events',
         'All participants must complete a health declaration form before competition. Warm up properly and stay hydrated. Emergency contacts must be provided.',
         'warning', 'all', None, 1),
        ('Badminton Cup - Draw Ceremony',
         'The draw ceremony for the Beijing High School Badminton Cup will be held online on July 15. All registered participants will receive a link.',
         'info', 'all', 2, 3),
        ('Football Tournament: Team Registration Deadline',
         'Team registration for the Football 7-a-side Tournament closes July 25. Teams must register together and submit player lists.',
         'danger', 'all', 4, 3),
    ]
    c.executemany("""
        INSERT INTO announcements(title,content,type,target_role,event_id,author_id)
        VALUES(?,?,?,?,?,?)
    """, announcements)


# ══════════════════════════════════════════════════
#  静态文件服务（前端 index.html）
# ══════════════════════════════════════════════════
@app.route('/')
def serve_index():
    return send_from_directory('..', 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('..', filename)


# ══════════════════════════════════════════════════
#  AUTH API
# ══════════════════════════════════════════════════
@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json()
    required = ['username', 'password', 'role', 'name']
    for f in required:
        if not data.get(f):
            return jsonify({'error': f'Missing field: {f}'}), 400

    conn = get_db()
    try:
        # 查找关联学生（家长注册时必须提供）
        linked_student_id = None
        linked_username = data.get('linked_student_username', '').strip()
        if linked_username:
            stu = conn.execute(
                "SELECT id FROM users WHERE username=? AND role='student'",
                (linked_username,)
            ).fetchone()
            # 大小写不敏感回退查找
            if not stu:
                stu = conn.execute(
                    "SELECT id FROM users WHERE LOWER(username)=LOWER(?) AND role='student'",
                    (linked_username,)
                ).fetchone()
            if stu:
                linked_student_id = stu['id']
            elif data['role'] == 'parent':
                return jsonify({'error': f'Student username "{linked_username}" not found. Ask your child for their username.'}), 400
        elif data['role'] == 'parent' and not linked_username:
            return jsonify({'error': 'Parent account must link to a student. Provide your child\'s username.'}), 400

        conn.execute("""
            INSERT INTO users(username,password,role,name,school,grade,student_class,student_id_number,phone,email,linked_student_id)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """, (
            data['username'],
            hash_password(data['password']),
            data['role'],
            data['name'],
            data.get('school', ''),
            data.get('grade', ''),
            data.get('student_class', ''),
            data.get('student_id_number', ''),
            data.get('phone', ''),
            data.get('email', ''),
            linked_student_id,
        ))
        conn.commit()
        user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        return jsonify({'success': True, 'user_id': user_id, 'message': 'Registration successful'}), 201
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Username already exists'}), 409
    finally:
        conn.close()



@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username','').strip()
    password = data.get('password','')

    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400

    conn = get_db()
    user = conn.execute(
        "SELECT id,username,role,name,school,grade,student_class,student_id_number,phone,email,avatar_url,linked_student_id FROM users WHERE username=? AND password=?",
        (username, hash_password(password))
    ).fetchone()
    conn.close()

    if not user:
        return jsonify({'error': 'Invalid username or password'}), 401

    return jsonify({
        'success': True,
        'user': dict(user),
        'message': f'Welcome back, {user["name"]}!'
    })


# ══════════════════════════════════════════════════
#  EVENTS API
# ══════════════════════════════════════════════════
@app.route('/api/events', methods=['GET'])
def get_events():
    sport  = request.args.get('sport')
    status = request.args.get('status', 'open')
    limit  = int(request.args.get('limit', 20))

    conn = get_db()
    query = """
        SELECT e.*,
               COUNT(r.id) AS registered_count,
               u.name AS organizer_name
        FROM events e
        LEFT JOIN registrations r ON r.event_id=e.id AND r.status!='cancelled'
        LEFT JOIN users u ON u.id=e.organizer_id
        WHERE 1=1
    """
    params = []
    if sport:
        query += " AND e.sport=?"
        params.append(sport)
    if status:
        query += " AND e.status=?"
        params.append(status)
    query += " GROUP BY e.id ORDER BY e.event_date ASC LIMIT ?"
    params.append(limit)

    events = [dict(row) for row in conn.execute(query, params).fetchall()]
    conn.close()
    return jsonify({'events': events, 'total': len(events)})


@app.route('/api/events/<int:event_id>', methods=['GET'])
def get_event(event_id):
    conn = get_db()
    event = conn.execute("""
        SELECT e.*, COUNT(r.id) AS registered_count, u.name AS organizer_name
        FROM events e
        LEFT JOIN registrations r ON r.event_id=e.id AND r.status!='cancelled'
        LEFT JOIN users u ON u.id=e.organizer_id
        WHERE e.id=?
        GROUP BY e.id
    """, (event_id,)).fetchone()
    conn.close()
    if not event:
        return jsonify({'error': 'Event not found'}), 404
    return jsonify(dict(event))


@app.route('/api/events', methods=['POST'])
def create_event():
    data = request.get_json()
    required = ['title', 'sport', 'event_date', 'venue', 'organizer_id']
    for f in required:
        if not data.get(f):
            return jsonify({'error': f'Missing field: {f}'}), 400

    conn = get_db()
    conn.execute("""
        INSERT INTO events(title,sport,level,event_date,event_time,venue,max_capacity,description,cover_url,organizer_id)
        VALUES(?,?,?,?,?,?,?,?,?,?)
    """, (
        data['title'], data['sport'],
        data.get('level','All Levels'),
        data['event_date'],
        data.get('event_time','09:00'),
        data['venue'],
        int(data.get('max_capacity', 32)),
        data.get('description',''),
        data.get('cover_url',''),
        data['organizer_id']
    ))
    conn.commit()
    event_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return jsonify({'success': True, 'event_id': event_id}), 201


@app.route('/api/events/<int:event_id>', methods=['PUT'])
def update_event(event_id):
    data = request.get_json()
    allowed = ['title','sport','level','event_date','event_time','venue','max_capacity','description','status']
    sets = [f"{k}=?" for k in allowed if k in data]
    vals = [data[k] for k in allowed if k in data]
    if not sets:
        return jsonify({'error': 'Nothing to update'}), 400
    vals.append(event_id)
    conn = get_db()
    conn.execute(f"UPDATE events SET {', '.join(sets)} WHERE id=?", vals)
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ══════════════════════════════════════════════════
#  REGISTRATIONS API
# ══════════════════════════════════════════════════
@app.route('/api/registrations', methods=['POST'])
def register_event():
    data = request.get_json()
    required = ['event_id', 'user_id', 'real_name']
    for f in required:
        if not data.get(f):
            return jsonify({'error': f'Missing field: {f}'}), 400

    conn = get_db()
    # 检查活动是否存在且开放
    event = conn.execute("SELECT id,max_capacity,status FROM events WHERE id=?",
                         (data['event_id'],)).fetchone()
    if not event:
        return jsonify({'error': 'Event not found'}), 404
    if event['status'] != 'open':
        return jsonify({'error': 'Event registration is closed'}), 400

    # 检查名额
    count = conn.execute(
        "SELECT COUNT(*) FROM registrations WHERE event_id=? AND status!='cancelled'",
        (data['event_id'],)).fetchone()[0]
    if count >= event['max_capacity']:
        return jsonify({'error': 'Event is full'}), 400

    try:
        conn.execute("""
            INSERT INTO registrations(event_id,user_id,real_name,student_id,school,grade_class,phone,emergency_contact,medical_info)
            VALUES(?,?,?,?,?,?,?,?,?)
        """, (
            data['event_id'], data['user_id'], data['real_name'],
            data.get('student_id',''), data.get('school',''),
            data.get('grade_class',''), data.get('phone',''),
            data.get('emergency_contact',''), data.get('medical_info','')
        ))
        conn.commit()
        reg_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return jsonify({'success': True, 'registration_id': reg_id,
                        'message': 'Successfully registered!'}), 201
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'You are already registered for this event'}), 409


@app.route('/api/registrations/user/<int:user_id>', methods=['GET'])
def get_user_registrations(user_id):
    conn = get_db()
    rows = conn.execute("""
        SELECT r.*, e.title, e.sport, e.event_date, e.event_time, e.venue, e.cover_url
        FROM registrations r
        JOIN events e ON e.id = r.event_id
        WHERE r.user_id=?
        ORDER BY r.registered_at DESC
    """, (user_id,)).fetchall()
    conn.close()
    return jsonify({'registrations': [dict(r) for r in rows]})


@app.route('/api/registrations/event/<int:event_id>', methods=['GET'])
def get_event_registrations(event_id):
    conn = get_db()
    rows = conn.execute("""
        SELECT r.*, u.name AS user_name, u.school AS user_school
        FROM registrations r
        LEFT JOIN users u ON u.id=r.user_id
        WHERE r.event_id=?
        ORDER BY r.registered_at ASC
    """, (event_id,)).fetchall()
    conn.close()
    return jsonify({'registrations': [dict(r) for r in rows], 'total': len(rows)})


# ══════════════════════════════════════════════════
#  ANNOUNCEMENTS API
# ══════════════════════════════════════════════════
@app.route('/api/announcements', methods=['GET'])
def get_announcements():
    role  = request.args.get('role', 'all')
    limit = int(request.args.get('limit', 10))
    conn  = get_db()
    rows  = conn.execute("""
        SELECT a.*, u.name AS author_name, e.title AS event_title
        FROM announcements a
        LEFT JOIN users u ON u.id=a.author_id
        LEFT JOIN events e ON e.id=a.event_id
        WHERE a.target_role='all' OR a.target_role=?
        ORDER BY a.created_at DESC LIMIT ?
    """, (role, limit)).fetchall()
    conn.close()
    return jsonify({'announcements': [dict(r) for r in rows]})


@app.route('/api/announcements', methods=['POST'])
def create_announcement():
    data = request.get_json()
    if not data.get('title') or not data.get('content'):
        return jsonify({'error': 'Title and content required'}), 400
    conn = get_db()
    conn.execute("""
        INSERT INTO announcements(title,content,type,target_role,event_id,author_id)
        VALUES(?,?,?,?,?,?)
    """, (
        data['title'], data['content'],
        data.get('type','info'),
        data.get('target_role','all'),
        data.get('event_id'),
        data.get('author_id')
    ))
    conn.commit()
    ann_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return jsonify({'success': True, 'announcement_id': ann_id}), 201


@app.route('/api/announcements/<int:ann_id>/delete', methods=['POST'])
def delete_announcement(ann_id):
    """删除公告"""
    conn = get_db()
    conn.execute("DELETE FROM announcements WHERE id=?", (ann_id,))
    conn.commit()
    deleted = conn.total_changes
    conn.close()
    if deleted:
        return jsonify({'success': True})
    return jsonify({'error': 'Announcement not found'}), 404


# ══════════════════════════════════════════════════
#  STATS API（首页统计数据）
# ══════════════════════════════════════════════════
@app.route('/api/stats', methods=['GET'])
def get_stats():
    conn = get_db()

    total_students = conn.execute("SELECT COUNT(*) FROM users WHERE role='student'").fetchone()[0]
    total_schools  = conn.execute("SELECT COUNT(DISTINCT school) FROM users WHERE role='student'").fetchone()[0]
    total_events   = conn.execute("SELECT COUNT(*) FROM events WHERE status='open'").fetchone()[0]
    total_regs     = conn.execute("SELECT COUNT(*) FROM registrations WHERE status!='cancelled'").fetchone()[0]

    # 各运动报名人数（用于图表）
    sport_stats = conn.execute("""
        SELECT e.sport, COUNT(r.id) as count
        FROM events e
        LEFT JOIN registrations r ON r.event_id=e.id AND r.status!='cancelled'
        GROUP BY e.sport ORDER BY count DESC
    """).fetchall()

    # 近6个月赛事趋势
    trend = conn.execute("""
        SELECT strftime('%Y-%m', event_date) as month, COUNT(*) as count
        FROM events
        WHERE event_date >= date('now','-6 months')
        GROUP BY month ORDER BY month
    """).fetchall()

    conn.close()
    return jsonify({
        'total_students': total_students,
        'total_schools':  total_schools,
        'total_events':   total_events,
        'total_registrations': total_regs,
        'sport_stats': [dict(r) for r in sport_stats],
        'trend': [dict(r) for r in trend],
    })


# ══════════════════════════════════════════════════
#  USERS API
# ══════════════════════════════════════════════════
@app.route('/api/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    conn = get_db()
    user = conn.execute(
        "SELECT id,username,role,name,school,grade,student_class,student_id_number,phone,email,avatar_url,linked_student_id,created_at FROM users WHERE id=?",
        (user_id,)).fetchone()
    conn.close()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify(dict(user))


@app.route('/api/users', methods=['GET'])
def list_users():
    role = request.args.get('role')
    conn = get_db()
    if role:
        rows = conn.execute(
            "SELECT id,username,role,name,school,grade,student_class,student_id_number,phone,email,avatar_url,linked_student_id FROM users WHERE role=?", (role,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id,username,role,name,school,grade,student_class,student_id_number,phone,email,avatar_url,linked_student_id FROM users"
        ).fetchall()
    conn.close()
    return jsonify({'users': [dict(r) for r in rows]})


# ══════════════════════════════════════════════════
@app.route('/api/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    """更新用户信息（姓名、邮箱、电话、学校、年级、头像等）"""
    data = request.get_json()
    allowed = ['name', 'email', 'phone', 'school', 'grade', 'student_class', 'student_id_number', 'avatar_url']
    sets = [f"{k}=?" for k in allowed if k in data]
    vals = [data[k] for k in allowed if k in data]
    if not sets:
        return jsonify({'error': 'Nothing to update'}), 400
    vals.append(user_id)
    conn = get_db()
    conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE id=?", vals)
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ══════════════════════════════════════════════════
#  TEAMS API
# ══════════════════════════════════════════════════
import random, string

def _gen_invite_code(length=6):
    """生成邀请码：大写字母+数字"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


@app.route('/api/teams', methods=['GET'])
def list_teams():
    """搜索招募中的队伍"""
    sport  = request.args.get('sport')
    school = request.args.get('school')
    status = request.args.get('status', 'recruiting')
    event_id = request.args.get('event_id', type=int)
    q = "SELECT t.*, u.name AS captain_name, u.avatar_url AS captain_avatar," \
        " (SELECT COUNT(*) FROM team_members tm WHERE tm.team_id=t.id) AS member_count" \
        " FROM teams t LEFT JOIN users u ON t.captain_id=u.id WHERE 1=1"
    params = []
    if sport:
        q += " AND t.sport=?"; params.append(sport)
    if school:
        q += " AND t.school LIKE ?"; params.append(f'%{school}%')
    if status:
        q += " AND t.status=?"; params.append(status)
    if event_id:
        q += " AND t.event_id=?"; params.append(event_id)
    q += " ORDER BY t.created_at DESC"
    conn = get_db()
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return jsonify({'teams': [dict(r) for r in rows]})


@app.route('/api/teams/my', methods=['GET'])
def my_teams():
    """我加入的队伍 + 我创建的队伍"""
    uid = request.args.get('user_id', type=int)
    if not uid:
        return jsonify({'error': 'user_id required'}), 400
    conn = get_db()
    # 我加入的队伍（含成员信息）
    rows = conn.execute(
        "SELECT t.*, u.name AS captain_name, tm.role AS my_role,"
        " (SELECT COUNT(*) FROM team_members tm2 WHERE tm2.team_id=t.id) AS member_count"
        " FROM team_members tm JOIN teams t ON tm.team_id=t.id"
        " LEFT JOIN users u ON t.captain_id=u.id"
        " WHERE tm.user_id=? ORDER BY t.created_at DESC", (uid,)
    ).fetchall()
    conn.close()
    return jsonify({'teams': [dict(r) for r in rows]})


@app.route('/api/teams/<int:team_id>', methods=['GET'])
def get_team(team_id):
    """队伍详情（含成员列表）"""
    conn = get_db()
    team = conn.execute(
        "SELECT t.*, u.name AS captain_name"
        " FROM teams t LEFT JOIN users u ON t.captain_id=u.id WHERE t.id=?", (team_id,)
    ).fetchone()
    if not team:
        conn.close()
        return jsonify({'error': 'Team not found'}), 404
    members = conn.execute(
        "SELECT tm.*, u.name, u.avatar_url, u.school, u.grade FROM team_members tm"
        " LEFT JOIN users u ON tm.user_id=u.id WHERE tm.team_id=? ORDER BY tm.role DESC, tm.joined_at",
        (team_id,)
    ).fetchall()
    conn.close()
    result = dict(team)
    result['members'] = [dict(m) for m in members]
    return jsonify(result)


@app.route('/api/teams', methods=['POST'])
def create_team():
    """创建队伍"""
    data = request.get_json()
    event_id    = data.get('event_id')
    name        = data.get('name', '').strip()
    captain_id  = data.get('captain_id')
    sport       = data.get('sport', '')
    school      = data.get('school', '')
    level       = data.get('level', 'All Levels')
    max_members = data.get('max_members', 5)
    if not name or not event_id or not captain_id:
        return jsonify({'error': 'name, event_id, captain_id required'}), 400
    invite_code = _gen_invite_code()
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO teams(event_id,name,captain_id,sport,school,level,max_members,invite_code)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (event_id, name, captain_id, sport, school, level, max_members, invite_code)
        )
        team_id = cur.lastrowid
        # 队长自动成为成员
        conn.execute("INSERT INTO team_members(team_id,user_id,role) VALUES(?,?,?)",
                     (team_id, captain_id, 'captain'))
        conn.commit()
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 400
    conn.close()
    return jsonify({'success': True, 'team_id': team_id, 'invite_code': invite_code}), 201


@app.route('/api/teams/join', methods=['POST'])
def join_team_by_code():
    """通过邀请码直接加入队伍"""
    data = request.get_json()
    code    = data.get('invite_code', '').strip().upper()
    user_id = data.get('user_id')
    if not code or not user_id:
        return jsonify({'error': 'invite_code and user_id required'}), 400
    conn = get_db()
    team = conn.execute("SELECT * FROM teams WHERE invite_code=?", (code,)).fetchone()
    if not team:
        conn.close()
        return jsonify({'error': 'Invalid invite code'}), 404
    if team['status'] == 'disbanded':
        conn.close()
        return jsonify({'error': 'Team has been disbanded'}), 400
    # 检查人数
    cnt = conn.execute("SELECT COUNT(*) FROM team_members WHERE team_id=?", (team['id'],)).fetchone()[0]
    if cnt >= team['max_members']:
        conn.close()
        return jsonify({'error': 'Team is full'}), 400
    # 检查是否已加入
    exists = conn.execute("SELECT 1 FROM team_members WHERE team_id=? AND user_id=?",
                          (team['id'], user_id)).fetchone()
    if exists:
        conn.close()
        return jsonify({'error': 'Already a member'}), 400
    conn.execute("INSERT INTO team_members(team_id,user_id,role) VALUES(?,?,?)",
                 (team['id'], user_id, 'member'))
    # 如果满了，更新状态
    if cnt + 1 >= team['max_members']:
        conn.execute("UPDATE teams SET status='full' WHERE id=?", (team['id'],))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'team_id': team['id'], 'team_name': team['name']})


@app.route('/api/team-requests', methods=['POST'])
def create_team_request():
    """申请加入 / 邀请某人"""
    data = request.get_json()
    team_id  = data.get('team_id')
    user_id  = data.get('user_id')
    rtype    = data.get('type', 'apply')  # apply | invite
    message  = data.get('message', '')
    if not team_id or not user_id:
        return jsonify({'error': 'team_id and user_id required'}), 400
    conn = get_db()
    # 检查是否已有 pending 请求
    existing = conn.execute(
        "SELECT 1 FROM team_requests WHERE team_id=? AND user_id=? AND type=? AND status='pending'",
        (team_id, user_id, rtype)
    ).fetchone()
    if existing:
        conn.close()
        return jsonify({'error': 'Request already exists'}), 400
    # 检查是否已是成员
    is_member = conn.execute("SELECT 1 FROM team_members WHERE team_id=? AND user_id=?",
                             (team_id, user_id)).fetchone()
    if is_member:
        conn.close()
        return jsonify({'error': 'Already a member'}), 400
    conn.execute("INSERT INTO team_requests(team_id,user_id,type,message) VALUES(?,?,?,?)",
                 (team_id, user_id, rtype, message))
    conn.commit()
    conn.close()
    return jsonify({'success': True}), 201


@app.route('/api/team-requests/<int:req_id>', methods=['PUT'])
def handle_team_request(req_id):
    """接受/拒绝申请或邀请"""
    data = request.get_json()
    action = data.get('action')  # accepted | rejected | cancelled
    if action not in ('accepted', 'rejected', 'cancelled'):
        return jsonify({'error': 'action must be accepted/rejected/cancelled'}), 400
    conn = get_db()
    req = conn.execute("SELECT * FROM team_requests WHERE id=?", (req_id,)).fetchone()
    if not req:
        conn.close()
        return jsonify({'error': 'Request not found'}), 404
    conn.execute("UPDATE team_requests SET status=? WHERE id=?", (action, req_id))
    if action == 'accepted':
        # 加入队伍
        team = conn.execute("SELECT * FROM teams WHERE id=?", (req['team_id'],)).fetchone()
        exists = conn.execute("SELECT 1 FROM team_members WHERE team_id=? AND user_id=?",
                              (req['team_id'], req['user_id'])).fetchone()
        if not exists and team:
            conn.execute("INSERT INTO team_members(team_id,user_id,role) VALUES(?,?,?)",
                         (req['team_id'], req['user_id'], 'member'))
            # 检查是否满员
            cnt = conn.execute("SELECT COUNT(*) FROM team_members WHERE team_id=?",
                               (req['team_id'],)).fetchone()[0]
            if cnt >= team['max_members']:
                conn.execute("UPDATE teams SET status='full' WHERE id=?", (req['team_id'],))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/team-requests', methods=['GET'])
def list_team_requests():
    """查询队伍请求：我收到的邀请 / 我队伍收到的申请"""
    user_id  = request.args.get('user_id', type=int)
    team_id  = request.args.get('team_id', type=int)
    rtype    = request.args.get('type')  # invite | apply
    status   = request.args.get('status', 'pending')
    conn = get_db()
    q = "SELECT tr.*, t.name AS team_name, t.sport, u.name AS user_name, u.avatar_url AS user_avatar" \
        " FROM team_requests tr" \
        " LEFT JOIN teams t ON tr.team_id=t.id" \
        " LEFT JOIN users u ON tr.user_id=u.id WHERE 1=1"
    params = []
    if user_id:
        q += " AND tr.user_id=?"; params.append(user_id)
    if team_id:
        q += " AND tr.team_id=?"; params.append(team_id)
    if rtype:
        q += " AND tr.type=?"; params.append(rtype)
    if status:
        q += " AND tr.status=?"; params.append(status)
    q += " ORDER BY tr.created_at DESC"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return jsonify({'requests': [dict(r) for r in rows]})


# ══════════════════════════════════════════════════
#  PRACTICE CHALLENGES API
# ══════════════════════════════════════════════════
@app.route('/api/practice-challenges', methods=['GET'])
def list_challenges():
    """搜索练习赛约战 — 支持 user_id 筛选（返回与该用户相关的约战）"""
    sport   = request.args.get('sport')
    status  = request.args.get('status', 'pending')
    user_id = request.args.get('user_id', type=int)
    conn = get_db()
    q = "SELECT pc.* FROM practice_challenges pc WHERE 1=1"
    params = []
    if sport:
        q += " AND pc.sport=?"; params.append(sport)
    if status:
        q += " AND pc.status=?"; params.append(status)
    # 按 user_id 筛选：作为个人挑战方/被挑战方，或所属队伍的挑战方/被挑战方
    if user_id:
        # 查找该用户所在的所有队伍 ID
        my_team_ids = [r[0] for r in conn.execute(
            "SELECT team_id FROM team_members WHERE user_id=?", (user_id,)
        ).fetchall()]
        # ⚠️ 注意：params 顺序必须和 SQL ? 占位符顺序一致！
        # SQL 顺序：individual challenger_id → individual challenged_id → team clauses
        # 所以 user_id 必须先加入 params，然后才是 team_ids
        team_clause = ""
        if my_team_ids:
            placeholders = ",".join(["?"] * len(my_team_ids))
            team_clause = f" OR (pc.challenger_type='team' AND pc.challenger_id IN ({placeholders})) OR (pc.challenged_type='team' AND pc.challenged_id IN ({placeholders}))"
        q += f" AND ((pc.challenger_type='individual' AND pc.challenger_id=?) OR (pc.challenged_type='individual' AND pc.challenged_id=?){team_clause})"
        # 先加 user_id（对应 individual 条件），再加 team_ids（对应 IN 条件）
        params.extend([user_id, user_id])
        if my_team_ids:
            params.extend(my_team_ids)
            params.extend(my_team_ids)
    q += " ORDER BY pc.created_at DESC"
    app.logger.info('[list_challenges] SQL: %s params: %s', q, params)
    rows = conn.execute(q, params).fetchall()
    app.logger.info('[list_challenges] found %d rows', len(rows))
    result = []
    for r in rows:
        d = dict(r)
        # 展开挑战方/被挑战方名称
        if d['challenger_type'] == 'team':
            t = conn.execute("SELECT name,school FROM teams WHERE id=?", (d['challenger_id'],)).fetchone()
            d['challenger_name'] = t['name'] if t else '?'
            d['challenger_school'] = t['school'] if t else ''
        else:
            u = conn.execute("SELECT name,school FROM users WHERE id=?", (d['challenger_id'],)).fetchone()
            d['challenger_name'] = u['name'] if u else '?'
            d['challenger_school'] = u['school'] if u else ''
        if d['challenged_type'] == 'team':
            t = conn.execute("SELECT name,school FROM teams WHERE id=?", (d['challenged_id'],)).fetchone()
            d['challenged_name'] = t['name'] if t else '?'
            d['challenged_school'] = t['school'] if t else ''
        else:
            u = conn.execute("SELECT name,school FROM users WHERE id=?", (d['challenged_id'],)).fetchone()
            d['challenged_name'] = u['name'] if u else '?'
            d['challenged_school'] = u['school'] if u else ''
        result.append(d)
    conn.close()
    return jsonify({'challenges': result})


@app.route('/api/practice-challenges', methods=['POST'])
def create_challenge():
    """发起约战"""
    data = request.get_json()
    conn = get_db()
    conn.execute(
        "INSERT INTO practice_challenges(event_id,sport,challenger_type,challenger_id,"
        "challenged_type,challenged_id,proposed_time,proposed_venue,level,message)"
        " VALUES(?,?,?,?,?,?,?,?,?,?)",
        (data.get('event_id'), data.get('sport',''), data.get('challenger_type','individual'),
         data.get('challenger_id'), data.get('challenged_type','individual'),
         data.get('challenged_id'), data.get('proposed_time',''),
         data.get('proposed_venue',''), data.get('level','All Levels'), data.get('message',''))
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True}), 201


@app.route('/api/practice-challenges/<int:ch_id>', methods=['PUT'])
def handle_challenge(ch_id):
    """接受/拒绝/完成约战"""
    data = request.get_json()
    action = data.get('action')  # accepted | declined | completed | cancelled
    if action not in ('accepted', 'declined', 'completed', 'cancelled'):
        return jsonify({'error': 'Invalid action'}), 400
    conn = get_db()
    conn.execute("UPDATE practice_challenges SET status=? WHERE id=?", (action, ch_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ══════════════════════════════════════════════════
#  NOTIFICATIONS API
# ══════════════════════════════════════════════════
@app.route('/api/notifications/count', methods=['GET'])
def notification_count():
    """当前用户待处理通知数"""
    uid = request.args.get('user_id', type=int)
    if not uid:
        return jsonify({'count': 0})
    conn = get_db()
    # 1) 收到的入队邀请
    invites = conn.execute(
        "SELECT COUNT(*) FROM team_requests WHERE user_id=? AND type='invite' AND status='pending'", (uid,)
    ).fetchone()[0]
    # 2) 我队伍收到的申请（我是队长的队伍）
    applys = conn.execute(
        "SELECT COUNT(*) FROM team_requests tr JOIN teams t ON tr.team_id=t.id"
        " WHERE t.captain_id=? AND tr.type='apply' AND tr.status='pending'", (uid,)
    ).fetchone()[0]
    # 3) 收到的约战（个人约战）
    p_challenges = conn.execute(
        "SELECT COUNT(*) FROM practice_challenges"
        " WHERE challenged_type='individual' AND challenged_id=? AND status='pending'", (uid,)
    ).fetchone()[0]
    # 4) 我队伍收到的约战（我是队长的队伍）
    my_teams = conn.execute("SELECT id FROM teams WHERE captain_id=?", (uid,)).fetchall()
    t_challenges = 0
    for t in my_teams:
        c = conn.execute(
            "SELECT COUNT(*) FROM practice_challenges"
            " WHERE challenged_type='team' AND challenged_id=? AND status='pending'", (t['id'],)
        ).fetchone()[0]
        t_challenges += c
    conn.close()
    total = invites + applys + p_challenges + t_challenges
    return jsonify({'count': total, 'invites': invites, 'applys': applys,
                    'individual_challenges': p_challenges, 'team_challenges': t_challenges})
# ══════════════════════════════════════════════════
@app.route('/api/results/event/<int:event_id>', methods=['GET'])
def get_event_results(event_id):
    conn = get_db()
    rows = conn.execute("""
        SELECT rs.*, r.real_name, r.school, r.grade_class
        FROM results rs
        JOIN registrations r ON r.id=rs.registration_id
        WHERE rs.event_id=?
        ORDER BY rs.rank ASC
    """, (event_id,)).fetchall()
    conn.close()
    return jsonify({'results': [dict(r) for r in rows]})


@app.route('/api/results', methods=['POST'])
def post_result():
    data = request.get_json()
    conn = get_db()
    conn.execute("""
        INSERT OR REPLACE INTO results(event_id,registration_id,rank,score,notes)
        VALUES(?,?,?,?,?)
    """, (data['event_id'], data['registration_id'], data.get('rank'), data.get('score',''), data.get('notes','')))
    conn.commit()
    conn.close()
    return jsonify({'success': True}), 201


# ══════════════════════════════════════════════════
#  健康检查
# ══════════════════════════════════════════════════
@app.route('/api/ping')
def ping():
    return jsonify({'status': 'ok', 'time': datetime.now().isoformat()})



# ══════════════════════════════════════════════════
#  主入口
# ══════════════════════════════════════════════════
if __name__ == '__main__':
    init_db()
    PORT = int(os.environ.get('PORT', 5000))
    DEBUG = os.environ.get('FLASK_ENV', 'production') == 'development'
    print("=" * 50)
    print("  Venlo Backend API  启动中")
    print(f"  访问地址: http://0.0.0.0:{PORT}")
    print("  API 文档: http://0.0.0.0:{}/api/ping".format(PORT))
    print("=" * 50)

    if DEBUG:
        # 开发模式：Flask 内置服务器
        app.run(host='0.0.0.0', port=PORT, debug=True)
    else:
        # 生产模式：waitress WSGI 服务器（Windows 友好）
        try:
            from waitress import serve
            print("  [生产模式] 使用 waitress WSGI 服务器")
            serve(app, host='0.0.0.0', port=PORT)
        except ImportError:
            print("  [警告] 未安装 waitress，使用 Flask 开发服务器")
            app.run(host='0.0.0.0', port=PORT, debug=False)
