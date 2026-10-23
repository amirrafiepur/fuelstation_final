"""
"لیست اطلاعات فروش": the monthly, nozzle-based report (screen + PDF + keyboard).

Expected figures are worked out BY HAND from the raw meter readings, tests
and frozen rates (operation = new - previous; mechanical sales = operation
- test; amount = mechanical sales x rate), then compared with the service,
the page and the PDF.

JALALI 1405/05 (2026-07-23 .. 2026-08-22):
  nozzle 1 : d1 0->1000 test10 @1200 | d2 1000->2500 test5 @1300
             operation 2,500  test 15  sales 2,485  amount 1,188,000+1,943,500 = 3,131,500
  nozzle 2 : d1 500->900 test0 @1200       -> 400 | 0 | 400 | 480,000
  nozzle 19: d1 0->300 test2 @1500 | d3 300->450 test0 @1600
             operation 450  test 2  sales 448  amount 447,000+240,000 = 687,000
  nozzle 26: d2 100->160 test4 @1500       -> 60 | 4 | 56 | 84,000
  all other nozzles                        -> 0 | 0 | 0 | 0
  TOTALS   : operation 3,410 | test 21 | sales 3,389 | amount 4,382,500
JALALI 1405/06 (must never leak into 05): nozzle 1 2500->2800 test1 @1300
             -> 300 | 1 | 299 | 388,700
"""

import datetime
import io
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.test_number_display import pdf_text, render_pdf_with_html
from apps.license.models import License
from apps.reports import services as report_services
from apps.reports.test_nozzle_ledger_keyboard import NODE, NODE_ENV
from apps.sales.models import NozzleSale, SalesInvoice
from apps.stations.models import Nozzle, Product, Station, Tank
from apps.workday.models import DailyWorkingDay

User = get_user_model()
HARNESS = Path(__file__).parent / "js_tests" / "all_nozzles_keyboard.js"

D = Decimal
EXPECTED_05 = {
    1: (2500, 15, 2485, 3131500),
    2: (400, 0, 400, 480000),
    19: (450, 2, 448, 687000),
    26: (60, 4, 56, 84000),
}
TOTALS_05 = (3410, 21, 3389, 4382500)
EXPECTED_06 = {1: (300, 1, 299, 388700)}
TOTALS_06 = (300, 1, 299, 388700)

FIELDS = ("total_operation", "total_test", "total_mechanical_sales", "total_amount")

# Main-table column layout: شماره نازل | کنتور اول ماه | کنتور آخر ماه | جمع فروش مکانیکی | جمع آزمایش | جمع کارکرد
# (no جمع مبلغ کل column -- that total lives in the summary strip only).
FIRST_LAST_05 = {1: (0, 2500), 2: (500, 900), 19: (0, 450), 26: (100, 160)}      # (first previous, last new)
FIRST_LAST_06 = {1: (2500, 2800)}


def expected_row(number, month_data, first_last):
    """The six cells a nozzle's row must show, worked from the hand data above."""
    op, test, sales, _amount = month_data.get(number, (0, 0, 0, 0))
    first, last = first_last.get(number, (None, None))
    dash = "—"
    return [str(number), dash if first is None else fmt(first), dash if last is None else fmt(last),
            fmt(sales), fmt(test), fmt(op)]
TOTAL_KEYS = ("operation", "test", "mechanical-sales", "amount")


def fmt(n):
    return f"{n:,}"


def screen_totals(html):
    d = dict(re.findall(r'data-total="([a-z-]+)"[^>]*>([^<]*)<', html))
    return tuple(d[k] for k in TOTAL_KEYS)


def table_rows(html, table_id="all-nozzles-table"):
    """Rows of the on-screen table as lists of cell text."""
    body = html.split(f'id="{table_id}"', 1)[1].split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    return [
        [c.strip() for c in re.findall(r"<td[^>]*>([^<]*)</td>", tr)]
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body, flags=re.S)
    ]


def to_int(text):
    return int(text.replace(",", ""))


def pdf_summary(html):
    block = html.split("print-summary", 1)[1].split("</table>", 1)[0]
    return tuple(v.strip() for v in re.findall(r'class="numeric"[^>]*>([^<]*)<', block))


def pdf_table_rows(html):
    main = html.split("print-summary", 1)[1].split("</table>", 1)[1]
    body = main.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    return [
        [c.strip() for c in re.findall(r"<td[^>]*>([^<]*)</td>", tr)]
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body, flags=re.S)
    ]


class AllNozzlesBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="op1", password="testpass123")
        License.objects.create(start_date=datetime.date(2026, 7, 23), duration_days=365)
        station = Station.objects.create(name="140 Jahan Pour", province="Razavi Khorasan", city="Mashhad")
        regular = Product.objects.create(name="Regular")
        sup = Product.objects.create(name="Super")
        rtank = Tank.objects.create(station=station, product=regular, capacity=50000)
        stank = Tank.objects.create(station=station, product=sup, capacity=30000)
        # Only some nozzles exist -- the report must still list all 26.
        nozzles = {n: Nozzle.objects.create(tank=rtank, number=n) for n in (1, 2, 3)}
        nozzles.update({n: Nozzle.objects.create(tank=stank, number=n) for n in (19, 26)})
        self.client.login(username="op1", password="testpass123")

        days = {k: DailyWorkingDay.objects.create(date=datetime.date(*v)) for k, v in {
            "d1": (2026, 7, 24), "d2": (2026, 7, 26), "d3": (2026, 8, 2), "d4": (2026, 8, 25)}.items()}
        invoices = {k: SalesInvoice.objects.create(working_day=wd, operator=self.user) for k, wd in days.items()}

        def sale(day, number, prev, new, test, rate):
            NozzleSale.objects.create(
                sales_invoice=invoices[day], nozzle=nozzles[number], previous_meter=D(prev),
                new_meter=D(new), test=D(test), sales_rate=D(rate))

        sale("d1", 1, 0, 1000, 10, 1200)
        sale("d2", 1, 1000, 2500, 5, 1300)
        sale("d1", 2, 500, 900, 0, 1200)
        sale("d1", 19, 0, 300, 2, 1500)
        sale("d3", 19, 300, 450, 0, 1600)
        sale("d2", 26, 100, 160, 4, 1500)
        sale("d4", 1, 2500, 2800, 1, 1300)        # month 06 -- must not leak into 05

    def url(self, month=5, year=1405):
        return f"/reports/all-nozzles/?year={year}&month={month}"

    def print_url(self, month=5, year=1405):
        return f"/print/all-nozzles/?year={year}&month={month}"

    def page(self, month=5, year=1405):
        resp = self.client.get(self.url(month, year))
        self.assertEqual(resp.status_code, 200)
        return resp.content.decode()


class AllNozzlesServiceTests(AllNozzlesBase):
    def test_exactly_26_rows_numbered_1_to_26_in_order(self):
        rows = report_services.all_nozzles_monthly_summary(1405, 5)
        self.assertEqual(len(rows), 26)
        self.assertEqual([r["nozzle_number"] for r in rows], list(range(1, 27)))

    def test_each_nozzle_row_equals_the_hand_worked_monthly_totals(self):
        rows = {r["nozzle_number"]: r for r in report_services.all_nozzles_monthly_summary(1405, 5)}
        for number, row in rows.items():
            expected = EXPECTED_05.get(number, (0, 0, 0, 0))
            self.assertEqual(tuple(row[f] for f in FIELDS), tuple(D(x) for x in expected), f"nozzle {number}")

    def test_other_months_never_leak_in(self):
        rows = {r["nozzle_number"]: r for r in report_services.all_nozzles_monthly_summary(1405, 6)}
        for number, row in rows.items():
            expected = EXPECTED_06.get(number, (0, 0, 0, 0))
            self.assertEqual(tuple(row[f] for f in FIELDS), tuple(D(x) for x in expected), f"nozzle {number}")

    def test_month_with_no_sales_still_has_26_zero_rows(self):
        rows = report_services.all_nozzles_monthly_summary(1405, 9)
        self.assertEqual(len(rows), 26)
        self.assertTrue(all(r[f] == 0 for r in rows for f in FIELDS))

    def test_totals_equal_hand_worked_numbers_and_the_column_sums(self):
        rows = report_services.all_nozzles_monthly_summary(1405, 5)
        totals = report_services.all_nozzles_monthly_totals(rows)
        self.assertEqual(tuple(totals[f] for f in FIELDS), tuple(D(x) for x in TOTALS_05))
        for f in FIELDS:
            self.assertEqual(totals[f], sum(r[f] for r in rows))

    def test_values_come_from_the_existing_nozzle_sale_properties(self):
        """No new formulas: each nozzle's figures are the sums of NozzleSale's own properties."""
        for number in (1, 19):
            sales = NozzleSale.objects.filter(
                nozzle__number=number,
                sales_invoice__working_day__date__range=(datetime.date(2026, 7, 23), datetime.date(2026, 8, 22)))
            row = report_services.all_nozzles_monthly_summary(1405, 5)[number - 1]
            self.assertEqual(row["total_operation"], sum(s.operation for s in sales))
            self.assertEqual(row["total_mechanical_sales"], sum(s.mechanical_sales for s in sales))
            self.assertEqual(row["total_amount"], sum(s.total_amount for s in sales))


