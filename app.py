import json
import os
import random
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, jsonify, session
import sqlite3

app = Flask(__name__)
app.secret_key = os.urandom(24)

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'scores.db')
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quiz_type TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                difficulty TEXT,
                score INTEGER NOT NULL,
                max_score INTEGER NOT NULL,
                timestamp TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS daily_challenges (
                date TEXT PRIMARY KEY,
                quiz_type TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                bonus_awarded INTEGER DEFAULT 0
            )
        ''')
        conn.commit()


DIFFICULTY_TIME   = {'beginner': 120, 'intermediate': 90, 'advanced': 60}
UNLOCK_THRESHOLD  = 2
UNLOCK_MIN_PCT    = 50
DAILY_BONUS       = 25

MODULE_ICONS = {
    'phishing': '🎣', 'scenario': '🎭', 'login': '🌐', 'headers': '📋'
}
MODULE_URLS = {
    'phishing': '/phishing', 'scenario': '/scenarios',
    'login': '/login-detector', 'headers': '/headers'
}


def get_streak():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT DATE(timestamp) as d FROM scores ORDER BY d DESC"
        ).fetchall()
    if not rows:
        return 0
    today = datetime.utcnow().date()
    streak = 0
    check = today
    for row in rows:
        d = date.fromisoformat(row['d'])
        if d == check:
            streak += 1
            check -= timedelta(days=1)
        elif d < check:
            break
    return streak


def _daily_pick(today_str):
    all_items = []
    for e in load_json('phishing_emails.json'):
        all_items.append({'quiz_type': 'phishing', 'item_id': e['id'], 'item': e})
    for s in load_json('scenarios.json'):
        all_items.append({'quiz_type': 'scenario', 'item_id': s['id'], 'item': s})
    for l in load_json('fake_logins.json'):
        all_items.append({'quiz_type': 'login', 'item_id': l['id'], 'item': l})
    for h in load_json('email_headers.json'):
        all_items.append({'quiz_type': 'headers', 'item_id': h['id'], 'item': h})
    return random.Random(today_str).choice(all_items)


def get_daily_challenge():
    today = datetime.utcnow().strftime('%Y-%m-%d')
    pick = _daily_pick(today)
    with get_db() as conn:
        row = conn.execute(
            "SELECT bonus_awarded FROM daily_challenges WHERE date=?", (today,)
        ).fetchone()
    completed = row is not None and row['bonus_awarded']
    item = pick['item']
    title = item.get('subject') or item.get('title') or item.get('category', '?')
    return {
        'date': today,
        'quiz_type': pick['quiz_type'],
        'item_id': pick['item_id'],
        'title': title,
        'category': item.get('category', ''),
        'difficulty': item.get('difficulty', ''),
        'completed': completed,
        'icon': MODULE_ICONS.get(pick['quiz_type'], '?'),
        'url': f"{MODULE_URLS[pick['quiz_type']]}/{pick['item_id']}"
    }


def check_and_award_daily(quiz_type, item_id):
    today = datetime.utcnow().strftime('%Y-%m-%d')
    pick = _daily_pick(today)
    if pick['quiz_type'] != quiz_type or pick['item_id'] != item_id:
        return 0
    with get_db() as conn:
        existing = conn.execute(
            "SELECT bonus_awarded FROM daily_challenges WHERE date=?", (today,)
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO daily_challenges (date, quiz_type, item_id, bonus_awarded) VALUES (?,?,?,1)",
                (today, quiz_type, item_id)
            )
            conn.commit()
            return DAILY_BONUS
        if not existing['bonus_awarded']:
            conn.execute(
                "UPDATE daily_challenges SET bonus_awarded=1 WHERE date=?", (today,)
            )
            conn.commit()
            return DAILY_BONUS
    return 0


def load_json(filename):
    with open(os.path.join(DATA_DIR, filename)) as f:
        return json.load(f)


def get_unlock_status(quiz_type):
    """Return set of unlocked difficulty levels for a quiz type."""
    with get_db() as conn:
        rows = conn.execute('''
            SELECT difficulty, COUNT(DISTINCT item_id) as cnt
            FROM scores
            WHERE quiz_type = ?
              AND CAST(score AS FLOAT) / max_score >= ?
            GROUP BY difficulty
        ''', (quiz_type, UNLOCK_MIN_PCT / 100)).fetchall()
    completed = {r['difficulty']: r['cnt'] for r in rows}
    unlocked = {'beginner'}
    if completed.get('beginner', 0) >= UNLOCK_THRESHOLD:
        unlocked.add('intermediate')
    if completed.get('intermediate', 0) >= UNLOCK_THRESHOLD:
        unlocked.add('advanced')
    return unlocked


@app.route('/')
def index():
    with get_db() as conn:
        rows = conn.execute('''
            SELECT quiz_type, COUNT(*) as attempts,
                   ROUND(AVG(CAST(score AS FLOAT)/max_score*100), 1) as avg_pct
            FROM scores
            GROUP BY quiz_type
        ''').fetchall()
    stats = {r['quiz_type']: dict(r) for r in rows}
    return render_template('index.html', stats=stats,
                           streak=get_streak(),
                           daily=get_daily_challenge())


@app.route('/daily')
def daily():
    challenge = get_daily_challenge()
    return render_template('daily.html', challenge=challenge)


@app.route('/phishing')
def phishing_list():
    emails = load_json('phishing_emails.json')
    unlocked = get_unlock_status('phishing')
    return render_template('phishing_list.html', emails=emails, unlocked=unlocked,
                           threshold=UNLOCK_THRESHOLD)


@app.route('/phishing/<int:email_id>')
def phishing_sim(email_id):
    emails = load_json('phishing_emails.json')
    email = next((e for e in emails if e['id'] == email_id), None)
    if not email:
        return 'Niet gevonden', 404
    unlocked = get_unlock_status('phishing')
    if email['difficulty'] not in unlocked:
        return render_template('locked.html', difficulty=email['difficulty'],
                               quiz_type='phishing', threshold=UNLOCK_THRESHOLD), 403
    time_limit = DIFFICULTY_TIME[email['difficulty']]
    return render_template('phishing_sim.html', email=email, time_limit=time_limit)


@app.route('/phishing/<int:email_id>/submit', methods=['POST'])
def phishing_submit(email_id):
    emails = load_json('phishing_emails.json')
    email = next((e for e in emails if e['id'] == email_id), None)
    if not email:
        return jsonify({'error': 'not found'}), 404

    data = request.json
    selected = data.get('selected', [])
    time_remaining = max(0, int(data.get('time_remaining', 0)))
    hint_used = bool(data.get('hint_used', False))

    all_flag_ids = {rf['id'] for rf in email['red_flags']}
    correct = set(selected) & all_flag_ids
    wrong = set(selected) - all_flag_ids

    score = sum(rf['points'] for rf in email['red_flags'] if rf['id'] in correct)
    penalty = len(wrong) * 10
    score = max(0, score - penalty)
    max_score = sum(rf['points'] for rf in email['red_flags'])
    effective_max = max_score // 2 if hint_used else max_score

    time_bonus  = min(30, time_remaining // 4) if score > 0 else 0
    daily_bonus = check_and_award_daily('phishing', email_id)
    total_score = min(score + time_bonus + daily_bonus, effective_max + daily_bonus)

    with get_db() as conn:
        conn.execute(
            'INSERT INTO scores (quiz_type, item_id, difficulty, score, max_score, timestamp) VALUES (?,?,?,?,?,?)',
            ('phishing', email_id, email['difficulty'], total_score,
             effective_max, datetime.utcnow().isoformat())
        )
        conn.commit()

    result = {
        'score': score, 'time_bonus': time_bonus, 'daily_bonus': daily_bonus,
        'total_score': total_score, 'max_score': effective_max, 'hint_used': hint_used,
        'pct': round(min(total_score, effective_max) / effective_max * 100) if effective_max else 0,
        'correct_flags': [rf for rf in email['red_flags'] if rf['id'] in correct],
        'missed_flags': [rf for rf in email['red_flags'] if rf['id'] not in correct],
        'wrong_count': len(wrong), 'explanation': email['explanation']
    }
    return jsonify(result)


@app.route('/scenarios')
def scenario_list():
    scenarios = load_json('scenarios.json')
    unlocked = get_unlock_status('scenario')
    return render_template('scenario_list.html', scenarios=scenarios, unlocked=unlocked,
                           threshold=UNLOCK_THRESHOLD)


@app.route('/scenarios/<int:scenario_id>')
def scenario_quiz(scenario_id):
    scenarios = load_json('scenarios.json')
    scenario = next((s for s in scenarios if s['id'] == scenario_id), None)
    if not scenario:
        return 'Niet gevonden', 404
    unlocked = get_unlock_status('scenario')
    if scenario['difficulty'] not in unlocked:
        return render_template('locked.html', difficulty=scenario['difficulty'],
                               quiz_type='scenarios', threshold=UNLOCK_THRESHOLD), 403
    time_limit = DIFFICULTY_TIME[scenario['difficulty']]
    return render_template('scenario_quiz.html', scenario=scenario, time_limit=time_limit)


@app.route('/scenarios/<int:scenario_id>/submit', methods=['POST'])
def scenario_submit(scenario_id):
    scenarios = load_json('scenarios.json')
    scenario = next((s for s in scenarios if s['id'] == scenario_id), None)
    if not scenario:
        return jsonify({'error': 'not found'}), 404

    data = request.json
    chosen = data.get('answer')
    timed_out = data.get('timed_out', False)
    hint_used = bool(data.get('hint_used', False))
    option = next((o for o in scenario['options'] if o['id'] == chosen), None)

    effective_max = 50 if hint_used else 100

    if timed_out:
        score = 0
        correct = False
        explanation = 'Tijd verstreken — geen antwoord gegeven.'
        lesson = scenario['lesson']
        tactic = scenario['tactic']
    else:
        if not option:
            return jsonify({'error': 'invalid answer'}), 400
        score = effective_max if option['correct'] else 0
        correct = option['correct']
        explanation = option['explanation']
        lesson = scenario['lesson']
        tactic = scenario['tactic']

    daily_bonus = check_and_award_daily('scenario', scenario_id) if not timed_out else 0
    total_score = score + daily_bonus

    with get_db() as conn:
        conn.execute(
            'INSERT INTO scores (quiz_type, item_id, difficulty, score, max_score, timestamp) VALUES (?,?,?,?,?,?)',
            ('scenario', scenario_id, scenario['difficulty'], total_score, effective_max,
             datetime.utcnow().isoformat())
        )
        conn.commit()

    return jsonify({
        'correct': correct, 'timed_out': timed_out, 'hint_used': hint_used,
        'explanation': explanation, 'lesson': lesson, 'tactic': tactic,
        'score': score, 'daily_bonus': daily_bonus,
        'total_score': total_score, 'max_score': effective_max
    })


@app.route('/login-detector')
def login_detector_list():
    logins = load_json('fake_logins.json')
    unlocked = get_unlock_status('login')
    return render_template('login_detector_list.html', logins=logins, unlocked=unlocked,
                           threshold=UNLOCK_THRESHOLD)


@app.route('/login-detector/<int:login_id>')
def login_detector_sim(login_id):
    logins = load_json('fake_logins.json')
    login = next((l for l in logins if l['id'] == login_id), None)
    if not login:
        return 'Niet gevonden', 404
    unlocked = get_unlock_status('login')
    if login['difficulty'] not in unlocked:
        return render_template('locked.html', difficulty=login['difficulty'],
                               quiz_type='login-detector', threshold=UNLOCK_THRESHOLD), 403
    time_limit = DIFFICULTY_TIME[login['difficulty']]
    return render_template('login_detector_sim.html', login=login, time_limit=time_limit)


@app.route('/login-detector/<int:login_id>/submit', methods=['POST'])
def login_detector_submit(login_id):
    logins = load_json('fake_logins.json')
    login = next((l for l in logins if l['id'] == login_id), None)
    if not login:
        return jsonify({'error': 'not found'}), 404

    data = request.json
    selected = data.get('selected', [])
    time_remaining = max(0, int(data.get('time_remaining', 0)))
    hint_used = bool(data.get('hint_used', False))

    all_flag_ids = {rf['id'] for rf in login['red_flags']}
    correct = set(selected) & all_flag_ids
    wrong = set(selected) - all_flag_ids

    score = sum(rf['points'] for rf in login['red_flags'] if rf['id'] in correct)
    penalty = len(wrong) * 10
    score = max(0, score - penalty)
    max_score = sum(rf['points'] for rf in login['red_flags'])
    effective_max = max_score // 2 if hint_used else max_score
    time_bonus  = min(20, time_remaining // 6) if score > 0 else 0
    daily_bonus = check_and_award_daily('login', login_id)
    total_score = min(score + time_bonus + daily_bonus, effective_max + daily_bonus)

    with get_db() as conn:
        conn.execute(
            'INSERT INTO scores (quiz_type, item_id, difficulty, score, max_score, timestamp) VALUES (?,?,?,?,?,?)',
            ('login', login_id, login['difficulty'], total_score, effective_max,
             datetime.utcnow().isoformat())
        )
        conn.commit()

    return jsonify({
        'score': score, 'time_bonus': time_bonus, 'daily_bonus': daily_bonus,
        'total_score': total_score, 'max_score': effective_max, 'hint_used': hint_used,
        'pct': round(min(total_score, effective_max) / effective_max * 100) if effective_max else 0,
        'correct_flags': [rf for rf in login['red_flags'] if rf['id'] in correct],
        'missed_flags': [rf for rf in login['red_flags'] if rf['id'] not in correct],
        'wrong_count': len(wrong), 'explanation': login['explanation']
    })


@app.route('/headers')
def headers_list():
    headers = load_json('email_headers.json')
    unlocked = get_unlock_status('headers')
    return render_template('headers_list.html', headers=headers, unlocked=unlocked,
                           threshold=UNLOCK_THRESHOLD)


@app.route('/headers/<int:header_id>')
def headers_sim(header_id):
    headers = load_json('email_headers.json')
    header = next((h for h in headers if h['id'] == header_id), None)
    if not header:
        return 'Niet gevonden', 404
    unlocked = get_unlock_status('headers')
    if header['difficulty'] not in unlocked:
        return render_template('locked.html', difficulty=header['difficulty'],
                               quiz_type='headers', threshold=UNLOCK_THRESHOLD), 403
    time_limit = DIFFICULTY_TIME[header['difficulty']]
    return render_template('headers_sim.html', header=header, time_limit=time_limit)


@app.route('/headers/<int:header_id>/submit', methods=['POST'])
def headers_submit(header_id):
    headers = load_json('email_headers.json')
    header = next((h for h in headers if h['id'] == header_id), None)
    if not header:
        return jsonify({'error': 'not found'}), 404

    data = request.json
    selected = data.get('selected', [])
    time_remaining = max(0, int(data.get('time_remaining', 0)))
    hint_used = bool(data.get('hint_used', False))

    all_flag_ids = {rf['id'] for rf in header['red_flags']}
    correct = set(selected) & all_flag_ids
    wrong = set(selected) - all_flag_ids

    score = sum(rf['points'] for rf in header['red_flags'] if rf['id'] in correct)
    penalty = len(wrong) * 10
    score = max(0, score - penalty)
    max_score = sum(rf['points'] for rf in header['red_flags'])
    effective_max = max_score // 2 if hint_used else max_score
    time_bonus  = min(20, time_remaining // 6) if score > 0 else 0
    daily_bonus = check_and_award_daily('headers', header_id)
    total_score = min(score + time_bonus + daily_bonus, effective_max + daily_bonus)

    with get_db() as conn:
        conn.execute(
            'INSERT INTO scores (quiz_type, item_id, difficulty, score, max_score, timestamp) VALUES (?,?,?,?,?,?)',
            ('headers', header_id, header['difficulty'], total_score, effective_max,
             datetime.utcnow().isoformat())
        )
        conn.commit()

    return jsonify({
        'score': score, 'time_bonus': time_bonus, 'daily_bonus': daily_bonus,
        'total_score': total_score, 'max_score': effective_max, 'hint_used': hint_used,
        'pct': round(min(total_score, effective_max) / effective_max * 100) if effective_max else 0,
        'correct_flags': [rf for rf in header['red_flags'] if rf['id'] in correct],
        'missed_flags': [rf for rf in header['red_flags'] if rf['id'] not in correct],
        'wrong_count': len(wrong), 'explanation': header['explanation']
    })


@app.route('/export/csv')
def export_csv():
    import csv
    import io
    emails    = {e['id']: e for e in load_json('phishing_emails.json')}
    scenarios = {s['id']: s for s in load_json('scenarios.json')}
    logins    = {l['id']: l for l in load_json('fake_logins.json')}
    hdr_items = {h['id']: h for h in load_json('email_headers.json')}
    type_map  = {'phishing': emails, 'scenario': scenarios, 'login': logins, 'headers': hdr_items}

    with get_db() as conn:
        rows = conn.execute('SELECT * FROM scores ORDER BY timestamp DESC').fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['timestamp', 'quiz_type', 'item_id', 'category', 'difficulty',
                     'score', 'max_score', 'pct'])
    for r in rows:
        item = type_map.get(r['quiz_type'], {}).get(r['item_id'])
        cat  = item['category'] if item else 'Onbekend'
        pct  = round(r['score'] / r['max_score'] * 100) if r['max_score'] else 0
        writer.writerow([r['timestamp'], r['quiz_type'], r['item_id'], cat,
                         r['difficulty'], r['score'], r['max_score'], pct])

    from flask import Response
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=se_trainer_scores.csv'}
    )


def _all_items():
    emails    = {('phishing',  e['id']): e for e in load_json('phishing_emails.json')}
    scenarios = {('scenario',  s['id']): s for s in load_json('scenarios.json')}
    logins    = {('login',     l['id']): l for l in load_json('fake_logins.json')}
    hdr_items = {('headers',   h['id']): h for h in load_json('email_headers.json')}
    return {**emails, **scenarios, **logins, **hdr_items}


@app.route('/review')
def review_list():
    items = _all_items()
    with get_db() as conn:
        rows = conn.execute('''
            SELECT quiz_type, item_id,
                   COUNT(*) as attempts,
                   MAX(CAST(score AS FLOAT)/max_score*100) as best_pct,
                   MAX(timestamp) as last_played
            FROM scores
            GROUP BY quiz_type, item_id
            ORDER BY last_played DESC
        ''').fetchall()

    entries = []
    for r in rows:
        item = items.get((r['quiz_type'], r['item_id']))
        if not item:
            continue
        title = item.get('subject') or item.get('title') or item.get('category', '?')
        entries.append({
            'quiz_type': r['quiz_type'],
            'item_id': r['item_id'],
            'title': title,
            'category': item.get('category', ''),
            'difficulty': item.get('difficulty', ''),
            'attempts': r['attempts'],
            'best_pct': round(r['best_pct'], 1),
            'last_played': r['last_played'][:16].replace('T', ' ')
        })

    return render_template('review_list.html', entries=entries)


@app.route('/review/<quiz_type>/<int:item_id>')
def review_detail(quiz_type, item_id):
    items = _all_items()
    item = items.get((quiz_type, item_id))
    if not item:
        return 'Niet gevonden', 404

    with get_db() as conn:
        history = conn.execute('''
            SELECT score, max_score, timestamp
            FROM scores
            WHERE quiz_type=? AND item_id=?
            ORDER BY timestamp DESC
            LIMIT 10
        ''', (quiz_type, item_id)).fetchall()

    attempts = [{
        'score': r['score'], 'max_score': r['max_score'],
        'pct': round(r['score'] / r['max_score'] * 100) if r['max_score'] else 0,
        'timestamp': r['timestamp'][:16].replace('T', ' ')
    } for r in history]

    return render_template('review_detail.html', item=item, quiz_type=quiz_type,
                           attempts=attempts)


@app.route('/library')
def library():
    tactics = [
        {
            'name': 'Phishing',
            'icon': '🎣',
            'description': 'Frauduleuze emails die slachtoffers verleiden tot het klikken op links of afstaan van gegevens.',
            'signs': ['Urgentie of dreiging', 'Verdacht afzenderdomein', 'Spelfouten', 'Generieke aanhef', 'Verdachte URL'],
            'defense': 'Hover over links voor je klikt. Verifieer afzender. Bel bedrijf direct bij twijfel.'
        },
        {
            'name': 'Pretexting',
            'icon': '🎭',
            'description': 'Aanvaller creëert een nep-scenario (pretext) om vertrouwen te winnen en info te extraheren.',
            'signs': ['Onverwacht contact', 'Claimen van autoriteit', 'Vraagt om info die ze al zouden moeten hebben', 'Druk om snel te handelen'],
            'defense': 'Verifieer identiteit altijd via onafhankelijk kanaal. Vraag om officieel ticket/ID.'
        },
        {
            'name': 'Vishing',
            'icon': '📞',
            'description': 'Voice phishing — telefonische aanvallen waarbij aanvallers zich voordoen als bank, IT, overheid.',
            'signs': ['Inkomende oproep met urgentie', 'Vraagt om gevoelige info', 'Telefoonnummer kan gespoofed zijn', 'Druk om nu te handelen'],
            'defense': 'Hang op. Bel terug via officieel nummer (website/bankpas). Geef nooit info via inkomende oproepen.'
        },
        {
            'name': 'Baiting',
            'icon': '🪤',
            'description': 'Slachtoffer wordt verleid met iets aantrekkelijks — USB-stick, gratis download, prijs.',
            'signs': ['Te mooi om waar te zijn', 'Gevonden USB-stick', 'Gratis software/content', 'Verkorte URLs'],
            'defense': 'Gebruik nooit gevonden USB-sticks. Download alleen van vertrouwde bronnen. Gratis = risico.'
        },
        {
            'name': 'Tailgating',
            'icon': '🚪',
            'description': 'Fysieke SE — ongeautoriseerde persoon volgt medewerker door beveiligde toegang.',
            'signs': ['Vraagt deur open te houden', 'Vol handen / uniform', 'Doet vriendelijk / beroept op sympathie', 'Claimt medewerker te zijn'],
            'defense': 'Elke persoon authenticeert zelf. Verwijst bezoekers naar receptie. Meld verdachte situaties.'
        },
        {
            'name': 'Business Email Compromise (BEC)',
            'icon': '💼',
            'description': 'Aanvaller imiteert executive of leverancier via nep-email om grote betalingen of data te stelen.',
            'signs': ['Spoedoverboeking via email', "Vraagt 'hou dit geheim'", 'Licht afwijkend domein (typosquat)', 'Omzeilt normale procedures'],
            'defense': 'Verifieer betalingsverzoeken altijd telefonisch via bekend nummer. Vier-ogen-principe voor overboekingen.'
        },
        {
            'name': 'Quid Pro Quo',
            'icon': '🤝',
            'description': 'Aanvaller biedt dienst of voordeel aan in ruil voor info of toegang.',
            'signs': ['Onverwacht aanbod van hulp', 'IT-support die ongevraagd contact opneemt', 'Vraagt toegang in ruil voor oplossing'],
            'defense': 'Gebruik alleen officiële IT-kanalen. Geen toegang verlenen aan onbekenden, ook niet als ze helpen.'
        }
    ]
    return render_template('library.html', tactics=tactics)


@app.route('/dashboard')
def dashboard():
    emails    = {e['id']: e for e in load_json('phishing_emails.json')}
    scenarios = {s['id']: s for s in load_json('scenarios.json')}
    logins    = {l['id']: l for l in load_json('fake_logins.json')}
    hdr_items = {h['id']: h for h in load_json('email_headers.json')}

    with get_db() as conn:
        rows = conn.execute('SELECT * FROM scores ORDER BY timestamp DESC').fetchall()

    category_stats = {}
    difficulty_stats = {'beginner': [], 'intermediate': [], 'advanced': []}
    total_attempts = len(rows)
    recent_scores = []

    type_map = {'phishing': emails, 'scenario': scenarios, 'login': logins, 'headers': hdr_items}

    for r in rows:
        pct = r['score'] / r['max_score'] * 100 if r['max_score'] else 0
        item_dict = type_map.get(r['quiz_type'], {})
        item = item_dict.get(r['item_id'])
        cat = item['category'] if item else 'Onbekend'

        if cat not in category_stats:
            category_stats[cat] = {'scores': [], 'quiz_type': r['quiz_type']}
        category_stats[cat]['scores'].append(pct)

        if r['difficulty'] in difficulty_stats:
            difficulty_stats[r['difficulty']].append(pct)

        if len(recent_scores) < 10:
            recent_scores.append({
                'quiz_type': r['quiz_type'],
                'category': cat,
                'difficulty': r['difficulty'],
                'pct': round(pct),
                'timestamp': r['timestamp'][:16].replace('T', ' ')
            })

    category_avgs = {
        cat: {'avg': round(sum(d['scores']) / len(d['scores']), 1),
              'attempts': len(d['scores']),
              'quiz_type': d['quiz_type']}
        for cat, d in category_stats.items()
    }

    sorted_cats = sorted(category_avgs.items(), key=lambda x: x[1]['avg'])
    weakest = sorted_cats[:3]
    strongest = sorted_cats[-3:][::-1]

    diff_avgs = {
        d: round(sum(v) / len(v), 1) if v else None
        for d, v in difficulty_stats.items()
    }

    overall_avg = round(sum(
        r['score'] / r['max_score'] * 100 for r in rows if r['max_score']
    ) / len(rows), 1) if rows else None

    return render_template('dashboard.html',
        category_avgs=category_avgs,
        weakest=weakest,
        strongest=strongest,
        diff_avgs=diff_avgs,
        overall_avg=overall_avg,
        total_attempts=total_attempts,
        recent_scores=recent_scores
    )


@app.route('/stats')
def stats():
    with get_db() as conn:
        recent = conn.execute(
            'SELECT * FROM scores ORDER BY timestamp DESC LIMIT 20'
        ).fetchall()
        totals = conn.execute('''
            SELECT quiz_type, difficulty,
                   COUNT(*) as attempts,
                   ROUND(AVG(CAST(score AS FLOAT)/max_score*100), 1) as avg_pct
            FROM scores
            GROUP BY quiz_type, difficulty
            ORDER BY quiz_type, difficulty
        ''').fetchall()
    return render_template('stats.html', recent=recent, totals=totals)


if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5001)
