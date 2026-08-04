import { useState, useEffect, useCallback } from "react";
import { api } from "./lib/api";
import type { Bond, BondScore } from "./lib/api";

interface AigenisBondAnalyzerProps {
  /** Запускать в режиме виджета (iframe) или полностранично */
  embed?: boolean;
  /** Initially selected currency */
  defaultCurrency?: string;
}

const CURRENCIES = ["ALL", "USD", "RUB", "BYN", "EUR", "XAU", "XAG", "XPT"];
const CURRENCY_LABELS: Record<string, string> = {
  ALL: "Все",
  USD: "USD",
  RUB: "RUB",
  BYN: "BYN",
  EUR: "EUR",
  XAU: "Золото",
  XAG: "Серебро",
  XPT: "Платина",
};

type SortKey = "score" | "ytm" | "maturity" | "name";

interface BondWithScore extends Bond {
  scoreData?: BondScore;
}

function tierColorClass(tier: string | null | undefined): string {
  switch (tier) {
    case "S": return "aigenis-tier-S";
    case "A": return "aigenis-tier-A";
    case "B": return "aigenis-tier-B";
    case "C": return "aigenis-tier-C";
    case "D": return "aigenis-tier-D";
    default: return "aigenis-tier-B";
  }
}

function verdictClass(tier: string | null | undefined): string {
  switch (tier) {
    case "S": return "aigenis-verdict-strong";
    case "A": return "aigenis-verdict-good";
    case "B": return "aigenis-verdict-moderate";
    case "C": return "aigenis-verdict-moderate";
    default: return "aigenis-verdict-weak";
  }
}

function verdictText(tier: string | null | undefined): string {
  switch (tier) {
    case "S": return "Исключительная возможность";
    case "A": return "Хорошая возможность";
    case "B": return "Умеренно интересна";
    case "C": return "Средняя";
    case "D": return "Слабая / избегать";
    default: return "";
  }
}

function formatPercent(v: number | null | undefined): string {
  if (v == null) return "—";
  return v.toFixed(2) + "%";
}

function formatDate(d: string | null | undefined): string {
  if (!d) return "—";
  try {
    return new Date(d).toLocaleDateString("ru-RU", { day: "2-digit", month: "short", year: "numeric" });
  } catch {
    return d;
  }
}

function daysUntil(d: string | null | undefined): number | null {
  if (!d) return null;
  try {
    return Math.ceil((new Date(d).getTime() - Date.now()) / 86400000);
  } catch {
    return null;
  }
}

