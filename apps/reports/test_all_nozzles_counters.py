"""
لیست اطلاعات فروش: the monthly counter columns کنتور اول ماه / کنتور آخر ماه.

  کنتور اول ماه = کنتور قبلی of the nozzle's FIRST RECORDED working day in the month
  کنتور آخر ماه = کنتور جدید of the nozzle's LAST RECORDED working day in the month

Taken from the real فاکتورهای فروش records -- never from the 1st / last calendar
day, never from record creation order. A nozzle with no record that month shows
"—" (a missing record is not a reading of 0), while a real 0 shows as 0.

Extra hand data on top of test_all_nozzles_report.AllNozzlesBase (that file's
month 1405/05 and 1405/06 figures are reused unchanged):

JALALI 1405/07 (2026-09-23 .. 2026-10-22) -- records created OUT OF ORDER, with gaps:
  nozzle 3: created first 2026-10-02 (700 -> 900, test 0), then 2026-09-25 (100 -> 700, test 5), rate 1200
            first = 100 (not 700, the lowest id) | last = 900
            operation 600+200 = 800 | test 5 | sales 595+200 = 795 | amount 795 x 1200 = 954,000
  nozzle 2: 2026-10-20 only (900 -> 950, test 0)   first 900 | last 950 | 50 | 0 | 50 | 60,000
  month totals: operation 850 | test 5 | sales 845 | amount 1,014,000
JALALI 1405/08 (from 2026-10-23): nozzle 5: 2026-10-25, 0 -> 300000   (the brief's example)
"""

import datetime
from decimal import Decimal

from apps.core.test_number_display import pdf_text, render_pdf_with_html
from apps.reports import services as report_services
from apps.reports.test_all_nozzles_report import (
    EXPECTED_05, EXPECTED_06, FIRST_LAST_05, FIRST_LAST_06, TOTALS_05, AllNozzlesBase,
    expected_row, fmt, pdf_summary, pdf_table_rows, screen_totals, table_rows,
)
from apps.sales.models import NozzleSale, SalesInvoice
from apps.stations.models import Nozzle
from apps.workday.models import DailyWorkingDay

D = Decimal
EXPECTED_07 = {3: (800, 5, 795, 954000), 2: (50, 0, 50, 60000)}
FIRST_LAST_07 = {3: (100, 900), 2: (900, 950)}
TOTALS_07 = (850, 5, 845, 1014000)
EXPECTED_08 = {5: (300000, 0, 300000, 360000000)}
FIRST_LAST_08 = {5: (0, 300000)}


class CounterBase(AllNozzlesBase):
    def add_sale(self, day, number, prev, new, test=0, rate=1200):
        wd, _ = DailyWorkingDay.objects.get_or_create(date=day)
        inv, _ = SalesInvoice.objects.get_or_create(working_day=wd, defaults={"operator": self.user})
        nozzle = Nozzle.objects.get(number=number)
        return NozzleSale.objects.create(sales_invoice=inv, nozzle=nozzle, previous_meter=D(prev), new_meter=D(new),
                                         test=D(test), sales_rate=D(rate))

    def setUp(self):
        super().setUp()
        tank = Nozzle.objects.get(number=1).tank
        Nozzle.objects.create(tank=tank, number=5)
        # month 07, deliberately created in reverse chronological order, with gaps around them
        self.add_sale(datetime.date(2026, 10, 2), 3, 700, 900, 0)
        self.add_sale(datetime.date(2026, 9, 25), 3, 100, 700, 5)
        self.add_sale(datetime.date(2026, 10, 20), 2, 900, 950, 0)
        # month 08: the brief's example
        self.add_sale(datetime.date(2026, 10, 25), 5, 0, 300000, 0)


