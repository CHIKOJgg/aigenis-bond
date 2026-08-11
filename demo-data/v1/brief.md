# Demo Brief — Aigenis Invest Analytics Preview

**Date:** 2026-08-10
**Brand mode:** concept (no Aigenis logos/icons/pixel-perfect design)  
**Primary market:** BCSE (default), MOEX (toggle)

## Data Mode

The running demo uses live read-only data from the Aigenis API integration:

- `GET /api/v1/demo/market-data` — current market universe, YTM, duration and Score;
- `GET /api/v1/demo/search` — live instrument search;
- `GET /api/v1/demo/bond/{internal_id}` — detail, explainability, history and coupon schedule.

The frontend does not fall back to fixtures at runtime. Files under `demo-data/`
remain test fixtures and contract examples only. The demo never creates orders,
payments, alerts or other write-side effects.

## Demo Persona

```
Марина К. · Частный инвестор · Демо-среда
Портфель: 50 000 BYN
Цель: регулярный доход при умеренном риске
```

## Live Instruments

The displayed instruments, Score and yields change with the connected source.
Do not promise a fixed bond name, Score or yield in the pitch. Select a current
high-Score or clearly explainable instrument from the live table.

## Final Action

**Portfolio impact** — показать влияние добавления 5/10/15% выбранной live-бумаги
на портфель Марины К. (`50 000 BYN`).

## Demo Scenario (5 min)

1. **Trading → Analytics** — контекст терминала, переход без внешней вкладки
2. **Filter & sort** — BCSE/MOEX, валюта, срок, статус, сортировка по Score/YTM
3. **Bond detail** — открыть текущую live-бумагу, показать Score, breakdown и explainability
4. **Portfolio impact** — добавить 10% позиции, показать изменение доходности,
   duration, live Score, liquidity и ожидаемый доход в BYN
5. **Pilot pitch** — "Первый пилот: 3 экрана + интеграция с вашим источником данных"

## Branding Rules (concept mode)

- Palette: `--demo-brand-*` CSS variables, primary ~ `#0B526B`
- No Aigenis logo, icons, or pixel-perfect terminal copy
- Disclaimer on every page
- Watermark: "Концепт пилотной интеграции для Aigenis Invest"