export default function AigenisBondAnalyzer({ embed = false, defaultCurrency = "ALL" }: AigenisBondAnalyzerProps) {
  const [bonds, setBonds] = useState<BondWithScore[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currency, setCurrency] = useState(defaultCurrency);
  const [sortBy, setSortBy] = useState<SortKey>("score");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [selectedBond, setSelectedBond] = useState<BondWithScore | null>(null);
  const PAGE_SIZE = 25;

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string> = {};
      if (currency !== "ALL") params.currency = currency;
      const bondList = await api.bonds.list(params);
      const ids = bondList.map((b: Bond) => b.internal_id);
      const scoreMap: Record<string, BondScore> = {};
      try {
        const scores = await api.bonds.scores();
        for (const s of scores) {
          scoreMap[s.internal_id] = s;
        }
      } catch {
        // scores not available — show bonds without scores
      }
      const merged: BondWithScore[] = bondList.map((b: Bond) => ({
        ...b,
        scoreData: scoreMap[b.internal_id],
      }));
      setBonds(merged);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Ошибка загрузки");
    } finally {
      setLoading(false);
    }
  }, [currency]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const sorted = [...bonds]
    .filter(b => {
      if (!search) return true;
      const q = search.toLowerCase();
      return (
        (b.name && b.name.toLowerCase().includes(q)) ||
        b.internal_id.toLowerCase().includes(q) ||
        (b.issuer && b.issuer.toLowerCase().includes(q))
      );
    })
    .sort((a, b) => {
      const getVal = (bond: BondWithScore): number => {
        switch (sortBy) {
          case "score": return bond.scoreData?.score ?? -999;
          case "ytm": return Number(bond.yield_to_maturity ?? -999);
          case "maturity": return bond.maturity_date ? new Date(bond.maturity_date).getTime() : 0;
          case "name": return (bond.name || bond.internal_id).charCodeAt(0);
          default: return 0;
        }
      };
      const diff = getVal(b) - getVal(a);
      return sortDir === "desc" ? diff : -diff;
    });

  const totalPages = Math.ceil(sorted.length / PAGE_SIZE);
  const paged = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const toggleSort = (key: SortKey) => {
    if (sortBy === key) {
      setSortDir(d => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortBy(key);
      setSortDir("desc");
    }
  };

  const sortIcon = (key: SortKey) => {
    if (sortBy !== key) return " ↕";
    return sortDir === "desc" ? " ↓" : " ↑";
  };

  const currencyCounts = CURRENCIES.reduce((acc, cur) => {
    if (cur === "ALL") return acc;
    acc[cur] = bonds.filter(b => b.currency?.toUpperCase() === cur).length;
    return acc;
  }, {} as Record<string, number>);
  const totalCount = bonds.length;

  return (
    <div className="aigenis-bond-analyzer" style={{ maxWidth: 1200, margin: "0 auto", padding: embed ? 12 : "16px 24px" }}>
      {/* Заголовок */}
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 24 }}>
        <h2 style={{ fontSize: 22, fontWeight: 700, color: "var(--aigenis-tx-primary)", margin: 0 }}>
          Аналитика облигаций
        </h2>
        <span style={{ fontSize: 14, color: "var(--aigenis-tx-secondary)" }}>
          {totalCount} выпусков · Reward/Risk Score
        </span>
      </div>

      {/* Тулбар */}
      <div style={{
        display: "flex", gap: 8, marginBottom: 20, flexWrap: "wrap",
        padding: 12, background: "var(--aigenis-bg-secondary)",
        borderRadius: "var(--aigenis-radius-lg)",
      }}>
        <input
          className="aigenis-input"
          type="text"
          placeholder="Поиск по названию, ISIN, эмитенту..."
          value={search}
          onChange={e => { setSearch(e.target.value); setPage(0); }}
          style={{ flex: 1, minWidth: 200 }}
        />
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
          {CURRENCIES.map(cur => (
            <button
              key={cur}
              className={`aigenis-btn ${cur === currency ? "aigenis-btn-primary" : "aigenis-btn-outline"}`}
              onClick={() => { setCurrency(cur); setPage(0); }}
              style={{ fontSize: 12, height: 32, padding: "0 12px" }}
            >
              {CURRENCY_LABELS[cur]}
              {cur !== "ALL" && <span style={{ opacity: .6, marginLeft: 4 }}>{currencyCounts[cur] ?? 0}</span>}
            </button>
          ))}
        </div>
      </div>

      {/* Ошибка */}
      {error && (
        <div style={{
          padding: "12px 16px", marginBottom: 16, borderRadius: "var(--aigenis-radius-sm)",
          background: "var(--aigenis-error-50)", color: "var(--aigenis-error-600)",
          border: "1px solid #ffb199", fontSize: 14,
        }}>
          {error}
          <button className="aigenis-btn aigenis-btn-outline" onClick={fetchData}
            style={{ marginLeft: 12, height: 28, fontSize: 12 }}>
            Повторить
          </button>
        </div>
      )}

      {/* Загрузка */}
      {loading && (
        <div style={{ textAlign: "center", padding: 60, color: "var(--aigenis-tx-secondary)" }}>
          <div style={{
            width: 36, height: 36, border: "3px solid var(--aigenis-border-tertiary)",
            borderTopColor: "var(--aigenis-brand-500)", borderRadius: "50%",
            animation: "aigenis-spin .8s linear infinite", margin: "0 auto 12px",
          }} />
          Загрузка данных...
          <style>{`@keyframes aigenis-spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      )}

      {/* Таблица */}
      {!loading && !error && (
        <>
          <div style={{ overflowX: "auto" }}>
            <table className="aigenis-table">
              <thead>
                <tr>
                  <th style={{ cursor: "pointer", userSelect: "none" }} onClick={() => toggleSort("name")}>
                    Облигация{sortIcon("name")}
                  </th>
                  <th style={{ cursor: "pointer" }} onClick={() => toggleSort("score")}>
                    Скор{sortIcon("score")}
                  </th>
                  <th style={{ cursor: "pointer" }} onClick={() => toggleSort("ytm")}>
                    Доходность{sortIcon("ytm")}
                  </th>
                  <th>Купон</th>
                  <th>Валюта</th>
                  <th style={{ cursor: "pointer" }} onClick={() => toggleSort("maturity")}>
                    Погашение{sortIcon("maturity")}
                  </th>
                  <th>Дней</th>
                </tr>
              </thead>
              <tbody>
                {paged.map(bond => {
                  const score = bond.scoreData;
                  const days = daysUntil(bond.maturity_date);
                  return (
                    <tr
                      key={bond.internal_id}
                      onClick={() => setSelectedBond(bond)}
                      style={{ cursor: "pointer" }}
                    >
                      <td>
                        <div style={{ fontWeight: 600, fontSize: 13 }}>
                          {bond.name || bond.internal_id}
                        </div>
                        <div style={{ fontSize: 11, color: "var(--aigenis-tx-secondary)", fontFamily: "monospace" }}>
                          {bond.issuer || bond.internal_id}
                        </div>
                      </td>
                      <td>
                        {score ? (
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <span className={`aigenis-tier-badge ${tierColorClass(score.tier)}`}>
                              {score.tier || "—"}
                            </span>
                            <span className="aigenis-metric" style={{ fontSize: 15 }}>
                              {score.score.toFixed(1)}
                            </span>
                          </div>
                        ) : (
                          <span style={{ color: "var(--aigenis-tx-disabled)" }}>—</span>
                        )}
                      </td>
                      <td>
                        <span className="aigenis-metric" style={{
                          color: Number(bond.yield_to_maturity ?? 0) >= 10
                            ? "var(--aigenis-success-600)"
                            : Number(bond.yield_to_maturity ?? 0) >= 5
                              ? "var(--aigenis-tx-primary)"
                              : "var(--aigenis-tx-secondary)",
                        }}>
                          {formatPercent(Number(bond.yield_to_maturity))}
                        </span>
                      </td>
                      <td className="aigenis-metric">{formatPercent(Number(bond.coupon_rate))}</td>
                      <td>
                        <span style={{
                          display: "inline-block", padding: "2px 8px", borderRadius: "var(--aigenis-radius-xs)",
                          background: "var(--aigenis-bg-active)", fontSize: 12, fontWeight: 600,
                        }}>
                          {bond.currency || "—"}
                        </span>
                      </td>
                      <td style={{ fontSize: 13 }}>{formatDate(bond.maturity_date)}</td>
                      <td style={{ fontSize: 12, color: days != null && days < 365
                        ? "var(--aigenis-warning-500)" : "var(--aigenis-tx-secondary)" }}>
                        {days != null ? `${days} дн` : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {sorted.length === 0 && !loading && (
            <div style={{ textAlign: "center", padding: 60, color: "var(--aigenis-tx-secondary)", fontSize: 15 }}>
              Облигаций не найдено по заданным фильтрам
            </div>
          )}

          {/* Пагинация */}
          {totalPages > 1 && (
            <div style={{
              display: "flex", justifyContent: "center", alignItems: "center",
              gap: 8, marginTop: 20,
            }}>
              <button className="aigenis-btn aigenis-btn-outline"
                disabled={page === 0} onClick={() => setPage(p => p - 1)}>
                ← Назад
              </button>
              <span style={{ fontSize: 13, color: "var(--aigenis-tx-secondary)" }}>
                {page + 1} / {totalPages}
              </span>
              <button className="aigenis-btn aigenis-btn-outline"
                disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}>
                Вперёд →
              </button>
            </div>
          )}
        </>
      )}

      {/* Детальная карточка облигации */}
      {selectedBond && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(0,29,37,.4)",
          display: "flex", alignItems: "center", justifyContent: "center",
          zIndex: 1000, padding: 16,
        }} onClick={() => setSelectedBond(null)}>
          <div style={{
            background: "var(--aigenis-bg-primary)", borderRadius: "var(--aigenis-radius-xl)",
            maxWidth: 640, width: "100%", maxHeight: "90vh", overflow: "auto",
            boxShadow: "var(--aigenis-shadow-2xl)",
          }} onClick={e => e.stopPropagation()}>
            {/* Шапка */}
            <div style={{
              padding: "24px 24px 16px", borderBottom: "1px solid var(--aigenis-border-tertiary)",
              display: "flex", justifyContent: "space-between", alignItems: "start",
            }}>
              <div>
                <h3 style={{ fontSize: 20, fontWeight: 700, margin: "0 0 4px" }}>
                  {selectedBond.name || selectedBond.internal_id}
                </h3>
                <div style={{ fontSize: 13, color: "var(--aigenis-tx-secondary)", fontFamily: "monospace" }}>
                  {selectedBond.internal_id}
                  {selectedBond.issuer && ` · ${selectedBond.issuer}`}
                </div>
              </div>
              <button className="aigenis-btn aigenis-btn-outline"
                style={{ height: 32, width: 32, padding: 0, minWidth: 32 }}
                onClick={() => setSelectedBond(null)}>
                ✕
              </button>
            </div>

            {/* Скор и вердикт */}
            {selectedBond.scoreData && (
              <div style={{
                margin: 16, padding: 20, borderRadius: "var(--aigenis-radius-lg)",
                background: "var(--aigenis-bg-secondary)",
                border: "1px solid var(--aigenis-border-tertiary)",
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
                  <span className={`aigenis-tier-badge ${tierColorClass(selectedBond.scoreData.tier)}`}
                    style={{ minWidth: 48, height: 36, fontSize: 20 }}>
                    {selectedBond.scoreData.tier || "—"}
                  </span>
                  <div>
                    <div className={`aigenis-verdict ${verdictClass(selectedBond.scoreData.tier)}`}>
                      {verdictText(selectedBond.scoreData.tier)}
                    </div>
                    <div style={{ fontSize: 13, color: "var(--aigenis-tx-secondary)" }}>
                      Reward/Risk Score: <strong>{selectedBond.scoreData.score.toFixed(1)}</strong> из 100
                    </div>
                  </div>
                </div>

                {/* Факторы */}
                {selectedBond.scoreData.breakdown && (
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 16px" }}>
                    {[
                      ["Доходность", selectedBond.scoreData.breakdown.yield_component],
                      ["Валюта", selectedBond.scoreData.breakdown.currency_component],
                      ["Дюрация", selectedBond.scoreData.breakdown.duration_component],
                      ["Ликвидность", selectedBond.scoreData.breakdown.liquidity_component],
                      ["Кредитный риск", selectedBond.scoreData.breakdown.credit_risk_component],
                      ["Инфляция", selectedBond.scoreData.breakdown.inflation_component],
                      ["Купон", selectedBond.scoreData.breakdown.coupon_component],
                      ["Волатильность", selectedBond.scoreData.breakdown.volatility_component],
                      ["Драгметалл", selectedBond.scoreData.breakdown.metal_component ?? 0],
                    ].map(([label, val]) => {
                      const v = Number(val ?? 0);
                      return (
                        <div key={label} className="aigenis-factor"
                          style={{ display: "flex", justifyContent: "space-between" }}>
                          <span>{label}</span>
                          <span className={
                            v > 0 ? "aigenis-factor-positive"
                              : v < 0 ? "aigenis-factor-negative"
                                : "aigenis-factor-neutral"
                          }>
                            {v > 0 ? "+" : ""}{v.toFixed(1)}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {/* Метрики */}
            <div style={{ padding: "0 24px 24px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px 24px" }}>
              <MetricRow label="Валюта" value={selectedBond.currency} />
              <MetricRow label="Статус" value={selectedBond.status} />
              <MetricRow label="Доходность" value={formatPercent(Number(selectedBond.yield_to_maturity))} />
              <MetricRow label="Купон" value={formatPercent(Number(selectedBond.coupon_rate))} />
              <MetricRow label="Периодичность" value={selectedBond.coupon_frequency
                ? `раз в ${12 / selectedBond.coupon_frequency} мес` : "—"} />
              <MetricRow label="Цена" value={selectedBond.price != null
                ? Number(selectedBond.price).toFixed(2) : "—"} />
              <MetricRow label="Номинал" value={selectedBond.nominal != null
                ? Number(selectedBond.nominal).toFixed(2) : "—"} />
              <MetricRow label="Погашение" value={formatDate(selectedBond.maturity_date)} />
              {selectedBond.issuer && (
                <MetricRow label="Эмитент" value={selectedBond.issuer} fullWidth />
              )}
            </div>

            {/* Дисклеймер */}
            <div style={{
              margin: "0 24px 24px", padding: 12, borderRadius: "var(--aigenis-radius-sm)",
              background: "var(--aigenis-warning-50)", fontSize: 11,
              color: "var(--aigenis-tx-secondary)", lineHeight: 1.5,
            }}>
              Данная информация носит справочно-аналитический характер и НЕ является
              индивидуальной инвестиционной рекомендацией. Оценки не гарантируют доходности.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function MetricRow({ label, value, fullWidth }: { label: string; value: string | null | undefined; fullWidth?: boolean }) {
  return (
    <div style={fullWidth ? { gridColumn: "1 / -1" } : {}}>
      <div style={{ fontSize: 11, color: "var(--aigenis-tx-secondary)", textTransform: "uppercase", marginBottom: 2 }}>
        {label}
      </div>
      <div style={{ fontSize: 14, fontWeight: 500, color: "var(--aigenis-tx-primary)" }}>
        {value || "—"}
      </div>
    </div>
  );
}
