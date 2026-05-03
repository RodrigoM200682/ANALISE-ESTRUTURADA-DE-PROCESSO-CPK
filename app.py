import io
import json
import math
import os
import re
from datetime import datetime, date

import pandas as pd
import streamlit as st
import plotly.graph_objects as go

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.graphics.shapes import Drawing, Line, Circle, String, Rect
except Exception:
    A4 = None

st.set_page_config(page_title="Carta de Inspeção CPK", layout="wide", page_icon="📊")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELOS_FILE = os.path.join(BASE_DIR, "modelos_cartas_cpk.json")

st.markdown(
    """
    <style>
    .stApp {background: linear-gradient(180deg,#0a0a0d 0%,#12121a 100%); color:#e8e8f0;}
    h1, h2, h3 {color:#e8e8f0;}
    .version {color:#8a8a9e; font-size:10px; font-style:italic; text-align:right;}
    .card {background:#1c1c25; border:1px solid #2a2a32; border-radius:16px; padding:16px; margin-bottom:10px;}
    .ok {border-left:5px solid #00e5a0; padding:10px; background:#11181a; border-radius:10px; margin-bottom:8px;}
    .wn {border-left:5px solid #ffb340; padding:10px; background:#1d1810; border-radius:10px; margin-bottom:8px;}
    .fl {border-left:5px solid #ff4d4d; padding:10px; background:#1d1111; border-radius:10px; margin-bottom:8px;}
    .muted {color:#9a9aad; font-size:0.9rem;}
    .orange-help {border-left:5px solid #ff8c00; padding:10px; background:#20160a; border-radius:10px; margin-bottom:8px;}
    div.stButton > button[kind="primary"] {background:#00a86b !important; border-color:#00a86b !important; color:white !important;}
    div.stFormSubmitButton > button {background:#ff8c00 !important; border-color:#ff8c00 !important; color:white !important; font-weight:700;}
    div.stDownloadButton > button {background:#00a86b !important; border-color:#00a86b !important; color:white !important; font-weight:700;}
    </style>
    """,
    unsafe_allow_html=True,
)

