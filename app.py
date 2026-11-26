import os
import re
import sqlite3
import requests
from datetime import datetime, timedelta
from urllib.parse import quote
from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify

app = Flask(__name__)

app.secret_key = "chave_secreta_chama_ai_servicos_2026_v3"
SENHA_ADMIN = "22041988"

PIX_PADRAO = "997ef3d7-4a1c-436f-b4fa-2c668ad2478c"
WPP_PADRAO = "5544998258119"

VALOR_30D_PADRAO = "R$ 19,90"
VALOR_90D_PADRAO = "R$ 44,90"
LIMITE_VAGAS_VIP = 4
SENHA_CLIENTES_VIP_PADRAO = "VIP2026"
ITENS_POR_PAGINA = 12

DATABASE_URL = os.environ.get("DATABASE_URL")
DB_NAME = "vitrine.db"

class DBWrapper:
    def __init__(self):
        self.is_pg = bool(DATABASE_URL)
        if self.is_pg:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            self.conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        else:
            self.conn = sqlite3.connect(DB_NAME)
            self.conn.row_factory = sqlite3.Row

    def execute(self, query, params=()):
        if self.is_pg:
            query = query.replace("?", "%s")
            query = query.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
            query = query.replace("INSERT OR IGNORE INTO config", "INSERT INTO config")
            if "INSERT INTO config" in query and "ON CONFLICT" not in query:
                query += " ON CONFLICT (chave) DO NOTHING"
        cur = self.conn.cursor()
        cur.execute(query, params)
        return cur

    def insert_returning_id(self, query, params=()):
        cur = self.conn.cursor()
        if self.is_pg:
            query = query.replace("?", "%s") + " RETURNING id"
            cur.execute(query, params)
            row = cur.fetchone()
            return row["id"]
        else:
            cur.execute(query, params)
            return cur.lastrowid

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

def init_db():
    db = DBWrapper()
    db.execute("""
        CREATE TABLE IF NOT EXISTS servicos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            titulo TEXT NOT NULL,
            categoria TEXT NOT NULL,
            cidade TEXT NOT NULL,
            preco TEXT NOT NULL,
            descricao TEXT NOT NULL,
            contato TEXT NOT NULL,
            imagem TEXT,
            destaque_ate TEXT,
            criado_em TEXT NOT NULL,
            visualizacoes INTEGER DEFAULT 0,
            cliques_wpp INTEGER DEFAULT 0,
            pin_edicao TEXT DEFAULT '0000'
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS avaliacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            servico_id INTEGER NOT NULL,
            autor TEXT NOT NULL,
            estrelas INTEGER NOT NULL,
            comentario TEXT,
            criado_em TEXT NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_nome TEXT NOT NULL,
            categoria TEXT NOT NULL,
            cidade TEXT NOT NULL,
            descricao TEXT NOT NULL,
            whatsapp TEXT NOT NULL,
            criado_em TEXT NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS pagamentos_pix (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mp_payment_id TEXT UNIQUE,
            servico_id INTEGER NOT NULL,
            dias INTEGER NOT NULL,
            valor REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            qr_code TEXT,
            criado_em TEXT NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS config (
            chave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        )
    """)
    db.commit()

    colunas_novas = [
        ("visualizacoes", "INTEGER DEFAULT 0"),
        ("cliques_wpp", "INTEGER DEFAULT 0"),
        ("pin_edicao", "TEXT DEFAULT '0000'")
    ]
    for col, tipo in colunas_novas:
        try:
            db.execute(f"ALTER TABLE servicos ADD COLUMN {col} {tipo}")
            db.commit()
        except Exception:
            db.conn.rollback()

    padroes = {
        "chave_pix": PIX_PADRAO,
        "mp_access_token": os.environ.get("MP_ACCESS_TOKEN", ""),
        "seu_whatsapp": WPP_PADRAO,
        "valor_30d": VALOR_30D_PADRAO,
        "valor_90d": VALOR_90D_PADRAO,
        "senha_vip_clientes": SENHA_CLIENTES_VIP_PADRAO,
        "banner_ativo": "1",
        "banner_titulo": "Espaço Reservado para Patrocinador Local",
        "banner_texto": "Divulgue sua loja ou empresa aqui para milhares de clientes de Formosa, Goioerê, Assis e região!",
        "banner_link": f"https://wa.me/{WPP_PADRAO}?text=Olá!%20Tenho%20interesse%20no%20espaço%20de%20patrocinador%20do%20Chama%20Aí%20Serviços."
    }
    for k, v in padroes.items():
        db.execute("INSERT OR IGNORE INTO config (chave, valor) VALUES (?, ?)", (k, v))
    db.commit()
    db.close()

def get_config():
    db = DBWrapper()
    rows = db.execute("SELECT chave, valor FROM config").fetchall()
    db.close()
    return {r["chave"]: r["valor"] for r in rows}

def formatar_whatsapp(contato):
    numeros = "".join(filter(str.isdigit, contato))
    if len(numeros) in (10, 11):
        return f"https://wa.me/55{numeros}"
    elif len(numeros) in (12, 13) and numeros.startswith("55"):
        return f"https://wa.me/{numeros}"
    return None

def extrair_valor_float(valor_texto):
    limpo = re.sub(r"[^\d,\.]", "", valor_texto).replace(",", ".")
    try:
        return round(float(limpo), 2)
    except ValueError:
        return 19.90

def gerar_pix_copia_cola(chave_pix, valor_texto, txid="CHAMAAIVIP"):
    def emv(tag, val):
        return f"{tag}{len(val):02d}{val}"

    valor_str = f"{extrair_valor_float(valor_texto):.2f}"
    merchant_account = emv("00", "br.gov.bcb.pix") + emv("01", chave_pix.strip())
    payload = (
        emv("00", "01") +
        emv("26", merchant_account) +
        emv("52", "0000") +
        emv("53", "986") +
        emv("54", valor_str) +
        emv("58", "BR") +
        emv("59", "CHAMA AI SERVICOS") +
        emv("60", "BRASIL") +
        emv("62", emv("05", re.sub(r"[^a-zA-Z0-9]", "", txid)[:20] or "VIP")) +
        "6304"
    )

    crc = 0xFFFF
    for char in payload:
        crc ^= ord(char) << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF

    return f"{payload}{crc:04X}"

def ativar_destaque_automatico(db, servico_id, dias):
    row = db.execute("SELECT destaque_ate FROM servicos WHERE id = ?", (servico_id,)).fetchone()
    agora = datetime.now()
    base = agora
    if row and row["destaque_ate"]:
        atual = datetime.fromisoformat(row["destaque_ate"])
        if atual > agora:
            base = atual
    nova_validade = (base + timedelta(days=int(dias))).isoformat()
    db.execute("UPDATE servicos SET destaque_ate = ? WHERE id = ?", (nova_validade, servico_id))

