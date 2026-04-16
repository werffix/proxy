#!/usr/bin/env python3
# app.py — простой генератор прокси для пользователей
import os, secrets, subprocess, json
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# ⚙️ НАСТРОЙКИ
CONFIG = {
    "server_ip": os.getenv("SERVER_IP", "your.server.ip"),
    "proxy_port": int(os.getenv("PROXY_PORT", 443)),
    "mtproto_path": "/opt/mtproto_proxy",
    "config_file": "/opt/mtproto_proxy/config/prod-sys.config"
}

# 📢 ЖЁСТКО ЗАШИТЫЙ СПОНСОРСКИЙ TAG
SPONSOR_TAG = "baa70264aaf0a772b7946b62036b06ee"

def generate_secret():
    return secrets.token_hex(16)

def add_secret_to_config(secret, tag, user_hint=""):
    """Добавляет новый секрет в конфиг прокси"""
    name = f"mtp_{user_hint or secrets.token_hex(4)}"
    
    new_entry = f'''    #{name => {name},
       listen_ip => "0.0.0.0",
       port => {CONFIG['proxy_port']},
       secret => <<"{secret}">>,
       tag => <<"{tag}">>}}'''
    
    with open(CONFIG["config_file"], 'r', encoding='utf-8') as f:
        content = f.read()
    
    import re
    match = re.search(r'(\{ports,\s*\[)([\s\S]*?)(\]\s*\})', content)
    if match:
        prefix, ports_body, suffix = match.groups()
        if ports_body.strip() and not ports_body.rstrip().endswith(','):
            ports_body += ','
        new_ports = f"{prefix}{ports_body}\n{new_entry}{suffix}"
        content = content[:match.start()] + new_ports + content[match.end():]
        
        with open(CONFIG["config_file"], 'w', encoding='utf-8') as f:
            f.write(content)
        
        try:
            subprocess.run(['sudo', 'make', '-C', CONFIG['mtproto_path'], 'update-sysconfig'], check=True, capture_output=True)
            subprocess.run(['sudo', 'systemctl', 'reload', 'mtproto-proxy'], check=True, capture_output=True)
            return True
        except Exception as e:
            print(f"⚠️ Reload error: {e}")
            return False
    return False

def make_proxy_link(secret, fake_tls=False, tls_domain=""):
    if fake_tls and tls_domain:
        full_secret = f"ee{secret}{tls_domain.encode().hex()}"
    else:
        full_secret = secret
    
    return (f"https://t.me/proxy?server={CONFIG['server_ip']}"
            f"&port={CONFIG['proxy_port']}&secret={full_secret}")

@app.route('/')
def index():
    return render_template('index.html', server=CONFIG['server_ip'], port=CONFIG['proxy_port'])

@app.route('/api/generate', methods=['POST'])
def generate():
    data = request.json or {}
    
    user_id = (data.get('user_id') or f"user_{secrets.token_hex(4)}").strip().replace(' ', '_')
    fake_tls = data.get('fake_tls', False)
    tls_domain = data.get('tls_domain', '').strip() if fake_tls else ""
    
    secret = generate_secret()
    
    # 🔒 TAG ВСЕГДА БЕРЁТСЯ ИЗ КОНСТАНТЫ
    if not add_secret_to_config(secret, SPONSOR_TAG, user_id):
        return jsonify({'error': 'Не удалось активировать прокси. Попробуйте позже.'}), 500
    
    link = make_proxy_link(secret, fake_tls, tls_domain)
    
    return jsonify({
        'success': True,
        'user_id': user_id,
        'secret': secret,
        'proxy_link': link,
        'sponsor_tag': SPONSOR_TAG,
        'instructions': """
1. Откройте ссылку ниже в Telegram
2. Нажмите «Подключиться»
3. Готово! Ваш трафик идёт через персональный прокси 🎉
        """.strip()
    })

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000)