VERSION = f"RM_{datetime.now().strftime('%d_%m_%Y_%H%M')}"
st.markdown(f"<div class='version'>{VERSION}</div>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Persistência dos modelos
# ─────────────────────────────────────────────────────────────────────────────
def load_modelos():
    if not os.path.exists(MODELOS_FILE):
        return {}
    try:
        with open(MODELOS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_modelos(modelos):
    with open(MODELOS_FILE, "w", encoding="utf-8") as f:
        json.dump(modelos, f, ensure_ascii=False, indent=2)


def modelo_from_state(nome):
    return {
        "nome": nome,
        "criado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "carta_base": {
            "linha": st.session_state.carta_dados.get("linha", ""),
            "embalagem": st.session_state.carta_dados.get("embalagem", ""),
            "domo_mat": st.session_state.carta_dados.get("domo_mat", ""),
            "esp_domo": st.session_state.carta_dados.get("esp_domo", ""),
            "corpo_mat": st.session_state.carta_dados.get("corpo_mat", ""),
            "esp_corpo": st.session_state.carta_dados.get("esp_corpo", ""),
            "fundo_mat": st.session_state.carta_dados.get("fundo_mat", ""),
            "esp_fundo": st.session_state.carta_dados.get("esp_fundo", ""),
        },
        "caracteristicas": [
            {
                "descricao": c["descricao"],
                "lie": c["lie"],
                "lse": c["lse"],
                "num_amostras": c["num_amostras"],
                "num_medicoes": c.get("num_medicoes", 3),
            }
            for c in st.session_state.caracteristicas
        ],
    }


def aplicar_modelo(modelo):
    base = modelo.get("carta_base", {})
    st.session_state.carta_dados = {
        **st.session_state.get("carta_dados", {}),
        "linha": base.get("linha", ""),
        "embalagem": base.get("embalagem", ""),
        "domo_mat": base.get("domo_mat", ""),
        "esp_domo": base.get("esp_domo", ""),
        "corpo_mat": base.get("corpo_mat", ""),
        "esp_corpo": base.get("esp_corpo", ""),
        "fundo_mat": base.get("fundo_mat", ""),
        "esp_fundo": base.get("esp_fundo", ""),
    }
    chars = []
    for idx, c in enumerate(modelo.get("caracteristicas", []), start=1):
        n = int(c.get("num_amostras", 1) or 1)
        m = int(c.get("num_medicoes", 3) or 3)
        chars.append({
            "id": f"C{idx:03d}_{datetime.now().strftime('%H%M%S')}",
            "descricao": c.get("descricao", ""),
            "lie": float(c.get("lie")),
            "lse": float(c.get("lse")),
            "num_amostras": n,
            "num_medicoes": m,
            "medicoes": [{"Amostra": i, **{f"Medida {j}": None for j in range(1, m + 1)}} for i in range(1, n + 1)],
        })
    st.session_state.caracteristicas = chars
    st.session_state.selected_id = chars[0]["id"] if chars else None

# ─────────────────────────────────────────────────────────────────────────────
# Estado
# ─────────────────────────────────────────────────────────────────────────────
def init_state():
    defaults = {
        "carta_ok": False,
        "caracteristicas": [],
        "selected_id": None,
        "carta_dados": {},
        "modelos": load_modelos(),
        "char_form_nonce": 0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# ─────────────────────────────────────────────────────────────────────────────
# Cálculo estatístico
# ─────────────────────────────────────────────────────────────────────────────
def parse_float(value):
    if value is None or value == "":
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        return float(str(value).replace(",", "."))
    except Exception:
        return None


def calc_stats(samples, lse=None, lie=None):
    vals = [float(v) for v in samples if v is not None]
    if len(vals) < 2:
        return None
    n = len(vals)
    mean = sum(vals) / n
    variance = sum((v - mean) ** 2 for v in vals) / (n - 1)
    std = math.sqrt(variance)
    if std == 0:
        return None
    cp = cpu = cpl = cpk = None
    if lse is not None and lie is not None:
        cp = (lse - lie) / (6 * std)
        cpu = (lse - mean) / (3 * std)
        cpl = (mean - lie) / (3 * std)
        cpk = min(cpu, cpl)
    elif lse is not None:
        cpu = (lse - mean) / (3 * std)
        cpk = cpu
    elif lie is not None:
        cpl = (mean - lie) / (3 * std)
        cpk = cpl
    return {"vals": vals, "n": n, "mean": mean, "std": std, "cp": cp, "cpu": cpu, "cpl": cpl, "cpk": cpk}


def classify_cpk(cpk):
    if cpk is None:
        return "Sem cálculo"
    if cpk >= 1.33:
        return "Capaz"
    if cpk >= 1.00:
        return "Marginal"
    return "Incapaz"


def measurement_keys(char):
    qtd = int(char.get("num_medicoes", 3) or 3)
    return [f"Medida {i}" for i in range(1, qtd + 1)]


def flatten_measurements(char):
    vals = []
    keys = measurement_keys(char)
    for row in char.get("medicoes", []):
        for key in keys:
            v = parse_float(row.get(key))
            if v is not None:
                vals.append(v)
    return vals


def amostras_completas(char):
    completas = 0
    keys = measurement_keys(char)
    for row in char.get("medicoes", []):
        if all(parse_float(row.get(k)) is not None for k in keys):
            completas += 1
    return completas


def calc_characteristic(char):
    vals = flatten_measurements(char)
    s = calc_stats(vals, char.get("lse"), char.get("lie"))
    result = {
        "id": char["id"],
        "descricao": char["descricao"],
        "lie": char.get("lie"),
        "lse": char.get("lse"),
        "amostras_previstas": char.get("num_amostras", 0),
        "amostras_completas": amostras_completas(char),
        "medicoes_por_amostra": int(char.get("num_medicoes", 3) or 3),
        "medidas_previstas": char.get("num_amostras", 0) * int(char.get("num_medicoes", 3) or 3),
        "medidas_realizadas": len(vals),
        "valores": vals,
        "n": s["n"] if s else 0,
        "media": round(s["mean"], 4) if s else None,
        "desvio": round(s["std"], 4) if s else None,
        "cp": round(s["cp"], 4) if s and s["cp"] is not None else None,
        "cpu": round(s["cpu"], 4) if s and s["cpu"] is not None else None,
        "cpl": round(s["cpl"], 4) if s and s["cpl"] is not None else None,
        "cpk": round(s["cpk"], 4) if s and s["cpk"] is not None else None,
    }
    result["status"] = classify_cpk(result["cpk"])
    return result


def characteristic_has_measurements(char):
    return len(flatten_measurements(char)) > 0

def descricao_normalizada(txt):
    return re.sub(r"\s+", " ", str(txt or "").strip()).casefold()

def build_insights(results):
    valid = [r for r in results if r.get("cpk") is not None]
    if not valid:
        return [{"level":"wn", "text":"Ainda não há medições suficientes para análise. Cada característica deve ter medições válidas e limites de especificação informados."}]
    fail = [r for r in valid if r["cpk"] < 1]
    warn = [r for r in valid if 1 <= r["cpk"] < 1.33]
    ok = [r for r in valid if r["cpk"] >= 1.33]
    insights = []
    if fail:
        names = ", ".join(f"{r['descricao']} (Cpk {r['cpk']:.2f})" for r in fail)
        insights.append({"level":"fl", "text":f"Parecer: processo não capaz para {len(fail)} característica(s): {names}. Minha recomendação é não liberar o lote sem avaliação técnica, revisar setup, segregar material suspeito e repetir a coleta após correção."})
    if warn:
        names = ", ".join(f"{r['descricao']} (Cpk {r['cpk']:.2f})" for r in warn)
        insights.append({"level":"wn", "text":f"Parecer: processo marginal para {len(warn)} característica(s): {names}. Eu manteria o processo em acompanhamento reforçado, com ajuste preventivo e aumento temporário da frequência de inspeção."})
    if ok and not fail and not warn:
        insights.append({"level":"ok", "text":f"Parecer: processo capaz. Todas as {len(ok)} característica(s) avaliadas apresentam Cpk ≥ 1,33, indicando boa condição estatística frente aos limites especificados."})
    for r in valid:
        cp, cpk = r.get("cp"), r.get("cpk")
        if cp and cpk and cp > 0 and (cp - cpk) / cp > 0.15:
            perda = round((cp - cpk) / cp * 100)
            insights.append({"level":"wn", "text":f"Descentramento identificado em {r['descricao']}: Cp={cp:.2f} e Cpk={cpk:.2f}, com perda aproximada de {perda}% da capacidade potencial. A variação pode estar aceitável, mas o processo está deslocado em relação ao centro da especificação."})
    incompletas = [r for r in results if r["amostras_completas"] < r["amostras_previstas"]]
    if incompletas:
        names = ", ".join(f"{r['descricao']} ({r['amostras_completas']}/{r['amostras_previstas']} amostras)" for r in incompletas)
        insights.append({"level":"wn", "text":f"Atenção: existem coletas incompletas em {names}. O parecer estatístico é parcial até completar todas as medições previstas em cada amostra."})
    pct_ok = round(len(ok) / len(valid) * 100)
    level = "ok" if pct_ok >= 80 and not fail else "wn" if pct_ok >= 50 else "fl"
    insights.append({"level":level, "text":f"Resumo geral: {pct_ok}% das características calculadas estão capazes. Total analisado: {len(valid)} característica(s)."})
    return insights


def control_chart(result):
    vals = result.get("valores", [])
    if len(vals) < 2:
        return None
    mean = sum(vals) / len(vals)
    std = math.sqrt(sum((v - mean) ** 2 for v in vals) / (len(vals) - 1))
    ucl = mean + 3 * std
    lcl = mean - 3 * std
    x = list(range(1, len(vals) + 1))
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x,
        y=vals,
        mode="lines+markers",
        name="Medições",
        line=dict(width=2),
        marker=dict(size=7),
    ))
    # A média aparece no título para não poluir o gráfico com mais uma linha.
    fig.add_hline(y=ucl, line_dash="dash", line_color="#ff4d4d", line_width=3, annotation_text="LSC", annotation_font_color="#ff4d4d")
    fig.add_hline(y=lcl, line_dash="dash", line_color="#ff4d4d", line_width=3, annotation_text="LIC", annotation_font_color="#ff4d4d")
    if result.get("lse") is not None:
        fig.add_hline(y=result["lse"], line_dash="solid", line_color="#ff4d4d", line_width=4, annotation_text="LSE", annotation_font_color="#ff4d4d")
    if result.get("lie") is not None:
        fig.add_hline(y=result["lie"], line_dash="solid", line_color="#ff4d4d", line_width=4, annotation_text="LIE", annotation_font_color="#ff4d4d")
    media_txt = "—" if result.get("media") is None else f"{result['media']:.4f}"
    cpk_txt = "—" if result.get("cpk") is None else f"{result['cpk']:.4f}"
    fig.update_layout(
        height=370,
        title=f"{result['descricao']} | Cpk: {cpk_txt} | Média: {media_txt}",
        paper_bgcolor="#1c1c25",
        plot_bgcolor="#16161d",
        font=dict(color="#e8e8f0"),
        margin=dict(l=20, r=20, t=55, b=20),
        xaxis_title="Sequência das medições",
        yaxis_title="Valor medido",
        showlegend=False,
    )
    return fig