HTML_BASE_CSS = """
<style>
    :root {
        --primary: #0f172a;
        --secondary: #1e293b;
        --accent: #16a34a;
        --accent-hover: #15803d;
        --blue-cta: #2563eb;
        --blue-cta-hover: #1d4ed8;
        --vip: #f59e0b;
        --vip-dark: #d97706;
        --bg: #f1f5f9;
        --text: #1e293b;
        --muted: #64748b;
    }
    * { box-sizing: border-box; }
    body {
        font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
        background-color: var(--bg);
        color: var(--text);
        margin: 0;
        padding: 0;
    }
    .top-bar {
        background: #020617;
        color: #94a3b8;
        padding: 8px 20px;
        font-size: 13px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 8px;
    }
    .top-bar a { color: #cbd5e1; text-decoration: none; margin-left: 15px; font-weight: 500; }
    .top-bar a:hover { color: white; }

    header {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%);
        color: white;
        padding: 36px 20px 28px 20px;
        text-align: center;
    }
    .region-pill {
        display: inline-block;
        background: rgba(255, 255, 255, 0.14);
        color: #93c5fd;
        font-size: 12px;
        font-weight: 700;
        padding: 4px 12px;
        border-radius: 20px;
        margin-bottom: 10px;
        letter-spacing: 0.4px;
    }
    header h1 { margin: 0 0 10px 0; font-size: 32px; letter-spacing: -0.5px; }
    header p { margin: 0 auto 22px auto; color: #e2e8f0; font-size: 16px; max-width: 640px; }

    .cta-hero-group {
        display: flex;
        gap: 12px;
        justify-content: center;
        flex-wrap: wrap;
        margin-bottom: 22px;
    }
    .btn-hero {
        background: var(--accent);
        color: white;
        border: none;
        padding: 14px 24px;
        font-size: 15px;
        font-weight: bold;
        border-radius: 8px;
        cursor: pointer;
        box-shadow: 0 4px 14px rgba(22, 163, 74, 0.4);
        transition: transform 0.15s, background 0.15s;
        text-decoration: none;
        display: inline-flex;
        align-items: center;
        gap: 8px;
    }
    .btn-hero:hover { background: var(--accent-hover); transform: translateY(-1px); }
    .btn-hero-blue {
        background: var(--blue-cta);
        box-shadow: 0 4px 14px rgba(37, 99, 235, 0.4);
    }
    .btn-hero-blue:hover { background: var(--blue-cta-hover); }

    .social-proof-bar {
        display: flex;
        justify-content: center;
        gap: 20px;
        flex-wrap: wrap;
        font-size: 13px;
        color: #cbd5e1;
        border-top: 1px solid rgba(255,255,255,0.12);
        padding-top: 14px;
        max-width: 800px;
        margin: 0 auto;
    }
    .social-proof-bar strong { color: #4ade80; }

    .container { max-width: 1140px; margin: 24px auto; padding: 0 20px; }

    .sponsor-banner {
        background: linear-gradient(90deg, #1e293b 0%, #334155 100%);
        border-left: 5px solid var(--vip);
        color: white;
        padding: 15px 22px;
        border-radius: 10px;
        margin-bottom: 24px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 15px;
        flex-wrap: wrap;
        text-decoration: none;
        box-shadow: 0 2px 10px rgba(0,0,0,0.08);
    }
    .sponsor-badge {
        background: rgba(245, 158, 11, 0.2);
        color: #fbbf24;
        font-size: 11px;
        font-weight: bold;
        padding: 3px 8px;
        border-radius: 4px;
        text-transform: uppercase;
        display: inline-block;
        margin-bottom: 4px;
    }
    .sponsor-banner h4 { margin: 0 0 4px 0; font-size: 17px; color: white; }
    .sponsor-banner p { margin: 0; font-size: 13px; color: #cbd5e1; }
    .sponsor-cta {
        background: var(--vip);
        color: #0f172a;
        padding: 9px 16px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 13px;
        white-space: nowrap;
    }

    .leads-section {
        background: #eff6ff;
        border: 1px solid #bfdbfe;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 25px;
    }
    .leads-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 10px;
        margin-bottom: 14px;
    }
    .leads-header h3 { margin: 0; color: #1e3a8a; font-size: 18px; display: flex; align-items: center; gap: 8px; }
    .leads-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
        gap: 14px;
    }
    .lead-card {
        background: white;
        padding: 15px;
        border-radius: 8px;
        border-left: 4px solid var(--blue-cta);
        box-shadow: 0 2px 6px rgba(0,0,0,0.04);
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }
    .lead-meta { font-size: 11px; color: var(--muted); font-weight: 600; margin-bottom: 6px; }
    .lead-desc { font-size: 13px; color: var(--text); margin: 0 0 12px 0; line-height: 1.4; }
    .btn-lead-locked {
        background: #f1f5f9;
        color: #475569;
        border: 1px dashed #94a3b8;
        padding: 8px;
        border-radius: 6px;
        font-size: 12px;
        font-weight: bold;
        cursor: pointer;
        text-align: center;
        width: 100%;
    }
    .btn-lead-locked:hover { background: #e2e8f0; color: var(--primary); }

    .search-wrapper {
        background: white;
        padding: 16px;
        border-radius: 10px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        margin-bottom: 22px;
    }
    .busca-bar { display: flex; gap: 10px; flex-wrap: wrap; }
    .busca-bar input {
        flex: 1;
        min-width: 220px;
        padding: 11px 14px;
        border: 1px solid #cbd5e1;
        border-radius: 7px;
        font-size: 14px;
    }
    .btn {
        background-color: var(--accent);
        color: white;
        border: none;
        padding: 11px 20px;
        font-size: 14px;
        border-radius: 7px;
        cursor: pointer;
        font-weight: bold;
        text-decoration: none;
        display: inline-block;
        text-align: center;
    }
    .btn:hover { background-color: var(--accent-hover); }
    .btn-vip { background-color: var(--vip-dark); color: white; }
    .btn-vip:hover { background-color: #b45309; }
    .btn-danger { background-color: #dc2626; padding: 6px 12px; font-size: 12px; }
    .btn-sm { padding: 6px 12px; font-size: 12px; }

    .filtros-label { font-size: 12px; font-weight: 700; color: var(--muted); margin: 14px 0 6px 0; text-transform: uppercase; }
    .filtros { display: flex; gap: 8px; flex-wrap: wrap; }
    .filtro-btn {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        padding: 7px 13px;
        border-radius: 20px;
        text-decoration: none;
        color: #334155;
        font-size: 13px;
        font-weight: 600;
        transition: all 0.15s;
    }
    .filtro-btn.ativo, .filtro-btn:hover {
        background: var(--primary);
        color: white;
        border-color: var(--primary);
    }
    .cidade-pill.ativo, .cidade-pill:hover {
        background: var(--blue-cta);
        border-color: var(--blue-cta);
        color: white;
    }

    .scarcity-bar {
        background: #fffbeb;
        border: 1px solid #fde68a;
        color: #92400e;
        padding: 10px 16px;
        border-radius: 8px;
        margin-bottom: 18px;
        font-size: 13px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 10px;
    }

    .grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
        gap: 22px;
        align-items: start;
    }
    .card {
        background: white;
        border-radius: 12px;
        box-shadow: 0 3px 10px rgba(0,0,0,0.06);
        border-top: 4px solid #94a3b8;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        position: relative;
        overflow: hidden;
        transition: transform 0.15s;
    }
    .card:hover { transform: translateY(-2px); }
    .card.destaque {
        border: 2px solid var(--vip);
        border-top: 6px solid var(--vip);
        background: linear-gradient(to bottom, #fffdf5, #ffffff);
        box-shadow: 0 6px 20px rgba(245, 158, 11, 0.22);
    }
    .card-img-wrapper {
        width: 100%;
        background-color: #f8fafc;
        border-bottom: 1px solid #e2e8f0;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    .card-img {
        width: 100%;
        height: auto;
        max-height: 380px;
        object-fit: contain;
        display: block;
    }
    .card-body {
        padding: 20px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        flex: 1;
    }
    .badge-vip {
        position: absolute;
        top: 12px;
        right: 12px;
        background: linear-gradient(135deg, #f59e0b, #d97706);
        color: white;
        font-size: 11px;
        font-weight: bold;
        padding: 5px 11px;
        border-radius: 20px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.25);
        letter-spacing: 0.4px;
        z-index: 2;
    }
    .tags-row { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; align-items: center; }
    .categoria {
        font-size: 11px;
        background: #e2e8f0;
        color: #334155;
        padding: 3px 9px;
        border-radius: 12px;
        font-weight: 600;
    }
    .cidade-tag {
        font-size: 11px;
        background: #dbeafe;
        color: #1e40af;
        padding: 3px 9px;
        border-radius: 12px;
        font-weight: 600;
    }
    .rating-pill {
        font-size: 12px;
        color: #b45309;
        font-weight: bold;
        margin-left: auto;
    }
    .card h3 { margin: 4px 0 8px 0; color: var(--primary); font-size: 19px; }
    .descricao { font-size: 14px; color: #475569; line-height: 1.5; margin-bottom: 12px; }
    .preco { font-size: 21px; font-weight: 800; color: var(--accent); margin: 8px 0; }
    
    .metrics-pill {
        display: flex;
        gap: 12px;
        font-size: 11px;
        color: var(--muted);
        background: #f8fafc;
        padding: 6px 10px;
        border-radius: 6px;
        margin-bottom: 10px;
        border: 1px solid #e2e8f0;
    }
    .metrics-pill span { display: inline-flex; align-items: center; gap: 4px; font-weight: 600; }

    .reviews-preview {
        background: #f8fafc;
        border-radius: 6px;
        padding: 8px 10px;
        font-size: 12px;
        color: #475569;
        margin-bottom: 10px;
        border-left: 3px solid #cbd5e1;
    }

    .footer-card {
        border-top: 1px solid #e2e8f0;
        padding-top: 12px;
        margin-top: 8px;
        font-size: 13px;
        color: #475569;
    }
    .btn-wpp {
        display: block;
        background: #25D366;
        color: white;
        text-align: center;
        padding: 10px;
        border-radius: 7px;
        text-decoration: none;
        font-weight: bold;
        margin-top: 10px;
        font-size: 14px;
    }
    .btn-wpp:hover { background: #1ebe5d; }
    
    .card-actions-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 12px;
        padding-top: 10px;
        border-top: 1px dashed #e2e8f0;
        font-size: 12px;
    }
    .action-link {
        color: var(--muted);
        text-decoration: none;
        font-weight: 600;
        cursor: pointer;
        background: none;
        border: none;
        padding: 0;
        font-size: 12px;
    }
    .action-link:hover { color: var(--primary); text-decoration: underline; }
    .action-vip { color: var(--vip-dark); }

    .load-more-wrapper {
        text-align: center;
        margin: 30px 0 10px 0;
    }

    .alert-banner {
        padding: 12px 16px;
        border-radius: 8px;
        margin-bottom: 18px;
        font-weight: 600;
        font-size: 14px;
    }
    .alert-error { background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }
    .alert-success { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }

    .modal-overlay {
        display: none;
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        background: rgba(15, 23, 42, 0.75);
        z-index: 1000;
        overflow-y: auto;
        padding: 20px;
    }
    .modal-box {
        background: white;
        max-width: 650px;
        margin: 20px auto;
        padding: 28px;
        border-radius: 12px;
        position: relative;
        box-shadow: 0 10px 30px rgba(0,0,0,0.3);
    }
    .modal-close {
        position: absolute;
        top: 18px;
        right: 20px;
        font-size: 24px;
        background: none;
        border: none;
        cursor: pointer;
        color: var(--muted);
    }
    .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
    @media (max-width: 650px) { .form-grid { grid-template-columns: 1fr; } }
    .form-group { margin-bottom: 12px; }
    .full-width { grid-column: 1 / -1; }
    label { display: block; font-weight: 600; margin-bottom: 5px; font-size: 13px; }
    input, textarea, select {
        width: 100%;
        padding: 10px 12px;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        font-size: 14px;
    }
    .vip-box {
        background: #fffbeb;
        border: 2px solid var(--vip);
        padding: 14px;
        border-radius: 8px;
        margin: 14px 0;
    }
    .vip-box label {
        display: flex;
        align-items: flex-start;
        gap: 10px;
        cursor: pointer;
        margin: 0;
        color: #92400e;
        font-size: 14px;
    }
    .vip-box input[type="checkbox"] { width: 18px; height: 18px; margin-top: 2px; }
    .card-box {
        background: white;
        padding: 25px;
        border-radius: 10px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.08);
        margin-bottom: 25px;
    }
    .plan-selector {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
        margin: 15px 0;
    }
    @media (max-width: 500px) { .plan-selector { grid-template-columns: 1fr; } }
    .plan-card {
        border: 2px solid #cbd5e1;
        border-radius: 10px;
        padding: 15px;
        text-decoration: none;
        color: var(--text);
        display: block;
        position: relative;
        transition: all 0.15s;
    }
    .plan-card.active {
        border-color: var(--vip);
        background: #fffbeb;
        box-shadow: 0 4px 12px rgba(245, 158, 11, 0.2);
    }
    .plan-tag {
        position: absolute;
        top: -10px;
        right: 10px;
        background: var(--accent);
        color: white;
        font-size: 10px;
        font-weight: bold;
        padding: 2px 8px;
        border-radius: 10px;
    }
</style>
"""

