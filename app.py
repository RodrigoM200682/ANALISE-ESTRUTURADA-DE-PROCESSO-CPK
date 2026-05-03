import io
import math
from datetime import datetime, date

import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# Optional PDF dependency
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
except Exception:
    A4 = None

st.set_page_config(page_title="CPK Process Analyzer", layout="wide", page_icon="📊")

# ─────────────────────────────────────────────────────────────────────────────
# STYLE
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .main {background-color: #0a0a0d; color: #e8e8f0;}
    .stApp {background: linear-gradient(180deg,#0a0a0d 0%,#12121a 100%);}
    h1, h2, h3 {color:#e8e8f0;}
    .small-muted {color:#8a8a9e; font-size:0.85rem;}
    .version {color:#8a8a9e; font-size:10px; font-style:italic; text-align:right;}
    .card {background:#1c1c25; border:1px solid #2a2a32; border-radius:16px; padding:16px;}
    .ok {border-left:5px solid #00e5a0; padding:10px; background:#11181a; border-radius:10px;}
    .wn {border-left:5px solid #ffb340; padding:10px; background:#1d1810; border-radius:10px;}
    .fl {border-left:5px solid #ff4d4d; padding:10px; background:#1d1111; border-radius:10px;}
    </style>
    """,
    unsafe_allow_html=True,
)

VERSION = "RM_03_05_2026_HR"
st.markdown(f"<div class='version'>{VERSION}</div>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# CPK CALCULATIONS
# ─────────────────────────────────────────────────────────────────────────────
def parse_float(value):
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except Exception:
        return None


def parse_samples(text):
    if text is None:
        return []
    if isinstance(text, list):
        raw = text
    else:
        raw = str(text).replace(";", "\n").replace(",", ".").splitlines()
    vals = []
    for item in raw:
        v = parse_float(item)
        if v is not None:
            vals.append(v)
    return vals


def calc_stats(samples, lse=None, lie=None):
    vals = [float(s) for s in samples if s != "" and s is not None]
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
    return {"vals": vals, "n": n, "mean": mean, "std": std, "cp": cp, "cpk": cpk, "cpu": cpu, "cpl": cpl}


def classify_cpk(cpk):
    if cpk is None:
        return "Sem cálculo"
    if cpk >= 1.33:
        return "Capaz"
    if cpk >= 1:
        return "Marginal"
    return "Incapaz"


def build_insights(params):
    valid = [p for p in params if p.get("cpk") is not None]
    fail = [p for p in valid if p["cpk"] < 1]
    warn = [p for p in valid if 1 <= p["cpk"] < 1.33]
    ok = [p for p in valid if p["cpk"] >= 1.33]
    insights = []
    if not valid:
        return [{"level": "wn", "text": "Inclua pelo menos 2 amostras válidas e limite LIE ou LSE para calcular Cpk."}]
    if not fail and not warn and ok:
        insights.append({"level": "ok", "text": f"Processo excelente. Todos os {len(ok)} parâmetros com Cpk ≥ 1,33."})
    if fail:
        names = ", ".join(f"{p['name']} (Cpk {p['cpk']:.2f})" for p in fail)
        insights.append({"level": "fl", "text": f"{len(fail)} parâmetro(s) crítico(s): {names}. Ação imediata necessária."})
    if warn:
        names = ", ".join(f"{p['name']} (Cpk {p['cpk']:.2f})" for p in warn)
        insights.append({"level": "wn", "text": f"{len(warn)} parâmetro(s) marginal(is): {names}. Monitoramento intensificado recomendado."})
    for p in valid:
        cp, cpk = p.get("cp"), p.get("cpk")
        if cp and cpk and cp > 0 and (cp - cpk) / cp > 0.15:
            pct = round((cp - cpk) / cp * 100)
            insights.append({"level": "wn", "text": f"Descentramento — {p['name']}: Cp={cp:.2f} vs Cpk={cpk:.2f} ({pct}% de perda). Revisar setup."})
    if ok:
        best = max(ok, key=lambda p: p["cpk"])
        insights.append({"level": "ok", "text": f"Melhor desempenho: {best['name']} com Cpk={best['cpk']:.2f}."})
    pct = round(len(ok) / len(valid) * 100)
    msg = "Processo sob controle." if pct >= 80 else ("Atenção em pontos específicos." if pct >= 50 else "Revisão urgente necessária.")
    level = "ok" if pct >= 80 else ("wn" if pct >= 50 else "fl")
    insights.append({"level": level, "text": f"Índice geral: {pct}% dos parâmetros capazes. {msg}"})
    return insights


def calculate_dataframe(df):
    results = []
    for _, row in df.iterrows():
        name = str(row.get("Parâmetro", "")).strip()
        if not name:
            continue
        lse = parse_float(row.get("LSE"))
        lie = parse_float(row.get("LIE"))
        samples = parse_samples(row.get("Amostras"))
        s = calc_stats(samples, lse, lie)
        item = {
            "name": name,
            "unit": row.get("Unidade", "mm") or "mm",
            "lie": lie,
            "lse": lse,
            "samples": samples,
            "n": s["n"] if s else 0,
            "mean": round(s["mean"], 4) if s else None,
            "std": round(s["std"], 4) if s else None,
            "cp": round(s["cp"], 4) if s and s["cp"] is not None else None,
            "cpu": round(s["cpu"], 4) if s and s["cpu"] is not None else None,
            "cpl": round(s["cpl"], 4) if s and s["cpl"] is not None else None,
            "cpk": round(s["cpk"], 4) if s and s["cpk"] is not None else None,
        }
        item["status"] = classify_cpk(item["cpk"])
        results.append(item)
    return results


def control_chart(p):
    vals = p["samples"]
    if len(vals) < 2:
        return None
    mean = sum(vals) / len(vals)
    std = math.sqrt(sum((v - mean) ** 2 for v in vals) / (len(vals) - 1))
    ucl = mean + 3 * std
    lcl = mean - 3 * std
    x = list(range(1, len(vals) + 1))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=vals, mode="lines+markers+text", text=[f"{v:.3f}" for v in vals], textposition="top center", name="Amostras"))
    fig.add_hline(y=mean, line_dash="solid", annotation_text=f"Média {mean:.3f}")
    fig.add_hline(y=ucl, line_dash="dash", annotation_text=f"LSC {ucl:.3f}")
    fig.add_hline(y=lcl, line_dash="dash", annotation_text=f"LIC {lcl:.3f}")
    if p.get("lse") is not None:
        fig.add_hline(y=p["lse"], line_dash="dot", annotation_text=f"LSE {p['lse']:.3f}")
    if p.get("lie") is not None:
        fig.add_hline(y=p["lie"], line_dash="dot", annotation_text=f"LIE {p['lie']:.3f}")
    fig.update_layout(height=360, margin=dict(l=20, r=20, t=45, b=20), title=f"{p['name']} | Cpk: {p['cpk'] if p['cpk'] is not None else '—'}", paper_bgcolor="#1c1c25", plot_bgcolor="#16161d", font=dict(color="#e8e8f0"))
    return fig


def make_pdf(ident, params):
    if A4 is None:
        return None
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=13*mm, rightMargin=13*mm, topMargin=14*mm, bottomMargin=16*mm)
    W = A4[0] - 26*mm
    styles = getSampleStyleSheet()
    def S(name, **kw):
        return ParagraphStyle(name, parent=styles["Normal"], **kw)
    TEXT = colors.HexColor("#e8e8f0"); MUTED = colors.HexColor("#6b6b80"); CARD = colors.HexColor("#1c1c25")
    GREEN = colors.HexColor("#00e5a0"); AMBER = colors.HexColor("#ffb340"); RED = colors.HexColor("#ff4d4d")
    story = []
    story.append(Paragraph("<b>CPK Process Analyzer</b>", S("title", fontSize=17, textColor=TEXT, fontName="Helvetica-Bold")))
    story.append(Paragraph(f"Gerado: {datetime.now().strftime('%d/%m/%Y %H:%M')}", S("sub", fontSize=8, textColor=MUTED)))
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph("1. Identificação", S("sec", fontSize=9, textColor=TEXT, fontName="Helvetica-Bold")))
    id_rows = [["Linha", ident.get("linha", "—"), "Embalagem", ident.get("emb", "—"), "Data", ident.get("data", "—"), "OP", ident.get("op", "—")]]
    t = Table(id_rows, colWidths=[W/8]*8)
    t.setStyle(TableStyle([("BACKGROUND", (0,0),(-1,-1), CARD), ("TEXTCOLOR", (0,0),(-1,-1), TEXT), ("GRID", (0,0),(-1,-1), .25, colors.HexColor("#2a2a32")), ("FONTSIZE", (0,0),(-1,-1), 7)]))
    story.append(t); story.append(Spacer(1, 5*mm))
    valid = [p for p in params if p.get("cpk") is not None]
    ok_n = len([p for p in valid if p["cpk"] >= 1.33]); wn_n = len([p for p in valid if 1 <= p["cpk"] < 1.33]); fl_n = len([p for p in valid if p["cpk"] < 1])
    avg_cpk = round(sum(p["cpk"] for p in valid) / len(valid), 2) if valid else "—"
    story.append(Paragraph(f"2. Resumo: Cpk médio {avg_cpk} | Capazes {ok_n} | Marginais {wn_n} | Incapazes {fl_n}", S("sec2", fontSize=9, textColor=TEXT, fontName="Helvetica-Bold")))
    rows = [["Parâmetro", "Un.", "N", "Média", "Desvio", "LIE", "LSE", "Cp", "Cpk", "Status"]]
    for p in params:
        rows.append([p["name"], p.get("unit", "mm"), p.get("n", 0), p.get("mean", "—"), p.get("std", "—"), p.get("lie", "—"), p.get("lse", "—"), p.get("cp", "—"), p.get("cpk", "—"), p.get("status", "—")])
    tb = Table(rows, colWidths=[W*.22, W*.06, W*.05, W*.09, W*.09, W*.08, W*.08, W*.07, W*.08, W*.10], repeatRows=1)
    tb.setStyle(TableStyle([("BACKGROUND", (0,0),(-1,0), colors.HexColor("#12121a")), ("BACKGROUND", (0,1),(-1,-1), CARD), ("TEXTCOLOR", (0,0),(-1,-1), TEXT), ("GRID", (0,0),(-1,-1), .25, colors.HexColor("#2a2a32")), ("FONTSIZE", (0,0),(-1,-1), 6.5)]))
    story.append(tb); story.append(Spacer(1, 4*mm))
    story.append(Paragraph("3. Diagnóstico automático", S("sec3", fontSize=9, textColor=TEXT, fontName="Helvetica-Bold")))
    for ins in build_insights(params):
        col = GREEN if ins["level"] == "ok" else AMBER if ins["level"] == "wn" else RED
        story.append(Paragraph(ins["text"], S("ins", fontSize=8, textColor=col, leading=11)))
    story.append(Spacer(1, 8*mm))
    story.append(Paragraph("Responsável técnico: _______________________________", S("sig", fontSize=8, textColor=TEXT)))
    doc.build(story)
    buf.seek(0)
    return buf.getvalue()

# ─────────────────────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────────────────────
st.title("📊 CPK Process Analyzer")
st.caption("Aplicativo Streamlit para análise de capacidade dimensional por parâmetro.")

with st.sidebar:
    st.header("Identificação")
    linha = st.text_input("Linha", value="GL")
    emb = st.text_input("Embalagem", value="")
    data_ref = st.date_input("Data", value=date.today(), format="DD/MM/YYYY")
    op = st.text_input("OP", value="")
    st.divider()
    st.subheader("Materiais")
    corpo_usina = st.text_input("Corpo - Usina")
    corpo_esp = st.text_input("Corpo - Espessura mm")
    domo_usina = st.text_input("Domo - Usina")
    domo_esp = st.text_input("Domo - Espessura mm")
    fundo_usina = st.text_input("Fundo - Usina")
    fundo_esp = st.text_input("Fundo - Espessura mm")
    obs = st.text_area("Observações")

ident = {
    "linha": linha, "emb": emb, "data": data_ref.strftime("%d/%m/%Y"), "op": op,
    "corpo_usina": corpo_usina, "corpo_esp": corpo_esp, "domo_usina": domo_usina,
    "domo_esp": domo_esp, "fundo_usina": fundo_usina, "fundo_esp": fundo_esp, "obs": obs,
}

st.markdown("### 1. Entrada de parâmetros")
st.info("Preencha uma linha por característica. Em 'Amostras', informe um valor por linha ou separe por ponto e vírgula. Exemplo: 52.01;52.03;52.02")

base_df = pd.DataFrame([
    {"Parâmetro": "Diâmetro interno", "Unidade": "mm", "LIE": "", "LSE": "", "Amostras": ""},
    {"Parâmetro": "Altura", "Unidade": "mm", "LIE": "", "LSE": "", "Amostras": ""},
    {"Parâmetro": "Pestana", "Unidade": "mm", "LIE": "", "LSE": "", "Amostras": ""},
])

edited = st.data_editor(
    base_df,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Amostras": st.column_config.TextColumn("Amostras", width="large", help="Valores separados por ; ou por linha"),
        "LIE": st.column_config.TextColumn("LIE"),
        "LSE": st.column_config.TextColumn("LSE"),
    },
)

params = calculate_dataframe(edited)

st.markdown("### 2. Resumo executivo")
valid = [p for p in params if p.get("cpk") is not None]
ok_n = len([p for p in valid if p["cpk"] >= 1.33])
wn_n = len([p for p in valid if 1 <= p["cpk"] < 1.33])
fl_n = len([p for p in valid if p["cpk"] < 1])
avg_cpk = round(sum(p["cpk"] for p in valid) / len(valid), 2) if valid else None

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Cpk médio", "—" if avg_cpk is None else avg_cpk)
c2.metric("Capazes ≥ 1,33", ok_n)
c3.metric("Marginais", wn_n)
c4.metric("Incapazes", fl_n)
c5.metric("Total avaliado", len(params))

if params:
    result_df = pd.DataFrame([{
        "Parâmetro": p["name"], "Un.": p["unit"], "N": p["n"], "Média": p["mean"],
        "Desvio": p["std"], "LIE": p["lie"], "LSE": p["lse"], "Cp": p["cp"], "CPU": p["cpu"], "CPL": p["cpl"], "Cpk": p["cpk"], "Status": p["status"]
    } for p in params])
    st.dataframe(result_df, use_container_width=True, hide_index=True)

st.markdown("### 3. Diagnóstico automático")
for ins in build_insights(params):
    st.markdown(f"<div class='{ins['level']}'>{ins['text']}</div>", unsafe_allow_html=True)

st.markdown("### 4. Gráficos de controle")
for p in params:
    fig = control_chart(p)
    if fig:
        st.plotly_chart(fig, use_container_width=True)

st.markdown("### 5. Exportação")
col_a, col_b = st.columns(2)
with col_a:
    if params:
        export_df = pd.DataFrame([{
            "Parametro": p["name"], "Unidade": p["unit"], "N": p["n"], "Media": p["mean"],
            "Desvio": p["std"], "LIE": p["lie"], "LSE": p["lse"], "Cp": p["cp"], "CPU": p["cpu"], "CPL": p["cpl"], "Cpk": p["cpk"], "Status": p["status"]
        } for p in params])
        xlsx = io.BytesIO()
        with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
            export_df.to_excel(writer, sheet_name="RESULTADOS", index=False)
        st.download_button("Baixar resultados em Excel", xlsx.getvalue(), file_name=f"cpk_resultados_{datetime.now().strftime('%d_%m_%Y_%H%M')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
with col_b:
    pdf_bytes = make_pdf(ident, params)
    if pdf_bytes:
        st.download_button("Baixar relatório PDF", pdf_bytes, file_name=f"cpk_relatorio_{datetime.now().strftime('%d_%m_%Y_%H%M')}.pdf", mime="application/pdf")
    else:
        st.warning("Para exportar PDF, inclua reportlab no requirements.txt")