class ServiceCounterTests(CounterBase):
    def test_first_and_last_counters_per_nozzle(self):
        for month, data in ((5, FIRST_LAST_05), (6, FIRST_LAST_06), (7, FIRST_LAST_07), (8, FIRST_LAST_08)):
            rows = {r["nozzle_number"]: r for r in report_services.all_nozzles_monthly_summary(1405, month)}
            for number, row in rows.items():
                first, last = data.get(number, (None, None))
                self.assertEqual(row["first_meter"], None if first is None else D(first), (month, number))
                self.assertEqual(row["last_meter"], None if last is None else D(last), (month, number))

    def test_counters_match_the_underlying_sales_records(self):
        """Independently, straight from the فاکتورهای فروش rows: earliest day's کنتور قبلی, latest day's کنتور جدید."""
        for month, (start, end) in ((5, (datetime.date(2026, 7, 23), datetime.date(2026, 8, 22))),
                                    (7, (datetime.date(2026, 9, 23), datetime.date(2026, 10, 22)))):
            rows = {r["nozzle_number"]: r for r in report_services.all_nozzles_monthly_summary(1405, month)}
            for number in range(1, 27):
                sales = sorted(
                    NozzleSale.objects.filter(nozzle__number=number, sales_invoice__working_day__date__range=(start, end)),
                    key=lambda s: s.sales_invoice.working_day.date)
                if not sales:
                    self.assertIsNone(rows[number]["first_meter"]); self.assertIsNone(rows[number]["last_meter"])
                else:
                    self.assertEqual(rows[number]["first_meter"], sales[0].previous_meter, (month, number))
                    self.assertEqual(rows[number]["last_meter"], sales[-1].new_meter, (month, number))

    def test_uses_recorded_days_not_calendar_edges_or_creation_order(self):
        row = {r["nozzle_number"]: r for r in report_services.all_nozzles_monthly_summary(1405, 7)}[3]
        self.assertEqual(row["first_meter"], D(100))      # day 3 of the month, created second (higher id)
        self.assertEqual(row["last_meter"], D(900))       # day 10 of the month, created first (lower id)

    def test_existing_calculations_are_unchanged(self):
        for month, data, totals_expected in ((5, EXPECTED_05, TOTALS_05), (6, EXPECTED_06, None),
                                            (7, EXPECTED_07, TOTALS_07), (8, EXPECTED_08, None)):
            rows = report_services.all_nozzles_monthly_summary(1405, month)
            for r in rows:
                op, test, sales, amount = data.get(r["nozzle_number"], (0, 0, 0, 0))
                self.assertEqual((r["total_operation"], r["total_test"], r["total_mechanical_sales"], r["total_amount"]),
                                 (D(op), D(test), D(sales), D(amount)), (month, r["nozzle_number"]))
            if totals_expected:
                t = report_services.all_nozzles_monthly_totals(rows)
                self.assertEqual((t["total_operation"], t["total_test"], t["total_mechanical_sales"], t["total_amount"]),
                                 tuple(D(x) for x in totals_expected))

    def test_26_rows_in_nozzle_order_for_every_month(self):
        for month in (5, 7, 8, 9):
            rows = report_services.all_nozzles_monthly_summary(1405, month)
            self.assertEqual([r["nozzle_number"] for r in rows], list(range(1, 27)))