class AllNozzlesScreenTests(AllNozzlesBase):
    def test_exactly_26_rows_with_nozzle_specific_totals(self):
        rows = table_rows(self.page())
        self.assertEqual(len(rows), 26)
        self.assertEqual([r[0] for r in rows], [str(n) for n in range(1, 27)])
        for r in rows:
            number = int(r[0])
            self.assertEqual(r, expected_row(number, EXPECTED_05, FIRST_LAST_05), f"nozzle {number}")
            self.assertEqual(len(r), 6)

    def test_header_labels_and_order(self):
        html = self.page()
        head = html.split('id="all-nozzles-table"', 1)[1].split("</thead>", 1)[0]
        self.assertEqual(re.findall(r"<th[^>]*>([^<]*)</th>", head),
                         ["شماره نازل", "کنتور اول ماه", "کنتور آخر ماه", "جمع فروش مکانیکی", "جمع آزمایش", "جمع کارکرد"])
        self.assertNotIn("تاریخ", head)
        self.assertNotIn("جمع مبلغ کل", head)                     # removed from the main table only

    def test_summary_labels_order_and_values(self):
        html = self.page()
        block = html.split('id="all-nozzles-totals"', 1)[1].split("</div>\n  </div>", 1)[0]
        labels = re.findall(r'<div class="form-label">([^<]+)</div>', block)
        self.assertEqual(labels, ["جمع کارکرد", "مجموع آزمایش", "مجموع فروش مکانیکی", "مجموع مبلغ کل"])
        self.assertEqual(screen_totals(html), tuple(fmt(x) for x in TOTALS_05))

    def test_summary_sits_above_the_table_and_equals_the_displayed_column_sums(self):
        html = self.page()
        self.assertLess(html.index('id="all-nozzles-totals"'), html.index('id="all-nozzles-table"'))
        rows = table_rows(html)
        shown = tuple(to_int(x) for x in screen_totals(html))          # operation, test, sales, amount
        # The three remaining total columns: جمع کارکرد (col 5), جمع آزمایش (4), جمع فروش مکانیکی (3).
        self.assertEqual(shown[:3], (sum(to_int(r[5]) for r in rows), sum(to_int(r[4]) for r in rows),
                                     sum(to_int(r[3]) for r in rows)))
        self.assertEqual(shown[3], TOTALS_05[3])                       # مجموع مبلغ کل: summary only, unchanged

    def test_changing_month_or_year_changes_rows_and_summary(self):
        self.assertEqual(screen_totals(self.page(6)), tuple(fmt(x) for x in TOTALS_06))
        rows = table_rows(self.page(6))
        self.assertEqual(len(rows), 26)
        self.assertEqual(rows[0], expected_row(1, EXPECTED_06, FIRST_LAST_06))
        self.assertEqual(screen_totals(self.page(9)), ("0", "0", "0", "0"))
        self.assertEqual(len(table_rows(self.page(9))), 26)
        self.assertEqual(screen_totals(self.page(5, 1404)), ("0", "0", "0", "0"))

    def test_year_month_selectors_and_print_link(self):
        html = self.page(6)
        self.assertIn('value="1405"', html)
        self.assertRegex(html, r'<option value="6" selected>')
        self.assertIn("/print/all-nozzles/?year=1405&month=6", html)
        content = html.split("<main", 1)[1]            # the page itself, not the site header
        self.assertTrue("start_date" not in content and "end_date" not in content, "date-range filter still present")
        self.assertTrue("jalali-date-input" not in content, "date inputs still present")

    def test_defaults_to_the_current_jalali_month(self):
        resp = self.client.get("/reports/all-nozzles/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(table_rows(resp.content.decode())), 26)

    def test_other_reports_and_data_are_unaffected(self):
        before = list(NozzleSale.objects.values_list("id", "previous_meter", "new_meter", "test", "sales_rate").order_by("id"))
        self.page()
        self.client.get(self.print_url())
        self.assertEqual(before, list(NozzleSale.objects.values_list(
            "id", "previous_meter", "new_meter", "test", "sales_rate").order_by("id")))
        nozzle = Nozzle.objects.get(number=1)
        resp = self.client.get(f"/reports/nozzle-ledger/?nozzle_id={nozzle.id}&start_date=2026-07-23&end_date=2026-08-22")
        self.assertEqual(resp.status_code, 200)
        self.assertIn('id="nozzle-ledger-table"', resp.content.decode())


class AllNozzlesPdfTests(AllNozzlesBase):
    def test_pdf_summary_and_26_rows_match_the_screen(self):
        for month in (5, 6, 9):
            html_screen = self.page(month)
            resp, html = render_pdf_with_html(self.client, self.print_url(month))
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.content.startswith(b"%PDF"))
            self.assertEqual(pdf_summary(html), screen_totals(html_screen), month)
            self.assertEqual(pdf_table_rows(html), table_rows(html_screen), month)
            self.assertEqual(len(pdf_table_rows(html)), 26)

    def test_pdf_values_are_the_hand_worked_ones(self):
        resp, html = render_pdf_with_html(self.client, self.print_url(5))
        self.assertEqual(pdf_summary(html), tuple(fmt(x) for x in TOTALS_05))
        rows = pdf_table_rows(html)
        self.assertEqual(rows[18], expected_row(19, EXPECTED_05, FIRST_LAST_05))   # nozzle 19 is row 19
        self.assertEqual(rows[0], expected_row(1, EXPECTED_05, FIRST_LAST_05))
        self.assertEqual(rows[2], expected_row(3, EXPECTED_05, FIRST_LAST_05))      # idle nozzle: dashes and zeros

    def test_pdf_headings_labels_and_structure_are_preserved(self):
        resp, html = render_pdf_with_html(self.client, self.print_url(5))
        for needle in ("کارکرد تمام نازل‌ها", "سال 1405 — ماه 5", "جایگاه", "شماره نازل", "کنتور اول ماه",
                       "کنتور آخر ماه", "جمع کارکرد", "جمع آزمایش", "جمع فروش مکانیکی", "مجموع آزمایش",
                       "مجموع فروش مکانیکی", "مجموع مبلغ کل"):
            self.assertIn(needle, html, needle)
        main = html.split("print-summary", 1)[1].split("</table>", 1)[1]            # everything after the summary table
        self.assertNotIn("جمع مبلغ کل", main)                    # gone from the main table...
        self.assertIn("مجموع مبلغ کل", html.split("</table>", 1)[0])                # ...still in the summary strip
        self.assertLess(html.index("print-summary"), html.index("شماره نازل"))
        text = pdf_text(resp.content)
        for needle in ("4,382,500", "3,389", "3,410", "شماره نازل"):
            self.assertIn(needle, text)

    def test_pdf_is_one_portrait_page_with_everything_on_it(self):
        from pypdf import PdfReader
        resp = self.client.get(self.print_url(5))
        reader = PdfReader(io.BytesIO(resp.content))
        self.assertEqual(len(reader.pages), 1)
        box = reader.pages[0].mediabox
        self.assertLess(float(box.width), float(box.height))

    def test_font_size_is_not_reduced(self):
        """The PDF keeps the readable size it had: 14px table type (10.5pt),
        unchanged in the stylesheet and as actually rendered."""
        from django.conf import settings
        css = (Path(settings.STATICFILES_DIRS[0]) / "css" / "print.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"table\.print-table \{[^}]*font-size: 14px")
        self.assertNotIn("body.all-nozzles", css)
        try:
            import pymupdf
        except ImportError:
            self.skipTest("pymupdf not installed (dev-only check)")
        doc = pymupdf.open(stream=self.client.get(self.print_url(5)).content, filetype="pdf")
        sizes = [span["size"] for block in doc[0].get_text("dict")["blocks"] if "lines" in block
                 for line in block["lines"] for span in line["spans"]
                 if re.fullmatch(r"[\d,]+", span["text"].strip()) and len(span["text"].strip()) >= 5]
        self.assertTrue(sizes)
        self.assertGreaterEqual(min(sizes), 10.4)          # 14px == 10.5pt; never smaller


class AllNozzlesKeyboardStructureTests(AllNozzlesBase):
    def test_page_uses_the_shared_row_navigation(self):
        html = self.page()
        self.assertIn('class="row-nav-table"', html)
        self.assertIn("TableRowNavigation.init", html)
        self.assertIn("#all-nozzles-table tbody tr", html)
        self.assertIn('id="table-mode-hint"', html)
        self.assertRegex(html, r"tr\.row-selected td \{[^}]*background: #1d4ed8")
        self.assertIn("scrollIntoView", html)

    def test_the_nozzle_ledger_page_uses_the_same_shared_code(self):
        nozzle = Nozzle.objects.get(number=1)
        html = self.client.get(f"/reports/nozzle-ledger/?nozzle_id={nozzle.id}"
                               "&start_date=2026-07-23&end_date=2026-08-22").content.decode()
        self.assertIn("TableRowNavigation.init", html)
        self.assertIn("onArrowOutsideTableMode", html)


@unittest.skipUnless(NODE, "Node.js with the jsdom package is not installed (optional dev-only check)")
class AllNozzlesKeyboardBehaviourTests(AllNozzlesBase):
    def test_keyboard_navigation_behaves_as_specified(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "page.html"
            page.write_text(self.page(), encoding="utf-8")
            result = subprocess.run([NODE, str(HARNESS), str(page)], env=NODE_ENV,
                                    capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        checks = json.loads(result.stdout)
        self.assertGreaterEqual(len(checks), 30)
        failed = [name for name, ok in checks.items() if not ok]
        self.assertEqual(failed, [], f"failed browser-behaviour checks: {failed}")
