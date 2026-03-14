from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, join_room, leave_room, emit
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
import uuid
import json
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ludo-secret-key-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")
login_manager = LoginManager(app)
login_manager.login_view = 'login'


# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# Global Game State
games = {}
rooms = {}


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/')
def index():
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])

        if User.query.filter_by(username=username).first():
            return render_template('register.html', error='Username already exists!')

        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            return redirect(url_for('lobby'))
        return render_template('login.html', error='Invalid credentials!')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/lobby')
@login_required
def lobby():
    return render_template('lobby.html', username=current_user.username)


@app.route('/create_game', methods=['POST'])
@login_required
def create_game():
    game_id = str(uuid.uuid4())[:8]
    games[game_id] = {
        'players': [current_user.username],
        'max_players': 4,
        'host': current_user.username,
        'status': 'waiting'
    }
    return jsonify({'game_id': game_id, 'url': url_for('game', game_id=game_id, _external=True)})


@app.route('/join_game/<game_id>')
@login_required
def join_game(game_id):
    if game_id in games:
        if len(games[game_id]['players']) < games[game_id]['max_players']:
            games[game_id]['players'].append(current_user.username)
            return redirect(url_for('game', game_id=game_id))
    return redirect(url_for('lobby'))


@app.route('/game/<game_id>')
@login_required
def game(game_id):
    if game_id not in games or current_user.username not in games[game_id]['players']:
        return redirect(url_for('lobby'))
    return render_template('game.html', game_id=game_id, game=games[game_id])


# SocketIO Events
@socketio.on('join')
def on_join(data):
    game_id = data['game_id']
    username = data['username']
    join_room(game_id)
    emit('status', {'msg': f'{username} joined the game!'}, room=game_id)

    # Start game if 4 players
    if len(games[game_id]['players']) == 4:
        games[game_id]['status'] = 'started'
        emit('start_game', {'players': games[game_id]['players']}, room=game_id)


@socketio.on('move')
def on_move(data):
    game_id = data['game_id']
    emit('player_moved', data, room=game_id)


@socketio.on('roll_dice')
def on_roll_dice(data):
    game_id = data['game_id']
    import random
    dice = random.randint(1, 6)
    emit('dice_result', {'dice': dice, 'player': data['player']}, room=game_id)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)