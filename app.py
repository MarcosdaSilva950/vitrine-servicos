import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request, redirect, url_for, session

app = Flask(__name__)

# =====================================================================
# SUAS CONFIGURAÇÕES (ALTERE AQUI COM SEUS DADOS)
# =====================================================================
app.secret_key = "troque_essa_chave_por_uma_frase_aleatoria_qualquer"
SENHA_ADMIN = "22041988"                # Senha para acessar /admin
SUA_CHAVE_PIX = "03019260183"   # Sua chave Pix (CPF, E-mail ou Aleatória)
SEU_WHATSAPP = "5544998258119"        # Seu WhatsApp com 55 + DDD + Número (só números)
VALOR_DESTAQUE = "R$ 19,90"           # Valor cobrado por 30 dias no topo
DIAS_DESTAQUE = 30                    # Duração do plano VIP
# =====================================================================

DB_NAME = "vitrine.db"

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS servicos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            titulo TEXT NOT NULL,
            categoria TEXT NOT NULL,
            preco TEXT NOT NULL,
            descricao TEXT NOT NULL,
            contato TEXT NOT NULL,
            destaque_ate TEXT,
            criado_em TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def formatar_whatsapp(contato):
    """Extrai apenas números para montar o link wa.me se parecer um telefone."""
    numeros = "".join(filter(str.isdigit, contato))
    if len(numeros) in (10, 11):
        return f"https://wa.me/55{numeros}"
    elif len(numeros) in (12, 13) and numeros.startswith("55"):
        return f"https://wa.me/{numeros}"
    return None

# =====================================================================
# TEMPLATES HTML (INTERFACE PRINCIPAL, PIX E PAINEL ADMIN)
# =====================================================================

