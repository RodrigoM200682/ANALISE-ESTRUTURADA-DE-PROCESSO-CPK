from flask import Flask, render_template, request, jsonify, send_file
import json, math, io
from datetime import datetime

app = Flask(__name__)

# ─── CPK CALCULATIONS ────────────────────────────────────────────────────────

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
    return {
        "vals": vals, "n": n, "mean": mean, "std": std,
        "cp": cp, "cpk": cpk, "cpu": cpu, "cpl": cpl
    }

def build_insights(params):
    valid = [p for p in params if p.get("cpk") is not None]
    fail  = [p for p in valid if p["cpk"] < 1]
    warn  = [p for p in valid if 1 <= p["cpk"] < 1.33]
    ok    = [p for p in valid if p["cpk"] >= 1.33]
    insights = []
    if not fail and not warn and ok:
        insights.append({"level":"ok","text":f"Processo excelente. Todos os {len(ok)} parâmetros com Cpk ≥ 1,33."})
    if fail:
        names = ", ".join(f"{p['name']} (Cpk {p['cpk']:.2f})" for p in fail)
        insights.append({"level":"fl","text":f"{len(fail)} parâmetro(s) crítico(s): {names}. Ação imediata necessária."})
    if warn:
        names = ", ".join(f"{p['name']} (Cpk {p['cpk']:.2f})" for p in warn)
        insights.append({"level":"wn","text":f"{len(warn)} parâmetro(s) marginal(is): {names}. Monitoramento intensificado recomendado."})
    for p in valid:
        cp, cpk = p.get("cp"), p.get("cpk")
        if cp and cpk and cp > 0 and (cp - cpk) / cp > 0.15:
            pct = round((cp - cpk) / cp * 100)
            insights.append({"level":"wn","text":f"Descentramento — {p['name']}: Cp={cp:.2f} vs Cpk={cpk:.2f} ({pct}% de perda). Revisar setup."})
    if ok:
        best = max(ok, key=lambda p: p["cpk"])
        insights.append({"level":"ok","text":f"Melhor desempenho: {best['name']} com Cpk={best['cpk']:.2f}."})
    if valid:
        pct = round(len(ok) / len(valid) * 100)
        msg = "Processo sob controle." if pct >= 80 else ("Atenção em pontos específicos." if pct >= 50 else "Revisão urgente necessária.")
        level = "ok" if pct >= 80 else ("wn" if pct >= 50 else "fl")
        insights.append({"level": level, "text": f"Índice geral: {pct}% dos parâmetros capazes. {msg}"})
    return insights

# ─── ROUTES ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/calc", methods=["POST"])
def api_calc():
    data = request.get_json()
    params = data.get("params", [])
    results = []
    for p in params:
        lse = float(p["lse"]) if p.get("lse") not in (None, "") else None
        lie = float(p["lie"]) if p.get("lie") not in (None, "") else None
        s = calc_stats(p.get("samples", []), lse, lie)
        results.append({
            "id": p["id"],
            "cpk":  round(s["cpk"],  4) if s and s["cpk"]  is not None else None,
            "cp":   round(s["cp"],   4) if s and s["cp"]   is not None else None,
            "cpu":  round(s["cpu"],  4) if s and s["cpu"]  is not None else None,
            "cpl":  round(s["cpl"],  4) if s and s["cpl"]  is not None else None,
            "mean": round(s["mean"], 4) if s else None,
            "std":  round(s["std"],  4) if s else None,
            "n":    s["n"] if s else 0,
        })
    return jsonify(results)

@app.route("/api/insights", methods=["POST"])
def api_insights():
    data = request.get_json()
    return jsonify(build_insights(data.get("params", [])))