def pdf_chart_drawing(result, W):
    vals = result.get("valores", [])
    if len(vals) < 2:
        return None
    mean = sum(vals) / len(vals)
    std = math.sqrt(sum((v - mean) ** 2 for v in vals) / (len(vals) - 1))
    ucl = mean + 3 * std
    lcl = mean - 3 * std
    lse = result.get("lse")
    lie = result.get("lie")
    all_v = vals + [ucl, lcl] + ([lse] if lse is not None else []) + ([lie] if lie is not None else [])
    vmn, vmx = min(all_v), max(all_v)
    vr = vmx - vmn or 0.001
    DW, DH = W, 42 * mm
    PAD_L, PAD_R, PAD_T, PAD_B = 13 * mm, 16 * mm, 5 * mm, 7 * mm
    CW, CH = DW - PAD_L - PAD_R, DH - PAD_T - PAD_B

    def xp(i):
        return PAD_L + (i / (len(vals) - 1 or 1)) * CW

    def yp(v):
        return PAD_B + ((v - vmn) / vr) * CH

    d = Drawing(DW, DH)
    d.add(Rect(0, 0, DW, DH, fillColor=colors.whitesmoke, strokeColor=colors.lightgrey, strokeWidth=0.5))

    def hline(val, col, label, width=1.0, dash=None):
        y = yp(val)
        ln = Line(PAD_L, y, PAD_L + CW, y, strokeColor=col, strokeWidth=width)
        if dash:
            ln.strokeDashArray = dash
        d.add(ln)
        d.add(String(PAD_L + CW + 2, y - 2, label, fontSize=5.5, fillColor=col))

    red = colors.HexColor("#cc0000")
    hline(ucl, red, "LSC", width=1.4, dash=[2, 2])
    hline(lcl, red, "LIC", width=1.4, dash=[2, 2])
    if lse is not None:
        hline(lse, red, "LSE", width=2.2)
    if lie is not None:
        hline(lie, red, "LIE", width=2.2)

    for i in range(len(vals) - 1):
        d.add(Line(xp(i), yp(vals[i]), xp(i + 1), yp(vals[i + 1]), strokeColor=colors.HexColor("#111111"), strokeWidth=0.9))
    for i, v in enumerate(vals):
        out = (lse is not None and v > lse) or (lie is not None and v < lie)
        col = colors.red if out else colors.HexColor("#00a86b")
        d.add(Circle(xp(i), yp(v), 1.7, fillColor=col, strokeColor=col))
    cpk_txt = "—" if result.get("cpk") is None else f"{result['cpk']:.4f}"
    media_txt = "—" if result.get("media") is None else f"{result['media']:.4f}"
    d.add(String(PAD_L, DH - 11, f"{result['descricao']} | Cpk: {cpk_txt} | Média: {media_txt}", fontSize=7.5, fillColor=colors.black))
    return d


