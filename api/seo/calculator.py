"""Public bond calculator (YTM / duration / price) - high-intent long-tail SEO.

Server-rendered, no DB dependency.
"""

from __future__ import annotations

import json
from datetime import date

from fastapi import Request
from fastapi.responses import HTMLResponse

from api.seo import router
from api.seo._common import _abs, _esc, _fmt_num, _is_bot, _skeleton, _spa_page

# ---------------------------------------------------------------------------
# Public bond calculator (YTM / duration / price) — high-intent long-tail SEO.
# Captures "калькулятор облигаций", "расчет доходности облигации", "duration облигаций".
# Server-rendered, no DB dependency.
# ---------------------------------------------------------------------------


def _calc_ytm(price: float, face: float, coupon: float, freq: int, years: float) -> float | None:
    """Approximate YTM via Newton-Raphson. Returns None if fails."""
    if price <= 0 or face <= 0 or years <= 0 or freq <= 0:
        return None
    # Coupon payment per period
    c = face * coupon / 100.0 / freq
    n = int(years * freq)
    if n <= 0:
        return None
    # Initial guess: current yield
    y = (coupon / 100.0) * (face / price)
    for _ in range(50):
        # Price as function of y
        pv_coupons = 0.0
        for i in range(1, n + 1):
            pv_coupons += c / (1 + y / freq) ** i
        pv_face = face / (1 + y / freq) ** n
        px = pv_coupons + pv_face
        # Derivative dP/dy
        dpx = 0.0
        for i in range(1, n + 1):
            dpx -= i * c / (freq * (1 + y / freq) ** (i + 1))
        dpx -= n * face / (freq * (1 + y / freq) ** (n + 1))
        if dpx == 0:
            break
        diff = px - price
        if abs(diff) < 1e-6:
            return y * 100.0
        y -= diff / dpx
        if y <= -0.99:
            return None
    return y * 100.0 if y > -0.99 else None


def _calc_price(face: float, coupon: float, freq: int, years: float, ytm: float) -> float | None:
    """Clean price from YTM."""
    if face <= 0 or years <= 0 or freq <= 0:
        return None
    c = face * coupon / 100.0 / freq
    n = int(years * freq)
    y = ytm / 100.0
    if y <= -0.99:
        return None
    pv_coupons = 0.0
    for i in range(1, n + 1):
        pv_coupons += c / (1 + y / freq) ** i
    pv_face = face / (1 + y / freq) ** n
    return pv_coupons + pv_face


def _calc_macaulay_duration(
    price: float, face: float, coupon: float, freq: int, years: float
) -> float | None:
    """Macaulay duration in years. Returns None if fails."""
    if price <= 0 or face <= 0 or years <= 0 or freq <= 0:
        return None
    c = face * coupon / 100.0 / freq
    n = int(years * freq)
    if n <= 0:
        return None
    y = None
    # Solve for y using approximate YTM
    ytm = _calc_ytm(price, face, coupon, freq, years)
    if ytm is None:
        return None
    y = ytm / 100.0
    # Weighted average time to cashflows
    num = 0.0
    denom = 0.0
    for i in range(1, n + 1):
        t = i / freq
        pv = c / (1 + y / freq) ** i
        num += t * pv
        denom += pv
    # Face
    t = years
    pv = face / (1 + y / freq) ** n
    num += t * pv
    denom += pv
    if denom == 0:
        return None
    return num / denom


def _calc_modified_duration(
    mac_duration: float | None, ytm: float | None, freq: int
) -> float | None:
    if mac_duration is None or ytm is None or freq <= 0:
        return None
    return mac_duration / (1 + (ytm / 100.0) / freq)


