"""Exportacion de la cuenta corriente a PDF y Excel."""

import os
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

EXPORTS_DIR = os.path.join(os.path.dirname(__file__), "exports")


def _asegurar_carpeta():
    os.makedirs(EXPORTS_DIR, exist_ok=True)
    return EXPORTS_DIR


def exportar_excel(df: pd.DataFrame, numero_cliente: int, nombre_cliente: str) -> str:
    _asegurar_carpeta()
    nombre_archivo = f"cuenta_corriente_cliente_{numero_cliente}.xlsx"
    ruta = os.path.join(EXPORTS_DIR, nombre_archivo)

    df_export = df.copy()
    df_export["Fecha"] = pd.to_datetime(df_export["Fecha"]).dt.strftime("%d/%m/%Y")

    with pd.ExcelWriter(ruta, engine="openpyxl") as writer:
        df_export.to_excel(writer, index=False, sheet_name="CuentaCorriente", startrow=2)
        ws = writer.sheets["CuentaCorriente"]
        ws["A1"] = f"Cuenta Corriente - Cliente {numero_cliente}: {nombre_cliente}"
        for col_cells in ws.columns:
            length = max(len(str(cell.value)) if cell.value is not None else 0 for cell in col_cells)
            ws.column_dimensions[col_cells[0].column_letter].width = max(12, length + 2)

    return ruta


def exportar_pdf(df: pd.DataFrame, numero_cliente: int, nombre_cliente: str, cuit: str) -> str:
    _asegurar_carpeta()
    nombre_archivo = f"cuenta_corriente_cliente_{numero_cliente}.pdf"
    ruta = os.path.join(EXPORTS_DIR, nombre_archivo)

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(ruta, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    elementos = []

    elementos.append(Paragraph("Cuenta Corriente", styles["Title"]))
    elementos.append(Paragraph(f"Cliente N.: {numero_cliente} - {nombre_cliente}", styles["Normal"]))
    elementos.append(Paragraph(f"CUIT: {cuit}", styles["Normal"]))
    elementos.append(Spacer(1, 0.5 * cm))

    df_pdf = df.copy()
    df_pdf["Fecha"] = pd.to_datetime(df_pdf["Fecha"]).dt.strftime("%d/%m/%Y")
    for col in ["Debe", "Haber", "Saldo"]:
        df_pdf[col] = df_pdf[col].map(lambda v: f"{v:,.2f}")

    data = [list(df_pdf.columns)] + df_pdf.values.tolist()
    tabla = Table(data, repeatRows=1, colWidths=[2.0 * cm, 2.8 * cm, 6.0 * cm, 2.3 * cm, 2.3 * cm, 2.3 * cm])
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (3, 1), (5, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
    ]))
    elementos.append(tabla)

    saldo_final = df["Debe"].sum() - df["Haber"].sum()
    elementos.append(Spacer(1, 0.5 * cm))
    elementos.append(Paragraph(f"Saldo final: {saldo_final:,.2f}", styles["Heading3"]))

    doc.build(elementos)
    return ruta
