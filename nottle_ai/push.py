"""FCM delivery to authenticated, unexpired app sessions only."""
import json
from .security import utc_now


class Push:
    def __init__(self, db, settings):
        self.db, self.settings = db, settings
        with db.connect() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS push_devices (
                token TEXT PRIMARY KEY,
                session_hash TEXT NOT NULL REFERENCES sessions(token_hash) ON DELETE CASCADE,
                business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE
            )''')

    def register(self, token, session_hash, business_id):
        with self.db.connect() as conn:
            conn.execute('DELETE FROM push_devices WHERE session_hash=? AND token<>?', (session_hash, token))
            conn.execute('INSERT INTO push_devices VALUES(?,?,?) ON CONFLICT(token) DO UPDATE SET '
                         'session_hash=excluded.session_hash,business_id=excluded.business_id',
                         (token, session_hash, business_id))

    def send(self, row, kind):
        import firebase_admin
        from firebase_admin import credentials, messaging
        if not self.settings.firebase_service_account_json:
            raise RuntimeError('Firebase not configured')
        try:
            app = firebase_admin.get_app('nottle-push')
        except ValueError:
            app = firebase_admin.initialize_app(credentials.Certificate(
                json.loads(self.settings.firebase_service_account_json)), name='nottle-push')
        with self.db.connect() as conn:
            tokens = [r['token'] for r in conn.execute('''SELECT p.token FROM push_devices p
                JOIN sessions s ON p.session_hash=s.token_hash
                WHERE p.business_id=? AND s.expires_at>?''', (row['business_id'], utc_now()))]
        if not tokens:
            raise RuntimeError('No registered device')
        for token in tokens:
            try:
                messaging.send(messaging.Message(token=token,
                    notification=messaging.Notification(title='NOTTLE AI', body=(
                        'New customer enquiry. Tap to review and reply.' if kind == 'push_request'
                        else 'Appointment status updated. Tap to review before messaging your customer.')),
                    data={'call_id': str(row['call_id'])},
                    android=messaging.AndroidConfig(collapse_key=f"booking-{row['id']}",
                        notification=messaging.AndroidNotification(channel_id='customer_calls',
                            tag=f"booking-{row['id']}"))), app=app)
            except messaging.UnregisteredError:
                with self.db.connect() as conn:
                    conn.execute('DELETE FROM push_devices WHERE token=?', (token,))