@router.get("/calculator", response_class=HTMLResponse)
async def seo_calculator(request: Request):
    """Bond calculator: YTM from price, or price from YTM, plus duration."""
    if not _is_bot(request):
        spa = _spa_page()
        if spa is not None:
            return spa
    # Parse query params for pre-filled form
    q = request.query_params
    price = q.get("price")
    face = q.get("face", "1000")
    coupon = q.get("coupon")
    freq = q.get("freq", "2")
    maturity = q.get("maturity")  # ISO date or years
    calc_mode = q.get("mode", "ytm")  # "ytm" or "price"

    # Defaults / parsed
    def _f(v, default=None):
        try:
            return float(v)
        except TypeError, ValueError:
            return default

    price_v = _f(price)
    face_v = _f(face, 1000.0)
    coupon_v = _f(coupon)
    freq_v = int(_f(freq, 2) or 2)
    if freq_v <= 0:
        freq_v = 2

    years_v = None
    if maturity:
        try:
            # Try ISO date
            mat_date = date.fromisoformat(maturity)
            years_v = max(0.0, (mat_date - date.today()).days / 365.0)
        except ValueError:
            years_v = _f(maturity)

    # Calculate
    ytm_v = None
    price_calc_v = None
    mac_dur = None
    mod_dur = None
    error = None

    if calc_mode == "ytm":
        if price_v is not None and coupon_v is not None and years_v is not None:
            ytm_v = _calc_ytm(price_v, face_v, coupon_v, freq_v, years_v)
            if ytm_v is not None:
                mac_dur = _calc_macaulay_duration(price_v, face_v, coupon_v, freq_v, years_v)
                mod_dur = _calc_modified_duration(mac_dur, ytm_v, freq_v)
            else:
                error = "Не удалось рассчитать YTM — проверьте ввод."
    else:  # price from YTM
        ytm_in = _f(q.get("ytm"))
        if ytm_in is not None and coupon_v is not None and years_v is not None:
            price_calc_v = _calc_price(face_v, coupon_v, freq_v, years_v, ytm_in)
            if price_calc_v is not None:
                mac_dur = _calc_macaulay_duration(price_calc_v, face_v, coupon_v, freq_v, years_v)
                mod_dur = _calc_modified_duration(mac_dur, ytm_in, freq_v)
            else:
                error = "Не удалось рассчитать цену — проверьте YTM."
        else:
            error = "Для расчёта цены укажите YTM, купон и срок."

    # Build form
    form_html = f"""
    <form method="get" action="/calculator" class="lead-form" style="max-width:600px">
      <label>Режим
        <select name="mode">
          <option value="ytm" {"selected" if calc_mode == "ytm" else ""}>YTM из цены</option>
          <option value="price" {"selected" if calc_mode == "price" else ""}>Цена из YTM</option>
        </select>
      </label>
      <label>Номинал (face value)<input name="face" type="number" step="0.01" value="{_esc(face)}" required></label>
      <label>Купон, % в год<input name="coupon" type="number" step="0.01" value="{_esc(coupon) if coupon else ""}" required></label>
      <label>Частота купонов в год
        <select name="freq">
          <option value="1" {"selected" if freq_v == 1 else ""}>1 (раз в год)</option>
          <option value="2" {"selected" if freq_v == 2 else ""}>2 (полугодие)</option>
          <option value="4" {"selected" if freq_v == 4 else ""}>4 (квартал)</option>
        </select>
      </label>
      <label>Срок до погашения
        <input name="maturity" type="text" placeholder="гггг-мм-дд или годы (напр. 2.5)" value="{_esc(maturity) if maturity else ""}" required>
        <span class="note">Год-месяц-день или дробное число лет</span>
      </label>
      <div id="ytm-fields" style="{"display:none" if calc_mode == "price" else ""}">
        <label>Текущая цена<input name="price" type="number" step="0.01" value="{_esc(price) if price else ""}" required></label>
      </div>
      <div id="price-fields" style="{"display:none" if calc_mode == "ytm" else ""}">
        <label>Ожидаемый YTM, %<input name="ytm" type="number" step="0.01" value="{_esc(q.get("ytm")) if q.get("ytm") else ""}" required></label>
      </div>
      <button class="cta" type="submit">Рассчитать</button>
      <span class="note">Результат — справа. Для глубокого анализа: <a href="/bonds">рейтинг облигаций</a> · <a href="/partners">B2B/API</a></span>
    </form>
    <script>
    // Toggle fields on mode change
    document.querySelector('select[name="mode"]').addEventListener('change', function(e) {{
      document.getElementById('ytm-fields').style.display = e.target.value === 'ytm' ? '' : 'none';
      document.getElementById('price-fields').style.display = e.target.value === 'price' ? '' : 'none';
    }});
    </script>
    """

    # Results card
    result_html = ""
    if ytm_v is not None or price_calc_v is not None:
        result_html = "<div class='card' style='border-color:var(--brand);background:#f0fdf9'><h2 style='margin-top:0'>Результат</h2>"
        if ytm_v is not None:
            result_html += f"<div class='grid'><div class='stat'><div class='k'>YTM (доходность к погашению)</div><div class='v num'>{_fmt_num(ytm_v, 2)}%</div></div>"
            if price_v is not None:
                result_html += f"<div class='stat'><div class='k'>Текущая цена</div><div class='v num'>{_fmt_num(price_v)}</div></div>"
        if price_calc_v is not None:
            result_html += f"<div class='stat'><div class='k'>Чистая цена (расчётная)</div><div class='v num'>{_fmt_num(price_calc_v, 2)}</div></div>"
        if mac_dur is not None:
            result_html += f"<div class='stat'><div class='k'>Модифицированная дюрация</div><div class='v num'>{_fmt_num(mod_dur, 2)}</div></div>"
        if mod_dur is not None:
            result_html += f"<div class='stat'><div class='k'>Дюрация Меколея</div><div class='v num'>{_fmt_num(mac_dur, 2)} лет</div></div>"
        result_html += "</div>"
    elif error:
        result_html = f"<div class='card' style='border-color:var(--red);background:#fef2f2'><p class='alarm'>{_esc(error)}</p></div>"

    body = f"""<h1>Калькулятор облигаций: YTM, цена, дюрация</h1>
<p class="sub">Рассчитайте доходность к погашению (YTM) по текущей цене — или обратную цену по целевому YTM. Дюрация показывает чувствительность к ставкам.</p>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;align-items:start">
  <div>{form_html}</div>
  <div>{result_html if result_html else "<div class='card'><p class='sub'>Заполните форму — результат появится здесь.</p></div>"}</div>
</div>
<p class="note">Гайды: <a href="/guides/kak-vybrat-obligaciyu">Как выбрать облигацию</a> · <a href="/guides/duration-i-repo-prosto">Duration и РЕПО</a> · <a href="/bonds">Рейтинг облигаций</a> · <a href="/partners">Для бизнеса →</a></p>"""

    title = "Калькулятор облигаций: YTM, цена, дюрация | Aigenis Bonds"
    desc = (
        "Бесплатный калькулятор облигаций: YTM из цены, цена из YTM, дюрация Меколея и модифицированная. "
        "Помогает сравнивать облигации и депозиты, оценивать процентный риск."
    )
    json_ld = [
        json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "WebApplication",
                "name": "Калькулятор облигаций Aigenis Bonds",
                "description": desc,
                "url": _abs(request, "/calculator"),
                "applicationCategory": "FinanceApplication",
                "operatingSystem": "Web",
                "offers": {
                    "@type": "Offer",
                    "price": "0",
                    "priceCurrency": "BYN",
                    "availability": "https://schema.org/InStock",
                },
            },
            ensure_ascii=False,
        )
    ]
    return _skeleton(title, desc, body, request, _abs(request, "/calculator"), json_ld)
