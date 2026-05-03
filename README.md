# CPK Analyzer — Process Capability Control

Aplicativo web para análise de capacidade de processo (Cpk) com geração de relatório PDF.

## Estrutura do projeto

```
cpk-app/
├── app.py                  # Flask backend + cálculos Cpk + geração PDF
├── requirements.txt        # Dependências Python
├── Procfile                # Comando para deploy (Railway / Render)
├── runtime.txt             # Versão do Python
├── templates/
│   └── index.html          # Interface principal (4 abas)
└── static/
    ├── css/style.css       # Estilos
    └── js/app.js           # Lógica frontend + Chart.js
```

---

## Como rodar localmente

```bash
# 1. Clone o repositório
git clone https://github.com/SEU_USUARIO/cpk-app.git
cd cpk-app

# 2. Crie um ambiente virtual
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Rode o servidor
python app.py

# Acesse: http://localhost:5000
```

---

## Deploy no GitHub + Railway (gratuito)

### Passo 1 — Subir para o GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/cpk-app.git
git push -u origin main
```

### Passo 2 — Deploy no Railway

1. Acesse [railway.app](https://railway.app) e faça login com GitHub
2. Clique em **"New Project"** → **"Deploy from GitHub repo"**
3. Selecione o repositório `cpk-app`
4. Railway detecta o `Procfile` automaticamente
5. Clique em **"Deploy"** — em ~2 minutos a URL estará disponível

> Railway oferece **$5/mês grátis** (suficiente para uso contínuo leve).

---

## Deploy no Render (alternativa gratuita)

1. Acesse [render.com](https://render.com) → **"New Web Service"**
2. Conecte o repositório GitHub
3. Configure:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
   - **Environment:** Python 3
4. Clique em **"Create Web Service"**

> Render free tier coloca o serviço em sleep após 15 min de inatividade.
> Para uso contínuo, use o plano pago ou Railway.

---

## Funcionalidades

| Aba | O que faz |
|-----|-----------|
| **1 — Identificação** | Linha, embalagem, data, OP, usinas/espessuras do Corpo/Domo/Fundo, observações |
| **2 — Parâmetros** | Cria dimensões com nome, unidade, LIE, LSE e nº de amostras |
| **3 — Coleta** | Inserção das medições; barra de progresso; alertas visuais de fora-de-spec |
| **4 — Análise** | KPIs, histograma, gráfico de controle, comparativo Cpk, diagnóstico automático |
| **PDF** | Relatório completo gerado no servidor com gráficos vetoriais por parâmetro |

---

## Tecnologias

- **Backend:** Python / Flask / ReportLab (PDF)
- **Frontend:** HTML + CSS + JavaScript vanilla / Chart.js
- **Deploy:** Gunicorn + Railway ou Render
