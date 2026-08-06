# Demo Brief — Aigenis Invest Analytics Preview

**Date:** 2026-08-06  
**Brand mode:** concept (no Aigenis logos/icons/pixel-perfect design)  
**Primary market:** BCSE (default), MOEX (toggle)

## Demo Persona

```
Марина К. · Частный инвестор · Демо-среда
Портфель: 50 000 BYN
Цель: регулярный доход при умеренном риске
```

## Demo Bonds (3 pieces)

| # | ID | Name | Market | Currency | YTM | Score | Status |
|---|----|------|--------|----------|-----|-------|--------|
| 1 | `demo-bond-001` | Облигации Минфина РБ 2028 | BCSE | BYN | 14.2% | 84 | attractive |
| 2 | `demo-bond-002` | Газпром нефть 2029 | BCSE | BYN | 12.0% | 62 | neutral |
| 3 | `demo-bond-003` | ОФЗ-ПД 2030 | MOEX | RUB | 10.5% | 48 | review |

## Final Action

**Portfolio impact** — показать влияние добавления demo-bond-001 (10%) на портфель Марины К.

## Demo Scenario (5 min)

1. **Trading → Analytics** — контекст терминала, переход без внешней вкладки
2. **Filter & sort** — BCSE, срок 1-3 года, сортировка по Score
3. **Bond detail** — открыть demo-bond-001, показать explainability
4. **Portfolio impact** — добавить 10% позиции, показать изменение
5. **Pilot pitch** — "Первый пилот: 3 экрана + интеграция с вашим источником данных"

## Branding Rules (concept mode)

- Palette: `--demo-brand-*` CSS variables, primary ~ `#0B526B`
- No Aigenis logo, icons, or pixel-perfect terminal copy
- Disclaimer on every page
- Watermark: "Концепт пилотной интеграции для Aigenis Invest"
