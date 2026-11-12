"""Reporte gerencial en Excel (openpyxl): tablas con formato, gráficos nativos y
formato condicional, listo para enviar a negocio sin retoques manuales."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.formatting.rule import CellIsRule, ColorScaleRule, DataBarRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.worksheet.worksheet import Worksheet

from radar_cartera.kpis import KpiBundle
from radar_cartera.quality import QualityReport

TEAL = "0D9488"
NAVY = "0F1F2E"
MONEY = '"$" #,##0'
PCT = "0.0%"
INT = "#,##0"

TITLE = Font(name="Calibri", size=16, bold=True, color=NAVY)
SUBTITLE = Font(name="Calibri", size=10, color="5B6B78")
CARD_LABEL = Font(name="Calibri", size=9, bold=True, color="5B6B78")
CARD_VALUE = Font(name="Calibri", size=16, bold=True, color=NAVY)
CARD_FILL = PatternFill("solid", fgColor="E6F6F4")
THIN = Side(style="thin", color="C9D6DE")

MONTHLY_COLUMNS: dict[str, tuple[str, str]] = {
    "anio_mes": ("Mes", "@"),
    "obligaciones": ("Obligaciones", INT),
    "saldo_total": ("Saldo total", MONEY),
    "saldo_vencido": ("Saldo vencido", MONEY),
    "obligaciones_mora": ("Oblig. en mora", INT),
    "par30": ("PAR30", PCT),
    "par90": ("PAR90", PCT),
    "recaudo": ("Recaudo", MONEY),
    "tasa_recuperacion": ("Tasa de recuperación", PCT),
    "gestiones": ("Gestiones", INT),
    "contactabilidad": ("Contactabilidad", PCT),
    "promesas_evaluables": ("Promesas evaluables", INT),
    "promesas_cumplidas": ("Promesas cumplidas", INT),
    "efectividad_promesas": ("Efectividad promesas", PCT),
}

RANKING_COLUMNS: dict[str, tuple[str, str]] = {
    "ranking": ("#", INT),
    "id_gestor": ("Gestor", "@"),
    "nombre": ("Nombre", "@"),
    "equipo": ("Equipo", "@"),
    "gestiones": ("Gestiones", INT),
    "contactos": ("Contactos", INT),
    "contactabilidad": ("Contactabilidad", PCT),
    "promesas": ("Promesas", INT),
    "promesas_cumplidas": ("Cumplidas", INT),
    "efectividad_promesas": ("Efectividad", PCT),
    "recaudo_promesas": ("Recaudo de promesas", MONEY),
}


def _write_table(
    ws: Worksheet,
    df: pd.DataFrame,
    columns: Mapping[str, tuple[str, str]],
    top: int,
    name: str,
    left: int = 1,
) -> tuple[int, int]:
    """Escribe ``df`` como Tabla de Excel con formatos por columna. Devuelve (fila_ini, fila_fin)."""
    for j, (header, _fmt) in enumerate(columns.values()):
        cell = ws.cell(row=top, column=left + j, value=header)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=NAVY)
        ws.column_dimensions[get_column_letter(left + j)].width = max(12, len(header) + 4)
    for i, row in enumerate(df[list(columns)].itertuples(index=False), start=1):
        for j, (value, (_, fmt)) in enumerate(zip(row, columns.values(), strict=True)):
            cell = ws.cell(row=top + i, column=left + j, value=None if pd.isna(value) else value)
            cell.number_format = fmt
    bottom = top + max(len(df), 1)
    ref = f"{get_column_letter(left)}{top}:{get_column_letter(left + len(columns) - 1)}{bottom}"
    table = Table(displayName=name, ref=ref)
    table.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
    ws.add_table(table)
    return top, bottom


def _header(ws: Worksheet, title: str, subtitle: str) -> None:
    ws["A1"] = title
    ws["A1"].font = TITLE
    ws["A2"] = subtitle
    ws["A2"].font = SUBTITLE
    ws.sheet_view.showGridLines = False


def _summary(wb: Workbook, kpis: KpiBundle, subtitle: str) -> None:
    ws = wb.active
    assert ws is not None
    ws.title = "Resumen"
    _header(ws, f"Cartera y cobranza · corte {kpis.month}", subtitle)
    latest = kpis.latest
    cards = [
        ("Saldo total", latest["saldo_total"], MONEY),
        ("Saldo vencido", latest["saldo_vencido"], MONEY),
        ("PAR30", latest["par30"], PCT),
        ("Recaudo del mes", latest["recaudo"], MONEY),
        ("Tasa de recuperación", latest["tasa_recuperacion"], PCT),
        ("Efectividad de promesas", latest["efectividad_promesas"], PCT),
    ]
    for j, (label, value, fmt) in enumerate(cards):
        col = 1 + j * 2
        ws.merge_cells(start_row=4, start_column=col, end_row=4, end_column=col + 1)
        ws.merge_cells(start_row=5, start_column=col, end_row=5, end_column=col + 1)
        top = ws.cell(row=4, column=col, value=label.upper())
        val = ws.cell(row=5, column=col, value=None if pd.isna(value) else float(value))
        top.font, val.font, val.number_format = CARD_LABEL, CARD_VALUE, fmt
        for cell in (top, val, ws.cell(row=4, column=col + 1), ws.cell(row=5, column=col + 1)):
            cell.fill = CARD_FILL
            cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        top.border = Border(top=Side(style="thick", color=TEAL))
    ws.row_dimensions[5].height = 30

    start, end = _write_table(ws, kpis.monthly, MONTHLY_COLUMNS, top=8, name="KpiMensual")
    ws.freeze_panes = "B9"

    months = Reference(ws, min_col=1, min_row=start + 1, max_row=end)
    bar = BarChart()
    bar.title, bar.y_axis.title, bar.height, bar.width = "Recaudo mensual", "COP", 8, 16
    bar.add_data(Reference(ws, min_col=8, min_row=start, max_row=end), titles_from_data=True)
    bar.set_categories(months)
    bar.y_axis.numFmt = '"$" #,##0,,"M"'
    ws.add_chart(bar, f"A{end + 3}")

    line = LineChart()
    line.title, line.height, line.width = "Indicadores de riesgo y gestión", 8, 16
    for col in (6, 9, 11, 14):  # PAR30, tasa recuperación, contactabilidad, efectividad
        line.add_data(Reference(ws, min_col=col, min_row=start, max_row=end), titles_from_data=True)
    line.set_categories(months)
    line.y_axis.numFmt = "0%"
    ws.add_chart(line, f"I{end + 3}")


def _buckets(wb: Workbook, kpis: KpiBundle, subtitle: str) -> None:
    ws = wb.create_sheet("Franjas de mora")
    _header(ws, "Saldo de capital por franja de mora", subtitle)
    columns = {"anio_mes": ("Mes", "@")} | {
        b: (b, MONEY) for b in kpis.buckets.columns if b != "anio_mes"
    }
    start, end = _write_table(ws, kpis.buckets, columns, top=4, name="Franjas")
    chart = BarChart()
    chart.type, chart.grouping, chart.overlap = "col", "stacked", 100
    chart.title, chart.height, chart.width = "Composición de la cartera", 9, 20
    chart.add_data(
        Reference(ws, min_col=2, max_col=len(columns), min_row=start, max_row=end),
        titles_from_data=True,
    )
    chart.set_categories(Reference(ws, min_col=1, min_row=start + 1, max_row=end))
    chart.y_axis.numFmt = '"$" #,##0,,"M"'
    ws.add_chart(chart, f"A{end + 3}")


def _roll_rates(wb: Workbook, kpis: KpiBundle, subtitle: str) -> None:
    ws = wb.create_sheet("Roll rate")
    _header(ws, f"Matriz de transición de franjas · {kpis.month}", subtitle)
    rates = kpis.roll_rates.reset_index()
    columns = {"origen": ("Origen \\ Destino", "@")} | {
        c: (c, PCT) for c in kpis.roll_rates.columns
    }
    start, end = _write_table(ws, rates, columns, top=4, name="RollRate")
    rng = f"B{start + 1}:{get_column_letter(len(columns))}{end}"
    ws.conditional_formatting.add(
        rng, ColorScaleRule(start_type="num", start_value=0, start_color="FFFFFF",
                            end_type="num", end_value=1, end_color="0D9488"),
    )  # fmt: skip
    counts = kpis.roll_counts.reset_index()
    count_cols = {"origen": ("Obligaciones", "@")} | {c: (c, INT) for c in kpis.roll_counts.columns}
    ws.cell(row=end + 3, column=1, value="Conteo de obligaciones").font = Font(bold=True)
    _write_table(ws, counts, count_cols, top=end + 4, name="RollConteo")
    ws.column_dimensions["A"].width = 20


def _ranking(wb: Workbook, kpis: KpiBundle, subtitle: str) -> None:
    ws = wb.create_sheet("Gestores")
    _header(ws, f"Ranking de gestores · {kpis.month}", subtitle)
    start, end = _write_table(ws, kpis.ranking, RANKING_COLUMNS, top=4, name="Ranking")
    ws.conditional_formatting.add(
        f"K{start + 1}:K{end}",
        DataBarRule(start_type="min", end_type="max", color=TEAL, showValue=True),
    )
    ws.column_dimensions["C"].width = 22


def _products(wb: Workbook, kpis: KpiBundle, subtitle: str) -> None:
    ws = wb.create_sheet("Productos")
    _header(ws, f"Cartera por producto · {kpis.month}", subtitle)
    columns = {
        "producto": ("Producto", "@"),
        "obligaciones": ("Obligaciones", INT),
        "saldo_total": ("Saldo total", MONEY),
        "par30": ("PAR30", PCT),
    }
    _write_table(ws, kpis.by_product, columns, top=4, name="Productos")
    ws.column_dimensions["A"].width = 22


def _quality(wb: Workbook, quality: QualityReport, subtitle: str) -> None:
    ws = wb.create_sheet("Calidad de datos")
    _header(ws, "Reglas de calidad aplicadas en la carga", subtitle)
    frame = quality.to_frame()
    columns = {
        "conjunto": ("Conjunto de datos", "@"),
        "regla": ("Regla", "@"),
        "descripcion": ("Descripción", "@"),
        "severidad": ("Severidad", "@"),
        "revisados": ("Revisados", INT),
        "fallidos": ("Fallidos", INT),
        "cumplimiento": ("Cumplimiento", "0.00%"),
    }
    start, end = _write_table(ws, frame, columns, top=4, name="Calidad")
    ws.conditional_formatting.add(
        f"F{start + 1}:F{end}",
        CellIsRule(operator="greaterThan", formula=["0"], fill=PatternFill("solid", fgColor="FEE2E2"),
                   font=Font(color="991B1B", bold=True)),
    )  # fmt: skip
    ws.column_dimensions["B"].width = 26
    ws.column_dimensions["C"].width = 48

    rejected = quality.rejected_frame().head(5000)
    rs = wb.create_sheet("Rechazados")
    _header(rs, "Registros en cuarentena (máx. 5.000)", subtitle)
    cols = {
        "conjunto": ("Conjunto de datos", "@"),
        "motivo": ("Motivo", "@"),
        "registro": ("Registro", "@"),
    }
    _write_table(rs, rejected, cols, top=4, name="Rechazados")
    rs.column_dimensions["B"].width = 26
    rs.column_dimensions["C"].width = 120


def write_excel(
    kpis: KpiBundle, quality: QualityReport, path: Path, run_id: str, generated: datetime
) -> Path:
    subtitle = f"Generado {generated:%Y-%m-%d %H:%M} · ejecución {run_id} · fuente: radar-cartera"
    wb = Workbook()
    _summary(wb, kpis, subtitle)
    _buckets(wb, kpis, subtitle)
    _roll_rates(wb, kpis, subtitle)
    _ranking(wb, kpis, subtitle)
    _products(wb, kpis, subtitle)
    _quality(wb, quality, subtitle)
    wb.properties.creator = "radar-cartera"
    wb.properties.title = f"Reporte de cartera {kpis.month}"
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