def make_pdf(carta, results):
    if A4 is None:
        return None
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=12*mm, rightMargin=12*mm, topMargin=12*mm, bottomMargin=14*mm)
    W = A4[0] - 24*mm
    styles = getSampleStyleSheet()
    def S(name, **kw):
        return ParagraphStyle(name, parent=styles["Normal"], **kw)
    TEXT = colors.HexColor("#111111")
    MUTED = colors.HexColor("#555555")
    story = []
    story.append(Paragraph("<b>Relatório de Carta de Inspeção e CPK</b>", S("title", fontSize=15, textColor=TEXT, fontName="Helvetica-Bold")))
    story.append(Paragraph(f"Gerado: {datetime.now().strftime('%d/%m/%Y %H:%M')}", S("sub", fontSize=8, textColor=MUTED)))
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph("<b>Dados dos materiais</b>", S("sec_mat", fontSize=9, textColor=TEXT, fontName="Helvetica-Bold")))
    dados_materiais = [
        ["Usina domo", carta.get("domo_mat", ""), "Espessura domo", carta.get("esp_domo", "")],
        ["Usina corpo", carta.get("corpo_mat", ""), "Espessura corpo", carta.get("esp_corpo", "")],
        ["Usina fundo", carta.get("fundo_mat", ""), "Espessura fundo", carta.get("esp_fundo", "")],
    ]
    t_mat = Table(dados_materiais, colWidths=[W*.18, W*.32, W*.18, W*.32])
    t_mat.setStyle(TableStyle([("GRID", (0,0),(-1,-1), .25, colors.grey), ("FONTSIZE", (0,0),(-1,-1), 7.5), ("BACKGROUND", (0,0),(-1,-1), colors.whitesmoke)]))
    story.append(t_mat)
    story.append(Spacer(1, 3*mm))

    story.append(Paragraph("<b>Dados do lote</b>", S("sec_lote", fontSize=9, textColor=TEXT, fontName="Helvetica-Bold")))
    dados_lote = [
        ["Linha", carta.get("linha", ""), "Embalagem", carta.get("embalagem", "")],
        ["Ordem de produção", carta.get("op", ""), "Quantidade", carta.get("lote_qtd", "")],
        ["Data", carta.get("data", ""), "Observações", carta.get("obs", "")],
    ]
    t_lote = Table(dados_lote, colWidths=[W*.18, W*.32, W*.18, W*.32])
    t_lote.setStyle(TableStyle([("GRID", (0,0),(-1,-1), .25, colors.grey), ("FONTSIZE", (0,0),(-1,-1), 7.5), ("BACKGROUND", (0,0),(-1,-1), colors.whitesmoke)]))
    story.append(t_lote)
    story.append(Spacer(1, 3*mm))

    story.append(Paragraph("<b>Responsável pela inspeção</b>", S("sec_resp", fontSize=9, textColor=TEXT, fontName="Helvetica-Bold")))
    dados_resp = [["Nome", carta.get("responsavel_nome", ""), "Chapa", carta.get("responsavel_chapa", "")]]
    t_resp = Table(dados_resp, colWidths=[W*.18, W*.32, W*.18, W*.32])
    t_resp.setStyle(TableStyle([("GRID", (0,0),(-1,-1), .25, colors.grey), ("FONTSIZE", (0,0),(-1,-1), 7.5), ("BACKGROUND", (0,0),(-1,-1), colors.whitesmoke)]))
    story.append(t_resp)
    story.append(Spacer(1, 4*mm))
    rows = [["Característica", "Amostras", "Med./am.", "N", "Média", "Desvio", "LIE", "LSE", "Cp", "Cpk", "Status"]]
    for r in results:
        rows.append([r["descricao"], f"{r['amostras_completas']}/{r['amostras_previstas']}", r.get("medicoes_por_amostra", ""), r["n"], r["media"], r["desvio"], r["lie"], r["lse"], r["cp"], r["cpk"], r["status"]])
    tb = Table(rows, colWidths=[W*.23, W*.075, W*.065, W*.04, W*.075, W*.075, W*.07, W*.07, W*.055, W*.06, W*.095], repeatRows=1)
    tb.setStyle(TableStyle([("GRID", (0,0),(-1,-1), .25, colors.grey), ("FONTSIZE", (0,0),(-1,-1), 6.2), ("BACKGROUND", (0,0),(-1,0), colors.lightgrey)]))
    story.append(tb)
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph("<b>Gráficos das coletas</b>", S("sec1", fontSize=10, textColor=TEXT, fontName="Helvetica-Bold")))
    for r in results:
        d = pdf_chart_drawing(r, W)
        if d:
            story.append(d)
            story.append(Spacer(1, 3*mm))
    story.append(Paragraph("<b>Análise e parecer automático</b>", S("sec2", fontSize=10, textColor=TEXT, fontName="Helvetica-Bold")))
    for ins in build_insights(results):
        story.append(Paragraph(ins["text"], S("body", fontSize=8, leading=11, textColor=TEXT)))
        story.append(Spacer(1, 1.2*mm))
    story.append(Spacer(1, 8*mm))
    story.append(Paragraph(f"Responsável pela inspeção: {carta.get('responsavel_nome','')} | Chapa: {carta.get('responsavel_chapa','')}", S("resp", fontSize=8, textColor=TEXT)))
    story.append(Paragraph("Assinatura: _______________________________", S("sig", fontSize=8, textColor=TEXT)))
    doc.build(story)
    buf.seek(0)
    return buf.getvalue()