HTML_BASE_CSS = """
<style>
    * { box-sizing: border-box; }
    body {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        background-color: #f0f2f5;
        color: #1c1e21;
        margin: 0;
        padding: 0;
    }
    header {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        color: white;
        padding: 25px 20px;
        text-align: center;
    }
    header h1 { margin: 0 0 8px 0; font-size: 28px; }
    header p { margin: 0; color: #cbd5e1; font-size: 15px; }
    .nav-bar {
        background: #0f172a;
        padding: 8px 20px;
        text-align: right;
        font-size: 13px;
    }
    .nav-bar a { color: #94a3b8; text-decoration: none; margin-left: 15px; }
    .nav-bar a:hover { color: white; }
    .container { max-width: 1000px; margin: 30px auto; padding: 0 20px; }
    .card-box {
        background: white;
        padding: 25px;
        border-radius: 10px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.08);
        margin-bottom: 35px;
    }
    .form-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 15px;
    }
    @media (max-width: 650px) { .form-grid { grid-template-columns: 1fr; } }
    .form-group { margin-bottom: 15px; }
    .full-width { grid-column: 1 / -1; }
    label { display: block; font-weight: 600; margin-bottom: 5px; font-size: 14px; }
    input, textarea, select {
        width: 100%;
        padding: 10px 12px;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        font-size: 14px;
    }
    .vip-box {
        background: #fffbeb;
        border: 2px solid #f59e0b;
        padding: 15px;
        border-radius: 8px;
        margin: 15px 0;
    }
    .vip-box label {
        display: flex;
        align-items: center;
        gap: 10px;
        cursor: pointer;
        margin: 0;
        color: #92400e;
        font-size: 15px;
    }
    .vip-box input[type="checkbox"] { width: 18px; height: 18px; }
    .btn {
        background-color: #16a34a;
        color: white;
        border: none;
        padding: 13px 20px;
        font-size: 16px;
        border-radius: 6px;
        cursor: pointer;
        width: 100%;
        font-weight: bold;
        text-decoration: none;
        display: inline-block;
        text-align: center;
    }
    .btn:hover { background-color: #15803d; }
    .btn-vip { background-color: #d97706; }
    .btn-vip:hover { background-color: #b45309; }
    .btn-danger { background-color: #dc2626; padding: 6px 12px; font-size: 13px; width: auto; }
    .btn-sm { padding: 6px 12px; font-size: 13px; width: auto; }
    
    /* Filtros */
    .filtros { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 20px; }
    .filtro-btn {
        background: white;
        border: 1px solid #cbd5e1;
        padding: 7px 14px;
        border-radius: 20px;
        text-decoration: none;
        color: #334155;
        font-size: 13px;
        font-weight: 600;
    }
    .filtro-btn.ativo, .filtro-btn:hover { background: #1e293b; color: white; border-color: #1e293b; }

    /* Grid de Anúncios */
    .grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
        gap: 20px;
    }
    .card {
        background: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        border-top: 4px solid #64748b;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        position: relative;
    }
    .card.destaque {
        border: 2px solid #f59e0b;
        border-top: 6px solid #f59e0b;
        background: linear-gradient(to bottom, #fffdf7, #ffffff);
        box-shadow: 0 4px 15px rgba(245, 158, 11, 0.18);
    }
    .badge-vip {
        position: absolute;
        top: -12px;
        right: 15px;
        background: #f59e0b;
        color: white;
        font-size: 11px;
        font-weight: bold;
        padding: 3px 10px;
        border-radius: 12px;
        letter-spacing: 0.5px;
    }
    .categoria {
        font-size: 12px;
        background: #e2e8f0;
        color: #334155;
        padding: 3px 9px;
        border-radius: 12px;
        display: inline-block;
        margin-bottom: 8px;
        font-weight: 600;
    }
    .card h3 { margin: 5px 0 10px 0; color: #0f172a; font-size: 18px; }
    .descricao { font-size: 14px; color: #475569; line-height: 1.5; }
    .preco { font-size: 20px; font-weight: bold; color: #16a34a; margin: 12px 0; }
    .footer-card {
        border-top: 1px solid #e2e8f0;
        padding-top: 12px;
        margin-top: 10px;
        font-size: 13px;
        color: #475569;
    }
    .btn-wpp {
        display: block;
        background: #25D366;
        color: white;
        text-align: center;
        padding: 9px;
        border-radius: 6px;
        text-decoration: none;
        font-weight: bold;
        margin-top: 10px;
        font-size: 14px;
    }
    .btn-wpp:hover { background: #1ebe5d; }
    .link-destacar {
        display: inline-block;
        margin-top: 8px;
        font-size: 12px;
        color: #d97706;
        text-decoration: none;
        font-weight: 600;
    }
    .link-destacar:hover { text-decoration: underline; }
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

<div class="nav-bar">
    <a href="/">Início</a>
    <a href="/admin">Painel Admin</a>
</div>

<header>
    <h1>Vitrine de Serviços</h1>
    <p>Encontre profissionais qualificados ou divulgue seu trabalho gratuitamente</p>
</header>

<div class="container">
    <!-- Formulário de Cadastro -->
    <div class="card-box">
        <h2 style="margin-top:0;">Divulgar Meu Trabalho</h2>
        <form action="/adicionar" method="POST">
            <div class="form-grid">
                <div class="form-group">
                    <label>Seu Nome ou Empresa:</label>
                    <input type="text" name="nome" required placeholder="Ex: Carlos Mendes">
                </div>
                <div class="form-group">
                    <label>Título do Serviço:</label>
                    <input type="text" name="titulo" required placeholder="Ex: Eletricista e Reparos Residenciais">
                </div>
                <div class="form-group">
                    <label>Categoria:</label>
                    <select name="categoria">
                        <option value="Reformas e Reparos">Reformas e Reparos</option>
                        <option value="Tecnologia e Informática">Tecnologia e Informática</option>
                        <option value="Design e Marketing">Design e Marketing</option>
                        <option value="Aulas e Consultoria">Aulas e Consultoria</option>
                        <option value="Saúde e Bem-estar">Saúde e Bem-estar</option>
                        <option value="Outros Serviços">Outros Serviços</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Preço (ou valor inicial):</label>
                    <input type="text" name="preco" required placeholder="Ex: R$ 100,00 / visita">
                </div>
                <div class="form-group full-width">
                    <label>Descrição Detalhada:</label>
                    <textarea name="descricao" rows="3" required placeholder="Explique o que você faz, região de atendimento e diferenciais..."></textarea>
                </div>
                <div class="form-group full-width">
                    <label>WhatsApp (com DDD) ou Instagram:</label>
                    <input type="text" name="contato" required placeholder="Ex: (44) 99999-8888">
                </div>
            </div>

            <div class="vip-box">
                <label>
                    <input type="checkbox" name="quer_destaque" value="1">
                    <span>
                        <strong>Quero Destaque VIP no Topo por {{ dias }} dias ({{ valor }})</strong><br>
                        <small style="font-weight:normal;">Seu anúncio fica fixado no topo com borda dourada e botão direto para o seu WhatsApp!</small>
                    </span>
                </label>
            </div>

            <button type="submit" class="btn">Publicar Anúncio</button>
        </form>
    </div>

    <!-- Filtros por Categoria -->
    <div class="filtros">
        <a href="/" class="filtro-btn {{ 'ativo' if not cat_atual else '' }}">Todos ({{ total }})</a>
        {% for c in categorias %}
            <a href="/?categoria={{ c }}" class="filtro-btn {{ 'ativo' if cat_atual == c else '' }}">{{ c }}</a>
        {% endfor %}
    </div>

    <!-- Lista de Serviços -->
    <div class="grid">
        {% for item in servicos %}
        <div class="card {{ 'destaque' if item.is_vip else '' }}">
            {% if item.is_vip %}
                <span class="badge-vip">★ PROFISSIONAL DESTAQUE</span>
            {% endif %}
            <div>
                <span class="categoria">{{ item.categoria }}</span>
                <h3>{{ item.titulo }}</h3>
                <p class="descricao">{{ item.descricao }}</p>
            </div>
            <div>
                <div class="preco">{{ item.preco }}</div>
                <div class="footer-card">
                    <strong>Profissional:</strong> {{ item.nome }}<br>
                    <strong>Contato:</strong> {{ item.contato }}
                    
                    {% if item.is_vip and item.wpp_link %}
                        <a href="{{ item.wpp_link }}?text=Olá%20{{ item.nome }},%20vi%20seu%20anúncio%20na%20Vitrine%20de%20Serviços!" target="_blank" class="btn-wpp">
                            Chamar no WhatsApp
                        </a>
                    {% elif not item.is_vip %}
                        <br><a href="/pagar/{{ item.id }}" class="link-destacar">⚡ Impulsionar este anúncio para o topo</a>
                    {% endif %}
                </div>
            </div>
        </div>
        {% else %}
            <p>Nenhum serviço encontrado nesta categoria ainda. Seja o primeiro a publicar!</p>
        {% endfor %}
    </div>
</div>

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
    <p>Aumente seus clientes ficando em primeiro lugar por {{ dias }} dias</p>
</header>
<div class="container" style="max-width: 600px;">
    <div class="card-box" style="text-align: center;">
        <h2 style="margin-top:0; color:#d97706;">Anúncio: {{ servico.titulo }}</h2>
        <p>Seu anúncio gratuito já está publicado! Para ativar o <strong>Selo VIP, Borda Dourada, Topo da Página e Botão Direto do WhatsApp</strong>, faça o Pix abaixo:</p>
        
        <div style="background:#f8fafc; border:1px dashed #94a3b8; padding:20px; border-radius:8px; margin:20px 0;">
            <p style="margin:0 0 5px 0; font-size:14px; color:#64748b;">Valor do Plano ({{ dias }} dias):</p>
            <div style="font-size:28px; font-weight:bold; color:#16a34a; margin-bottom:15px;">{{ valor }}</div>
            
            <p style="margin:0 0 5px 0; font-size:14px; color:#64748b;">Chave Pix (Copie abaixo):</p>
            <input type="text" value="{{ chave_pix }}" id="chavePix" readonly style="text-align:center; font-weight:bold; font-size:16px; background:white;">
            <button onclick="copiarPix()" class="btn" style="margin-top:10px; background:#334155;">Copiar Chave Pix</button>
        </div>

        <p style="font-size:14px; color:#475569;">Após realizar o pagamento, clique no botão abaixo para enviar o comprovante e liberar seu destaque imediatamente:</p>
        
        <a href="https://wa.me/{{ seu_wpp }}?text=Olá!%20Acabei%20de%20fazer%20o%20Pix%20de%20{{ valor }}%20para%20destacar%20o%20anúncio%20ID%20%23{{ servico.id }}%20({{ servico.titulo }}).%20Segue%20o%20comprovante:" target="_blank" class="btn btn-vip">
            Enviar Comprovante no WhatsApp
        </a>
        
        <br><br>
        <a href="/" style="color:#64748b; text-decoration:none; font-size:14px;">← Voltar para a Vitrine</a>
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
<div class="nav-bar">
    <a href="/">Ver Site</a>
    {% if logado %}<a href="/admin/logout">Sair</a>{% endif %}
</div>
<header>
    <h1>Painel de Controle</h1>
    <p>Gerencie anúncios e libere destaques VIP</p>
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
                <button type="submit" class="btn">Entrar</button>
            </form>
        </div>
    {% else %}
        <div class="card-box" style="overflow-x:auto;">
            <h2 style="margin-top:0;">Anúncios Cadastrados ({{ servicos|length }})</h2>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Profissional / Serviço</th>
                        <th>Contato</th>
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
                        <td>{{ s.contato }}</td>
                        <td>
                            {% if s.is_vip %}
                                <span style="color:#d97706; font-weight:bold;">VIP até {{ s.destaque_ate[:10] }}</span>
                            {% else %}
                                <span style="color:#64748b;">Gratuito</span>
                            {% endif %}
                        </td>
                        <td style="display:flex; gap:6px; flex-wrap:wrap;">
                            <a href="/admin/vip/{{ s.id }}" class="btn btn-vip btn-sm">+{{ dias }}d VIP</a>
                            {% if s.is_vip %}
                                <a href="/admin/remover_vip/{{ s.id }}" class="btn btn-sm" style="background:#64748b;">Tirar VIP</a>
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
    conn = get_db()
    
    if categoria:
        rows = conn.execute("SELECT * FROM servicos WHERE categoria = ? ORDER BY id DESC", (categoria,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM servicos ORDER BY id DESC").fetchall()
        
    total = conn.execute("SELECT COUNT(*) FROM servicos").fetchone()[0]
    conn.close()

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
        lista_servicos.append(item)

    # Ordena colocando os VIPs primeiro no topo, mantendo os mais recentes no topo de cada grupo
    lista_servicos.sort(key=lambda x: x["is_vip"], reverse=True)

    categorias = [
        "Reformas e Reparos",
        "Tecnologia e Informática",
        "Design e Marketing",
        "Aulas e Consultoria",
        "Saúde e Bem-estar",
        "Outros Serviços"
    ]

    return render_template_string(
        HTML_INDEX,
        servicos=lista_servicos,
        categorias=categorias,
        cat_atual=categoria,
        total=total,
        valor=VALOR_DESTAQUE,
        dias=DIAS_DESTAQUE
    )

@app.route("/adicionar", methods=["POST"])
def adicionar():
    nome = request.form.get("nome")
    titulo = request.form.get("titulo")
    categoria = request.form.get("categoria")
    preco = request.form.get("preco")
    descricao = request.form.get("descricao")
    contato = request.form.get("contato")
    quer_destaque = request.form.get("quer_destaque")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO servicos (nome, titulo, categoria, preco, descricao, contato, destaque_ate, criado_em)
        VALUES (?, ?, ?, ?, ?, ?, NULL, ?)
    """, (nome, titulo, categoria, preco, descricao, contato, datetime.now().isoformat()))
    novo_id = cursor.lastrowid
    conn.commit()
    conn.close()

    if quer_destaque == "1":
        return redirect(url_for("pagar", servico_id=novo_id))
    return redirect(url_for("index"))

