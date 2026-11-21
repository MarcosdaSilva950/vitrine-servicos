import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request, redirect, url_for, session

app = Flask(__name__)

# =====================================================================
# CONFIGURAÇÕES INICIAIS (SUAS CREDENCIAIS)
# =====================================================================
app.secret_key = "chave_secreta_vitrine_marcao_2026"
SENHA_ADMIN = "22041988"
PIX_PADRAO = "997ef3d7-4a1c-436f-b4fa-2c668ad7"
WPP_PADRAO = "5544998258119"
VALOR_PADRAO = "R$ 19,90"
DIAS_PADRAO = "30"
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
            cidade TEXT NOT NULL,
            preco TEXT NOT NULL,
            descricao TEXT NOT NULL,
            contato TEXT NOT NULL,
            imagem TEXT,
            destaque_ate TEXT,
            criado_em TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS config (
            chave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        )
    """)
    padroes = {
        "chave_pix": PIX_PADRAO,
        "seu_whatsapp": WPP_PADRAO,
        "valor_destaque": VALOR_PADRAO,
        "dias_destaque": DIAS_PADRAO
    }
    for k, v in padroes.items():
        conn.execute("INSERT OR IGNORE INTO config (chave, valor) VALUES (?, ?)", (k, v))
    conn.commit()
    conn.close()

def get_config():
    conn = get_db()
    rows = conn.execute("SELECT chave, valor FROM config").fetchall()
    conn.close()
    return {r["chave"]: r["valor"] for r in rows}

def formatar_whatsapp(contato):
    numeros = "".join(filter(str.isdigit, contato))
    if len(numeros) in (10, 11):
        return f"https://wa.me/55{numeros}"
    elif len(numeros) in (12, 13) and numeros.startswith("55"):
        return f"https://wa.me/{numeros}"
    return None

# =====================================================================
# ESTILOS E TEMPLATES HTML
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
    .container { max-width: 1050px; margin: 30px auto; padding: 0 20px; }
    .card-box {
        background: white;
        padding: 25px;
        border-radius: 10px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.08);
        margin-bottom: 30px;
    }
    .form-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 15px;
    }
    @media (max-width: 650px) { .form-grid { grid-template-columns: 1fr; } }
    .form-group { margin-bottom: 12px; }
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
    
    /* Busca e Filtros */
    .busca-bar {
        display: flex;
        gap: 10px;
        margin-bottom: 15px;
        flex-wrap: wrap;
    }
    .busca-bar input { flex: 1; min-width: 220px; background: white; }
    .busca-bar button { width: auto; padding: 10px 20px; background: #1e293b; }
    .filtros { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 25px; }
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
        border-radius: 10px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        border-top: 4px solid #64748b;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        position: relative;
        overflow: hidden;
    }
    .card.destaque {
        border: 2px solid #f59e0b;
        border-top: 6px solid #f59e0b;
        background: linear-gradient(to bottom, #fffdf7, #ffffff);
        box-shadow: 0 4px 15px rgba(245, 158, 11, 0.18);
    }
    .card-img {
        width: 100%;
        height: 180px;
        object-fit: cover;
        border-bottom: 1px solid #e2e8f0;
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
        top: 10px;
        right: 10px;
        background: #f59e0b;
        color: white;
        font-size: 11px;
        font-weight: bold;
        padding: 4px 10px;
        border-radius: 12px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.2);
    }
    .tags-row { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }
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
    <p>Encontre profissionais da sua região ou divulgue seu trabalho gratuitamente</p>
</header>

<div class="container">
    <!-- Formulário de Cadastro -->
    <div class="card-box">
        <h2 style="margin-top:0;">Divulgar Meu Trabalho</h2>
        <form action="/adicionar" method="POST" id="formServico">
            <div class="form-grid">
                <div class="form-group">
                    <label>Seu Nome ou Empresa:</label>
                    <input type="text" name="nome" required placeholder="Ex: Marcão do Povo">
                </div>
                <div class="form-group">
                    <label>Título do Serviço:</label>
                    <input type="text" name="titulo" required placeholder="Ex: Reparos Residenciais e Manutenção">
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
                    <label>Cidade / Bairro de Atendimento:</label>
                    <input type="text" name="cidade" required placeholder="Ex: Assis Chateaubriand - PR">
                </div>
                <div class="form-group">
                    <label>Preço (ou valor inicial):</label>
                    <input type="text" name="preco" required placeholder="Ex: R$ 80,00">
                </div>
                <div class="form-group">
                    <label>WhatsApp (com DDD) ou Instagram:</label>
                    <input type="text" name="contato" required placeholder="Ex: (44) 99825-8119">
                </div>
                <div class="form-group full-width">
                    <label>Foto do Trabalho ou Cartão (Opcional):</label>
                    <input type="file" id="inputFoto" accept="image/*">
                    <input type="hidden" name="imagem_base64" id="imagemBase64">
                    <small style="color:#64748b;" id="statusFoto">Escolha uma foto do celular ou PC para chamar mais atenção.</small>
                </div>
                <div class="form-group full-width">
                    <label>Descrição Detalhada:</label>
                    <textarea name="descricao" rows="3" required placeholder="Explique o que você faz, horários e diferenciais..."></textarea>
                </div>
            </div>

            <div class="vip-box">
                <label>
                    <input type="checkbox" name="quer_destaque" value="1">
                    <span>
                        <strong>Quero Destaque VIP no Topo por {{ cfg.dias_destaque }} dias ({{ cfg.valor_destaque }})</strong><br>
                        <small style="font-weight:normal;">Seu anúncio fica fixado no topo com borda dourada e botão direto para o seu WhatsApp!</small>
                    </span>
                </label>
            </div>

            <button type="submit" class="btn">Publicar Anúncio</button>
        </form>
    </div>

    <!-- Barra de Busca por Cidade ou Serviço -->
    <form action="/" method="GET" class="busca-bar">
        {% if cat_atual %}<input type="hidden" name="categoria" value="{{ cat_atual }}">{% endif %}
        <input type="text" name="busca" value="{{ busca_atual }}" placeholder="Buscar por cidade, bairro ou tipo de serviço...">
        <button type="submit" class="btn">Filtrar</button>
        {% if busca_atual or cat_atual %}
            <a href="/" class="btn" style="width:auto; background:#64748b; padding:10px 15px;">Limpar</a>
        {% endif %}
    </form>

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
            {% if item.imagem %}
                <img src="{{ item.imagem }}" alt="{{ item.titulo }}" class="card-img">
            {% endif %}
            <div class="card-body">
                <div>
                    <div class="tags-row">
                        <span class="categoria">{{ item.categoria }}</span>
                        <span class="cidade-tag">📍 {{ item.cidade }}</span>
                    </div>
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
        </div>
        {% else %}
            <p>Nenhum serviço encontrado com esse filtro. Seja o primeiro a publicar!</p>
        {% endfor %}
    </div>
</div>

<script>
// Redimensiona e comprime a foto automaticamente antes de enviar para ficar leve e rápido
document.getElementById('inputFoto').addEventListener('change', function(e) {
    const file = e.target.files[0];
    if (!file) return;
    document.getElementById('statusFoto').innerText = "Processando imagem...";
    const reader = new FileReader();
    reader.onload = function(event) {
        const img = new Image();
        img.onload = function() {
            const canvas = document.createElement('canvas');
            const maxWidth = 600;
            const scale = maxWidth / img.width;
            canvas.width = maxWidth;
            canvas.height = img.height * scale;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            const dataUrl = canvas.toDataURL('image/jpeg', 0.72);
            document.getElementById('imagemBase64').value = dataUrl;
            document.getElementById('statusFoto').innerText = "✓ Foto pronta para envio!";
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
    <p>Aumente seus clientes ficando em primeiro lugar por {{ cfg.dias_destaque }} dias</p>
</header>
<div class="container" style="max-width: 600px;">
    <div class="card-box" style="text-align: center;">
        <h2 style="margin-top:0; color:#d97706;">Anúncio: {{ servico.titulo }}</h2>
        <p>Seu anúncio gratuito já está publicado! Para ativar o <strong>Selo VIP, Borda Dourada, Topo da Página e Botão Direto do WhatsApp</strong>, faça o Pix abaixo:</p>
        
        <div style="background:#f8fafc; border:1px dashed #94a3b8; padding:20px; border-radius:8px; margin:20px 0;">
            <p style="margin:0 0 5px 0; font-size:14px; color:#64748b;">Valor do Plano ({{ cfg.dias_destaque }} dias):</p>
            <div style="font-size:28px; font-weight:bold; color:#16a34a; margin-bottom:15px;">{{ cfg.valor_destaque }}</div>
            
            <p style="margin:0 0 5px 0; font-size:14px; color:#64748b;">Chave Pix (Copie abaixo):</p>
            <input type="text" value="{{ cfg.chave_pix }}" id="chavePix" readonly style="text-align:center; font-weight:bold; font-size:15px; background:white;">
            <button onclick="copiarPix()" class="btn" style="margin-top:10px; background:#334155;">Copiar Chave Pix</button>
        </div>

        <p style="font-size:14px; color:#475569;">Após realizar o pagamento, clique no botão abaixo para enviar o comprovante e liberar seu destaque imediatamente:</p>
        
        <a href="https://wa.me/{{ cfg.seu_whatsapp }}?text=Olá!%20Acabei%20de%20fazer%20o%20Pix%20de%20{{ cfg.valor_destaque }}%20para%20destacar%20o%20anúncio%20ID%20%23{{ servico.id }}%20({{ servico.titulo }}).%20Segue%20o%20comprovante:" target="_blank" class="btn btn-vip">
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
    <p>Gerencie anúncios, libere destaques VIP e ajuste suas configurações</p>
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
        <!-- Bloco de Configurações Rápidas -->
        <div class="card-box">
            <h2 style="margin-top:0;">Configurações de Cobrança (Pix e VIP)</h2>
            {% if salvo %}<p style="color:#16a34a; font-weight:bold;">✓ Configurações atualizadas com sucesso!</p>{% endif %}
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
                        <label>Duração do VIP (em dias):</label>
                        <input type="number" name="dias_destaque" value="{{ cfg.dias_destaque }}" required>
                    </div>
                </div>
                <button type="submit" class="btn" style="max-width:250px;">Salvar Configurações</button>
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
                                <span style="color:#d97706; font-weight:bold;">VIP até {{ s.destaque_ate[:10] }}</span>
                            {% else %}
                                <span style="color:#64748b;">Gratuito</span>
                            {% endif %}
                        </td>
                        <td style="display:flex; gap:6px; flex-wrap:wrap;">
                            <a href="/admin/vip/{{ s.id }}" class="btn btn-vip btn-sm">+{{ cfg.dias_destaque }}d VIP</a>
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
    busca = request.args.get("busca", "").strip()
    cfg = get_config()
    conn = get_db()
    
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
    rows = conn.execute(query, params).fetchall()
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
        busca_atual=busca,
        total=total,
        cfg=cfg
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

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO servicos (nome, titulo, categoria, cidade, preco, descricao, contato, imagem, destaque_ate, criado_em)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
    """, (nome, titulo, categoria, cidade, preco, descricao, contato, imagem, datetime.now().isoformat()))
    novo_id = cursor.lastrowid
    conn.commit()
    conn.close()

    if quer_destaque == "1":
        return redirect(url_for("pagar", servico_id=novo_id))
    return redirect(url_for("index"))

@app.route("/pagar/<int:servico_id>")
def pagar(servico_id):
    cfg = get_config()
    conn = get_db()
    servico = conn.execute("SELECT * FROM servicos WHERE id = ?", (servico_id,)).fetchone()
    conn.close()
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
    conn = get_db()
    rows = conn.execute("SELECT * FROM servicos ORDER BY id DESC").fetchall()
    conn.close()

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
    campos = ["chave_pix", "seu_whatsapp", "valor_destaque", "dias_destaque"]
    conn = get_db()
    for c in campos:
        val = request.form.get(c, "").strip()
        if val:
            conn.execute("UPDATE config SET valor = ? WHERE chave = ?", (val, c))
    conn.commit()
    conn.close()
    return redirect(url_for("admin", salvo=1))

@app.route("/admin/vip/<int:servico_id>")
def ativar_vip(servico_id):
    if not session.get("admin_logado"):
        return redirect(url_for("admin"))
    cfg = get_config()
    dias = int(cfg.get("dias_destaque", 30))
    validade = (datetime.now() + timedelta(days=dias)).isoformat()
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

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
