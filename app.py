import json
import os
from datetime import datetime
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
        conn.commit()


DIFFICULTY_TIME = {'beginner': 120, 'intermediate': 90, 'advanced': 60}
UNLOCK_THRESHOLD = 2
UNLOCK_MIN_PCT = 50


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
    return render_template('index.html', stats=stats)


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

    time_bonus = min(30, time_remaining // 4) if score > 0 else 0
    total_score = min(score + time_bonus, effective_max)

    with get_db() as conn:
        conn.execute(
            'INSERT INTO scores (quiz_type, item_id, difficulty, score, max_score, timestamp) VALUES (?,?,?,?,?,?)',
            ('phishing', email_id, email['difficulty'], total_score,
             effective_max, datetime.utcnow().isoformat())
        )
        conn.commit()

    result = {
        'score': score,
        'time_bonus': time_bonus,
        'total_score': total_score,
        'max_score': effective_max,
        'pct': round(total_score / effective_max * 100) if effective_max else 0,
        'hint_used': hint_used,
        'correct_flags': [rf for rf in email['red_flags'] if rf['id'] in correct],
        'missed_flags': [rf for rf in email['red_flags'] if rf['id'] not in correct],
        'wrong_count': len(wrong),
        'explanation': email['explanation']
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

    with get_db() as conn:
        conn.execute(
            'INSERT INTO scores (quiz_type, item_id, difficulty, score, max_score, timestamp) VALUES (?,?,?,?,?,?)',
            ('scenario', scenario_id, scenario['difficulty'], score, effective_max,
             datetime.utcnow().isoformat())
        )
        conn.commit()

    return jsonify({
        'correct': correct,
        'timed_out': timed_out,
        'hint_used': hint_used,
        'explanation': explanation,
        'lesson': lesson,
        'tactic': tactic,
        'score': score,
        'max_score': effective_max
    })


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
    emails = {e['id']: e for e in load_json('phishing_emails.json')}
    scenarios = {s['id']: s for s in load_json('scenarios.json')}

    with get_db() as conn:
        rows = conn.execute('SELECT * FROM scores ORDER BY timestamp DESC').fetchall()

    category_stats = {}
    difficulty_stats = {'beginner': [], 'intermediate': [], 'advanced': []}
    total_attempts = len(rows)
    recent_scores = []

    for r in rows:
        pct = r['score'] / r['max_score'] * 100 if r['max_score'] else 0
        if r['quiz_type'] == 'phishing':
            item = emails.get(r['item_id'])
            cat = item['category'] if item else 'Onbekend'
        else:
            item = scenarios.get(r['item_id'])
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