HTML_CARDS_FRAGMENT = """
{% for item in servicos %}
<div class="card {{ 'destaque' if item.is_vip else '' }}">
    {% if item.is_vip %}
        <span class="badge-vip">★ PROFISSIONAL DESTAQUE</span>
    {% endif %}
    {% if item.imagem %}
        <div class="card-img-wrapper">
            <img src="{{ item.imagem }}" alt="{{ item.titulo }}" class="card-img" loading="lazy">
        </div>
    {% endif %}
    <div class="card-body">
        <div>
            <div class="tags-row">
                <span class="categoria">{{ item.categoria }}</span>
                <span class="cidade-tag">📍 {{ item.cidade }}</span>
                {% if item.total_aval > 0 %}
                    <span class="rating-pill">★ {{ item.media_estrelas }} ({{ item.total_aval }})</span>
                {% endif %}
            </div>
            <h3>{{ item.titulo }}</h3>
            <p class="descricao">{{ item.descricao }}</p>
            
            {% if item.ultimo_comentario %}
                <div class="reviews-preview">
                    <em>"{{ item.ultimo_comentario.comentario }}"</em> — <strong>{{ item.ultimo_comentario.autor }}</strong>
                </div>
            {% endif %}
        </div>

        <div>
            <div class="preco">{{ item.preco }}</div>
            
            <div class="metrics-pill">
                <span>👁️ {{ item.visualizacoes }} visualizações</span>
                {% if item.is_vip %}
                    <span>💬 {{ item.cliques_wpp }} cliques no WhatsApp</span>
                {% endif %}
            </div>

            <div class="footer-card">
                <strong>Profissional:</strong> {{ item.nome }}<br>
                <strong>Contato:</strong> {{ item.contato }}
                
                {% if item.is_vip and item.wpp_link %}
                    <a href="/whatsapp/{{ item.id }}" target="_blank" class="btn-wpp">
                        💬 Chamar no WhatsApp
                    </a>
                {% endif %}
            </div>

            <div class="card-actions-row">
                <button onclick="abrirAvaliacao({{ item.id }}, '{{ item.titulo|replace("'", "") }}')" class="action-link">
                    ⭐ Avaliar
                </button>
                <a href="https://api.whatsapp.com/send?text=Olha%20esse%20profissional%20que%20encontrei%20no%20Chama%20Aí%20Serviços:%20*{{ item.titulo }}*%20({{ item.cidade }})%20-%20{{ item.preco }}.%20Veja%20mais%20em:%20{{ url_site }}" target="_blank" class="action-link">
                    📤 Compartilhar
                </a>
                <a href="/editar/{{ item.id }}" class="action-link">
                    ✏️ Editar
                </a>
                {% if not item.is_vip %}
                    {% if item.pode_destacar %}
                        <a href="/pagar/{{ item.id }}" class="action-link action-vip">⚡ Destacar ({{ item.vagas_cat }} vagas)</a>
                    {% else %}
                        <span style="color:#94a3b8; font-size:11px;">Topo Lotado</span>
                    {% endif %}
                {% endif %}
            </div>
        </div>
    </div>
</div>
{% endfor %}
"""

HTML_INDEX = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chama Aí Serviços - Profissionais da Região</title>
    """ + HTML_BASE_CSS + """
</head>
<body>

<div class="top-bar">
    <span>📍 Formosa do Oeste • Goioerê • Assis Chateaubriand • Guaíra e Região</span>
    <div>
        <a href="/">Início</a>
        {% if vip_desbloqueado %}
            <a href="/sair_vip" style="color:#fbbf24;">★ Acesso VIP Ativo (Sair)</a>
        {% else %}
            <a href="#" onclick="abrirModal('modalAcessoVip'); return false;" style="color:#fbbf24;">🔑 Sou Profissional VIP</a>
        {% endif %}
        <a href="/admin">Painel Admin</a>
    </div>
</div>

<header>
    <span class="region-pill">CONECTANDO QUEM PRECISA A QUEM SABE FAZER</span>
    <h1>Chama Aí Serviços</h1>
    <p>Encontre profissionais de confiança na sua cidade ou divulgue seu trabalho gratuitamente em 1 minuto.</p>
    <div class="cta-hero-group">
        <button onclick="abrirModal('modalCadastro')" class="btn-hero">
            + Divulgar Meu Trabalho Grátis
        </button>
        <button onclick="abrirModal('modalPedido')" class="btn-hero btn-hero-blue">
            📢 Pedir Orçamento Urgente
        </button>
    </div>
    <div class="social-proof-bar">
        <span>✅ <strong>{{ total }}</strong> profissionais cadastrados</span>
        <span>🔥 <strong>{{ pedidos|length }}</strong> clientes buscando serviço agora</span>
        <span>🛡️ Contato direto sem intermediários</span>
    </div>
</header>

<div class="container">

    {% if erro_vip %}
        <div class="alert-banner alert-error">
            ⚠️ Senha de acesso VIP incorreta. Assine o Destaque VIP em qualquer anúncio para receber a senha oficial!
        </div>
    {% endif %}

    {% if msg_ok == 'editado' %}
        <div class="alert-banner alert-success">
            ✓ Anúncio atualizado com sucesso!
        </div>
    {% elif msg_ok == 'cadastrado' %}
        <div class="alert-banner alert-success">
            ✓ Seu anúncio foi publicado com sucesso! Guarde seu PIN de 4 dígitos caso precise editar depois.
        </div>
    {% elif msg_ok == 'vip_ativado' %}
        <div class="alert-banner alert-success">
            🎉 Pagamento confirmado automaticamente! Seu anúncio já está no TOPO com Selo VIP e o mural de clientes foi liberado!
        </div>
    {% endif %}

    {% if cfg.banner_ativo == '1' %}
    <a href="{{ cfg.banner_link }}" target="_blank" class="sponsor-banner">
        <div>
            <span class="sponsor-badge">Patrocinador Oficial da Região</span>
            <h4>{{ cfg.banner_titulo }}</h4>
            <p>{{ cfg.banner_texto }}</p>
        </div>
        <span class="sponsor-cta">Conhecer →</span>
    </a>
    {% endif %}

    {% if pedidos %}
    <div class="leads-section">
        <div class="leads-header">
            <h3>📢 Clientes Procurando Profissionais Agora ({{ pedidos|length }})</h3>
            <button onclick="abrirModal('modalPedido')" class="btn btn-sm" style="background:var(--blue-cta);">+ Publicar Meu Pedido</button>
        </div>
        <div class="leads-grid">
            {% for p in pedidos %}
            <div class="lead-card">
                <div>
                    <div class="lead-meta">📍 {{ p.cidade }} • {{ p.categoria }} • Cliente: {{ p.cliente_nome }}</div>
                    <p class="lead-desc">"{{ p.descricao }}"</p>
                </div>
                {% if vip_desbloqueado and p.wpp_link %}
                    <a href="{{ p.wpp_link }}?text=Olá%20{{ p.cliente_nome }},%20vi%20seu%20pedido%20no%20Chama%20Aí%20Serviços%20e%20posso%20te%20atender!" target="_blank" class="btn-wpp" style="margin-top:0; padding:8px; font-size:13px;">
                        💬 Chamar Cliente no WhatsApp
                    </a>
                {% else %}
                    <button onclick="abrirModal('modalAcessoVip')" class="btn-lead-locked">
                        🔒 WhatsApp Liberado Apenas para Profissionais VIP
                    </button>
                {% endif %}
            </div>
            {% endfor %}
        </div>
    </div>
    {% endif %}

    <div class="search-wrapper">
        <form action="/" method="GET" class="busca-bar">
            {% if cat_atual %}<input type="hidden" name="categoria" value="{{ cat_atual }}">{% endif %}
            {% if cidade_atual %}<input type="hidden" name="cidade" value="{{ cidade_atual }}">{% endif %}
            <input type="text" name="busca" value="{{ busca_atual }}" placeholder="O que você procura? (Ex: Eletricista, Pedreiro, Frete, Limpeza...)">
            <button type="submit" class="btn" style="background: var(--primary);">Buscar</button>
            {% if busca_atual or cat_atual or cidade_atual %}
                <a href="/" class="btn" style="background: var(--muted);">Limpar Filtros</a>
            {% endif %}
        </form>

        {% if cidades_disponiveis %}
        <div class="filtros-label">Filtrar por Cidade:</div>
        <div class="filtros">
            <a href="/?categoria={{ cat_atual }}" class="filtro-btn cidade-pill {{ 'ativo' if not cidade_atual else '' }}">Todas as Cidades</a>
            {% for cid in cidades_disponiveis %}
                <a href="/?cidade={{ cid }}&categoria={{ cat_atual }}" class="filtro-btn cidade-pill {{ 'ativo' if cidade_atual == cid else '' }}">📍 {{ cid }}</a>
            {% endfor %}
        </div>
        {% endif %}

        <div class="filtros-label">Filtrar por Categoria:</div>
        <div class="filtros">
            <a href="/?cidade={{ cidade_atual }}" class="filtro-btn {{ 'ativo' if not cat_atual else '' }}">📋 Todos ({{ total }})</a>
            {% for nome_cat, icone in categorias %}
                <a href="/?categoria={{ nome_cat }}&cidade={{ cidade_atual }}" class="filtro-btn {{ 'ativo' if cat_atual == nome_cat else '' }}">{{ icone }} {{ nome_cat }}</a>
            {% endfor %}
        </div>
    </div>

    <div class="scarcity-bar">
        <span>
            ⚡ <strong>Destaque no Topo:</strong>
            {% if cat_atual %}
                {% if vagas_restantes > 0 %}
                    Restam apenas <strong>{{ vagas_restantes }} de {{ limite_vagas }} vagas VIP</strong> na categoria <em>{{ cat_atual }}</em>!
                {% else %}
                    <strong>Vagas VIP esgotadas</strong> no momento para <em>{{ cat_atual }}</em>!
                {% endif %}
            {% else %}
                Limite exclusivo de <strong>{{ limite_vagas }} profissionais VIP por categoria</strong> no topo da página!
            {% endif %}
        </span>
        <button onclick="abrirModal('modalCadastro')" class="btn btn-vip btn-sm">Garantir Minha Vaga</button>
    </div>

    <div class="grid" id="gridServicos">
        {% if servicos %}
            """ + HTML_CARDS_FRAGMENT + """
        {% else %}
            <div class="card-box full-width" style="text-align:center;">
                <p>Nenhum serviço encontrado neste filtro ainda.</p>
                <button onclick="abrirModal('modalCadastro')" class="btn">Cadastrar Primeiro Serviço</button>
            </div>
        {% endif %}
    </div>

    {% if tem_mais %}
    <div class="load-more-wrapper" id="wrapperCarregarMais">
        <button onclick="carregarMais()" id="btnCarregarMais" class="btn" style="background: var(--primary); padding: 13px 28px;">
            Carregar Mais Profissionais ↓
        </button>
    </div>
    {% endif %}