# ─────────────────────────────────────────────────────────────────────────────
# Interface
# ─────────────────────────────────────────────────────────────────────────────
st.title("📊 Carta de Inspeção CPK")
st.caption("Fluxo: modelo salvo → carta de dados → características sem duplicidade → medições por amostra → análise somente das cartas preenchidas → parecer automático.")

tab1, tab2, tab3, tab4 = st.tabs(["1. Carta de dados", "2. Criar inspeção", "3. Registrar medições", "4. Análise estatística"])

with tab1:
    st.subheader("Carta de dados — materiais e identificação")

    modelos = st.session_state.modelos
    if modelos:
        st.markdown("#### Utilizar modelo salvo")
        nomes_modelos = ["— Novo preenchimento sem modelo —"] + sorted(modelos.keys())
        modelo_sel = st.selectbox("Modelo de carta", nomes_modelos)
        c_load, c_del = st.columns(2)
        if c_load.button("Carregar modelo selecionado", use_container_width=True, type="primary", disabled=(modelo_sel.startswith("—"))):
            aplicar_modelo(modelos[modelo_sel])
            st.session_state.carta_ok = False
            st.success("Modelo carregado. Complete os dados variáveis da carta e salve para liberar a inspeção.")
            st.rerun()
        if c_del.button("Excluir modelo selecionado", use_container_width=True, disabled=(modelo_sel.startswith("—"))):
            modelos.pop(modelo_sel, None)
            save_modelos(modelos)
            st.session_state.modelos = modelos
            st.warning("Modelo excluído.")
            st.rerun()
    else:
        st.markdown("<div class='orange-help'>Nenhum modelo salvo ainda. Após criar as características, salve o modelo para reutilizar nas próximas inspeções.</div>", unsafe_allow_html=True)

    with st.form("form_carta"):
        st.markdown("#### Materiais")
        m1, m2 = st.columns(2)
        with m1:
            domo_mat = st.text_input("Usina domo", value=st.session_state.carta_dados.get("domo_mat", ""))
        with m2:
            esp_domo = st.text_input("Espessura domo *", value=st.session_state.carta_dados.get("esp_domo", ""))

        m3, m4 = st.columns(2)
        with m3:
            corpo_mat = st.text_input("Usina corpo", value=st.session_state.carta_dados.get("corpo_mat", ""))
        with m4:
            esp_corpo = st.text_input("Espessura corpo *", value=st.session_state.carta_dados.get("esp_corpo", ""))

        m5, m6 = st.columns(2)
        with m5:
            fundo_mat = st.text_input("Usina fundo", value=st.session_state.carta_dados.get("fundo_mat", ""))
        with m6:
            esp_fundo = st.text_input("Espessura fundo *", value=st.session_state.carta_dados.get("esp_fundo", ""))

        st.markdown("#### Dados do lote")
        l1, l2 = st.columns(2)
        with l1:
            linha = st.text_input("Linha *", value=st.session_state.carta_dados.get("linha", "GL"))
        with l2:
            embalagem = st.text_input("Embalagem *", value=st.session_state.carta_dados.get("embalagem", ""))

        l3, l4 = st.columns(2)
        with l3:
            op = st.text_input("Ordem de produção *", value=st.session_state.carta_dados.get("op", ""))
        with l4:
            lote_qtd = st.number_input("Quantidade / lote produzido *", min_value=0, step=1, value=int(st.session_state.carta_dados.get("lote_qtd", 0) or 0))

        data_carta = st.date_input("Data", value=date.today(), format="DD/MM/YYYY")

        st.markdown("#### Responsável pela inspeção")
        r1, r2 = st.columns(2)
        with r1:
            responsavel_nome = st.text_input("Nome do responsável pela inspeção *", value=st.session_state.carta_dados.get("responsavel_nome", ""))
        with r2:
            responsavel_chapa = st.text_input("Chapa do responsável pela inspeção *", value=st.session_state.carta_dados.get("responsavel_chapa", ""))

        obs = st.text_area("Observações gerais", value=st.session_state.carta_dados.get("obs", ""))
        submitted = st.form_submit_button("Salvar carta e liberar criação da inspeção", use_container_width=True)
    if submitted:
        obrig = [linha, embalagem, op, esp_corpo, esp_domo, esp_fundo, responsavel_nome, responsavel_chapa]
        if any(str(v).strip() == "" for v in obrig) or lote_qtd <= 0:
            st.error("Preencha todos os campos obrigatórios marcados com * e informe lote produzido maior que zero.")
        else:
            st.session_state.carta_ok = True
            st.session_state.carta_dados = {
                "linha": linha, "embalagem": embalagem, "op": op, "esp_corpo": esp_corpo,
                "esp_domo": esp_domo, "esp_fundo": esp_fundo, "lote_qtd": lote_qtd,
                "data": data_carta.strftime("%d/%m/%Y"), "domo_mat": domo_mat,
                "corpo_mat": corpo_mat, "fundo_mat": fundo_mat, "obs": obs,
                "responsavel_nome": responsavel_nome.strip(), "responsavel_chapa": responsavel_chapa.strip(),
            }
            st.success("Carta salva. A aba 'Criar inspeção' está liberada.")

    if st.session_state.carta_ok:
        st.markdown("<div class='card'><b>Carta ativa:</b> " + f"Linha {st.session_state.carta_dados.get('linha')} | Embalagem {st.session_state.carta_dados.get('embalagem')} | OP {st.session_state.carta_dados.get('op')} | Responsável {st.session_state.carta_dados.get('responsavel_nome')} - Chapa {st.session_state.carta_dados.get('responsavel_chapa')}" + "</div>", unsafe_allow_html=True)

