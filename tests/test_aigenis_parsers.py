"""Tests for scraper/sources/aigenis/parsers/* and the JSON api parsers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from bs4 import BeautifulSoup

from scraper.errors import ParseError
from scraper.sources.aigenis.api import (
    _coerce_date,
    _first_not_none,
    parse_bond_payload,
    parse_history_items,
    parse_listing_items,
)
from scraper.sources.aigenis.parsers.detail import (
    _coerce,
    _find_label,
    _id_matches,
    _parse_dom,
    _try_json_state,
    parse_detail_html,
)
from scraper.sources.aigenis.parsers.detail import (
    _parse_coupon_frequency_from_description as detail_freq,
)
from scraper.sources.aigenis.parsers.detail import (
    _parse_coupon_rate_from_description as detail_rate,
)
from scraper.sources.aigenis.parsers.detail import (
    _parse_coupon_schedule as detail_schedule,
)
from scraper.sources.aigenis.parsers.history import (
    _parse_table,
    _try_state,
    parse_history_html,
)
from scraper.sources.aigenis.parsers.listing import (
    _parse_aigenis_bond_block,
    _parse_coupon_frequency_from_description,
    _parse_coupon_rate_from_description,
    _parse_coupon_schedule,
    _parse_guarantor,
    _try_aigenis_by_blocks,
    _try_jsonld,
    _try_next_data,
    _try_table,
    parse_listing_html,
)

CURRENCIES = ("USD", "BYN", "EUR", "RUB", "XAU", "XAG", "XPT")


# ---------------------------------------------------------------- listing ---


class TestTryJsonLd:
    def test_graph(self):
        soup = BeautifulSoup(
            '<script type="application/ld+json">{"@graph": [{"a": 1}, "x"]}</script>',
            "lxml",
        )
        assert _try_jsonld(soup) == [{"a": 1}]

    def test_list(self):
        soup = BeautifulSoup('<script type="application/ld+json">[{"a": 1}, []]</script>', "lxml")
        assert _try_jsonld(soup) == [{"a": 1}]

    def test_invalid_json_skipped(self):
        soup = BeautifulSoup('<script type="application/ld+json">{not json}</script>', "lxml")
        assert _try_jsonld(soup) is None

    def test_no_scripts(self):
        assert _try_jsonld(BeautifulSoup("<html></html>", "lxml")) is None


class TestTryNextData:
    def _soup(self, props):
        import json

        return BeautifulSoup(
            f'<script id="__NEXT_DATA__">{json.dumps({"props": {"pageProps": props}})}</script>',
            "lxml",
        )

    def test_bonds_list(self):
        assert _try_next_data(self._soup({"bonds": [{"x": 1}, 5]})) == [{"x": 1}]

    def test_items_list(self):
        assert _try_next_data(self._soup({"items": [{"x": 2}]})) == [{"x": 2}]

    def test_data_dict_with_items(self):
        assert _try_next_data(self._soup({"data": {"items": [{"x": 3}]}})) == [{"x": 3}]

    def test_invalid_json(self):
        soup = BeautifulSoup('<script id="__NEXT_DATA__">{bad}</script>', "lxml")
        assert _try_next_data(soup) is None

    def test_no_tag(self):
        assert _try_next_data(BeautifulSoup("<html></html>", "lxml")) is None

    def test_no_candidates(self):
        assert _try_next_data(self._soup({"other": 1})) is None


class TestTryTable:
    def test_rows_with_links(self):
        soup = BeautifulSoup(
            """
            <table class="bonds">
              <tbody>
                <tr><td><a href="/bonds/OP-51">Айгенис 51</a></td></tr>
                <tr><td><a href="/bonds/op-52"></a></td></tr>
              </tbody>
            </table>
            """,
            "lxml",
        )
        out = _try_table(soup, "byn")
        assert out == [
            {"internal_id": "OP-51", "name": "Айгенис 51", "currency": "BYN", "isin": None},
            {"internal_id": "op-52", "name": "op-52", "currency": "BYN", "isin": None},
        ]

    def test_rows_without_links_skipped(self):
        soup = BeautifulSoup(
            '<table class="bonds"><tbody><tr><td>no link</td></tr></tbody></table>', "lxml"
        )
        assert _try_table(soup, "usd") == []

    def test_bad_href_skipped(self):
        soup = BeautifulSoup('<div class="bond-row"><a href="/prices/1">x</a></div>', "lxml")
        assert _try_table(soup, "usd") == []

    def test_href_without_id_skipped(self):
        soup = BeautifulSoup('<div class="bond-row"><a href="/bonds/">x</a></div>', "lxml")
        assert _try_table(soup, "usd") == []


class TestCouponHelpers:
    def test_rate_from_description(self):
        assert _parse_coupon_rate_from_description("7% годовых, 1 раз в квартал") == "7"
        assert _parse_coupon_rate_from_description("ставка 12,5%") == "12.5"
        assert _parse_coupon_rate_from_description("без процентов") is None

    def test_frequency_from_description(self):
        assert _parse_coupon_frequency_from_description("1 раз в месяц") == 12
        assert _parse_coupon_frequency_from_description("1 раз в квартал") == 4
        assert _parse_coupon_frequency_from_description("2 раза в год") == 2
        assert _parse_coupon_frequency_from_description("3 раза в год") == 3
        assert _parse_coupon_frequency_from_description("7% годовых, 1 раз в квартал") == 4
        assert _parse_coupon_frequency_from_description("1 раз в 3 месяца") == 4
        assert _parse_coupon_frequency_from_description("1 раз в 6 месяцев") == 2
        assert _parse_coupon_frequency_from_description("неизвестно") is None
        assert _parse_coupon_frequency_from_description("выплата ежемесячно") is None


class TestCouponSchedule:
    def test_schedule_parsed(self):
        soup = BeautifulSoup(
            "<div><p class='bounds-years'>2026\n15.01.2026, 15.07.2026\n2027\n15.01.2027</p></div>",
            "lxml",
        )
        assert _parse_coupon_schedule(soup) == {
            "2026": ["15.01.2026", "15.07.2026"],
            "2027": ["15.01.2027"],
        }

    def test_schedule_without_dates_returns_none(self):
        soup = BeautifulSoup(
            "<div><p class='bounds-years'>Организация: Айгенис\n15.01.2026</p></div>",
            "lxml",
        )
        assert _parse_coupon_schedule(soup) is None

    def test_guarantor_in_bounds_years(self):
        soup = BeautifulSoup(
            "<div><p class='bounds-years'>Организация: ООО Гарант\n2026\n15.01.2026</p></div>",
            "lxml",
        )
        assert _parse_guarantor(soup) == "ООО Гарант"

    def test_none_input(self):
        assert _parse_coupon_schedule(None) is None

    def test_missing_p(self):
        assert _parse_coupon_schedule(BeautifulSoup("<div>no</div>", "lxml")) is None

    def test_no_dates_returns_none(self):
        soup = BeautifulSoup("<div><p class='bounds-years'>просто текст</p></div>", "lxml")
        assert _parse_coupon_schedule(soup) is None

    def test_empty_tokens_skipped(self):
        soup = BeautifulSoup(
            "<div><p class='bounds-years'>2026\n\n\n15.01.2026</p></div>",
            "lxml",
        )
        assert _parse_coupon_schedule(soup) == {"2026": ["15.01.2026"]}

    def test_whitespace_token_skipped(self):
        soup = BeautifulSoup(
            "<div><p class='bounds-years'>2026\n \n15.01.2026</p></div>",
            "lxml",
        )
        assert _parse_coupon_schedule(soup) == {"2026": ["15.01.2026"]}


class TestGuarantor:
    def test_found(self):
        soup = BeautifulSoup("<div><p class='bounds-years'>Организация: Айгенис</p></div>", "lxml")
        assert _parse_guarantor(soup) == "Айгенис"

    def test_not_found(self):
        assert _parse_guarantor(None) is None
        soup = BeautifulSoup("<div><p>нет гаранта</p></div>", "lxml")
        assert _parse_guarantor(soup) is None


def _block_html(**overrides):
    attrs = {
        "data-curency": "BYN",
        "data-eterm": "31.12.2030",
        "data-vterm": "5 лет",
        "data-stock": "true",
        "data-code": "Айгенис 51 выпуск",
        "data-reg": "OP-51",
    }
    attrs.update(overrides)
    parts = " ".join(f'{k}="{v}"' for k, v in attrs.items())
    return f"""
    <div class="wp-block-aigenis-bounds" {parts}>
      <summary>
        <div class="display-column">
          <span class="title">Доходность</span>
          <span class="text">7,5%</span>
        </div>
        <div class="display-column">
          <span class="title">Другое</span>
          <span class="text">—</span>
        </div>
      </summary>
      <div class="content">
        <div class="col-md-4">
          <h4>Основное</h4>
          <h5>Регистрационный номер</h5><p>OP-51</p>
          <h5>Номинал</h5><p>1 000,00</p>
          <h5>Объем</h5><p>10 000 000</p>
          <h5>Способ выплат</h5><p>7% годовых, 1 раз в квартал</p>
          <h5>Эмитент</h5><p>Айгенис</p>
        </div>
        <div class="col-md-4">
          <h4>Ставка купона</h4>
          <p>12,5% годовых, 2 раза в год</p>
        </div>
        <div class="col-md-4">
          <h4>График купона</h4>
          <p class='bounds-years'>2026
            15.01.2026, 15.07.2026
            2027
            15.01.2027
          </p>
          <p class='bounds-footer'>Организация: Гарант</p>
        </div>
      </div>
    </div>
    """


class TestParseBondBlock:
    def test_full_block(self):
        block = BeautifulSoup(_block_html(), "lxml").select_one(".wp-block-aigenis-bounds")
        p = _parse_aigenis_bond_block(block, "ALL")
        assert p["internal_id"] == "OP-51"
        assert p["name"] == "Айгенис 51 выпуск"
        assert p["currency"] == "BYN"
        assert p["registration_number"] == "OP-51"
        assert p["issue_number"] == 51
        assert p["in_stock"] is True
        assert p["end_date"] == "31.12.2030"
        assert p["maturity_term_text"] == "5 лет"
        assert p["coupon_rate"] == "12.5"
        assert p["coupon_description"] == "12,5% годовых, 2 раза в год"
        assert p["coupon_frequency"] == 2
        assert p["nominal"] == "1000.00"
        assert p["issue_volume"] == "10000000"
        assert p["income_method"] == "7% годовых, 1 раз в квартал"
        assert p["issuer"] == "Айгенис"
        assert p["coupon_schedule"] == {
            "2026": ["15.01.2026", "15.07.2026"],
            "2027": ["15.01.2027"],
        }
        assert p["guarantor"] == "Гарант"

    def test_no_currency_returns_none(self):
        block = BeautifulSoup(_block_html(**{"data-curency": ""}), "lxml").select_one(
            ".wp-block-aigenis-bounds"
        )
        assert _parse_aigenis_bond_block(block, "ALL") is None

    def test_currency_filter_mismatch(self):
        block = BeautifulSoup(_block_html(), "lxml").select_one(".wp-block-aigenis-bounds")
        assert _parse_aigenis_bond_block(block, "USD") is None

    def test_in_stock_false_and_missing(self):
        block = BeautifulSoup(_block_html(**{"data-stock": "false"}), "lxml").select_one(
            ".wp-block-aigenis-bounds"
        )
        assert _parse_aigenis_bond_block(block, "ALL")["in_stock"] is False
        block2 = BeautifulSoup(_block_html(**{"data-stock": ""}), "lxml").select_one(
            ".wp-block-aigenis-bounds"
        )
        assert _parse_aigenis_bond_block(block2, "ALL")["in_stock"] is None

    def test_coupon_rate_from_income_method(self):
        html = _block_html()
        html = html.replace(
            """<div class="display-column">
          <span class="title">Доходность</span>
          <span class="text">7,5%</span>
        </div>
        """,
            "",
        )
        html = html.replace("<p>12,5% годовых, 2 раза в год</p>", "<p>просто текст</p>")
        block = BeautifulSoup(html, "lxml").select_one(".wp-block-aigenis-bounds")
        p = _parse_aigenis_bond_block(block, "ALL")
        assert p["coupon_rate"] == "7"
        assert p["coupon_frequency"] == 4
        assert p["income_method"] == "7% годовых, 1 раз в квартал"
        assert p["coupon_description"] == "просто текст"

    def test_zero_yield_column_is_not_coupon_rate(self):
        # «Доходность» в шапке — это доходность, а не ставка купона. 0,00%
        # неторгуемой бумаги не превращает её в «нулевой купон» и не блокирует
        # реальную ставку из описания «Способ выплат».
        html = _block_html()
        html = html.replace(
            '<span class="text">7,5%</span>',
            '<span class="text">0,00%</span>',
        )
        html = html.replace("<p>12,5% годовых, 2 раза в год</p>", "<p>—</p>")
        block = BeautifulSoup(html, "lxml").select_one(".wp-block-aigenis-bounds")
        p = _parse_aigenis_bond_block(block, "ALL")
        assert p["coupon_rate"] == "7"
        assert p["coupon_frequency"] == 4

    def test_positive_yield_column_kept_when_no_coupon_section(self):
        # Положительная доходность из шапки по-прежнему используется как
        # coupon_rate, если секция «Ставка купона» не отдала значение.
        html = _block_html()
        html = html.replace("<p>12,5% годовых, 2 раза в год</p>", "<p>—</p>")
        block = BeautifulSoup(html, "lxml").select_one(".wp-block-aigenis-bounds")
        p = _parse_aigenis_bond_block(block, "ALL")
        assert p["coupon_rate"] == "7.5"

    def test_internal_id_filled_from_content(self):
        block = BeautifulSoup(
            _block_html(**{"data-code": "Айгенис 51", "data-reg": ""}), "lxml"
        ).select_one(".wp-block-aigenis-bounds")
        p = _parse_aigenis_bond_block(block, "ALL")
        assert p["internal_id"] == "OP-51"
        assert p["registration_number"] == "OP-51"

    def test_summary_column_without_spans(self):
        html = _block_html().replace(
            """<div class="display-column">
          <span class="title">Другое</span>
          <span class="text">—</span>
        </div>""",
            """<div class="display-column">без спанов</div>""",
        )
        block = BeautifulSoup(html, "lxml").select_one(".wp-block-aigenis-bounds")
        p = _parse_aigenis_bond_block(block, "ALL")
        assert p["coupon_rate"] == "12.5"

    def test_content_row_without_h4(self):
        html = _block_html().replace(
            "<h4>Ставка купона</h4>",
            "<div class='col-md-4'>без заголовка</div>",
        )
        block = BeautifulSoup(html, "lxml").select_one(".wp-block-aigenis-bounds")
        p = _parse_aigenis_bond_block(block, "ALL")
        assert p["coupon_rate"] == "7.5"

    def test_guarantor_from_bounds_years(self):
        html = _block_html().replace(
            "<p class='bounds-years'>2026",
            "<p class='bounds-years'>Организация: ООО Гарант\n2026",
        )
        block = BeautifulSoup(html, "lxml").select_one(".wp-block-aigenis-bounds")
        p = _parse_aigenis_bond_block(block, "ALL")
        assert p["guarantor"] == "ООО Гарант"

    def test_footer_guarantor(self):
        html = _block_html().replace(
            "<p class='bounds-years'>2026",
            "<p class='bounds-years'>текст без дат",
        )
        html = html.replace(
            "15.01.2026, 15.07.2026\n            2027\n            15.01.2027\n", ""
        )
        block = BeautifulSoup(html, "lxml").select_one(".wp-block-aigenis-bounds")
        p = _parse_aigenis_bond_block(block, "ALL")
        assert p.get("guarantor") == "Гарант"


class TestTryAigenisByBlocks:
    def test_multiple_blocks(self):
        html = _block_html() + _block_html(**{"data-code": "Айгенис 52", "data-reg": "OP-52"})
        soup = BeautifulSoup(html, "lxml")
        out = _try_aigenis_by_blocks(soup, "ALL")
        assert [p["internal_id"] for p in out] == ["OP-51", "OP-52"]

    def test_currency_filter(self):
        soup = BeautifulSoup(_block_html(), "lxml")
        assert _try_aigenis_by_blocks(soup, "EUR") == []


class TestParseListingHtml:
    def test_blocks_path(self):
        assert parse_listing_html(_block_html(), "ALL")[0]["internal_id"] == "OP-51"

    def test_next_data_path(self):
        import json

        html = (
            "<html><body><script id='__NEXT_DATA__'>"
            + json.dumps(
                {
                    "props": {
                        "pageProps": {
                            "bonds": [
                                {"internal_id": "OP-9", "name": "Айгенис 9", "isin": "BY000000"}
                            ]
                        }
                    }
                }
            )
            + "</script></body></html>"
        )
        out = parse_listing_html(html, "byn")
        assert out[0]["internal_id"] == "OP-9"
        assert out[0]["currency"] == "BYN"
        assert out[0]["isin"] == "BY000000"

    def test_jsonld_path(self):
        import json

        html = (
            "<html><body><script type='application/ld+json'>"
            + json.dumps({"@graph": [{"id": "OP-9", "name": "X", "isin": "BY123"}]})
            + "</script></body></html>"
        )
        out = parse_listing_html(html, "usd")
        assert out[0]["internal_id"] == "OP-9"
        assert out[0]["currency"] == "USD"
        assert out[0]["isin"] == "BY123"

    def test_table_fallback(self):
        html = (
            "<table class='bonds'><tbody><tr>"
            "<td><a href='/bonds/OP-77'>Айгенис 77</a></td></tr>"
            "</tbody></table>"
        )
        out = parse_listing_html(html, "usd")
        assert out == [
            {
                "internal_id": "OP-77",
                "name": "Айгенис 77",
                "currency": "USD",
                "isin": None,
            }
        ]


# ---------------------------------------------------------------- history ---


class TestHistoryState:
    def _soup(self, payload):
        import json

        return BeautifulSoup(
            f'<script id="__NEXT_DATA__">{json.dumps({"props": {"pageProps": payload}})}</script>',
            "lxml",
        )

    def test_history_list(self):
        assert _try_state(self._soup({"history": [{"d": 1}, 2]})) == [{"d": 1}]

    def test_items_list(self):
        assert _try_state(self._soup({"items": [{"d": 2}]})) == [{"d": 2}]

    def test_dict_with_items(self):
        assert _try_state(self._soup({"history": {"items": [{"d": 3}]}})) == [{"d": 3}]

    def test_none(self):
        assert _try_state(self._soup({"other": 1})) is None
        assert _try_state(BeautifulSoup("<html></html>", "lxml")) is None
        assert (
            _try_state(BeautifulSoup('<script id="__NEXT_DATA__">{bad}</script>', "lxml")) is None
        )


class TestHistoryTable:
    def test_full_row(self):
        soup = BeautifulSoup(
            "<table class='history'><tbody><tr>"
            "<td>2026-06-01</td><td>100.5</td><td>7.2</td><td>5.0</td><td>active</td>"
            "</tr></tbody></table>",
            "lxml",
        )
        assert _parse_table(soup) == [
            {
                "date": "2026-06-01",
                "price": "100.5",
                "yield": "7.2",
                "coupon": "5.0",
                "status": "active",
            }
        ]

    def test_date_regex_fallback(self):
        soup = BeautifulSoup(
            "<div class='history-row'><td>данные на 2026-06-01</td><td>99</td></div>", "lxml"
        )
        assert _parse_table(soup)[0]["date"] == "2026-06-01"

    def test_invalid_date_row_skipped(self):
        soup = BeautifulSoup(
            "<table class='history'><tbody><tr><td>не дата</td><td>99</td></tr></tbody></table>",
            "lxml",
        )
        assert _parse_table(soup) == []

    def test_short_row_skipped(self):
        soup = BeautifulSoup(
            "<table class='history'><tbody><tr><td>only one</td></tr></tbody></table>", "lxml"
        )
        assert _parse_table(soup) == []

    def test_z_suffix_date(self):
        soup = BeautifulSoup(
            "<table class='history'><tbody><tr><td>2026-06-01T12:00:00Z</td><td>1</td></tr></tbody></table>",
            "lxml",
        )
        assert _parse_table(soup)[0]["date"] == "2026-06-01"

    def test_invalid_calendar_date_skipped(self):
        soup = BeautifulSoup(
            "<table class='history'><tbody><tr><td>данные 2026-13-01</td><td>1</td></tr></tbody></table>",
            "lxml",
        )
        assert _parse_table(soup) == []


class TestParseHistoryHtml:
    def test_state_path(self):
        import json

        html = (
            "<html><body><script id='__NEXT_DATA__'>"
            + json.dumps(
                {"props": {"pageProps": {"history": [{"date": "2026-06-01", "price": 99}]}}}
            )
            + "</script></body></html>"
        )
        assert parse_history_html(html, "OP-51") == [{"date": "2026-06-01", "price": 99}]

    def test_table_path(self):
        html = (
            "<table class='history'><tbody><tr><td>2026-06-01</td><td>100</td></tr></tbody></table>"
        )
        assert parse_history_html(html, "OP-51")[0]["price"] == "100"


# ------------------------------------------------------------------ detail ---


class TestIdMatches:
    def test_exact(self):
        assert _id_matches({"internal_id": "OP-51"}, "OP-51") is True

    def test_dash_insensitive(self):
        assert _id_matches({"id": "OP51"}, "OP-51") is True

    def test_numeric(self):
        assert _id_matches({"registration_number": "OP-52"}, "52") is True

    def test_no_target(self):
        assert _id_matches({"internal_id": "OP-51"}, "") is False
        assert _id_matches({"internal_id": "OP-51"}, None) is False

    def test_no_match(self):
        assert _id_matches({"internal_id": "OP-51"}, "OP-99") is False


class TestTryJsonState:
    def _soup(self, payload):
        import json

        return BeautifulSoup(
            f'<script id="__NEXT_DATA__">{json.dumps({"props": {"pageProps": payload}})}</script>',
            "lxml",
        )

    def test_bond(self):
        assert _try_json_state(self._soup({"bond": {"name": "X"}}), "OP-1") == {
            "name": "X",
            "id": "OP-1",
        }

    def test_item(self):
        assert _try_json_state(self._soup({"item": {"a": 1}})) == {"a": 1, "id": None}

    def test_candidates_list(self):
        soup = self._soup({"bonds": [{"internal_id": "OP-9"}, {"internal_id": "OP-10"}]})
        out = _try_json_state(soup, "OP-10")
        assert out["internal_id"] == "OP-10"
        assert out["id"] == "OP-10"

    def test_candidates_dict(self):
        soup = self._soup({"results": {"items": [{"internal_id": "OP-9"}]}})
        assert _try_json_state(soup, "OP-9")["internal_id"] == "OP-9"

    def test_no_match(self):
        assert _try_json_state(self._soup({"bonds": [{"internal_id": "OP-9"}]}), "OP-55") is None

    def test_jsonld_bond(self):
        soup = BeautifulSoup(
            '<script type=\'application/ld+json\'>{"@type": "Bond", "name": "X"}</script>',
            "lxml",
        )
        assert _try_json_state(soup) == {"@type": "Bond", "name": "X"}

    def test_jsonld_list(self):
        soup = BeautifulSoup(
            "<script type='application/ld+json'>"
            '[{"@type": "Bond", "name": "X"}, {"@type": "Article"}]</script>',
            "lxml",
        )
        assert _try_json_state(soup)["name"] == "X"

    def test_jsonld_ignores_other_types(self):
        soup = BeautifulSoup(
            '<script type=\'application/ld+json\'>{"@type": "Article"}</script>',
            "lxml",
        )
        assert _try_json_state(soup) is None

    def test_invalid_json(self):
        assert (
            _try_json_state(BeautifulSoup('<script id="__NEXT_DATA__">{x}</script>', "lxml"))
            is None
        )

    def test_invalid_ldjson_skipped(self):
        soup = BeautifulSoup('<script type="application/ld+json">{bad json}</script>', "lxml")
        assert _try_json_state(soup) is None


class TestFindLabel:
    def test_sibling_value(self):
        soup = BeautifulSoup("<div><span>Эмитент</span><div>Айгенис</div></div>", "lxml")
        assert _find_label(soup, ["эмитент"]) == "Айгенис"

    def test_colon_in_parent(self):
        soup = BeautifulSoup("<div><span>Валюта: USD</span></div>", "lxml")
        assert _find_label(soup, ["валюта"]) == "USD"

    def test_script_excluded(self):
        soup = BeautifulSoup(
            "<script>Эмитент: Bad</script><div><span>Эмитент</span><div>Good</div></div>",
            "lxml",
        )
        assert _find_label(soup, ["эмитент"]) == "Good"

    def test_no_match(self):
        assert _find_label(BeautifulSoup("<div>nothing</div>", "lxml"), ["валюта"]) is None

    def test_label_without_value(self):
        soup = BeautifulSoup("<div><span>Валюта</span></div>", "lxml")
        assert _find_label(soup, ["валюта"]) is None

    def test_label_without_parent(self):
        soup = BeautifulSoup("<div><span>Эмитент</span></div>", "lxml")
        soup.find(string="Эмитент").parent = None
        assert _find_label(soup, ["эмитент"]) is None


class TestCoerce:
    def test_none(self):
        assert _coerce(None) is None

    def test_blank(self):
        assert _coerce("   ") is None

    def test_trim(self):
        assert _coerce("  x  ") == "x"


class TestDetailCouponHelpers:
    def test_rate(self):
        assert detail_rate("7% годовых") == "7"
        assert detail_rate("12,5%") == "12.5"
        assert detail_rate("none") is None

    def test_frequency(self):
        assert detail_freq("ежемесячно") == 12
        assert detail_freq("1 раз в месяц") == 12
        assert detail_freq("1 раз в квартал") == 4
        assert detail_freq("2 раза в год") == 2
        assert detail_freq("5 раз в год") == 5
        assert detail_freq("3 раза в год") == 3
        assert detail_freq("unknown") is None

    def test_schedule(self):
        assert detail_schedule("<div><p class='bounds-years'>2026\n15.01.2026</p></div>") == {
            "2026": ["15.01.2026"]
        }
        assert detail_schedule("<div>no schedule</div>") is None
        assert detail_schedule("<div><p class='bounds-years'>2026\n15.01.2026</p></div>") == {
            "2026": ["15.01.2026"]
        }

    def test_schedule_empty_tokens_skipped(self):
        assert detail_schedule("<div><p class='bounds-years'>2026\n\n\n15.01.2026</p></div>") == {
            "2026": ["15.01.2026"]
        }

    def test_schedule_whitespace_token_skipped(self):
        assert detail_schedule("<div><p class='bounds-years'>2026\n \n15.01.2026</p></div>") == {
            "2026": ["15.01.2026"]
        }


class TestParseDom:
    def test_plain_dom(self):
        html = """
        <html><head><title>Обл 51</title></head><body>
          <h1>Айгенис 51</h1>
          <div><span>Эмитент</span><div>ООО Айгенис</div></div>
          <div><span>Ставка купона</span><div>7%</div></div>
          <div><span>Дата погашения</span><div>31.12.2030</div></div>
        </body></html>
        """
        p = _parse_dom(html, "OP-51")
        assert p["id"] == "OP-51"
        assert p["name"] == "Айгенис 51"
        assert p["issuer"] == "ООО Айгенис"
        assert p["coupon_rate"] == "7%"
        assert p["maturity_date"] == "31.12.2030"
        assert p["currency"] == "USD"

    def test_block_path(self):
        block = _block_html().replace('<span class="title">Доходность</span>', "")
        block = block.replace('<span class="text">7,5%</span>', '<span class="text">—</span>')
        html = f"<html><body>{block}</body></html>"
        p = _parse_dom(html, "OP-51")
        assert p["id"] == "OP-51"
        assert p["currency"] == "USD"
        assert p["registration_number"] == "OP-51"
        assert p["nominal"] == "1 000,00"
        assert p["issue_volume"] == "10000000"
        assert p["income_method"] == "7% годовых, 1 раз в квартал"
        assert p["coupon_rate"] == "12.5"
        assert p["coupon_schedule"]["2026"] == ["15.01.2026", "15.07.2026"]
        assert p["guarantor"] == "Гарант"

    def test_block_skipped_when_ids_differ(self):
        block = _block_html()
        html = f"<html><body>{block}</body></html>"
        p = _parse_dom(html, "OP-99")
        assert p["id"] == "OP-99"
        assert "registration_number" not in p
        assert "issue_volume" not in p
        assert "income_method" not in p

    def test_block_without_content_skipped(self):
        block = _block_html().replace('<div class="content">', '<div class="other">')
        html = f"<html><body>{block}</body></html>"
        p = _parse_dom(html, "OP-51")
        assert p["registration_number"] == "OP-51"
        assert "issue_volume" not in p
        assert "income_method" not in p

    def test_content_row_without_h4(self):
        block = _block_html().replace(
            "<h4>Ставка купона</h4>", "<div class='col-md-4'>без заголовка</div>"
        )
        block = block.replace(
            "<h4>График купона</h4>", "<div class='col-md-4'>тоже без заголовка</div>"
        )
        html = f"<html><body>{block}</body></html>"
        p = _parse_dom(html, "OP-51")
        assert p["coupon_rate"] is None

    def test_div_footer_guarantor(self):
        block = _block_html().replace(
            "<p class='bounds-footer'>Организация: Гарант</p>",
            "<div class='bounds-footer'>Организация: ДивГарант</div>",
        )
        html = f"<html><body>{block}</body></html>"
        p = _parse_dom(html, "OP-51")
        assert p["guarantor"] == "ДивГарант"

    def test_no_title(self):
        p = _parse_dom("<html><body>no title</body></html>", "OP-1")
        assert p["name"] == "OP-1"


class TestParseDetailHtml:
    def test_block_match(self):
        html = f"<html><body>{_block_html()}</body></html>"
        p = parse_detail_html(html, "OP-51")
        assert p["internal_id"] == "OP-51"
        assert p["name"] == "Айгенис 51 выпуск"

    def test_json_state_path(self):
        import json

        html = (
            "<html><body><script id='__NEXT_DATA__'>"
            + json.dumps(
                {"props": {"pageProps": {"bond": {"name": "Айгенис 51", "coupon_rate": 7.5}}}}
            )
            + "</script></body></html>"
        )
        p = parse_detail_html(html, "OP-51")
        assert p["name"] == "Айгенис 51"
        assert p["id"] == "OP-51"

    def test_dom_fallback(self):
        html = "<html><head><title>Облигация</title></head><body>текст</body></html>"
        p = parse_detail_html(html, "OP-1")
        assert p["id"] == "OP-1"
        assert p["name"] == "Облигация"

    def test_block_without_candidate_id_skipped(self):
        html = (
            "<html><body>"
            "<div class='wp-block-aigenis-bounds' data-curency='BYN'>"
            "<summary><div class='display-column'><span class='title'>Доходность</span>"
            "<span class='text'>7,5%</span></div></summary>"
            "</div>"
            "</body></html>"
        )
        p = parse_detail_html(html, "OP-99")
        assert p["id"] == "OP-99"


# ------------------------------------------------------------- json api ----


class TestCoerceDate:
    def test_none_and_empty(self):
        assert _coerce_date(None) is None
        assert _coerce_date("") is None

    def test_date(self):
        d = date(2026, 1, 1)
        assert _coerce_date(d) is d

    def test_iso(self):
        assert _coerce_date("2026-06-01T00:00:00Z") == date(2026, 6, 1)

    def test_dotted(self):
        assert _coerce_date("01.06.2026") == date(2026, 6, 1)

    def test_bad_raises(self):
        with pytest.raises(ParseError):
            _coerce_date("не дата")
        with pytest.raises(ParseError):
            _coerce_date("32.01.2026")


class TestFirstNotNull:
    def test_picks_first(self):
        assert _first_not_none(None, 0, 2) == 0
        assert _first_not_none(1, 2) == 1
        assert _first_not_none(None, None) is None


class TestParseListingItems:
    def test_normalizes(self):
        items = [
            {
                "state_security_id": "OP-5",
                "title": "Айгенис 5",
                "currency": "byn",
                "isin": "BY000",
                "coupon": "7.5",
                "frequency": 4,
                "reg_number": "R-1",
                "issue": 5,
                "maturity_term": "5 лет",
            }
        ]
        out = parse_listing_items(items, "usd")
        assert out[0]["internal_id"] == "OP-5"
        assert out[0]["name"] == "Айгенис 5"
        assert out[0]["currency"] == "BYN"
        assert out[0]["isin"] == "BY000"
        assert out[0]["coupon_rate"] == "7.5"
        assert out[0]["coupon_frequency"] == 4
        assert out[0]["registration_number"] == "R-1"
        assert out[0]["issue_number"] == 5
        assert out[0]["maturity_term_text"] == "5 лет"

    def test_skips_without_id(self):
        assert parse_listing_items([{"name": "X"}, "not-dict"], "usd") == []

    def test_uses_symbol_fallback(self):
        assert parse_listing_items([{"symbol": "OP-3"}], "usd")[0]["internal_id"] == "OP-3"


class TestParseBondPayload:
    def test_full_payload(self):
        bond = parse_bond_payload(
            {
                "id": "OP-5",
                "name": "Айгенис 5",
                "currency": "byn",
                "coupon": "7.5",
                "maturity_date": "01.06.2031",
                "yield": 7.9,
                "start_date": "2026-01-01",
                "status": "active",
                "in_stock": True,
                "issue": 5,
            }
        )
        assert bond.internal_id == "OP-5"
        assert bond.currency == "BYN"
        assert bond.coupon_rate == Decimal("7.5")
        assert bond.maturity_date == date(2031, 6, 1)
        assert bond.yield_to_maturity == Decimal("7.9")
        assert bond.start_date == date(2026, 1, 1)
        assert bond.status == "active"
        assert bond.in_stock is True
        assert bond.issue_number == 5

    def test_missing_internal_id_raises(self):
        with pytest.raises(ParseError):
            parse_bond_payload({"name": "X"})

    def test_missing_name_raises(self):
        with pytest.raises(ParseError):
            parse_bond_payload({"id": "OP-1"})

    def test_fallback_id(self):
        bond = parse_bond_payload({"name": "X"}, internal_id_fallback="OP-9")
        assert bond.internal_id == "OP-9"

    def test_bad_fetched_at(self):
        bond = parse_bond_payload({"id": "OP-1", "name": "X", "fetched_at": "не дата"})
        assert bond.fetched_at is not None

    def test_bad_dates_raise(self):
        with pytest.raises(ParseError):
            parse_bond_payload({"id": "OP-1", "name": "X", "maturity_date": "bad"})


class TestParseHistoryItems:
    def test_parses(self):
        items = [
            {"date": "2026-06-01", "price": "100", "yield": 7.5, "coupon": 5.0},
            {"timestamp": "01.06.2026", "yield_to_maturity": "7.2"},
            "not-dict",
        ]
        out = parse_history_items(items, internal_id="OP-1")
        assert len(out) == 2
        assert out[0].internal_id == "OP-1"
        assert out[0].date == date(2026, 6, 1)
        assert out[0].price == Decimal("100")
        assert out[0].yield_ == Decimal("7.5")
        assert out[0].coupon == Decimal("5.0")
        assert out[0].status == "unknown"
        assert out[1].yield_ == Decimal("7.2")

    def test_none_date_skipped(self):
        items = [{"date": None, "price": 1}]
        assert parse_history_items(items, internal_id="OP-1") == []

    def test_bad_date_raises(self):
        with pytest.raises(ParseError):
            parse_history_items([{"date": "bad", "price": 1}], internal_id="OP-1")

    def test_decimal_yield(self):
        items = [{"date": "2026-06-01", "yield": Decimal("7.5")}]
        assert parse_history_items(items, internal_id="OP-1")[0].yield_ == Decimal("7.5")


class TestApiWrappers:
    def test_parse_listing_payload_list(self):
        from scraper.sources.aigenis.api.listing import parse_listing_payload

        out = parse_listing_payload([{"internal_id": "OP-1"}], "usd")
        assert out[0]["internal_id"] == "OP-1"
        assert out[0]["currency"] == "USD"

    def test_parse_listing_payload_dict(self):
        from scraper.sources.aigenis.api.listing import parse_listing_payload

        out = parse_listing_payload({"items": [{"internal_id": "OP-2"}]}, "byn")
        assert out[0]["currency"] == "BYN"

    def test_parse_listing_payload_other(self):
        from scraper.sources.aigenis.api.listing import parse_listing_payload

        assert parse_listing_payload("nope", "usd") == []
        assert parse_listing_payload({"items": "nope"}, "usd") == []

    def test_parse_history_payload_list(self):
        from scraper.sources.aigenis.api.history import parse_history_payload

        items = [{"date": "2026-06-01", "price": "100"}]
        out = parse_history_payload(items, "OP-1")
        assert len(out) == 1
        assert out[0].date == date(2026, 6, 1)

    def test_parse_history_payload_dict(self):
        from scraper.sources.aigenis.api.history import parse_history_payload

        items = [{"date": "2026-06-01"}]
        out = parse_history_payload({"data": items}, "OP-1")
        assert len(out) == 1

    def test_parse_history_payload_unexpected(self):
        from scraper.sources.aigenis.api.history import parse_history_payload

        assert parse_history_payload({"other": 1}, "OP-1") == []

    def test_parse_detail_payload(self):
        from scraper.sources.aigenis.api.detail import parse_detail_payload

        bond = parse_detail_payload({"name": "X"}, "OP-1")
        assert bond.internal_id == "OP-1"

    def test_parse_detail_payload_not_dict(self):
        from scraper.sources.aigenis.api.detail import parse_detail_payload

        with pytest.raises(ValueError):
            parse_detail_payload("nope", "OP-1")