@app.route("/pagar/<int:servico_id>")
def pagar(servico_id):
    conn = get_db()
    servico = conn.execute("SELECT * FROM servicos WHERE id = ?", (servico_id,)).fetchone()
    conn.close()
    if not servico:
        return redirect(url_for("index"))
    return render_template_string(
        HTML_PAGAR,
        servico=servico,
        chave_pix=SUA_CHAVE_PIX,
        seu_wpp=SEU_WHATSAPP,
        valor=VALOR_DESTAQUE,
        dias=DIAS_DESTAQUE
    )

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

    conn = get_db()
    rows = conn.execute("SELECT * FROM servicos ORDER BY id DESC").fetchall()
    conn.close()

    agora = datetime.now()
    servicos = []
    for r in rows:
        item = dict(r)
        item["is_vip"] = bool(item["destaque_ate"] and datetime.fromisoformat(item["destaque_ate"]) > agora)
        servicos.append(item)

    return render_template_string(HTML_ADMIN, logado=True, servicos=servicos, dias=DIAS_DESTAQUE)

@app.route("/admin/vip/<int:servico_id>")
def ativar_vip(servico_id):
    if not session.get("admin_logado"):
        return redirect(url_for("admin"))
    validade = (datetime.now() + timedelta(days=DIAS_DESTAQUE)).isoformat()
    conn = get_db()
    conn.execute("UPDATE servicos SET destaque_ate = ? WHERE id = ?", (validade, servico_id))
    conn.commit()
    conn.close()
    return redirect(url_for("admin"))

@app.route("/admin/remover_vip/<int:servico_id>")
def remover_vip(servico_id):
    if not session.get("admin_logado"):
        return redirect(url_for("admin"))
    conn = get_db()
    conn.execute("UPDATE servicos SET destaque_ate = NULL WHERE id = ?", (servico_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin"))

@app.route("/admin/excluir/<int:servico_id>")
def excluir_servico(servico_id):
    if not session.get("admin_logado"):
        return redirect(url_for("admin"))
    conn = get_db()
    conn.execute("DELETE FROM servicos WHERE id = ?", (servico_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin"))

@app.route("/admin/logout")
def logout():
    session.pop("admin_logado", None)
    return redirect(url_for("index"))

# Inicializa o banco de dados ao carregar a aplicação
init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)