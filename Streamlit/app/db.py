"""Acceso a datos: conexion a SQLite y consultas de clientes / cuenta corriente."""

import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).parent.parent / "cuentacorriente.db"


@st.cache_resource
def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


@st.cache_data(ttl=60)
def get_clientes() -> pd.DataFrame:
    conn = get_connection()
    query = "SELECT NumeroCliente, Nombre, Cuit FROM Clientes ORDER BY NumeroCliente"
    return pd.read_sql(query, conn)


@st.cache_data(ttl=60)
def get_cuenta_corriente(numero_cliente: int) -> pd.DataFrame:
    conn = get_connection()
    query = """
        SELECT Fecha, NroComprobante, Detalle, Debe, Haber
        FROM CuentaCorriente
        WHERE NumeroCliente = ?
        ORDER BY Fecha, Id
    """
    df = pd.read_sql(query, conn, params=[numero_cliente])
    df["Saldo"] = (df["Debe"] - df["Haber"]).cumsum()
    return df


@st.cache_data(ttl=60)
def get_facturado_mensual(numero_cliente: int) -> pd.DataFrame:
    """Total facturado (Debe) por mes para un cliente, ordenado cronologicamente."""
    conn = get_connection()
    query = """
        SELECT
            strftime('%Y-%m', Fecha) AS AnioMes,
            SUM(Debe) AS TotalFacturado
        FROM CuentaCorriente
        WHERE NumeroCliente = ? AND Debe > 0
        GROUP BY strftime('%Y-%m', Fecha)
        ORDER BY AnioMes
    """
    return pd.read_sql(query, conn, params=[numero_cliente])
