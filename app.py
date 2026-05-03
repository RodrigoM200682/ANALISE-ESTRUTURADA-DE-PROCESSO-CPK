import io
import math
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
except Exception:
    A4 = None

st.set_page_config(page_title="Carta de Inspeção CPK", layout="wide", page_icon="📊")

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
    </style>
    """,
    unsafe_allow_html=True,
)

VERSION = f"RM_{datetime.now().strftime('%d_%m_%Y_%H%M')}"
st.markdown(f"<div class='version'>{VERSION}</div>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Estado
# ─────────────────────────────────────────────────────────────────────────────
if "carta_ok" not in st.session_state:
    st.session_state.carta_ok = False
if "caracteristicas" not in st.session_state:
    st.session_state.caracteristicas = []
if "selected_id" not in st.session_state:
    st.session_state.selected_id = None
if "carta_dados" not in st.session_state:
    st.session_state.carta_dados = {}

# ─────────────────────────────────────────────────────────────────────────────
# Funções de cálculo
# ─────────────────────────────────────────────────────────────────────────────
def parse_float(value):
    if value is None or value == "":
        return None
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


def status_level(cpk):
    if cpk is None:
        return "wn"
    if cpk >= 1.33:
        return "ok"
    if cpk >= 1.00:
        return "wn"
    return "fl"


def flatten_measurements(char):
    vals = []
    for row in char.get("medicoes", []):
        for key in ["Medida 1", "Medida 2", "Medida 3"]:
            v = parse_float(row.get(key))
            if v is not None:
                vals.append(v)
    return vals


def calc_characteristic(char):
    vals = flatten_measurements(char)
    s = calc_stats(vals, char.get("lse"), char.get("lie"))
    result = {
        "id": char["id"],
        "descricao": char["descricao"],
        "lie": char.get("lie"),
        "lse": char.get("lse"),
        "amostras_previstas": char.get("num_amostras", 0),
        "medidas_previstas": char.get("num_amostras", 0) * 3,
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


def build_insights(results):
    valid = [r for r in results if r.get("cpk") is not None]
    if not valid:
        return [{"level":"wn", "text":"Ainda não há medições suficientes para análise. São necessárias no mínimo 2 medições válidas por característica e pelo menos um limite de especificação."}]
    fail = [r for r in valid if r["cpk"] < 1]
    warn = [r for r in valid if 1 <= r["cpk"] < 1.33]
    ok = [r for r in valid if r["cpk"] >= 1.33]
    insights = []
    if fail:
        names = ", ".join(f"{r['descricao']} (Cpk {r['cpk']:.2f})" for r in fail)
        insights.append({"level":"fl", "text":f"Parecer: processo não capaz para {len(fail)} característica(s): {names}. Recomendo bloqueio técnico da liberação até avaliação do setup, segregação do lote e nova coleta após correção."})
    if warn:
        names = ", ".join(f"{r['descricao']} (Cpk {r['cpk']:.2f})" for r in warn)
        insights.append({"level":"wn", "text":f"Parecer: processo marginal para {len(warn)} característica(s): {names}. Recomendo acompanhamento reforçado, ajuste preventivo e aumento temporário da frequência de inspeção."})
    if ok and not fail and not warn:
        insights.append({"level":"ok", "text":f"Parecer: processo capaz. Todas as {len(ok)} característica(s) avaliadas apresentam Cpk ≥ 1,33, indicando boa condição estatística frente aos limites especificados."})
    for r in valid:
        cp, cpk = r.get("cp"), r.get("cpk")
        if cp and cpk and cp > 0 and (cp - cpk) / cp > 0.15:
            perda = round((cp - cpk) / cp * 100)
            insights.append({"level":"wn", "text":f"Foi identificado descentramento em {r['descricao']}: Cp={cp:.2f} e Cpk={cpk:.2f}, com perda aproximada de {perda}% da capacidade potencial. O processo tem variação aceitável, mas está deslocado em relação ao centro da especificação."})
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
    fig.add_trace(go.Scatter(x=x, y=vals, mode="lines+markers+text", text=[f"{v:.3f}" for v in vals], textposition="top center", name="Medições"))
    fig.add_hline(y=mean, line_dash="solid", annotation_text=f"Média {mean:.3f}")
    fig.add_hline(y=ucl, line_dash="dash", annotation_text=f"LSC {ucl:.3f}")
    fig.add_hline(y=lcl, line_dash="dash", annotation_text=f"LIC {lcl:.3f}")
    if result.get("lse") is not None:
        fig.add_hline(y=result["lse"], line_dash="dot", annotation_text=f"LSE {result['lse']:.3f}")
    if result.get("lie") is not None:
        fig.add_hline(y=result["lie"], line_dash="dot", annotation_text=f"LIE {result['lie']:.3f}")
    fig.update_layout(
        height=370,
        title=f"{result['descricao']} | Cpk: {result['cpk'] if result['cpk'] is not None else '—'}",
        paper_bgcolor="#1c1c25",
        plot_bgcolor="#16161d",
        font=dict(color="#e8e8f0"),
        margin=dict(l=20, r=20, t=55, b=20),
    )
    return fig


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
    dados = [
        ["Linha", carta.get("linha", ""), "Embalagem", carta.get("embalagem", "")],
        ["Esp. Corpo", carta.get("esp_corpo", ""), "Esp. Domo", carta.get("esp_domo", "")],
        ["Esp. Fundo", carta.get("esp_fundo", ""), "Lote produzido", carta.get("lote_qtd", "")],
        ["OP", carta.get("op", ""), "Data", carta.get("data", "")],
    ]
    t = Table(dados, colWidths=[W*.18, W*.32, W*.18, W*.32])
    t.setStyle(TableStyle([("GRID", (0,0),(-1,-1), .25, colors.grey), ("FONTSIZE", (0,0),(-1,-1), 8), ("BACKGROUND", (0,0),(-1,-1), colors.whitesmoke)]))
    story.append(t)
    story.append(Spacer(1, 4*mm))
    rows = [["Característica", "N", "Média", "Desvio", "LIE", "LSE", "Cp", "CPU", "CPL", "Cpk", "Status"]]
    for r in results:
        rows.append([r["descricao"], r["n"], r["media"], r["desvio"], r["lie"], r["lse"], r["cp"], r["cpu"], r["cpl"], r["cpk"], r["status"]])
    tb = Table(rows, colWidths=[W*.24, W*.05, W*.08, W*.08, W*.08, W*.08, W*.07, W*.07, W*.07, W*.07, W*.11], repeatRows=1)
    tb.setStyle(TableStyle([("GRID", (0,0),(-1,-1), .25, colors.grey), ("FONTSIZE", (0,0),(-1,-1), 6.5), ("BACKGROUND", (0,0),(-1,0), colors.lightgrey)]))
    story.append(tb)
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph("<b>Análise e parecer automático</b>", S("sec", fontSize=10, textColor=TEXT, fontName="Helvetica-Bold")))
    for ins in build_insights(results):
        story.append(Paragraph(ins["text"], S("body", fontSize=8, leading=11, textColor=TEXT)))
    story.append(Spacer(1, 8*mm))
    story.append(Paragraph("Responsável técnico: _______________________________", S("sig", fontSize=8, textColor=TEXT)))
    doc.build(story)
    buf.seek(0)
    return buf.getvalue()

# ─────────────────────────────────────────────────────────────────────────────
# Interface
# ─────────────────────────────────────────────────────────────────────────────
st.title("📊 Carta de Inspeção CPK")
st.caption("Fluxo: dados da carta → criação das características → registro das medições → análise estatística e parecer automático.")

tab1, tab2, tab3, tab4 = st.tabs(["1. Carta de dados", "2. Criar inspeção", "3. Registrar medições", "4. Análise estatística"])

with tab1:
    st.subheader("Carta de dados — materiais e identificação")
    with st.form("form_carta"):
        c1, c2, c3 = st.columns(3)
        with c1:
            linha = st.text_input("Linha *", value=st.session_state.carta_dados.get("linha", "GL"))
            embalagem = st.text_input("Embalagem *", value=st.session_state.carta_dados.get("embalagem", ""))
            op = st.text_input("Ordem de produção *", value=st.session_state.carta_dados.get("op", ""))
        with c2:
            esp_corpo = st.text_input("Espessura corpo *", value=st.session_state.carta_dados.get("esp_corpo", ""))
            esp_domo = st.text_input("Espessura componente domo *", value=st.session_state.carta_dados.get("esp_domo", ""))
            esp_fundo = st.text_input("Espessura componente fundo *", value=st.session_state.carta_dados.get("esp_fundo", ""))
        with c3:
            lote_qtd = st.number_input("Lote produzido (Qtd) *", min_value=0, step=1, value=int(st.session_state.carta_dados.get("lote_qtd", 0) or 0))
            data_carta = st.date_input("Data", value=date.today(), format="DD/MM/YYYY")
        st.markdown("#### Materiais")
        m1, m2, m3 = st.columns(3)
        with m1:
            domo_mat = st.text_input("Material / lote domo", value=st.session_state.carta_dados.get("domo_mat", ""))
        with m2:
            corpo_mat = st.text_input("Material / lote corpo", value=st.session_state.carta_dados.get("corpo_mat", ""))
        with m3:
            fundo_mat = st.text_input("Material / lote fundo", value=st.session_state.carta_dados.get("fundo_mat", ""))
        obs = st.text_area("Observações gerais", value=st.session_state.carta_dados.get("obs", ""))
        submitted = st.form_submit_button("Salvar carta e liberar criação da inspeção", use_container_width=True)
    if submitted:
        obrig = [linha, embalagem, op, esp_corpo, esp_domo, esp_fundo]
        if any(str(v).strip() == "" for v in obrig) or lote_qtd <= 0:
            st.error("Preencha todos os campos obrigatórios marcados com * e informe lote produzido maior que zero.")
        else:
            st.session_state.carta_ok = True
            st.session_state.carta_dados = {
                "linha": linha, "embalagem": embalagem, "op": op, "esp_corpo": esp_corpo,
                "esp_domo": esp_domo, "esp_fundo": esp_fundo, "lote_qtd": lote_qtd,
                "data": data_carta.strftime("%d/%m/%Y"), "domo_mat": domo_mat,
                "corpo_mat": corpo_mat, "fundo_mat": fundo_mat, "obs": obs,
            }
            st.success("Carta salva. A aba 'Criar inspeção' está liberada.")

    if st.session_state.carta_ok:
        st.markdown("<div class='card'><b>Carta ativa:</b> " + f"Linha {st.session_state.carta_dados.get('linha')} | Embalagem {st.session_state.carta_dados.get('embalagem')} | OP {st.session_state.carta_dados.get('op')}" + "</div>", unsafe_allow_html=True)

with tab2:
    st.subheader("Criação das características de inspeção")
    if not st.session_state.carta_ok:
        st.warning("Primeiro salve a Carta de dados na aba 1.")
    else:
        with st.form("form_caracteristica"):
            descricao = st.text_input("Descrição da característica *", placeholder="Ex.: Diâmetro interno, pestana, altura, profundidade de expansão")
            c1, c2, c3 = st.columns(3)
            with c1:
                lie = st.text_input("Limite mínimo / LIE *", placeholder="Ex.: 52,10")
            with c2:
                lse = st.text_input("Limite máximo / LSE *", placeholder="Ex.: 52,30")
            with c3:
                num_amostras = st.number_input("Número de amostras que serão coletadas *", min_value=1, max_value=200, step=1, value=10)
            submitted_char = st.form_submit_button("Criar característica", use_container_width=True)
        if submitted_char:
            lie_v = parse_float(lie)
            lse_v = parse_float(lse)
            if not descricao.strip() or lie_v is None or lse_v is None or lie_v >= lse_v:
                st.error("Informe descrição, limite mínimo e limite máximo válidos. O limite mínimo deve ser menor que o limite máximo.")
            else:
                new_id = f"C{len(st.session_state.caracteristicas)+1:03d}_{datetime.now().strftime('%H%M%S')}"
                medicoes = [{"Amostra": i, "Medida 1": None, "Medida 2": None, "Medida 3": None} for i in range(1, int(num_amostras)+1)]
                st.session_state.caracteristicas.append({
                    "id": new_id, "descricao": descricao.strip(), "lie": lie_v, "lse": lse_v,
                    "num_amostras": int(num_amostras), "medicoes": medicoes,
                })
                st.session_state.selected_id = new_id
                st.success("Característica criada. Clique nela abaixo ou acesse a aba 'Registrar medições'.")

        if st.session_state.caracteristicas:
            st.markdown("#### Características abertas")
            for char in st.session_state.caracteristicas:
                result = calc_characteristic(char)
                cols = st.columns([4, 1, 1, 1])
                cols[0].markdown(f"**{char['descricao']}**  \nLIE: {char['lie']} | LSE: {char['lse']} | Amostras: {char['num_amostras']} | Medições: {result['medidas_realizadas']}/{result['medidas_previstas']}")
                cols[1].metric("Cpk", "—" if result["cpk"] is None else result["cpk"])
                cols[2].markdown(f"**Status:** {result['status']}")
                if cols[3].button("Abrir", key=f"open_{char['id']}"):
                    st.session_state.selected_id = char["id"]
                    st.success(f"Característica selecionada: {char['descricao']}")

with tab3:
    st.subheader("Registro das medições")
    if not st.session_state.caracteristicas:
        st.warning("Crie pelo menos uma característica na aba 2.")
    else:
        options = {f"{c['descricao']} | {c['id']}": c["id"] for c in st.session_state.caracteristicas}
        current_key = next((k for k, v in options.items() if v == st.session_state.selected_id), list(options.keys())[0])
        selected_label = st.selectbox("Selecione a característica", list(options.keys()), index=list(options.keys()).index(current_key))
        st.session_state.selected_id = options[selected_label]
        char = next(c for c in st.session_state.caracteristicas if c["id"] == st.session_state.selected_id)
        st.info(f"Cada amostra deve conter obrigatoriamente 3 medidas. Característica: {char['descricao']} | LIE {char['lie']} | LSE {char['lse']}")
        df_med = pd.DataFrame(char["medicoes"])
        edited_med = st.data_editor(
            df_med,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            column_config={
                "Amostra": st.column_config.NumberColumn("Amostra", disabled=True),
                "Medida 1": st.column_config.NumberColumn("Medida 1", format="%.4f"),
                "Medida 2": st.column_config.NumberColumn("Medida 2", format="%.4f"),
                "Medida 3": st.column_config.NumberColumn("Medida 3", format="%.4f"),
            },
            key=f"editor_{char['id']}",
        )
        if st.button("Salvar medições desta característica", use_container_width=True):
            char["medicoes"] = edited_med.to_dict("records")
            st.success("Medições salvas. A análise estatística já pode ser consultada na aba 4.")

with tab4:
    st.subheader("Análise estatística e parecer do processo")
    if not st.session_state.caracteristicas:
        st.warning("Não há características criadas para análise.")
    else:
        results = [calc_characteristic(c) for c in st.session_state.caracteristicas]
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
        c5.metric("Características", len(results))

        result_df = pd.DataFrame([{
            "Característica": r["descricao"], "Amostras previstas": r["amostras_previstas"],
            "Medições realizadas": r["medidas_realizadas"], "N": r["n"], "Média": r["media"],
            "Desvio": r["desvio"], "LIE": r["lie"], "LSE": r["lse"], "Cp": r["cp"],
            "CPU": r["cpu"], "CPL": r["cpl"], "Cpk": r["cpk"], "Status": r["status"],
        } for r in results])
        st.dataframe(result_df, use_container_width=True, hide_index=True)

        st.markdown("#### Parecer automático")
        for ins in build_insights(results):
            st.markdown(f"<div class='{ins['level']}'>{ins['text']}</div>", unsafe_allow_html=True)

        st.markdown("#### Gráficos por característica")
        for r in results:
            fig = control_chart(r)
            if fig:
                st.plotly_chart(fig, use_container_width=True)

        st.markdown("#### Exportação")
        col_a, col_b = st.columns(2)
        with col_a:
            xlsx = io.BytesIO()
            with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
                pd.DataFrame([st.session_state.carta_dados]).to_excel(writer, sheet_name="CARTA", index=False)
                result_df.to_excel(writer, sheet_name="RESULTADOS", index=False)
                for c in st.session_state.caracteristicas:
                    safe = re.sub(r"[^A-Za-z0-9_]+", "_", c["descricao"][:20]) or c["id"]
                    pd.DataFrame(c["medicoes"]).to_excel(writer, sheet_name=safe[:31], index=False)
            st.download_button("Baixar Excel da carta", xlsx.getvalue(), file_name=f"carta_cpk_{datetime.now().strftime('%d_%m_%Y_%H%M')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        with col_b:
            pdf = make_pdf(st.session_state.carta_dados, results)
            if pdf:
                st.download_button("Baixar relatório PDF", pdf, file_name=f"relatorio_cpk_{datetime.now().strftime('%d_%m_%Y_%H%M')}.pdf", mime="application/pdf", use_container_width=True)
            else:
                st.warning("Inclua reportlab no requirements.txt para exportar PDF.")