with tab2:
    st.subheader("Criação das características de inspeção")
    if not st.session_state.carta_ok:
        st.warning("Primeiro salve a Carta de dados na aba 1.")
    else:
        st.markdown("<div class='orange-help'>O botão de criação fica em laranja para indicar inclusão/edição. Após a característica estar criada e disponível para uso, os botões de abertura e exportação aparecem em verde.</div>", unsafe_allow_html=True)
        nonce = st.session_state.char_form_nonce
        with st.form(f"form_caracteristica_{nonce}"):
            descricao = st.text_input("Descrição da característica *", placeholder="Ex.: Diâmetro interno, pestana, altura, profundidade de expansão", key=f"desc_char_{nonce}")
            c1, c2 = st.columns(2)
            with c1:
                lie = st.text_input("Limite mínimo / LIE *", placeholder="Ex.: 52,10", key=f"lie_char_{nonce}")
            with c2:
                lse = st.text_input("Limite máximo / LSE *", placeholder="Ex.: 52,30", key=f"lse_char_{nonce}")
            c3, c4 = st.columns(2)
            with c3:
                num_amostras = st.number_input("Número de amostras que serão coletadas *", min_value=1, max_value=200, step=1, value=10, key=f"n_amostras_char_{nonce}")
            with c4:
                num_medicoes = st.number_input("Número de medições por amostra *", min_value=1, max_value=10, step=1, value=3, key=f"n_medicoes_char_{nonce}")
            submitted_char = st.form_submit_button("Salvar característica", use_container_width=True)
        if submitted_char:
            lie_v = parse_float(lie)
            lse_v = parse_float(lse)
            desc_norm = descricao_normalizada(descricao)
            duplicada = any(descricao_normalizada(c.get("descricao")) == desc_norm for c in st.session_state.caracteristicas)
            if not descricao.strip() or lie_v is None or lse_v is None or lie_v >= lse_v:
                st.error("Informe descrição, limite mínimo e limite máximo válidos. O limite mínimo deve ser menor que o limite máximo.")
            elif duplicada:
                st.error(f"A característica '{descricao.strip()}' já possui uma carta de inspeção criada. Não é permitido salvar duas cartas com a mesma descrição.")
            else:
                new_id = f"C{len(st.session_state.caracteristicas)+1:03d}_{datetime.now().strftime('%H%M%S')}"
                medicoes = [{"Amostra": i, **{f"Medida {j}": None for j in range(1, int(num_medicoes) + 1)}} for i in range(1, int(num_amostras)+1)]
                st.session_state.caracteristicas.append({
                    "id": new_id, "descricao": descricao.strip(), "lie": lie_v, "lse": lse_v,
                    "num_amostras": int(num_amostras), "num_medicoes": int(num_medicoes), "medicoes": medicoes,
                })
                st.session_state.selected_id = new_id
                st.session_state.char_form_nonce += 1
                st.success("Característica criada e habilitada para utilização. Os campos foram limpos para nova inclusão.")
                st.rerun()

        if st.session_state.caracteristicas:
            st.markdown("#### Características abertas")
            for char in st.session_state.caracteristicas:
                result = calc_characteristic(char)
                cols = st.columns([4, 1, 1, 1])
                cols[0].markdown(f"**{char['descricao']}**  \nLIE: {char['lie']} | LSE: {char['lse']} | Amostras: {char['num_amostras']} | Medições/amostra: {char.get('num_medicoes', 3)} | Medições: {result['medidas_realizadas']}/{result['medidas_previstas']}")
                cols[1].metric("Cpk", "—" if result["cpk"] is None else result["cpk"])
                cols[2].markdown(f"**Status:** {result['status']}")
                if cols[3].button("Abrir", key=f"open_{char['id']}", type="primary"):
                    st.session_state.selected_id = char["id"]
                    st.success(f"Característica selecionada: {char['descricao']}")

            st.markdown("#### Salvar modelo da carta")
            nome_modelo = st.text_input("Nome do modelo para reutilização", value=f"{st.session_state.carta_dados.get('linha','')}_{st.session_state.carta_dados.get('embalagem','')}".strip("_"))
            if st.button("Salvar modelo com estas características", use_container_width=True, type="primary"):
                if not nome_modelo.strip():
                    st.error("Informe um nome para o modelo.")
                else:
                    st.session_state.modelos[nome_modelo.strip()] = modelo_from_state(nome_modelo.strip())
                    save_modelos(st.session_state.modelos)
                    st.success("Modelo salvo. Ele será carregado automaticamente como opção quando o aplicativo for reiniciado.")