@app.route("/api/pdf", methods=["POST"])
def api_pdf():
    """Generate PDF server-side using reportlab."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.graphics.shapes import Drawing, Line, Circle, String, Rect
        from reportlab.graphics import renderPDF

        data   = request.get_json()
        ident  = data.get("ident", {})
        params = data.get("params", [])
        insights = build_insights(params)

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4,
                                leftMargin=13*mm, rightMargin=13*mm,
                                topMargin=14*mm, bottomMargin=16*mm)

        W = A4[0] - 26*mm
        BG    = colors.HexColor("#0a0a0d")
        ACC   = colors.HexColor("#00e5a0")
        CARD  = colors.HexColor("#1c1c25")
        MUTED = colors.HexColor("#6b6b80")
        TEXT  = colors.HexColor("#e8e8f0")
        GREEN = colors.HexColor("#00e5a0")
        AMBER = colors.HexColor("#ffb340")
        RED   = colors.HexColor("#ff4d4d")
        BLUE  = colors.HexColor("#4d9eff")

        styles = getSampleStyleSheet()
        def S(name, **kw):
            return ParagraphStyle(name, parent=styles["Normal"], **kw)

        sTitle  = S("t",  fontSize=16, textColor=TEXT,  fontName="Helvetica-Bold", spaceAfter=2)
        sSub    = S("s",  fontSize=8,  textColor=MUTED, fontName="Helvetica")
        sSec    = S("sc", fontSize=7,  textColor=TEXT,  fontName="Helvetica-Bold", textTransform="uppercase", spaceBefore=10, spaceAfter=4)
        sLabel  = S("la", fontSize=7,  textColor=MUTED, fontName="Helvetica")
        sValue  = S("va", fontSize=10, textColor=TEXT,  fontName="Helvetica-Bold")
        sBody   = S("bo", fontSize=8,  textColor=TEXT,  fontName="Helvetica", leading=12)
        sOk     = S("ok", fontSize=8,  textColor=GREEN, fontName="Helvetica", leading=12)
        sWn     = S("wn", fontSize=8,  textColor=AMBER, fontName="Helvetica", leading=12)
        sFl     = S("fl", fontSize=8,  textColor=RED,   fontName="Helvetica", leading=12)

        story = []

        # ── Header ──
        hdr_data = [[
            Paragraph("<b>CPK Process Analyzer</b>", S("hh", fontSize=17, textColor=TEXT, fontName="Helvetica-Bold")),
            Paragraph(f"Gerado: {datetime.now().strftime('%d/%m/%Y %H:%M')}", S("hd", fontSize=8, textColor=MUTED, fontName="Helvetica", alignment=2))
        ]]
        hdr_tbl = Table(hdr_data, colWidths=[W*0.65, W*0.35])
        hdr_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0,0),(-1,-1), BG),
            ("VALIGN",     (0,0),(-1,-1), "MIDDLE"),
            ("LEFTPADDING",(0,0),(-1,-1), 10),
            ("RIGHTPADDING",(0,0),(-1,-1),10),
            ("TOPPADDING", (0,0),(-1,-1), 10),
            ("BOTTOMPADDING",(0,0),(-1,-1),10),
            ("LINEBELOW",  (0,0),(-1,-1), 2, ACC),
        ]))
        story.append(hdr_tbl)
        story.append(Spacer(1, 6*mm))

        # ── Identification ──
        story.append(Paragraph("1. Identificação do processo", sSec))
        id_data = [[
            [Paragraph("Linha", sLabel), Paragraph(ident.get("linha","—"), sValue)],
            [Paragraph("Embalagem", sLabel), Paragraph(ident.get("emb","—"), sValue)],
            [Paragraph("Data", sLabel), Paragraph(ident.get("data","—"), sValue)],
            [Paragraph("OP", sLabel), Paragraph(ident.get("op","—"), sValue)],
        ]]
        flat = [[cell for pair in id_data[0] for cell in pair]]
        id_tbl = Table(flat, colWidths=[W/4]*4)
        id_tbl.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1), CARD),
            ("LEFTPADDING",(0,0),(-1,-1), 8),
            ("RIGHTPADDING",(0,0),(-1,-1),8),
            ("TOPPADDING",(0,0),(-1,-1), 6),
            ("BOTTOMPADDING",(0,0),(-1,-1),6),
            ("ROWBACKGROUNDS",(0,0),(-1,-1),[CARD]),
        ]))
        story.append(id_tbl)
        story.append(Spacer(1,4*mm))

        # ── Materials ──
        mats = [
            ("Corpo",  ident.get("corpo_usina","—"),  ident.get("corpo_esp","—"),  BLUE),
            ("Domo",   ident.get("domo_usina","—"),   ident.get("domo_esp","—"),   GREEN),
            ("Fundo",  ident.get("fundo_usina","—"),  ident.get("fundo_esp","—"),  AMBER),
        ]
        mat_row = []
        for nm, usina, esp, col in mats:
            mat_row.append([
                Paragraph(f"<b>{nm}</b>", S("mn", fontSize=8, textColor=col, fontName="Helvetica-Bold")),
                Paragraph(f"Usina: {usina}<br/>Esp.: {esp} mm", S("ms", fontSize=7, textColor=MUTED, fontName="Helvetica", leading=10)),
            ])
        mat_inner = Table([[cell for pair in mat_row for cell in pair]], colWidths=[W/6]*6)
        mat_inner.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1), CARD),
            ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),
            ("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),
        ]))
        story.append(mat_inner)

        if ident.get("obs"):
            story.append(Spacer(1,3*mm))
            story.append(Paragraph(f"<i>Observações:</i> {ident['obs']}", S("ob", fontSize=7.5, textColor=MUTED, fontName="Helvetica-Oblique", leading=11)))

        story.append(Spacer(1,5*mm))

        # ── Summary KPIs ──
        story.append(Paragraph("2. Resumo executivo de capacidade", sSec))
        valid  = [p for p in params if p.get("cpk") is not None]
        ok_n   = len([p for p in valid if p["cpk"] >= 1.33])
        wn_n   = len([p for p in valid if 1 <= p["cpk"] < 1.33])
        fl_n   = len([p for p in valid if p["cpk"] < 1])
        avg_cpk = round(sum(p["cpk"] for p in valid)/len(valid), 2) if valid else None
        avg_col = GREEN if avg_cpk and avg_cpk >= 1.33 else (AMBER if avg_cpk and avg_cpk >= 1 else RED) if avg_cpk else MUTED

        def kpi_cell(label, value, col):
            return [
                Paragraph(label, S("kl", fontSize=7, textColor=col, fontName="Helvetica-Bold", textTransform="uppercase")),
                Paragraph(str(value), S("kv", fontSize=18, textColor=col, fontName="Helvetica-Bold")),
            ]

        kpis = [kpi_cell("Cpk médio", avg_cpk or "—", avg_col),
                kpi_cell("Capazes ≥1,33", ok_n, GREEN),
                kpi_cell("Marginais", wn_n, AMBER),
                kpi_cell("Incapazes", fl_n, RED),
                kpi_cell("Total", len(params), MUTED)]
        kpi_flat = [cell for pair in kpis for cell in pair]
        kpi_tbl = Table([kpi_flat], colWidths=[W/5]*5)
        kpi_tbl.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1),CARD),
            ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),
            ("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8),
            ("LINEABOVE",(0,0),(-1,0),2,ACC),
        ]))
        story.append(kpi_tbl)
        story.append(Spacer(1,5*mm))

        # ── Results table ──
        story.append(Paragraph("3. Resultados por parâmetro", sSec))
        th_style = S("th", fontSize=7, textColor=TEXT, fontName="Helvetica-Bold")
        td_style = S("td", fontSize=7, textColor=TEXT, fontName="Helvetica")
        header_row = [Paragraph(h, th_style) for h in ["Parâmetro","Un.","N","Média","Desvio","LIE","LSE","Cp","Cpk"]]
        rows = [header_row]
        for p in params:
            st = "ok" if p.get("cpk") and p["cpk"] >= 1.33 else ("wn" if p.get("cpk") and p["cpk"] >= 1 else "fl")
            cpk_col = GREEN if st=="ok" else (AMBER if st=="wn" else RED)
            rows.append([
                Paragraph(p["name"][:28], td_style),
                Paragraph(p.get("unit","mm"), td_style),
                Paragraph(str(p.get("n","")), td_style),
                Paragraph(f"{p['mean']:.3f}" if p.get("mean") is not None else "—", td_style),
                Paragraph(f"{p['std']:.4f}" if p.get("std")  is not None else "—", td_style),
                Paragraph(str(p.get("lie","—")), td_style),
                Paragraph(str(p.get("lse","—")), td_style),
                Paragraph(f"{p['cp']:.2f}" if p.get("cp") is not None else "—", td_style),
                Paragraph(f"{p['cpk']:.2f}" if p.get("cpk") is not None else "—",
                          S("cpk", fontSize=7, textColor=cpk_col, fontName="Helvetica-Bold")),
            ])
        col_w = [W*0.22, W*0.06, W*0.05, W*0.09, W*0.09, W*0.08, W*0.08, W*0.07, W*0.08]
        res_tbl = Table(rows, colWidths=col_w, repeatRows=1)
        res_tbl.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0), colors.HexColor("#12121a")),
            ("BACKGROUND",(0,1),(-1,-1), CARD),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[CARD, colors.HexColor("#161620")]),
            ("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5),
            ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
            ("LINEBELOW",(0,0),(-1,0),0.5, colors.HexColor("#2a2a32")),
            ("GRID",(0,0),(-1,-1),0.2, colors.HexColor("#2a2a32")),
        ]))
        story.append(res_tbl)
        story.append(Spacer(1,5*mm))

        # ── Per-param sparkline charts ──
        story.append(Paragraph("4. Gráficos de controle por parâmetro", sSec))
        for p in params:
            samples_raw = p.get("samples", [])
            lse_v = float(p["lse"]) if p.get("lse") not in (None,"") else None
            lie_v = float(p["lie"]) if p.get("lie") not in (None,"") else None
            s = calc_stats(samples_raw, lse_v, lie_v)
            if not s:
                continue
            vals = s["vals"]
            mean_v, std_v = s["mean"], s["std"]
            ucl = mean_v + 3*std_v
            lcl = mean_v - 3*std_v
            all_v = vals + ([lse_v] if lse_v else []) + ([lie_v] if lie_v else []) + [ucl, lcl]
            vmn, vmx = min(all_v), max(all_v)
            vr = vmx - vmn or 0.001

            DW, DH = W, 36*mm
            PAD_L, PAD_R, PAD_T, PAD_B = 12*mm, 18*mm, 4*mm, 5*mm
            CW2 = DW - PAD_L - PAD_R
            CH2 = DH - PAD_T - PAD_B

            def xp(i): return PAD_L + (i/(len(vals)-1 or 1))*CW2
            def yp(v): return PAD_B + ((v-vmn)/vr)*CH2

            d = Drawing(DW, DH)
            # background
            bg = Rect(0, 0, DW, DH, fillColor=colors.HexColor("#16161d"), strokeColor=colors.HexColor("#2a2a32"), strokeWidth=0.5)
            d.add(bg)

            def hline(val, col, dash=None):
                yy = yp(val)
                ln = Line(PAD_L, yy, PAD_L+CW2, yy, strokeColor=col, strokeWidth=0.5)
                if dash:
                    ln.strokeDashArray = [2, 2]
                d.add(ln)
                lbl = String(PAD_L+CW2+1*mm, yy-1.5, f"{val:.3f}",
                             fontSize=5, fillColor=col, fontName="Helvetica")
                d.add(lbl)

            hline(mean_v, BLUE)
            hline(ucl, RED, True)
            hline(lcl, RED, True)
            if lse_v is not None: hline(lse_v, AMBER, True)
            if lie_v is not None: hline(lie_v, AMBER, True)

            st = "ok" if p.get("cpk") and p["cpk"]>=1.33 else ("wn" if p.get("cpk") and p["cpk"]>=1 else "fl")
            line_col = GREEN if st=="ok" else (AMBER if st=="wn" else RED)

            for i in range(len(vals)-1):
                d.add(Line(xp(i), yp(vals[i]), xp(i+1), yp(vals[i+1]),
                           strokeColor=line_col, strokeWidth=0.8))
            for i, v in enumerate(vals):
                out = (lse_v is not None and v > lse_v) or (lie_v is not None and v < lie_v)
                fc = RED if out else line_col
                d.add(Circle(xp(i), yp(v), 1.5, fillColor=fc, strokeColor=fc, strokeWidth=0))

            # x-axis labels
            step = max(1, len(vals)//8)
            for i in range(0, len(vals), step):
                d.add(String(xp(i)-1.5, PAD_B-4, str(i+1),
                             fontSize=5, fillColor=MUTED, fontName="Helvetica"))

            # param name title
            cpk_str = f"Cpk={p['cpk']:.2f}" if p.get("cpk") is not None else ""
            d.add(String(PAD_L, DH-3*mm, f"{p['name']}  {cpk_str}",
                         fontSize=7, fillColor=TEXT, fontName="Helvetica-Bold"))

            story.append(d)

            # stat strip
            stat_items = [
                ("Média",  f"{s['mean']:.3f}"),
                ("Desvio", f"{s['std']:.4f}"),
                ("Cp",     f"{s['cp']:.2f}"  if s["cp"]  is not None else "—"),
                ("Cpk",    f"{s['cpk']:.2f}" if s["cpk"] is not None else "—"),
                ("CPU",    f"{s['cpu']:.2f}" if s["cpu"] is not None else "—"),
                ("CPL",    f"{s['cpl']:.2f}" if s["cpl"] is not None else "—"),
            ]
            cpk_col2 = GREEN if st=="ok" else (AMBER if st=="wn" else RED)
            stat_cells = []
            for label, val in stat_items:
                col2 = cpk_col2 if label=="Cpk" else TEXT
                stat_cells.append([
                    Paragraph(label, S("sl", fontSize=6, textColor=MUTED, fontName="Helvetica")),
                    Paragraph(val,   S("sv", fontSize=9, textColor=col2,  fontName="Helvetica-Bold")),
                ])
            stat_flat = [cell for pair in stat_cells for cell in pair]
            stat_tbl  = Table([stat_flat], colWidths=[W/6]*6)
            stat_tbl.setStyle(TableStyle([
                ("BACKGROUND",(0,0),(-1,-1), CARD),
                ("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),
                ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
            ]))
            story.append(stat_tbl)
            story.append(Spacer(1,4*mm))

        # ── Diagnostic ──
        story.append(Paragraph("5. Diagnóstico automático", sSec))
        for ins in insights:
            col_map = {"ok": GREEN, "wn": AMBER, "fl": RED}
            col = col_map.get(ins["level"], MUTED)
            ins_tbl = Table([[Paragraph(ins["text"], S("it", fontSize=8, textColor=col, fontName="Helvetica", leading=11))]],
                            colWidths=[W])
            ins_tbl.setStyle(TableStyle([
                ("BACKGROUND",(0,0),(-1,-1), CARD),
                ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),
                ("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),
                ("LINEBEFOREBOLD",(0,0),(0,-1),3, col),
                ("LINEBEFORE",(0,0),(0,-1),3, col),
            ]))
            story.append(ins_tbl)
            story.append(Spacer(1,2*mm))

        # ── Signature ──
        story.append(Spacer(1,4*mm))
        sig_tbl = Table([[
            Paragraph("Responsável técnico: _______________________________", sBody),
            Paragraph("Data: ___/___/______  Assinatura: ___________________", S("sg", fontSize=8, textColor=MUTED, fontName="Helvetica", alignment=2)),
        ]], colWidths=[W*0.5, W*0.5])
        sig_tbl.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1),CARD),
            ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),
            ("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8),
        ]))
        story.append(sig_tbl)

        # ── Page footer via canvas ──
        def add_footer(canvas, doc):
            canvas.saveState()
            canvas.setFillColor(BG)
            canvas.rect(0, 0, A4[0], 10*mm, fill=1, stroke=0)
            canvas.setFillColor(ACC)
            canvas.rect(13*mm, 8*mm, A4[0]-26*mm, 0.5, fill=1, stroke=0)
            canvas.setFont("Helvetica", 6.5)
            canvas.setFillColor(MUTED)
            canvas.drawString(13*mm, 4*mm,
                f"CPK Analyzer  ·  {ident.get('linha','—')}  ·  {ident.get('emb','—')}  ·  {ident.get('data','—')}")
            canvas.drawRightString(A4[0]-13*mm, 4*mm,
                f"Página {doc.page}")
            canvas.restoreState()

        doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
        buf.seek(0)
        fname = f"cpk_{ident.get('linha','relatorio')}_{ident.get('data', datetime.now().strftime('%Y-%m-%d'))}.pdf"
        fname = fname.replace(" ", "_")
        return send_file(buf, as_attachment=True, download_name=fname, mimetype="application/pdf")

    except ImportError:
        return jsonify({"error": "reportlab not installed"}), 500

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
