/* ============================================================
   TAREA 1 (SQLite) - Base de datos embebida: Cuenta Corriente
   Crea las tablas Clientes y CuentaCorriente, y carga datos de
   prueba (10 clientes, 6 movimientos c/u). Version SQLite del
   script original 01_crear_base_datos.sql (T-SQL / SQL Server).
   ============================================================ */

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS CuentaCorriente;
DROP TABLE IF EXISTS Clientes;

-- ------------------------------------------------------------
-- Tabla Clientes
-- ------------------------------------------------------------
CREATE TABLE Clientes (
    NumeroCliente INTEGER NOT NULL PRIMARY KEY,
    Nombre        TEXT NOT NULL,
    Cuit          TEXT NOT NULL
);

-- ------------------------------------------------------------
-- Tabla CuentaCorriente (movimientos)
-- ------------------------------------------------------------
CREATE TABLE CuentaCorriente (
    Id             INTEGER PRIMARY KEY AUTOINCREMENT,
    NumeroCliente  INTEGER NOT NULL,
    Fecha          TEXT NOT NULL,
    NroComprobante TEXT NOT NULL,
    Detalle        TEXT NOT NULL,
    Debe           NUMERIC NOT NULL DEFAULT 0,
    Haber          NUMERIC NOT NULL DEFAULT 0,
    FOREIGN KEY (NumeroCliente) REFERENCES Clientes(NumeroCliente)
);

-- ------------------------------------------------------------
-- Datos: 10 clientes
-- ------------------------------------------------------------
INSERT INTO Clientes (NumeroCliente, Nombre, Cuit) VALUES
(1,  'Juan Perez',          '20-12345671-8'),
(2,  'Maria Gonzalez',      '27-23456782-3'),
(3,  'Carlos Rodriguez',    '20-34567893-4'),
(4,  'Ana Fernandez',       '27-45678904-5'),
(5,  'Roberto Gomez',       '20-56789015-6'),
(6,  'Laura Martinez',      '27-67890126-7'),
(7,  'Diego Lopez',         '20-78901237-8'),
(8,  'Silvia Sanchez',      '27-89012348-9'),
(9,  'Miguel Torres',       '20-90123459-0'),
(10, 'Patricia Diaz',       '27-01234560-1');

-- ------------------------------------------------------------
-- Datos: movimientos de cuenta corriente
-- 6 movimientos por cliente = 3 pares (Factura + Recibo que la
-- cancela por el mismo importe), intercalados.
-- ------------------------------------------------------------
INSERT INTO CuentaCorriente (NumeroCliente, Fecha, NroComprobante, Detalle, Debe, Haber) VALUES
-- Cliente 1
(1, '2026-01-11', 'FC-0001', 'Factura de venta N. FC-0001', 11000.00, 0),
(1, '2026-01-16', 'RC-0001', 'Recibo - cancela Factura FC-0001', 0, 11000.00),
(1, '2026-03-11', 'FC-0002', 'Factura de venta N. FC-0002', 16500.00, 0),
(1, '2026-03-16', 'RC-0002', 'Recibo - cancela Factura FC-0002', 0, 16500.00),
(1, '2026-05-11', 'FC-0003', 'Factura de venta N. FC-0003', 8250.00, 0),
(1, '2026-05-16', 'RC-0003', 'Recibo - cancela Factura FC-0003', 0, 8250.00),

-- Cliente 2
(2, '2026-02-12', 'FC-0004', 'Factura de venta N. FC-0004', 12000.00, 0),
(2, '2026-02-17', 'RC-0004', 'Recibo - cancela Factura FC-0004', 0, 12000.00),
(2, '2026-04-12', 'FC-0005', 'Factura de venta N. FC-0005', 18000.00, 0),
(2, '2026-04-17', 'RC-0005', 'Recibo - cancela Factura FC-0005', 0, 18000.00),
(2, '2026-06-12', 'FC-0006', 'Factura de venta N. FC-0006', 9000.00, 0),
(2, '2026-06-17', 'RC-0006', 'Recibo - cancela Factura FC-0006', 0, 9000.00),

-- Cliente 3
(3, '2026-01-13', 'FC-0007', 'Factura de venta N. FC-0007', 13000.00, 0),
(3, '2026-01-18', 'RC-0007', 'Recibo - cancela Factura FC-0007', 0, 13000.00),
(3, '2026-03-13', 'FC-0008', 'Factura de venta N. FC-0008', 19500.00, 0),
(3, '2026-03-18', 'RC-0008', 'Recibo - cancela Factura FC-0008', 0, 19500.00),
(3, '2026-05-13', 'FC-0009', 'Factura de venta N. FC-0009', 9750.00, 0),
(3, '2026-05-18', 'RC-0009', 'Recibo - cancela Factura FC-0009', 0, 9750.00),