with tab3:
    st.subheader("Registro das medições")
    if not st.session_state.caracteristicas:
        st.warning("Crie pelo menos uma característica na aba 2 ou carregue um modelo salvo.")
    else:
        options = {f"{c['descricao']} | {c['id']}": c["id"] for c in st.session_state.caracteristicas}
        current_key = next((k for k, v in options.items() if v == st.session_state.selected_id), list(options.keys())[0])
        selected_label = st.selectbox("Selecione a característica", list(options.keys()), index=list(options.keys()).index(current_key))
        st.session_state.selected_id = options[selected_label]
        char = next(c for c in st.session_state.caracteristicas if c["id"] == st.session_state.selected_id)
        keys_medicao = measurement_keys(char)
        st.info(f"Cada amostra deve conter obrigatoriamente {char.get('num_medicoes', 3)} medição(ões). Característica: {char['descricao']} | LIE {char['lie']} | LSE {char['lse']}")
        df_med = pd.DataFrame(char["medicoes"])
        expected_cols = ["Amostra"] + keys_medicao
        for col in expected_cols:
            if col not in df_med.columns:
                df_med[col] = None
        df_med = df_med[expected_cols]
        column_config = {"Amostra": st.column_config.NumberColumn("Amostra", disabled=True)}
        column_config.update({k: st.column_config.NumberColumn(k, format="%.4f") for k in keys_medicao})
        edited_med = st.data_editor(
            df_med,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            column_config=column_config,
            key=f"editor_{char['id']}",
        )
        if st.button("Salvar medições desta característica", use_container_width=True, type="primary"):
            registros = edited_med.to_dict("records")
            incompletas = []
            for row in registros:
                vals = [parse_float(row.get(k)) for k in keys_medicao]
                if any(v is not None for v in vals) and not all(v is not None for v in vals):
                    incompletas.append(int(row.get("Amostra", 0)))
            if incompletas:
                st.error(f"As amostras {incompletas} estão parcialmente preenchidas. Cada amostra registrada deve ter {len(keys_medicao)} medição(ões).")
            else:
                char["medicoes"] = registros
                st.success("Medições salvas. A análise estatística já pode ser consultada na aba 4.")