</div>

<div id="modalCadastro" class="modal-overlay">
    <div class="modal-box">
        <button onclick="fecharModal('modalCadastro')" class="modal-close">&times;</button>
        <h2 style="margin-top:0;">Divulgar Meu Trabalho</h2>
        <p style="font-size:13px; color:var(--muted); margin-top:-10px; margin-bottom:18px;">Preencha os dados abaixo para aparecer no Chama Aí Serviços.</p>
        
        <form action="/adicionar" method="POST">
            <div class="form-grid">
                <div class="form-group">
                    <label>Seu Nome ou Empresa:</label>
                    <input type="text" name="nome" required placeholder="Ex: João da Silva">
                </div>
                <div class="form-group">
                    <label>Título do Serviço:</label>
                    <input type="text" name="titulo" required placeholder="Ex: Reparos Residenciais">
                </div>
                <div class="form-group">
                    <label>Categoria:</label>
                    <select name="categoria">
                        {% for nome_cat, icone in categorias %}
                            <option value="{{ nome_cat }}">{{ icone }} {{ nome_cat }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="form-group">
                    <label>Cidade:</label>
                    <input type="text" name="cidade" required placeholder="Ex: Formosa do Oeste - PR">
                </div>
                <div class="form-group">
                    <label>Preço (ou valor inicial):</label>
                    <input type="text" name="preco" required placeholder="Ex: R$ 80,00">
                </div>
                <div class="form-group">
                    <label>WhatsApp (com DDD):</label>
                    <input type="text" name="contato" required placeholder="Ex: (44) 99999-9999">
                </div>
                <div class="form-group">
                    <label>Crie um PIN de 4 números (para editar depois):</label>
                    <input type="text" name="pin_edicao" maxlength="4" pattern="[0-9]{4}" required placeholder="Ex: 1234">
                </div>
                <div class="form-group">
                    <label>Foto do Trabalho ou Cartão (Opcional):</label>
                    <input type="file" id="inputFoto" accept="image/*">
                    <input type="hidden" name="imagem_base64" id="imagemBase64">
                    <small style="color:var(--muted);" id="statusFoto">Aparece inteira no anúncio.</small>
                </div>
                <div class="form-group full-width">
                    <label>Descrição do Serviço:</label>
                    <textarea name="descricao" rows="3" required placeholder="Explique o que você faz, horários e diferenciais..."></textarea>
                </div>
            </div>

            <div class="vip-box">
                <label>
                    <input type="checkbox" name="quer_destaque" value="1">
                    <span>
                        <strong>Quero Destaque VIP no Topo (a partir de {{ cfg.valor_30d }})</strong><br>
                        <small style="font-weight:normal;">Liberação imediata após o Pix: anúncio fixado no topo com borda dourada, botão direto do WhatsApp e acesso liberado ao mural de clientes buscando serviço!</small>
                    </span>
                </label>
            </div>

            <button type="submit" class="btn" style="width:100%; padding:14px; font-size:16px;">Publicar Anúncio Agora</button>
        </form>
    </div>
</div>

<div id="modalPedido" class="modal-overlay">
    <div class="modal-box" style="max-width: 520px;">
        <button onclick="fecharModal('modalPedido')" class="modal-close">&times;</button>
        <h2 style="margin-top:0; color:#1e3a8a;">📢 Pedir Orçamento Grátis</h2>
        <p style="font-size:13px; color:var(--muted); margin-top:-8px; margin-bottom:16px;">Descreva o que você precisa e os profissionais da sua cidade entram em contato com você pelo WhatsApp.</p>
        
        <form action="/pedir_orcamento" method="POST">
            <div class="form-group">
                <label>Seu Nome:</label>
                <input type="text" name="cliente_nome" required placeholder="Ex: Carlos Eduardo">
            </div>
            <div class="form-grid">
                <div class="form-group">
                    <label>Tipo de Serviço:</label>
                    <select name="categoria">
                        {% for nome_cat, icone in categorias %}
                            <option value="{{ nome_cat }}">{{ icone }} {{ nome_cat }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="form-group">
                    <label>Sua Cidade:</label>
                    <input type="text" name="cidade" required placeholder="Ex: Assis Chateaubriand">
                </div>
            </div>
            <div class="form-group">
                <label>Seu WhatsApp para receber orçamentos:</label>
                <input type="text" name="whatsapp" required placeholder="Ex: (44) 99999-9999">
            </div>
            <div class="form-group">
                <label>O que você precisa? (Seja específico):</label>
                <textarea name="descricao" rows="3" required placeholder="Ex: Preciso de um eletricista hoje à tarde para trocar um chuveiro e verificar uma tomada..."></textarea>
            </div>
            <button type="submit" class="btn" style="width:100%; background:var(--blue-cta); padding:13px;">Publicar Pedido de Orçamento</button>
        </form>
    </div>
</div>

<div id="modalAcessoVip" class="modal-overlay">
    <div class="modal-box" style="max-width: 440px; text-align:center;">
        <button onclick="fecharModal('modalAcessoVip')" class="modal-close">&times;</button>
        <h3 style="margin-top:0; color:var(--vip-dark);">🔒 Área Exclusiva Profissional VIP</h3>
        <p style="font-size:14px; color:#475569;">O contato direto dos clientes que pedem orçamento no mural é liberado exclusivamente para profissionais com anúncio VIP ativo.</p>
        
        <form action="/desbloquear_vip" method="POST" style="margin-top:15px; text-align:left;">
            <div class="form-group">
                <label>Já é VIP? Digite sua Chave de Acesso:</label>
                <input type="password" name="senha_vip" required placeholder="Digite a senha VIP">
            </div>
            <button type="submit" class="btn btn-vip" style="width:100%;">Liberar Contatos dos Clientes</button>
        </form>
        
        <div style="margin-top:18px; padding-top:14px; border-top:1px solid #e2e8f0; font-size:13px;">
            Ainda não tem destaque VIP?<br>
            <a href="#" onclick="fecharModal('modalAcessoVip'); abrirModal('modalCadastro'); return false;" style="color:var(--accent); font-weight:bold;">Cadastre seu anúncio e ative o VIP agora →</a>
        </div>
    </div>
</div>

<div id="modalAvaliacao" class="modal-overlay">
    <div class="modal-box" style="max-width: 440px;">
        <button onclick="fecharModal('modalAvaliacao')" class="modal-close">&times;</button>
        <h3 style="margin-top:0;">Avaliar Serviço</h3>
        <p id="tituloServicoAval" style="font-size:14px; font-weight:bold; color:var(--primary);"></p>
        <form action="/avaliar" method="POST">
            <input type="hidden" name="servico_id" id="inputServicoIdAval">
            <div class="form-group">
                <label>Seu Nome:</label>
                <input type="text" name="autor" required placeholder="Ex: Maria Souza">
            </div>
            <div class="form-group">
                <label>Nota:</label>
                <select name="estrelas">
                    <option value="5">⭐⭐⭐⭐⭐ (5 - Excelente)</option>
                    <option value="4">⭐⭐⭐⭐ (4 - Muito Bom)</option>
                    <option value="3">⭐⭐⭐ (3 - Bom)</option>
                    <option value="2">⭐⭐ (2 - Regular)</option>
                    <option value="1">⭐ (1 - Ruim)</option>
                </select>
            </div>
            <div class="form-group">
                <label>Comentário curto (Opcional):</label>
                <input type="text" name="comentario" maxlength="140" placeholder="Ex: Serviço rápido, limpo e preço justo!">
            </div>
            <button type="submit" class="btn" style="width:100%;">Enviar Avaliação</button>
        </form>
    </div>
</div>

<script>
function abrirModal(id) { document.getElementById(id).style.display = 'block'; }
function fecharModal(id) { document.getElementById(id).style.display = 'none'; }
function abrirAvaliacao(id, titulo) {
    document.getElementById('inputServicoIdAval').value = id;
    document.getElementById('tituloServicoAval').innerText = titulo;
    abrirModal('modalAvaliacao');
}
window.onclick = function(event) {
    if (event.target.classList.contains('modal-overlay')) {
        event.target.style.display = 'none';
    }
}

let paginaAtual = 1;
function carregarMais() {
    const btn = document.getElementById('btnCarregarMais');
    btn.innerText = "Carregando...";
    btn.disabled = true;
    paginaAtual += 1;
    
    const params = new URLSearchParams(window.location.search);
    params.set('pagina', paginaAtual);
    
    fetch('/api/servicos?' + params.toString())
        .then(r => r.json())
        .then(data => {
            if (data.html) {
                document.getElementById('gridServicos').insertAdjacentHTML('beforeend', data.html);
            }
            if (!data.tem_mais) {
                document.getElementById('wrapperCarregarMais').style.display = 'none';
            } else {
                btn.innerText = "Carregar Mais Profissionais ↓";
                btn.disabled = false;
            }
        })
        .catch(() => {
            btn.innerText = "Tentar novamente";
            btn.disabled = false;
        });
}

document.getElementById('inputFoto').addEventListener('change', function(e) {
    const file = e.target.files[0];
    if (!file) return;
    document.getElementById('statusFoto').innerText = "Processando foto...";
    const reader = new FileReader();
    reader.onload = function(event) {
        const img = new Image();
        img.onload = function() {
            const canvas = document.createElement('canvas');
            const maxWidth = 700;
            const scale = img.width > maxWidth ? maxWidth / img.width : 1;
            canvas.width = img.width * scale;
            canvas.height = img.height * scale;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            document.getElementById('imagemBase64').value = canvas.toDataURL('image/jpeg', 0.78);
            document.getElementById('statusFoto').innerText = "✓ Foto pronta!";
        };
        img.src = event.target.result;
    };
    reader.readAsDataURL(file);
});
</script>

</body>
</html>
"""

HTML_EDITAR = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Editar Meu Anúncio - Chama Aí Serviços</title>
    """ + HTML_BASE_CSS + """
</head>
<body>
<header>
    <h1>Editar Meu Anúncio</h1>
    <p>Atualize seus dados, preço ou foto usando seu PIN de 4 dígitos</p>
</header>
<div class="container" style="max-width: 620px;">
    <div class="card-box">
        <h2 style="margin-top:0;">Anúncio #{{ servico.id }}: {{ servico.titulo }}</h2>
        {% if erro %}
            <div class="alert-banner alert-error">{{ erro }}</div>
        {% endif %}
        
        <form action="/editar/{{ servico.id }}" method="POST">
            <div class="form-group" style="background:#fffbeb; padding:12px; border-radius:8px; border:1px solid #fde68a;">
                <label style="color:#92400e;">🔑 Digite seu PIN de 4 dígitos para confirmar a edição:</label>
                <input type="password" name="pin_digitado" maxlength="4" required placeholder="****" style="max-width:160px; font-weight:bold; letter-spacing:4px;">
            </div>

            <div class="form-grid">
                <div class="form-group">
                    <label>Seu Nome ou Empresa:</label>
                    <input type="text" name="nome" value="{{ servico.nome }}" required>
                </div>
                <div class="form-group">
                    <label>Título do Serviço:</label>
                    <input type="text" name="titulo" value="{{ servico.titulo }}" required>
                </div>
                <div class="form-group">
                    <label>Categoria:</label>
                    <select name="categoria">
                        {% for nome_cat, icone in categorias %}
                            <option value="{{ nome_cat }}" {{ 'selected' if servico.categoria == nome_cat else '' }}>{{ icone }} {{ nome_cat }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="form-group">
                    <label>Cidade:</label>
                    <input type="text" name="cidade" value="{{ servico.cidade }}" required>
                </div>
                <div class="form-group">
                    <label>Preço (ou valor inicial):</label>
                    <input type="text" name="preco" value="{{ servico.preco }}" required>
                </div>
                <div class="form-group">
                    <label>WhatsApp (com DDD):</label>
                    <input type="text" name="contato" value="{{ servico.contato }}" required>
                </div>
                <div class="form-group full-width">
                    <label>Trocar Foto (Opcional — deixe vazio para manter a atual):</label>
                    <input type="file" id="inputFotoEdit" accept="image/*">
                    <input type="hidden" name="imagem_base64" id="imagemBase64Edit">
                    <small style="color:var(--muted);" id="statusFotoEdit">A foto atual será mantida se você não enviar outra.</small>
                </div>
                <div class="form-group full-width">
                    <label>Descrição do Serviço:</label>
                    <textarea name="descricao" rows="3" required>{{ servico.descricao }}</textarea>
                </div>
            </div>

            <button type="submit" class="btn" style="width:100%; padding:14px; font-size:16px;">Salvar Alterações</button>
        </form>
        <div style="text-align:center; margin-top:16px;">
            <a href="/" style="color:var(--muted); text-decoration:none; font-size:14px;">← Cancelar e voltar para o Chama Aí Serviços</a>
        </div>
    </div>
</div>
<script>
document.getElementById('inputFotoEdit').addEventListener('change', function(e) {
    const file = e.target.files[0];
    if (!file) return;
    document.getElementById('statusFotoEdit').innerText = "Processando nova foto...";
    const reader = new FileReader();
    reader.onload = function(event) {
        const img = new Image();
        img.onload = function() {
            const canvas = document.createElement('canvas');
            const maxWidth = 700;
            const scale = img.width > maxWidth ? maxWidth / img.width : 1;
            canvas.width = img.width * scale;
            canvas.height = img.height * scale;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            document.getElementById('imagemBase64Edit').value = canvas.toDataURL('image/jpeg', 0.78);
            document.getElementById('statusFotoEdit').innerText = "✓ Nova foto pronta!";
        };
        img.src = event.target.result;
    };
    reader.readAsDataURL(file);
});
</script>
</body>
</html>
"""

HTML_PAGAR = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ativar Destaque VIP - Chama Aí Serviços</title>
    """ + HTML_BASE_CSS + """
</head>
<body>
<header>
    <h1>Destacar Anúncio no Topo</h1>
    <p>Liberação imediata e automática assim que o Pix for pago</p>
</header>
<div class="container" style="max-width: 600px;">
    <div class="card-box" style="text-align: center;">
        <h2 style="margin-top:0; color:var(--vip-dark);">Anúncio: {{ servico.titulo }}</h2>
        
        {% if vagas_restantes <= 0 %}
            <div style="background:#fee2e2; color:#991b1b; padding:18px; border-radius:8px; margin:20px 0;">
                <strong>⚠️ Vagas VIP Esgotadas nesta Categoria!</strong><br>
                Todas as {{ limite_vagas }} vagas de destaque para <em>{{ servico.categoria }}</em> estão ocupadas no momento.
            </div>
            <a href="/" class="btn">← Voltar para o Chama Aí Serviços</a>
        {% else %}
            <p style="font-size:14px; color:#475569;">Restam apenas <strong>{{ vagas_restantes }} vagas VIP</strong> para <em>{{ servico.categoria }}</em>. Escolha a duração:</p>

            <div class="plan-selector">
                <a href="/pagar/{{ servico.id }}?plano=30" class="plan-card {{ 'active' if plano == '30' else '' }}">
                    <div style="font-weight:bold; font-size:15px;">Plano Mensal</div>
                    <div style="font-size:24px; font-weight:800; color:var(--accent); margin:6px 0;">{{ cfg.valor_30d }}</div>
                    <div style="font-size:12px; color:var(--muted);">30 dias no topo + Mural Clientes</div>
                </a>
                <a href="/pagar/{{ servico.id }}?plano=90" class="plan-card {{ 'active' if plano == '90' else '' }}">
                    <span class="plan-tag">MAIS ESCOLHIDO</span>
                    <div style="font-weight:bold; font-size:15px;">Plano Trimestral</div>
                    <div style="font-size:24px; font-weight:800; color:var(--accent); margin:6px 0;">{{ cfg.valor_90d }}</div>
                    <div style="font-size:12px; color:var(--muted);">90 dias no topo + Mural Clientes</div>
                </a>
            </div>
            
            <div style="background:#f8fafc; border:1px dashed #94a3b8; padding:20px; border-radius:8px; margin:20px 0;">
                <p style="margin:0 0 5px 0; font-size:13px; color:var(--muted);">Pix Copia e Cola ({{ dias_escolhidos }} dias — Valor Travado):</p>
                <div style="font-size:28px; font-weight:bold; color:var(--accent); margin-bottom:12px;">{{ valor_escolhido }}</div>
                
                {% if mp_qr_base64 %}
                    <img src="data:image/png;base64,{{ mp_qr_base64 }}" alt="QR Code Pix" style="width:190px; height:190px; margin:0 auto 12px auto; display:block; border:1px solid #e2e8f0; border-radius:8px; padding:6px; background:white;">
                {% endif %}

                <input type="text" value="{{ pix_copia_cola }}" id="pixCopiaCola" readonly style="text-align:center; font-size:12px; background:white; color:#334155;">
                <button onclick="copiarCodigo('pixCopiaCola', 'Código Pix Copia e Cola copiado! Abra o app do seu banco e escolha Pix Copia e Cola.')" class="btn" style="margin-top:10px; background:var(--secondary); width:100%;">
                    📋 Copiar Pix Copia e Cola ({{ valor_escolhido }})
                </button>
            </div>

            {% if mp_payment_id %}
                <div id="statusPagamentoBox" style="background:#eff6ff; border:1px solid #bfdbfe; color:#1e40af; padding:14px; border-radius:8px; font-size:14px; font-weight:600; margin-bottom:15px;">
                    ⏳ Aguardando confirmação automática do pagamento...<br>
                    <small style="font-weight:normal;">Assim que você pagar no app do banco, esta tela liberará seu destaque VIP sozinha em alguns segundos!</small>
                </div>
                <script>
                    setInterval(function() {
                        fetch('/api/verificar_pix/{{ mp_payment_id }}')
                            .then(r => r.json())
                            .then(data => {
                                if (data.pago) {
                                    window.location.href = "/?ok=vip_ativado";
                                }
                            });
                    }, 3000);
                </script>
            {% else %}
                <p style="font-size:14px; color:#475569;">Após o pagamento, envie o comprovante para liberar seu destaque:</p>
                <a href="https://wa.me/{{ cfg.seu_whatsapp }}?text=Olá!%20Acabei%20de%20fazer%20o%20Pix%20de%20{{ valor_escolhido }}%20(Plano%20{{ dias_escolhidos }}%20dias)%20para%20destacar%20o%20anúncio%20ID%20%23{{ servico.id }}%20({{ servico.titulo }})%20no%20Chama%20Aí%20Serviços.%20Segue%20o%20comprovante:" target="_blank" class="btn btn-vip" style="width:100%; padding:14px; font-size:16px;">
                    Enviar Comprovante no WhatsApp
                </a>
            {% endif %}
            
            <br><br>
            <a href="/" style="color:var(--muted); text-decoration:none; font-size:14px;">← Voltar para o Chama Aí Serviços</a>
        {% endif %}
    </div>
</div>
<script>
function copiarCodigo(elementId, mensagem) {
    var copyText = document.getElementById(elementId);
    copyText.select();
    copyText.setSelectionRange(0, 99999);
    navigator.clipboard.writeText(copyText.value);
    alert(mensagem);
}
</script>
</body>
</html>
"""

HTML_ADMIN = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Painel Administrativo - Chama Aí Serviços</title>
    """ + HTML_BASE_CSS + """
    <style>
        table { width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 14px; }
        th, td { border-bottom: 1px solid #e2e8f0; padding: 12px 8px; text-align: left; }
        th { background: #f8fafc; }
    </style>
</head>
<body>
<div class="top-bar">
    <span>Administração — Chama Aí Serviços</span>
    <div>
        <a href="/">Ver Site</a>
        {% if logado %}<a href="/admin/logout">Sair</a>{% endif %}
    </div>
</div>
<header>
    <h1>Painel de Controle</h1>
    <p>Gerencie anúncios VIP, pagamentos automáticos, métricas e Pix</p>
</header>
<div class="container">
    {% if not logado %}
        <div class="card-box" style="max-width:400px; margin:0 auto;">
            <h3 style="margin-top:0;">Acesso Restrito</h3>
            {% if erro %}<p style="color:red;">{{ erro }}</p>{% endif %}
            <form method="POST">
                <div class="form-group">
                    <label>Senha do Administrador:</label>
                    <input type="password" name="senha" required>
                </div>
                <button type="submit" class="btn" style="width:100%;">Entrar</button>
            </form>
        </div>
    {% else %}
        <div class="card-box">
            <h2 style="margin-top:0;">Configurações de Lucro, Automação Pix e Patrocinador</h2>
            {% if salvo %}<p style="color:var(--accent); font-weight:bold;">✓ Configurações salvas com sucesso!</p>{% endif %}
            <form action="/admin/config" method="POST">
                <div class="form-grid">
                    <div class="form-group full-width" style="background:#f0fdf4; padding:14px; border-radius:8px; border:1px solid #bbf7d0;">
                        <label style="color:#166534;">⚡ Access Token Mercado Pago (Para liberação 100% automática do Pix sem precisar aprovar):</label>
                        <input type="text" name="mp_access_token" value="{{ cfg.mp_access_token }}" placeholder="APP_USR-0000000000000000-...">
                        <small style="color:#15803d;">Cole seu Token de Produção do Mercado Pago acima. Se deixar vazio, o sistema usa a Chave Pix manual abaixo.</small>
                    </div>
                    <div class="form-group">
                        <label>Chave Pix Manual (Plano B):</label>
                        <input type="text" name="chave_pix" value="{{ cfg.chave_pix }}" required>
                    </div>
                    <div class="form-group">
                        <label>Seu WhatsApp (com 55 + DDD):</label>
                        <input type="text" name="seu_whatsapp" value="{{ cfg.seu_whatsapp }}" required>
                    </div>
                    <div class="form-group">
                        <label>Valor Plano Mensal (30 dias):</label>
                        <input type="text" name="valor_30d" value="{{ cfg.valor_30d }}" required>
                    </div>
                    <div class="form-group">
                        <label>Valor Plano Trimestral (90 dias):</label>
                        <input type="text" name="valor_90d" value="{{ cfg.valor_90d }}" required>
                    </div>
                    <div class="form-group">
                        <label>Senha VIP (liberada automaticamente após o Pix):</label>
                        <input type="text" name="senha_vip_clientes" value="{{ cfg.senha_vip_clientes }}" required>
                    </div>
                    <div class="form-group">
                        <label>Exibir Banner de Patrocinador no Topo?</label>
                        <select name="banner_ativo">
                            <option value="1" {{ 'selected' if cfg.banner_ativo == '1' else '' }}>Sim (Ativo)</option>
                            <option value="0" {{ 'selected' if cfg.banner_ativo == '0' else '' }}>Não (Oculto)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Título do Banner Patrocinador:</label>
                        <input type="text" name="banner_titulo" value="{{ cfg.banner_titulo }}">
                    </div>
                    <div class="form-group">
                        <label>Texto do Banner Patrocinador:</label>
                        <input type="text" name="banner_texto" value="{{ cfg.banner_texto }}">
                    </div>
                    <div class="form-group full-width">
                        <label>Link ao clicar no Banner (WhatsApp ou Site do Patrocinador):</label>
                        <input type="text" name="banner_link" value="{{ cfg.banner_link }}">
                    </div>
                </div>
                <button type="submit" class="btn">Salvar Todas as Configurações</button>
            </form>
        </div>

        <div class="card-box" style="overflow-x:auto;">
            <h2 style="margin-top:0;">Profissionais Cadastrados ({{ servicos|length }})</h2>
            <table>
                <thead>
                    <tr>
                        <th>ID / PIN</th>
                        <th>Profissional / Serviço</th>
                        <th>Métricas</th>
                        <th>Status VIP</th>
                        <th>Ações</th>
                    </tr>
                </thead>
                <tbody>
                    {% for s in servicos %}
                    <tr>
                        <td>
                            <strong>#{{ s.id }}</strong><br>
                            <small style="color:var(--muted);">PIN: {{ s.pin_edicao }}</small>
                        </td>
                        <td>
                            <strong>{{ s.titulo }}</strong><br>
                            <small>{{ s.nome }} • {{ s.cidade }} • {{ s.contato }}</small>
                        </td>
                        <td>
                            <small>👁️ {{ s.visualizacoes }} views<br>💬 {{ s.cliques_wpp }} cliques</small>
                        </td>
                        <td>
                            {% if s.is_vip %}
                                <span style="color:var(--vip-dark); font-weight:bold;">VIP até {{ s.destaque_ate[:10] }}</span>
                            {% else %}
                                <span style="color:var(--muted);">Gratuito</span>
                            {% endif %}
                        </td>
                        <td style="display:flex; gap:6px; flex-wrap:wrap;">
                            <a href="/admin/vip/{{ s.id }}/30" class="btn btn-vip btn-sm">+30d VIP</a>
                            <a href="/admin/vip/{{ s.id }}/90" class="btn btn-vip btn-sm" style="background:#b45309;">+90d VIP</a>
                            {% if s.is_vip %}
                                <a href="/admin/remover_vip/{{ s.id }}" class="btn btn-sm" style="background:var(--muted);">Tirar VIP</a>
                            {% endif %}
                            <a href="/admin/excluir/{{ s.id }}" onclick="return confirm('Excluir este anúncio?')" class="btn btn-danger">Excluir</a>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>

        <div class="card-box" style="overflow-x:auto;">
            <h2 style="margin-top:0;">Pedidos de Orçamento de Clientes ({{ pedidos|length }})</h2>
            <table>
                <thead>
                    <tr>
                        <th>Cliente</th>
                        <th>Cidade / Categoria</th>
                        <th>Pedido</th>
                        <th>WhatsApp</th>
                        <th>Ação</th>
                    </tr>
                </thead>
                <tbody>
                    {% for p in pedidos %}
                    <tr>
                        <td><strong>{{ p.cliente_nome }}</strong></td>
                        <td>{{ p.cidade }}<br><small>{{ p.categoria }}</small></td>
                        <td>{{ p.descricao }}</td>
                        <td>{{ p.whatsapp }}</td>
                        <td>
                            <a href="/admin/excluir_pedido/{{ p.id }}" onclick="return confirm('Remover este pedido?')" class="btn btn-danger">Remover</a>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    {% endif %}
</div>
</body>
</html>
"""

def obter_servicos_paginados(db, categoria, cidade, busca, pagina, contar_views=True):
    todos_rows = db.execute("SELECT id, cidade, categoria, destaque_ate FROM servicos").fetchall()
    agora = datetime.now()
    vips_por_cat = {}
    cidades_set = set()

    for r in todos_rows:
        cidades_set.add(r["cidade"].strip())
        if r["destaque_ate"] and datetime.fromisoformat(r["destaque_ate"]) > agora:
            cat = r["categoria"]
            vips_por_cat[cat] = vips_por_cat.get(cat, 0) + 1

    query = "SELECT * FROM servicos WHERE 1=1"
    params = []
    if categoria:
        query += " AND categoria = ?"
        params.append(categoria)
    if cidade:
        query += " AND cidade = ?"
        params.append(cidade)
    if busca:
        query += " AND (titulo LIKE ? OR descricao LIKE ? OR cidade LIKE ? OR nome LIKE ?)"
        termo = f"%{busca}%"
        params.extend([termo, termo, termo, termo])

    query += " ORDER BY id DESC"
    rows = db.execute(query, params).fetchall()

    lista_completa = []
    for r in rows:
        item = dict(r)
        is_vip = bool(item["destaque_ate"] and datetime.fromisoformat(item["destaque_ate"]) > agora)
        item["is_vip"] = is_vip
        item["wpp_link"] = formatar_whatsapp(item["contato"])
        item["visualizacoes"] = (item.get("visualizacoes") or 0) + (1 if contar_views else 0)
        item["cliques_wpp"] = item.get("cliques_wpp") or 0

        ocupadas = vips_por_cat.get(item["categoria"], 0)
        restantes = max(0, LIMITE_VAGAS_VIP - ocupadas)
        item["vagas_cat"] = restantes
        item["pode_destacar"] = restantes > 0
        lista_completa.append(item)

    lista_completa.sort(key=lambda x: x["is_vip"], reverse=True)

    inicio = (pagina - 1) * ITENS_POR_PAGINA
    fim = inicio + ITENS_POR_PAGINA
    fatia = lista_completa[inicio:fim]
    tem_mais = len(lista_completa) > fim

    ids_exibidos = []
    for item in fatia:
        ids_exibidos.append(item["id"])
        avals = db.execute("SELECT * FROM avaliacoes WHERE servico_id = ? ORDER BY id DESC", (item["id"],)).fetchall()
        item["total_aval"] = len(avals)
        if avals:
            soma = sum(a["estrelas"] for a in avals)
            item["media_estrelas"] = f"{soma / len(avals):.1f}"
            com_texto = [dict(a) for a in avals if a["comentario"]]
            item["ultimo_comentario"] = com_texto[0] if com_texto else None
        else:
            item["media_estrelas"] = "0"
            item["ultimo_comentario"] = None

    if contar_views and ids_exibidos:
        for sid in ids_exibidos:
            db.execute("UPDATE servicos SET visualizacoes = COALESCE(visualizacoes, 0) + 1 WHERE id = ?", (sid,))
        db.commit()

    return fatia, tem_mais, len(todos_rows), sorted(list(cidades_set)), vips_por_cat

@app.route("/ping")
def ping():
    return "OK", 200

@app.route("/")
def index():
    categoria = request.args.get("categoria", "")
    cidade = request.args.get("cidade", "")
    busca = request.args.get("busca", "").strip()
    erro_vip = request.args.get("erro_vip") == "1"
    msg_ok = request.args.get("ok", "")
    cfg = get_config()
    db = DBWrapper()

    fatia, tem_mais, total, cidades_disponiveis, vips_por_cat = obter_servicos_paginados(
        db, categoria, cidade, busca, pagina=1, contar_views=True
    )

    pedidos_rows = db.execute("SELECT * FROM pedidos ORDER BY id DESC LIMIT 6").fetchall()
    pedidos = []
    for p in pedidos_rows:
        pd = dict(p)
        pd["wpp_link"] = formatar_whatsapp(pd["whatsapp"])
        pedidos.append(pd)

    db.close()

    categorias = [
        ("Reformas e Reparos", "🛠️"),
        ("Tecnologia e Informática", "💻"),
        ("Design e Marketing", "🎨"),
        ("Aulas e Consultoria", "📚"),
        ("Saúde e Bem-estar", "🏥"),
        ("Fretes e Mudanças", "🚚"),
        ("Outros Serviços", "⚡")
    ]

    vagas_restantes = max(0, LIMITE_VAGAS_VIP - vips_por_cat.get(categoria, 0)) if categoria else LIMITE_VAGAS_VIP

    return render_template_string(
        HTML_INDEX,
        servicos=fatia,
        tem_mais=tem_mais,
        pedidos=pedidos,
        categorias=categorias,
        cidades_disponiveis=cidades_disponiveis,
        cat_atual=categoria,
        cidade_atual=cidade,
        busca_atual=busca,
        total=total,
        cfg=cfg,
        limite_vagas=LIMITE_VAGAS_VIP,
        vagas_restantes=vagas_restantes,
        vip_desbloqueado=session.get("vip_desbloqueado", False),
        erro_vip=erro_vip,
        msg_ok=msg_ok,
        url_site=request.host_url
    )

@app.route("/api/servicos")
def api_servicos():
    categoria = request.args.get("categoria", "")
    cidade = request.args.get("cidade", "")
    busca = request.args.get("busca", "").strip()
    pagina = max(1, int(request.args.get("pagina", 1)))
    
    db = DBWrapper()
    fatia, tem_mais, _, _, _ = obter_servicos_paginados(
        db, categoria, cidade, busca, pagina=pagina, contar_views=True
    )
    db.close()

    html_cards = render_template_string(HTML_CARDS_FRAGMENT, servicos=fatia, url_site=request.host_url)
    return jsonify({"html": html_cards, "tem_mais": tem_mais})

@app.route("/whatsapp/<int:servico_id>")
def abrir_whatsapp(servico_id):
    db = DBWrapper()
    servico = db.execute("SELECT nome, contato FROM servicos WHERE id = ?", (servico_id,)).fetchone()
    if not servico:
        db.close()
        return redirect(url_for("index"))

    db.execute("UPDATE servicos SET cliques_wpp = COALESCE(cliques_wpp, 0) + 1 WHERE id = ?", (servico_id,))
    db.commit()
    db.close()

    wpp_base = formatar_whatsapp(servico["contato"])
    if not wpp_base:
        return redirect(url_for("index"))

    texto = quote(f"Olá {servico['nome']}, vi seu anúncio no Chama Aí Serviços!")
    return redirect(f"{wpp_base}?text={texto}")

@app.route("/adicionar", methods=["POST"])
def adicionar():
    nome = request.form.get("nome")
    titulo = request.form.get("titulo")
    categoria = request.form.get("categoria")
    cidade = request.form.get("cidade").strip()
    preco = request.form.get("preco")
    descricao = request.form.get("descricao")
    contato = request.form.get("contato")
    pin_edicao = re.sub(r"\D", "", request.form.get("pin_edicao", "0000"))[:4].zfill(4)
    imagem = request.form.get("imagem_base64") or None
    quer_destaque = request.form.get("quer_destaque")

    db = DBWrapper()
    novo_id = db.insert_returning_id("""
        INSERT INTO servicos (nome, titulo, categoria, cidade, preco, descricao, contato, imagem, destaque_ate, criado_em, visualizacoes, cliques_wpp, pin_edicao)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, 0, 0, ?)
    """, (nome, titulo, categoria, cidade, preco, descricao, contato, imagem, datetime.now().isoformat(), pin_edicao))
    db.commit()
    db.close()

    if quer_destaque == "1":
        return redirect(url_for("pagar", servico_id=novo_id))
    return redirect(url_for("index", ok="cadastrado"))

@app.route("/editar/<int:servico_id>", methods=["GET", "POST"])
def editar_servico(servico_id):
    categorias = [
        ("Reformas e Reparos", "🛠️"),
        ("Tecnologia e Informática", "💻"),
        ("Design e Marketing", "🎨"),
        ("Aulas e Consultoria", "📚"),
        ("Saúde e Bem-estar", "🏥"),
        ("Fretes e Mudanças", "🚚"),
        ("Outros Serviços", "⚡")
    ]
    db = DBWrapper()
    servico = db.execute("SELECT * FROM servicos WHERE id = ?", (servico_id,)).fetchone()
    if not servico:
        db.close()
        return redirect(url_for("index"))

    erro = None
    if request.method == "POST":
        pin_digitado = request.form.get("pin_digitado", "").strip()
        pin_salvo = servico["pin_edicao"] or "0000"
        if pin_digitado != pin_salvo and pin_digitado != SENHA_ADMIN:
            erro = "PIN incorreto! Verifique os 4 dígitos criados no cadastro."
        else:
            nome = request.form.get("nome")
            titulo = request.form.get("titulo")
            categoria = request.form.get("categoria")
            cidade = request.form.get("cidade").strip()
            preco = request.form.get("preco")
            contato = request.form.get("contato")
            descricao = request.form.get("descricao")
            nova_img = request.form.get("imagem_base64") or servico["imagem"]

            db.execute("""
                UPDATE servicos
                SET nome = ?, titulo = ?, categoria = ?, cidade = ?, preco = ?, contato = ?, descricao = ?, imagem = ?
                WHERE id = ?
            """, (nome, titulo, categoria, cidade, preco, contato, descricao, nova_img, servico_id))
            db.commit()
            db.close()
            return redirect(url_for("index", ok="editado"))

    db.close()
    return render_template_string(HTML_EDITAR, servico=servico, categorias=categorias, erro=erro)

@app.route("/pedir_orcamento", methods=["POST"])
def pedir_orcamento():
    cliente_nome = request.form.get("cliente_nome", "").strip()
    categoria = request.form.get("categoria")
    cidade = request.form.get("cidade", "").strip()
    whatsapp = request.form.get("whatsapp", "").strip()
    descricao = request.form.get("descricao", "").strip()

    if cliente_nome and descricao:
        db = DBWrapper()
        db.execute("""
            INSERT INTO pedidos (cliente_nome, categoria, cidade, descricao, whatsapp, criado_em)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (cliente_nome, categoria, cidade, descricao, whatsapp, datetime.now().isoformat()))
        db.commit()
        db.close()
    return redirect(url_for("index"))

@app.route("/desbloquear_vip", methods=["POST"])
def desbloquear_vip():
    cfg = get_config()
    if request.form.get("senha_vip") == cfg.get("senha_vip_clientes"):
        session["vip_desbloqueado"] = True
        return redirect(url_for("index"))
    return redirect(url_for("index", erro_vip=1))

@app.route("/sair_vip")
def sair_vip():
    session.pop("vip_desbloqueado", None)
    return redirect(url_for("index"))

@app.route("/avaliar", methods=["POST"])
def avaliar():
    servico_id = request.form.get("servico_id")
    autor = request.form.get("autor", "").strip()
    estrelas = int(request.form.get("estrelas", 5))
    comentario = request.form.get("comentario", "").strip()

    if servico_id and autor:
        db = DBWrapper()
        db.execute("""
            INSERT INTO avaliacoes (servico_id, autor, estrelas, comentario, criado_em)
            VALUES (?, ?, ?, ?, ?)
        """, (servico_id, autor, estrelas, comentario, datetime.now().isoformat()))
        db.commit()
        db.close()
    return redirect(url_for("index"))

@app.route("/pagar/<int:servico_id>")
def pagar(servico_id):
    plano = request.args.get("plano", "30")
    if plano not in ("30", "90"):
        plano = "30"
        
    cfg = get_config()
    db = DBWrapper()
    servico = db.execute("SELECT * FROM servicos WHERE id = ?", (servico_id,)).fetchone()
    
    if not servico:
        db.close()
        return redirect(url_for("index"))
        
    rows_cat = db.execute("SELECT destaque_ate FROM servicos WHERE categoria = ?", (servico["categoria"],)).fetchall()
    
    agora = datetime.now()
    ocupadas = sum(1 for r in rows_cat if r["destaque_ate"] and datetime.fromisoformat(r["destaque_ate"]) > agora)
    vagas_restantes = max(0, LIMITE_VAGAS_VIP - ocupadas)
    
    valor_escolhido = cfg["valor_90d"] if plano == "90" else cfg["valor_30d"]
    dias_escolhidos = 90 if plano == "90" else 30
    valor_float = extrair_valor_float(valor_escolhido)

    mp_token = cfg.get("mp_access_token", "").strip()
    mp_payment_id = None
    mp_qr_base64 = None
    pix_copia_cola = ""

    if mp_token and vagas_restantes > 0:
        try:
            webhook_url = request.url_root.rstrip("/") + "/webhook/mercadopago"
            headers = {
                "Authorization": f"Bearer {mp_token}",
                "Content-Type": "application/json",
                "X-Idempotency-Key": f"chamaai-{servico_id}-{dias_escolhidos}-{int(agora.timestamp())}"
            }
            payload_mp = {
                "transaction_amount": valor_float,
                "description": f"Destaque VIP {dias_escolhidos}d - Chama Ai #{servico_id}",
                "payment_method_id": "pix",
                "payer": {
                    "email": f"anuncio{servico_id}@chamaaiservicos.com.br",
                    "first_name": servico["nome"][:30]
                },
                "notification_url": webhook_url,
                "external_reference": f"{servico_id}:{dias_escolhidos}"
            }
            resp = requests.post("https://api.mercadopago.com/v1/payments", json=payload_mp, headers=headers, timeout=10)
            if resp.status_code in (200, 201):
                dados = resp.json()
                mp_payment_id = str(dados.get("id"))
                tx_data = dados.get("point_of_interaction", {}).get("transaction_data", {})
                pix_copia_cola = tx_data.get("qr_code", "")
                mp_qr_base64 = tx_data.get("qr_code_base64", "")

                db.execute("""
                    INSERT INTO pagamentos_pix (mp_payment_id, servico_id, dias, valor, status, qr_code, criado_em)
                    VALUES (?, ?, ?, ?, 'pending', ?, ?)
                """, (mp_payment_id, servico_id, dias_escolhidos, valor_float, pix_copia_cola, agora.isoformat()))
                db.commit()
        except Exception:
            mp_payment_id = None

    if not pix_copia_cola:
        pix_copia_cola = gerar_pix_copia_cola(
            cfg["chave_pix"],
            valor_escolhido,
            txid=f"VIP{dias_escolhidos}ID{servico_id}"
        )

    db.close()

    return render_template_string(
        HTML_PAGAR,
        servico=servico,
        cfg=cfg,
        plano=plano,
        valor_escolhido=valor_escolhido,
        dias_escolhidos=dias_escolhidos,
        pix_copia_cola=pix_copia_cola,
        mp_payment_id=mp_payment_id,
        mp_qr_base64=mp_qr_base64,
        vagas_restantes=vagas_restantes,
        limite_vagas=LIMITE_VAGAS_VIP
    )

@app.route("/api/verificar_pix/<mp_payment_id>")
def verificar_pix(mp_payment_id):
    cfg = get_config()
    db = DBWrapper()
    pag = db.execute("SELECT * FROM pagamentos_pix WHERE mp_payment_id = ?", (mp_payment_id,)).fetchone()
    if not pag:
        db.close()
        return jsonify({"pago": False})

    if pag["status"] == "approved":
        session["vip_desbloqueado"] = True
        db.close()
        return jsonify({"pago": True})

    mp_token = cfg.get("mp_access_token", "").strip()
    if mp_token:
        try:
            r = requests.get(
                f"https://api.mercadopago.com/v1/payments/{mp_payment_id}",
                headers={"Authorization": f"Bearer {mp_token}"},
                timeout=8
            )
            if r.status_code == 200 and r.json().get("status") == "approved":
                db.execute("UPDATE pagamentos_pix SET status = 'approved' WHERE mp_payment_id = ?", (mp_payment_id,))
                ativar_destaque_automatico(db, pag["servico_id"], pag["dias"])
                db.commit()
                session["vip_desbloqueado"] = True
                db.close()
                return jsonify({"pago": True})
        except Exception:
            pass

    db.close()
    return jsonify({"pago": False})

@app.route("/webhook/mercadopago", methods=["POST", "GET"])
def webhook_mercadopago():
    data = request.get_json(silent=True) or {}
    payment_id = None
    if isinstance(data.get("data"), dict):
        payment_id = data["data"].get("id")
    if not payment_id:
        payment_id = request.args.get("data.id") or request.args.get("id")

    if payment_id:
        cfg = get_config()
        mp_token = cfg.get("mp_access_token", "").strip()
        if mp_token:
            try:
                r = requests.get(
                    f"https://api.mercadopago.com/v1/payments/{payment_id}",
                    headers={"Authorization": f"Bearer {mp_token}"},
                    timeout=8
                )
                if r.status_code == 200 and r.json().get("status") == "approved":
                    db = DBWrapper()
                    pag = db.execute("SELECT * FROM pagamentos_pix WHERE mp_payment_id = ?", (str(payment_id),)).fetchone()
                    if pag and pag["status"] != "approved":
                        db.execute("UPDATE pagamentos_pix SET status = 'approved' WHERE mp_payment_id = ?", (str(payment_id),))
                        ativar_destaque_automatico(db, pag["servico_id"], pag["dias"])
                        db.commit()
                    db.close()
            except Exception:
                pass
    return "OK", 200

@app.route("/admin", methods=["GET", "POST"])
def admin():
    erro = None
    if request.method == "POST":
        if request.form.get("senha") == SENHA_ADMIN:
            session["admin_logado"] = True
        else:
            erro = "Senha incorreta."

    if not session.get("admin_logado"):
        return render_template_string(HTML_ADMIN, logado=False, erro=erro)

    cfg = get_config()
    salvo = request.args.get("salvo") == "1"
    db = DBWrapper()
    rows = db.execute("SELECT * FROM servicos ORDER BY id DESC").fetchall()
    pedidos = db.execute("SELECT * FROM pedidos ORDER BY id DESC").fetchall()
    db.close()

    agora = datetime.now()
    servicos = []
    for r in rows:
        item = dict(r)
        item["is_vip"] = bool(item["destaque_ate"] and datetime.fromisoformat(item["destaque_ate"]) > agora)
        item["visualizacoes"] = item.get("visualizacoes") or 0
        item["cliques_wpp"] = item.get("cliques_wpp") or 0
        item["pin_edicao"] = item.get("pin_edicao") or "0000"
        servicos.append(item)

    return render_template_string(HTML_ADMIN, logado=True, servicos=servicos, pedidos=pedidos, cfg=cfg, salvo=salvo)

@app.route("/admin/config", methods=["POST"])
def salvar_config():
    if not session.get("admin_logado"):
        return redirect(url_for("admin"))
    campos = [
        "mp_access_token", "chave_pix", "seu_whatsapp", "valor_30d", "valor_90d",
        "senha_vip_clientes", "banner_ativo", "banner_titulo", "banner_texto", "banner_link"
    ]
    db = DBWrapper()
    for c in campos:
        val = request.form.get(c, "").strip()
        if val != "" or c == "mp_access_token":
            db.execute("UPDATE config SET valor = ? WHERE chave = ?", (val, c))
    db.commit()
    db.close()
    return redirect(url_for("admin", salvo=1))

@app.route("/admin/vip/<int:servico_id>/<int:dias>")
def ativar_vip(servico_id, dias):
    if not session.get("admin_logado"):
        return redirect(url_for("admin"))
    db = DBWrapper()
    ativar_destaque_automatico(db, servico_id, dias)
    db.commit()
    db.close()
    return redirect(url_for("admin"))

@app.route("/admin/remover_vip/<int:servico_id>")
def remover_vip(servico_id):
    if not session.get("admin_logado"):
        return redirect(url_for("admin"))
    db = DBWrapper()
    db.execute("UPDATE servicos SET destaque_ate = NULL WHERE id = ?", (servico_id,))
    db.commit()
    db.close()
    return redirect(url_for("admin"))

@app.route("/admin/excluir/<int:servico_id>")
def excluir_servico(servico_id):
    if not session.get("admin_logado"):
        return redirect(url_for("admin"))
    db = DBWrapper()
    db.execute("DELETE FROM avaliacoes WHERE servico_id = ?", (servico_id,))
    db.execute("DELETE FROM servicos WHERE id = ?", (servico_id,))
    db.commit()
    db.close()
    return redirect(url_for("admin"))

@app.route("/admin/excluir_pedido/<int:pedido_id>")
def excluir_pedido(pedido_id):
    if not session.get("admin_logado"):
        return redirect(url_for("admin"))
    db = DBWrapper()
    db.execute("DELETE FROM pedidos WHERE id = ?", (pedido_id,))
    db.commit()
    db.close()
    return redirect(url_for("admin"))

@app.route("/admin/logout")
def logout():
    session.pop("admin_logado", None)
    return redirect(url_for("index"))

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
