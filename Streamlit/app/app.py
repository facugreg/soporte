"""
App Streamlit: Cuenta Corriente por Cliente (SQL Server)

Tarea 2: seleccionar cliente y ver su cuenta corriente.
Tarea 3: exportar la cuenta corriente a PDF / Excel (se guardan en app/exports).
Tarea 4: reporte con grafico de facturacion mensual (mes vs. monto facturado).
"""

import matplotlib.pyplot as plt
import streamlit as st

from db import get_clientes, get_cuenta_corriente, get_facturado_mensual
from exportar import exportar_excel, exportar_pdf

st.set_page_config(page_title="Cuenta Corriente", layout="wide")
st.title("Cuenta Corriente por Cliente")

clientes = get_clientes()

opciones = clientes.apply(lambda r: f"{r['NumeroCliente']} - {r['Nombre']}", axis=1)
seleccion = st.selectbox("Seleccionar cliente", opciones)
numero_cliente = int(seleccion.split(" - ")[0])
cliente = clientes.loc[clientes["NumeroCliente"] == numero_cliente].iloc[0]

st.subheader(f"{cliente['Nombre']}  (CUIT {cliente['Cuit']})")

movimientos = get_cuenta_corriente(numero_cliente)

col1, col2, col3 = st.columns(3)
col1.metric("Total Debe", f"$ {movimientos['Debe'].sum():,.2f}")
col2.metric("Total Haber", f"$ {movimientos['Haber'].sum():,.2f}")
col3.metric("Saldo final", f"$ {(movimientos['Debe'].sum() - movimientos['Haber'].sum()):,.2f}")

st.dataframe(
    movimientos.style.format({"Debe": "{:,.2f}", "Haber": "{:,.2f}", "Saldo": "{:,.2f}"}),
    use_container_width=True,
    hide_index=True,
)

st.divider()
st.subheader("Exportar")

exp_col1, exp_col2 = st.columns(2)

with exp_col1:
    if st.button("Exportar a PDF"):
        ruta_pdf = exportar_pdf(movimientos, numero_cliente, cliente["Nombre"], cliente["Cuit"])
        st.success(f"PDF guardado en: {ruta_pdf}")
        with open(ruta_pdf, "rb") as f:
            st.download_button("Descargar PDF", f, file_name=ruta_pdf.split("\\")[-1])

with exp_col2:
    if st.button("Exportar a Excel"):
        ruta_xlsx = exportar_excel(movimientos, numero_cliente, cliente["Nombre"])
        st.success(f"Excel guardado en: {ruta_xlsx}")
        with open(ruta_xlsx, "rb") as f:
            st.download_button("Descargar Excel", f, file_name=ruta_xlsx.split("\\")[-1])

st.divider()
st.subheader("Reporte de facturacion mensual")

if st.button("Ver reporte de facturacion mensual"):
    facturado = get_facturado_mensual(numero_cliente)

    if facturado.empty:
        st.info("Este cliente no tiene facturas registradas.")
    else:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar(facturado["AnioMes"], facturado["TotalFacturado"], color="#2C7BE5")
        ax.set_xlabel("Mes")
        ax.set_ylabel("Monto facturado ($)")
        ax.set_title(f"Facturacion mensual - {cliente['Nombre']}")
        plt.xticks(rotation=45)
        fig.tight_layout()
        st.pyplot(fig)
        st.dataframe(facturado, use_container_width=True, hide_index=True)