with tab4:
    st.subheader("Análise estatística e parecer do processo")
    if not st.session_state.caracteristicas:
        st.warning("Não há características criadas para análise.")
    else:
        todas_results = [calc_characteristic(c) for c in st.session_state.caracteristicas]
        chars_preenchidas = [c for c in st.session_state.caracteristicas if characteristic_has_measurements(c)]
        results = [calc_characteristic(c) for c in chars_preenchidas]
        if not results:
            st.warning("Nenhuma carta preenchida foi localizada. A análise estatística considera somente características com medições registradas.")
            st.stop()
        valid = [r for r in results if r.get("cpk") is not None]
        ok_n = len([r for r in valid if r["cpk"] >= 1.33])
        wn_n = len([r for r in valid if 1 <= r["cpk"] < 1.33])
        fl_n = len([r for r in valid if r["cpk"] < 1])
        avg_cpk = round(sum(r["cpk"] for r in valid) / len(valid), 2) if valid else None
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Cpk médio", "—" if avg_cpk is None else avg_cpk)
        c2.metric("Capazes ≥ 1,33", ok_n)
        c3.metric("Marginais", wn_n)
        c4.metric("Incapazes", fl_n)
        c5.metric("Cartas preenchidas", len(results))
        cartas_branco = len(todas_results) - len(results)
        if cartas_branco > 0:
            st.info(f"{cartas_branco} carta(s) em branco foram desconsideradas da análise estatística.")

        result_df = pd.DataFrame([{
            "Característica": r["descricao"], "Amostras completas": f"{r['amostras_completas']}/{r['amostras_previstas']}",
            "Medições/amostra": r.get("medicoes_por_amostra"), "Medições realizadas": r["medidas_realizadas"], "N": r["n"], "Média": r["media"],
            "Desvio": r["desvio"], "LIE": r["lie"], "LSE": r["lse"], "Cp": r["cp"],
            "CPU": r["cpu"], "CPL": r["cpl"], "Cpk": r["cpk"], "Status": r["status"],
        } for r in results])
        st.dataframe(result_df, use_container_width=True, hide_index=True)

        st.markdown("#### Gráficos das coletas por característica")
        for r in results:
            fig = control_chart(r)
            if fig:
                st.plotly_chart(fig, use_container_width=True)

        st.markdown("#### Análise e parecer automático")
        for ins in build_insights(results):
            st.markdown(f"<div class='{ins['level']}'>{ins['text']}</div>", unsafe_allow_html=True)

        st.markdown("#### Exportação")
        col_a, col_b = st.columns(2)
        with col_a:
            xlsx = io.BytesIO()
            with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
                pd.DataFrame([st.session_state.carta_dados]).to_excel(writer, sheet_name="CARTA", index=False)
                result_df.to_excel(writer, sheet_name="RESULTADOS", index=False)
                for c in chars_preenchidas:
                    safe = re.sub(r"[^A-Za-z0-9_]+", "_", c["descricao"][:20]) or c["id"]
                    pd.DataFrame(c["medicoes"]).to_excel(writer, sheet_name=safe[:31], index=False)
            st.download_button("Baixar Excel da carta", xlsx.getvalue(), file_name=f"carta_cpk_{datetime.now().strftime('%d_%m_%Y_%H%M')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        with col_b:
            pdf = make_pdf(st.session_state.carta_dados, results)
            if pdf:
                st.download_button("Baixar relatório PDF", pdf, file_name=f"relatorio_cpk_{datetime.now().strftime('%d_%m_%Y_%H%M')}.pdf", mime="application/pdf", use_container_width=True)
            else:
                st.warning("Inclua reportlab no requirements.txt para exportar PDF.")