class ScreenCounterTests(CounterBase):
    def test_columns_values_and_missing_markers(self):
        for month, data, first_last in ((5, EXPECTED_05, FIRST_LAST_05), (7, EXPECTED_07, FIRST_LAST_07),
                                        (8, EXPECTED_08, FIRST_LAST_08), (9, {}, {})):
            rows = table_rows(self.page(month))
            self.assertEqual(len(rows), 26)
            for r in rows:
                self.assertEqual(r, expected_row(int(r[0]), data, first_last), (month, r[0]))

    def test_the_brief_example_zero_then_300000(self):
        row = table_rows(self.page(8))[4]                       # nozzle 5
        self.assertEqual(row[:3], ["5", "0", "300,000"])

    def test_a_real_zero_reading_is_shown_as_0_not_as_missing(self):
        rows = table_rows(self.page(5))
        self.assertEqual(rows[0][1], "0")                       # nozzle 1: first previous meter is 0
        self.assertEqual(rows[2][1], "—")                       # nozzle 3: no record in month 05 at all

    def test_mechanical_sales_test_and_operation_keep_their_values(self):
        rows = table_rows(self.page(7))
        by_number = {int(r[0]): r for r in rows}
        self.assertEqual(by_number[3][3:], ["795", "5", "800"])         # sales, test, operation
        self.assertEqual(by_number[2][3:], ["50", "0", "50"])

    def test_total_amount_column_is_gone_from_the_table_but_the_summary_keeps_it(self):
        html = self.page(7)
        head = html.split('id="all-nozzles-table"', 1)[1].split("</thead>", 1)[0]
        self.assertNotIn("جمع مبلغ کل", head)
        self.assertEqual(len(table_rows(html)[0]), 6)
        summary = html.split('id="all-nozzles-totals"', 1)[1].split("</div>\n  </div>", 1)[0]
        self.assertIn("مجموع مبلغ کل", summary)
        self.assertEqual(screen_totals(html), tuple(fmt(x) for x in TOTALS_07))          # incl. 1,014,000

    def test_summary_totals_are_unchanged_for_the_original_months(self):
        self.assertEqual(screen_totals(self.page(5)), tuple(fmt(x) for x in TOTALS_05))
        self.assertEqual(screen_totals(self.page(9)), ("0", "0", "0", "0"))

    def test_viewing_changes_no_stored_data(self):
        before = list(NozzleSale.objects.values_list("id", "previous_meter", "new_meter", "test", "sales_rate").order_by("id"))
        for month in (5, 7, 8):
            self.page(month)
            self.client.get(self.print_url(month))
        self.assertEqual(before, list(NozzleSale.objects.values_list(
            "id", "previous_meter", "new_meter", "test", "sales_rate").order_by("id")))


class PdfCounterTests(CounterBase):
    def test_pdf_columns_values_and_summary_match_the_screen(self):
        for month in (5, 6, 7, 8, 9):
            screen_html = self.page(month)
            resp, html = render_pdf_with_html(self.client, self.print_url(month))
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.content.startswith(b"%PDF"))
            self.assertEqual(pdf_table_rows(html), table_rows(screen_html), month)
            self.assertEqual(pdf_summary(html), screen_totals(screen_html), month)

    def test_pdf_has_the_new_columns_in_order_and_keeps_the_summary_total_amount(self):
        resp, html = render_pdf_with_html(self.client, self.print_url(7))
        summary, main = html.split("print-summary", 1)[1].split("</table>", 1)
        self.assertIn("مجموع مبلغ کل", summary)
        self.assertNotIn("جمع مبلغ کل", main)
        head = main.split("<thead>", 1)[1].split("</thead>", 1)[0]
        import re
        self.assertEqual(re.findall(r"<th[^>]*>([^<]*)</th>", head),
                         ["شماره نازل", "کنتور اول ماه", "کنتور آخر ماه", "جمع فروش مکانیکی", "جمع آزمایش", "جمع کارکرد"])
        self.assertEqual(pdf_summary(html), tuple(fmt(x) for x in TOTALS_07))

    def test_pdf_example_values_and_file_text(self):
        resp, html = render_pdf_with_html(self.client, self.print_url(8))
        self.assertEqual(pdf_table_rows(html)[4][:3], ["5", "0", "300,000"])
        text = pdf_text(self.client.get(self.print_url(7)).content)
        for needle in ("1,014,000", "795", "900", "کنتور"):          # summary total amount, nozzle 3 sales + last counter
            self.assertIn(needle, text)
        self.assertNotIn("954,000", text)                            # per-nozzle amounts are no longer printed

    def test_pdf_is_still_one_portrait_page_with_unchanged_type_size(self):
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(self.client.get(self.print_url(7)).content))
        self.assertEqual(len(reader.pages), 1)
        box = reader.pages[0].mediabox
        self.assertLess(float(box.width), float(box.height))
        try:
            import pymupdf
        except ImportError:
            return
        doc = pymupdf.open(stream=self.client.get(self.print_url(7)).content, filetype="pdf")
        sizes = [span["size"] for block in doc[0].get_text("dict")["blocks"] if "lines" in block
                 for line in block["lines"] for span in line["spans"] if span["text"].strip().replace(",", "").isdigit()
                 and len(span["text"].strip()) >= 3]
        self.assertTrue(sizes)
        self.assertGreaterEqual(min(sizes), 10.4)               # 14px == 10.5pt, as before
