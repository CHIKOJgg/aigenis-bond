"""PDF Report export — generate and serve portfolio/analysis PDF reports."""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from api.access_control import RequireFeature, get_optional_user_id
from api import _helpers as _h
from portfolio.pnl import compute_pnl
from portfolio.positions_repository import list_positions
from portfolio.transactions import list_transactions
from scraper.db import session_scope
from scraper.orm import BondORM

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


def _generate_portfolio_pdf(
    pnl_data: dict,
    positions: list,
    bonds_by_id: dict,
) -> bytes:
    """Generate a simple HTML report that can be saved as PDF via browser."""
    today = date.today().isoformat()
    rows = ""
    for p in pnl_data.get("per_bond", []):
        b = bonds_by_id.get(p["internal_id"])
        name = b.name if b else p["internal_id"]
        pnl_class = "color: #22c55e" if p["total_pnl"] >= 0 else "color: #ef4444"
        rows += f"""
        <tr>
            <td style="padding:8px;border-bottom:1px solid #334155">{name}</td>
            <td style="padding:8px;border-bottom:1px solid #334155;text-align:right">{p['weight']*100:.1f}%</td>
            <td style="padding:8px;border-bottom:1px solid #334155;text-align:right">{p['current_value']:,.2f}</td>
            <td style="padding:8px;border-bottom:1px solid #334155;text-align:right" style="{pnl_class}">{p['total_pnl']:+,.2f}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; background: #0f172a; color: #e2e8f0; padding: 40px; }}
  h1 {{ font-size: 24px; margin-bottom: 4px; }}
  h2 {{ font-size: 16px; color: #94a3b8; font-weight: normal; margin-top: 32px; }}
  .meta {{ color: #64748b; font-size: 12px; margin-bottom: 24px; }}
  .stats {{ display: flex; gap: 16px; margin-bottom: 24px; }}
  .stat {{ background: #1e293b; border-radius: 8px; padding: 12px 16px; min-width: 120px; }}
  .stat-value {{ font-size: 20px; font-weight: bold; }}
  .stat-label {{ font-size: 11px; color: #94a3b8; margin-top: 2px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ text-align: left; padding: 8px; border-bottom: 2px solid #334155; color: #94a3b8; font-size: 11px; text-transform: uppercase; }}
  .footer {{ margin-top: 40px; text-align: center; color: #475569; font-size: 10px; }}
</style></head><body>
<h1>Aigenis Bonds — Отчёт по портфелю</h1>
<div class="meta">Дата: {today} | Автоматически сгенерированный отчёт</div>

<div class="stats">
  <div class="stat">
    <div class="stat-value">{pnl_data.get('total_invested', 0):,.2f}</div>
    <div class="stat-label">Инвестировано</div>
  </div>
  <div class="stat">
    <div class="stat-value">{pnl_data.get('total_value', 0):,.2f}</div>
    <div class="stat-label">Текущая стоимость</div>
  </div>
  <div class="stat">
    <div class="stat-value" style="color: {'#22c55e' if pnl_data.get('total_pnl', 0) >= 0 else '#ef4444'}">
      {pnl_data.get('total_pnl', 0):+,.2f}
    </div>
    <div class="stat-label">P&L</div>
  </div>
  <div class="stat">
    <div class="stat-value">{pnl_data.get('total_return_pct', 0):+.2f}%</div>
    <div class="stat-label">Доходность</div>
  </div>
</div>

<h2>Позиции</h2>
<table>
  <thead><tr><th>Облигация</th><th>Доля</th><th style="text-align:right">Стоимость</th><th style="text-align:right">P&L</th></tr></thead>
  <tbody>{rows}</tbody>
</table>

<div class="footer">
  Aigenis Bonds &copy; {date.today().year} — Данные носят информативный характер и не являются инвестиционной рекомендацией.
</div>
</body></html>"""
    return html.encode("utf-8")


@router.get("/portfolio", dependencies=[Depends(RequireFeature("access_portfolio"))])
async def export_portfolio_report(
    user_id: int | None = Depends(get_optional_user_id),
):
    """Generate an HTML portfolio report for browser print/save as PDF."""
    uid = user_id or 0
    async with session_scope() as session:
        positions = await list_positions(session, uid)
        txs = await list_transactions(session, uid, limit=1000)
        bond_rows = (
            await session.execute(select(BondORM))
        ).scalars().all()

    bonds_by_id = {b.internal_id: _h.orm_to_bond(b) for b in bond_rows}

    pnl = compute_pnl(
        transactions=txs,
        positions=positions,
        bonds_by_id=bonds_by_id,
    )

    html_bytes = _generate_portfolio_pdf(
        pnl_data=pnl.as_dict(),
        positions=positions,
        bonds_by_id=bonds_by_id,
    )

    return StreamingResponse(
        io.BytesIO(html_bytes),
        media_type="text/html",
        headers={
            "Content-Disposition": f'attachment; filename="portfolio_report_{date.today().isoformat()}.html"',
        },
    )