-- Cliente 4
(4, '2026-02-14', 'FC-0010', 'Factura de venta N. FC-0010', 14000.00, 0),
(4, '2026-02-19', 'RC-0010', 'Recibo - cancela Factura FC-0010', 0, 14000.00),
(4, '2026-04-14', 'FC-0011', 'Factura de venta N. FC-0011', 21000.00, 0),
(4, '2026-04-19', 'RC-0011', 'Recibo - cancela Factura FC-0011', 0, 21000.00),
(4, '2026-06-14', 'FC-0012', 'Factura de venta N. FC-0012', 10500.00, 0),
(4, '2026-06-19', 'RC-0012', 'Recibo - cancela Factura FC-0012', 0, 10500.00),

-- Cliente 5
(5, '2026-01-15', 'FC-0013', 'Factura de venta N. FC-0013', 15000.00, 0),
(5, '2026-01-20', 'RC-0013', 'Recibo - cancela Factura FC-0013', 0, 15000.00),
(5, '2026-03-15', 'FC-0014', 'Factura de venta N. FC-0014', 22500.00, 0),
(5, '2026-03-20', 'RC-0014', 'Recibo - cancela Factura FC-0014', 0, 22500.00),
(5, '2026-05-15', 'FC-0015', 'Factura de venta N. FC-0015', 11250.00, 0),
(5, '2026-05-20', 'RC-0015', 'Recibo - cancela Factura FC-0015', 0, 11250.00),

-- Cliente 6
(6, '2026-02-16', 'FC-0016', 'Factura de venta N. FC-0016', 16000.00, 0),
(6, '2026-02-21', 'RC-0016', 'Recibo - cancela Factura FC-0016', 0, 16000.00),
(6, '2026-04-16', 'FC-0017', 'Factura de venta N. FC-0017', 24000.00, 0),
(6, '2026-04-21', 'RC-0017', 'Recibo - cancela Factura FC-0017', 0, 24000.00),
(6, '2026-06-16', 'FC-0018', 'Factura de venta N. FC-0018', 12000.00, 0),
(6, '2026-06-21', 'RC-0018', 'Recibo - cancela Factura FC-0018', 0, 12000.00),

-- Cliente 7
(7, '2026-01-17', 'FC-0019', 'Factura de venta N. FC-0019', 17000.00, 0),
(7, '2026-01-22', 'RC-0019', 'Recibo - cancela Factura FC-0019', 0, 17000.00),
(7, '2026-03-17', 'FC-0020', 'Factura de venta N. FC-0020', 25500.00, 0),
(7, '2026-03-22', 'RC-0020', 'Recibo - cancela Factura FC-0020', 0, 25500.00),
(7, '2026-05-17', 'FC-0021', 'Factura de venta N. FC-0021', 12750.00, 0),
(7, '2026-05-22', 'RC-0021', 'Recibo - cancela Factura FC-0021', 0, 12750.00),

-- Cliente 8
(8, '2026-02-18', 'FC-0022', 'Factura de venta N. FC-0022', 18000.00, 0),
(8, '2026-02-23', 'RC-0022', 'Recibo - cancela Factura FC-0022', 0, 18000.00),
(8, '2026-04-18', 'FC-0023', 'Factura de venta N. FC-0023', 27000.00, 0),
(8, '2026-04-23', 'RC-0023', 'Recibo - cancela Factura FC-0023', 0, 27000.00),
(8, '2026-06-18', 'FC-0024', 'Factura de venta N. FC-0024', 13500.00, 0),
(8, '2026-06-23', 'RC-0024', 'Recibo - cancela Factura FC-0024', 0, 13500.00),

-- Cliente 9
(9, '2026-01-19', 'FC-0025', 'Factura de venta N. FC-0025', 19000.00, 0),
(9, '2026-01-24', 'RC-0025', 'Recibo - cancela Factura FC-0025', 0, 19000.00),
(9, '2026-03-19', 'FC-0026', 'Factura de venta N. FC-0026', 28500.00, 0),
(9, '2026-03-24', 'RC-0026', 'Recibo - cancela Factura FC-0026', 0, 28500.00),
(9, '2026-05-19', 'FC-0027', 'Factura de venta N. FC-0027', 14250.00, 0),
(9, '2026-05-24', 'RC-0027', 'Recibo - cancela Factura FC-0027', 0, 14250.00),

-- Cliente 10
(10, '2026-02-20', 'FC-0028', 'Factura de venta N. FC-0028', 20000.00, 0),
(10, '2026-02-25', 'RC-0028', 'Recibo - cancela Factura FC-0028', 0, 20000.00),
(10, '2026-04-20', 'FC-0029', 'Factura de venta N. FC-0029', 30000.00, 0),
(10, '2026-04-25', 'RC-0029', 'Recibo - cancela Factura FC-0029', 0, 30000.00),
(10, '2026-06-20', 'FC-0030', 'Factura de venta N. FC-0030', 15000.00, 0),
(10, '2026-06-25', 'RC-0030', 'Recibo - cancela Factura FC-0030', 0, 15000.00);
