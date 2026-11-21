import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request, redirect, url_for, session

app = Flask(__name__)

# =====================================================================
# CONFIGURAÇÕES INICIAIS (SUAS CREDENCIAIS)
# =====================================================================
app.secret_key = "chave_secreta_vitrine_marcao_2026_pro"
SENHA_ADMIN = "22041988"
PIX_PADRAO = "997ef3d7-4a1c-436f-b4fa-2c668ad7"
WPP_PADRAO = "5544998258119"
VALOR_PADRAO = "R$ 19,90"
DIAS_PADRAO = "30"
# =====================================================================

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
            criado_em TEXT NOT NULL
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
        CREATE TABLE IF NOT EXISTS config (
            chave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        )
    """)
    padroes = {
        "chave_pix": PIX_PADRAO,
        "seu_whatsapp": WPP_PADRAO,
        "valor_destaque": VALOR_PADRAO,
        "dias_destaque": DIAS_PADRAO,
        "banner_ativo": "1",
        "banner_titulo": "Espaço Reservado para Patrocinador Local",
        "banner_texto": "Divulgue sua loja ou empresa aqui para milhares de clientes da região! Clique para anunciar.",
        "banner_link": f"https://wa.me/{WPP_PADRAO}?text=Olá!%20Tenho%20interesse%20no%20espaço%20de%20patrocinador%20da%20Vitrine%20de%20Serviços."
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

# =====================================================================
# CSS E TEMPLATES PROFISSIONAIS
# =====================================================================

HTML_BASE_CSS = """
<style>
    :root {
        --primary: #0f172a;
        --secondary: #1e293b;
        --accent: #16a34a;
        --accent-hover: #15803d;
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
    }
    .top-bar a { color: #cbd5e1; text-decoration: none; margin-left: 15px; font-weight: 500; }
    .top-bar a:hover { color: white; }

    header {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%);
        color: white;
        padding: 35px 20px;
        text-align: center;
    }
    header h1 { margin: 0 0 10px 0; font-size: 32px; letter-spacing: -0.5px; }
    header p { margin: 0 auto 22px auto; color: #e2e8f0; font-size: 16px; max-width: 600px; }

    .cta-hero-group {
        display: flex;
        gap: 12px;
        justify-content: center;
        flex-wrap: wrap;
    }
    .btn-hero {
        background: var(--accent);
        color: white;
        border: none;
        padding: 14px 26px;
        font-size: 16px;
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

    .container { max-width: 1120px; margin: 25px auto; padding: 0 20px; }

    /* Banner Patrocinador */
    .sponsor-banner {
        background: linear-gradient(90deg, #1e293b 0%, #334155 100%);
        border-left: 5px solid var(--vip);
        color: white;
        padding: 16px 22px;
        border-radius: 10px;
        margin-bottom: 25px;
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

    /* Busca e Categorias */
    .search-wrapper {
        background: white;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        margin-bottom: 20px;
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

    .filtros { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 14px; }
    .filtro-btn {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        padding: 8px 14px;
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

    /* Grid e Cards de Serviços */
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
        box-shadow: 0 6px 20px rgba(245, 158, 11, 0.2);
    }
    /* EXIBIÇÃO DA IMAGEM 100% INTEIRA SEM CORTES */
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
        max-height: 360px;
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

    /* Modal Pop-up */
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
</style>
"""

HTML_INDEX = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vitrine de Serviços e Profissionais</title>
    """ + HTML_BASE_CSS + """
</head>
<body>

<div class="top-bar">
    <span>Plataforma Regional de Serviços</span>
    <div>
        <a href="/">Início</a>
        <a href="/admin">Painel Admin</a>
    </div>
</div>

<header>
    <h1>Vitrine de Serviços</h1>
    <p>Contrate profissionais de confiança perto de você ou divulgue seu trabalho gratuitamente em menos de 1 minuto.</p>
    <div class="cta-hero-group">
        <button onclick="abrirModal('modalCadastro')" class="btn-hero">
            + Divulgar Meu Trabalho Grátis
        </button>
    </div>
</header>

<div class="container">

    <!-- Banner de Patrocinador Local -->
    {% if cfg.banner_ativo == '1' %}
    <a href="{{ cfg.banner_link }}" target="_blank" class="sponsor-banner">
        <div>
            <span class="sponsor-badge">Destaque Comercial</span>
            <h4>{{ cfg.banner_titulo }}</h4>
            <p>{{ cfg.banner_texto }}</p>
        </div>
        <span class="sponsor-cta">Saiba Mais →</span>
    </a>
    {% endif %}

    <!-- Barra de Busca e Categorias com Ícones -->
    <div class="search-wrapper">
        <form action="/" method="GET" class="busca-bar">
            {% if cat_atual %}<input type="hidden" name="categoria" value="{{ cat_atual }}">{% endif %}
            <input type="text" name="busca" value="{{ busca_atual }}" placeholder="O que você precisa? (Ex: Eletricista, Formosa do Oeste, Frete...)">
            <button type="submit" class="btn" style="background: var(--primary);">Buscar</button>
            {% if busca_atual or cat_atual %}
                <a href="/" class="btn" style="background: var(--muted);">Limpar</a>
            {% endif %}
        </form>

        <div class="filtros">
            <a href="/" class="filtro-btn {{ 'ativo' if not cat_atual else '' }}">📋 Todos ({{ total }})</a>
            {% for nome_cat, icone in categorias %}
                <a href="/?categoria={{ nome_cat }}" class="filtro-btn {{ 'ativo' if cat_atual == nome_cat else '' }}">{{ icone }} {{ nome_cat }}</a>
            {% endfor %}
        </div>
    </div>

    <!-- Lista de Serviços -->
    <div class="grid">
        {% for item in servicos %}
        <div class="card {{ 'destaque' if item.is_vip else '' }}">
            {% if item.is_vip %}
                <span class="badge-vip">★ PROFISSIONAL DESTAQUE</span>
            {% endif %}
            {% if item.imagem %}
                <div class="card-img-wrapper">
                    <img src="{{ item.imagem }}" alt="{{ item.titulo }}" class="card-img">
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
                    <div class="footer-card">
                        <strong>Profissional:</strong> {{ item.nome }}<br>
                        <strong>Contato:</strong> {{ item.contato }}
                        
                        {% if item.is_vip and item.wpp_link %}
                            <a href="{{ item.wpp_link }}?text=Olá%20{{ item.nome }},%20vi%20seu%20anúncio%20na%20Vitrine%20de%20Serviços!" target="_blank" class="btn-wpp">
                                💬 Chamar no WhatsApp
                            </a>
                        {% endif %}
                    </div>

                    <div class="card-actions-row">
                        <button onclick="abrirAvaliacao({{ item.id }}, '{{ item.titulo|replace("'", "") }}')" class="action-link">
                            ⭐ Avaliar
                        </button>
                        <a href="https://api.whatsapp.com/send?text=Olha%20esse%20serviço%20que%20encontrei:%20*{{ item.titulo }}*%20({{ item.cidade }})%20-%20{{ item.preco }}.%20Veja%20mais%20em:%20{{ url_site }}" target="_blank" class="action-link">
                            📤 Compartilhar
                        </a>
                        {% if not item.is_vip %}
                            <a href="/pagar/{{ item.id }}" class="action-link action-vip">⚡ Destacar</a>
                        {% endif %}
                    </div>
                </div>
            </div>
        </div>
        {% else %}
            <div class="card-box full-width" style="text-align:center;">
                <p>Nenhum serviço encontrado neste filtro ainda.</p>
                <button onclick="abrirModal('modalCadastro')" class="btn">Cadastrar Primeiro Serviço</button>
            </div>
        {% endfor %}
    </div>
</div>

<!-- MODAL 1: FORMULÁRIO DE CADASTRO -->
<div id="modalCadastro" class="modal-overlay">
    <div class="modal-box">
        <button onclick="fecharModal('modalCadastro')" class="modal-close">&times;</button>
        <h2 style="margin-top:0;">Divulgar Meu Trabalho</h2>
        <p style="font-size:13px; color:var(--muted); margin-top:-10px; margin-bottom:18px;">Preencha os dados abaixo para aparecer na vitrine.</p>
        
        <form action="/adicionar" method="POST">
            <div class="form-grid">
                <div class="form-group">
                    <label>Seu Nome ou Empresa:</label>
                    <input type="text" name="nome" required placeholder="Ex: Marcão do Povo">
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
                    <label>Cidade / Bairro:</label>
                    <input type="text" name="cidade" required placeholder="Ex: Formosa do Oeste - PR">
                </div>
                <div class="form-group">
                    <label>Preço (ou valor inicial):</label>
                    <input type="text" name="preco" required placeholder="Ex: R$ 80,00">
                </div>
                <div class="form-group">
                    <label>WhatsApp (com DDD):</label>
                    <input type="text" name="contato" required placeholder="Ex: (44) 99825-8119">
                </div>
                <div class="form-group full-width">
                    <label>Foto do Trabalho ou Cartão (Opcional):</label>
                    <input type="file" id="inputFoto" accept="image/*">
                    <input type="hidden" name="imagem_base64" id="imagemBase64">
                    <small style="color:var(--muted);" id="statusFoto">A imagem aparecerá por inteiro no seu anúncio.</small>
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
                        <strong>Quero Destaque VIP no Topo por {{ cfg.dias_destaque }} dias ({{ cfg.valor_destaque }})</strong><br>
                        <small style="font-weight:normal;">Anúncios VIP recebem até <strong>5x mais contatos</strong>: ficam fixados no topo com borda dourada e botão direto para o seu WhatsApp!</small>
                    </span>
                </label>
            </div>

            <button type="submit" class="btn" style="width:100%; padding:14px; font-size:16px;">Publicar Anúncio Agora</button>
        </form>
    </div>
</div>

<!-- MODAL 2: AVALIAR PROFISSIONAL -->
<div id="modalAvaliacao" class="modal-overlay">
    <div class="modal-box" style="max-width: 440px;">
        <button onclick="fecharModal('modalAvaliacao')" class="modal-close">&times;</button>
        <h3 style="margin-top:0;">Avaliar Serviço</h3>
        <p id="tituloServicoAval" style="font-size:14px; font-weight:bold; color:var(--primary);"></p>
        <form action="/avaliar" method="POST">
            <input type="hidden" name="servico_id" id="inputServicoIdAval">
            <div class="form-group">
                <label>Seu Nome:</label>
                <input type="text" name="autor" required placeholder="Ex: João da Silva">
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
function abrirModal(id) {
    document.getElementById(id).style.display = 'block';
}
function fecharModal(id) {
    document.getElementById(id).style.display = 'none';
}
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
            document.getElementById('statusFoto').innerText = "✓ Foto pronta para publicação!";
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
    <title>Ativar Destaque VIP</title>
    """ + HTML_BASE_CSS + """
</head>
<body>
<header>
    <h1>Destacar Anúncio no Topo</h1>
    <p>Multiplique seus contatos ficando em primeiro lugar por {{ cfg.dias_destaque }} dias</p>
</header>
<div class="container" style="max-width: 580px;">
    <div class="card-box" style="text-align: center;">
        <h2 style="margin-top:0; color:var(--vip-dark);">Anúncio: {{ servico.titulo }}</h2>
        <p>Seu anúncio gratuito já está publicado! Para ativar o <strong>Selo VIP, Borda Dourada, Topo da Página e Botão Direto do WhatsApp</strong>, faça o Pix abaixo:</p>
        
        <div style="background:#f8fafc; border:1px dashed #94a3b8; padding:20px; border-radius:8px; margin:20px 0;">
            <p style="margin:0 0 5px 0; font-size:14px; color:var(--muted);">Valor do Plano ({{ cfg.dias_destaque }} dias):</p>
            <div style="font-size:30px; font-weight:bold; color:var(--accent); margin-bottom:15px;">{{ cfg.valor_destaque }}</div>
            
            <p style="margin:0 0 5px 0; font-size:14px; color:var(--muted);">Chave Pix (Copie abaixo):</p>
            <input type="text" value="{{ cfg.chave_pix }}" id="chavePix" readonly style="text-align:center; font-weight:bold; font-size:15px; background:white;">
            <button onclick="copiarPix()" class="btn" style="margin-top:10px; background:var(--secondary); width:100%;">Copiar Chave Pix</button>
        </div>

        <p style="font-size:14px; color:#475569;">Após realizar o Pix, clique no botão abaixo para enviar o comprovante e liberar seu destaque imediatamente:</p>
        
        <a href="https://wa.me/{{ cfg.seu_whatsapp }}?text=Olá!%20Acabei%20de%20fazer%20o%20Pix%20de%20{{ cfg.valor_destaque }}%20para%20destacar%20o%20anúncio%20ID%20%23{{ servico.id }}%20({{ servico.titulo }}).%20Segue%20o%20comprovante:" target="_blank" class="btn btn-vip" style="width:100%; padding:14px; font-size:16px;">
            Enviar Comprovante no WhatsApp
        </a>
        
        <br><br>
        <a href="/" style="color:var(--muted); text-decoration:none; font-size:14px;">← Voltar para a Vitrine</a>
    </div>
</div>
<script>
function copiarPix() {
    var copyText = document.getElementById("chavePix");
    copyText.select();
    copyText.setSelectionRange(0, 99999);
    navigator.clipboard.writeText(copyText.value);
    alert("Chave Pix copiada: " + copyText.value);
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
    <title>Painel Administrativo</title>
    """ + HTML_BASE_CSS + """
    <style>
        table { width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 14px; }
        th, td { border-bottom: 1px solid #e2e8f0; padding: 12px 8px; text-align: left; }
        th { background: #f8fafc; }
    </style>
</head>
<body>
<div class="top-bar">
    <span>Administração da Vitrine</span>
    <div>
        <a href="/">Ver Site</a>
        {% if logado %}<a href="/admin/logout">Sair</a>{% endif %}
    </div>
</div>
<header>
    <h1>Painel de Controle</h1>
    <p>Gerencie anúncios VIP, patrocinadores e configurações de Pix</p>
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
        <!-- Configurações de Pix e Patrocinador -->
        <div class="card-box">
            <h2 style="margin-top:0;">Configurações de Lucro (Pix e Banner Patrocinador)</h2>
            {% if salvo %}<p style="color:var(--accent); font-weight:bold;">✓ Configurações salvas com sucesso!</p>{% endif %}
            <form action="/admin/config" method="POST">
                <div class="form-grid">
                    <div class="form-group">
                        <label>Sua Chave Pix:</label>
                        <input type="text" name="chave_pix" value="{{ cfg.chave_pix }}" required>
                    </div>
                    <div class="form-group">
                        <label>Seu WhatsApp (com 55 + DDD):</label>
                        <input type="text" name="seu_whatsapp" value="{{ cfg.seu_whatsapp }}" required>
                    </div>
                    <div class="form-group">
                        <label>Valor do Destaque VIP:</label>
                        <input type="text" name="valor_destaque" value="{{ cfg.valor_destaque }}" required>
                    </div>
                    <div class="form-group">
                        <label>Duração do VIP (dias):</label>
                        <input type="number" name="dias_destaque" value="{{ cfg.dias_destaque }}" required>
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
                    <div class="form-group full-width">
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

        <!-- Tabela de Anúncios -->
        <div class="card-box" style="overflow-x:auto;">
            <h2 style="margin-top:0;">Anúncios Cadastrados ({{ servicos|length }})</h2>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Profissional / Serviço</th>
                        <th>Cidade / Contato</th>
                        <th>Status VIP</th>
                        <th>Ações</th>
                    </tr>
                </thead>
                <tbody>
                    {% for s in servicos %}
                    <tr>
                        <td><strong>#{{ s.id }}</strong></td>
                        <td>
                            <strong>{{ s.titulo }}</strong><br>
                            <small>{{ s.nome }} • {{ s.preco }}</small>
                        </td>
                        <td>
                            {{ s.cidade }}<br>
                            <small>{{ s.contato }}</small>
                        </td>
                        <td>
                            {% if s.is_vip %}
                                <span style="color:var(--vip-dark); font-weight:bold;">VIP até {{ s.destaque_ate[:10] }}</span>
                            {% else %}
                                <span style="color:var(--muted);">Gratuito</span>
                            {% endif %}
                        </td>
                        <td style="display:flex; gap:6px; flex-wrap:wrap;">
                            <a href="/admin/vip/{{ s.id }}" class="btn btn-vip btn-sm">+{{ cfg.dias_destaque }}d VIP</a>
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
    {% endif %}
</div>
</body>
</html>
"""

# =====================================================================
# ROTAS DO SISTEMA
# =====================================================================

@app.route("/")
def index():
    categoria = request.args.get("categoria", "")
    busca = request.args.get("busca", "").strip()
    cfg = get_config()
    db = DBWrapper()
    
    query = "SELECT * FROM servicos WHERE 1=1"
    params = []
    
    if categoria:
        query += " AND categoria = ?"
        params.append(categoria)
    if busca:
        query += " AND (titulo LIKE ? OR descricao LIKE ? OR cidade LIKE ? OR nome LIKE ?)"
        termo = f"%{busca}%"
        params.extend([termo, termo, termo, termo])
        
    query += " ORDER BY id DESC"
    rows = db.execute(query, params).fetchall()
    total = db.execute("SELECT COUNT(*) as c FROM servicos").fetchone()["c"]

    agora = datetime.now()
    lista_servicos = []
    
    for r in rows:
        item = dict(r)
        is_vip = False
        if item["destaque_ate"]:
            validade = datetime.fromisoformat(item["destaque_ate"])
            if validade > agora:
                is_vip = True
        item["is_vip"] = is_vip
        item["wpp_link"] = formatar_whatsapp(item["contato"])
        
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

        lista_servicos.append(item)

    db.close()
    lista_servicos.sort(key=lambda x: x["is_vip"], reverse=True)

    categorias = [
        ("Reformas e Reparos", "🛠️"),
        ("Tecnologia e Informática", "💻"),
        ("Design e Marketing", "🎨"),
        ("Aulas e Consultoria", "📚"),
        ("Saúde e Bem-estar", "🏥"),
        ("Fretes e Mudanças", "🚚"),
        ("Outros Serviços", "⚡")
    ]

    return render_template_string(
        HTML_INDEX,
        servicos=lista_servicos,
        categorias=categorias,
        cat_atual=categoria,
        busca_atual=busca,
        total=total,
        cfg=cfg,
        url_site=request.host_url
    )

@app.route("/adicionar", methods=["POST"])
def adicionar():
    nome = request.form.get("nome")
    titulo = request.form.get("titulo")
    categoria = request.form.get("categoria")
    cidade = request.form.get("cidade")
    preco = request.form.get("preco")
    descricao = request.form.get("descricao")
    contato = request.form.get("contato")
    imagem = request.form.get("imagem_base64") or None
    quer_destaque = request.form.get("quer_destaque")

    db = DBWrapper()
    novo_id = db.insert_returning_id("""
        INSERT INTO servicos (nome, titulo, categoria, cidade, preco, descricao, contato, imagem, destaque_ate, criado_em)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
    """, (nome, titulo, categoria, cidade, preco, descricao, contato, imagem, datetime.now().isoformat()))
    db.commit()
    db.close()

    if quer_destaque == "1":
        return redirect(url_for("pagar", servico_id=novo_id))
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
    cfg = get_config()
    db = DBWrapper()
    servico = db.execute("SELECT * FROM servicos WHERE id = ?", (servico_id,)).fetchone()
    db.close()
    if not servico:
        return redirect(url_for("index"))
    return render_template_string(HTML_PAGAR, servico=servico, cfg=cfg)

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
    db.close()

    agora = datetime.now()
    servicos = []
    for r in rows:
        item = dict(r)
        item["is_vip"] = bool(item["destaque_ate"] and datetime.fromisoformat(item["destaque_ate"]) > agora)
        servicos.append(item)

    return render_template_string(HTML_ADMIN, logado=True, servicos=servicos, cfg=cfg, salvo=salvo)

@app.route("/admin/config", methods=["POST"])
def salvar_config():
    if not session.get("admin_logado"):
        return redirect(url_for("admin"))
    campos = [
        "chave_pix", "seu_whatsapp", "valor_destaque", "dias_destaque",
        "banner_ativo", "banner_titulo", "banner_texto", "banner_link"
    ]
    db = DBWrapper()
    for c in campos:
        val = request.form.get(c, "").strip()
        if val != "":
            db.execute("UPDATE config SET valor = ? WHERE chave = ?", (val, c))
    db.commit()
    db.close()
    return redirect(url_for("admin", salvo=1))

@app.route("/admin/vip/<int:servico_id>")
def ativar_vip(servico_id):
    if not session.get("admin_logado"):
        return redirect(url_for("admin"))
    cfg = get_config()
    dias = int(cfg.get("dias_destaque", 30))
    validade = (datetime.now() + timedelta(days=dias)).isoformat()
    db = DBWrapper()
    db.execute("UPDATE servicos SET destaque_ate = ? WHERE id = ?", (validade, servico_id))
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

@app.route("/admin/logout")
def logout():
    session.pop("admin_logado", None)
    return redirect(url_for("index"))

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
