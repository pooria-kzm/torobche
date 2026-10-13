from unittest.mock import patch

from django.test import SimpleTestCase

from .services import (
    BamaCrawler,
    HamrahMechanicCrawler,
    KarnamehCrawler,
    Khodro45Crawler,
    SheypoorCrawler,
    find_mileage,
)


class SourceParserTests(SimpleTestCase):
    def capture(self, crawler, html):
        rows = list(crawler.records(html))
        self.assertEqual(len(rows), 1)
        values = []
        with patch(
            "cars.services.upsert_record",
            side_effect=lambda *args, **kwargs: values.append((args, kwargs)),
        ):
            crawler.parse_and_save(*rows[0])
        return values[0]

    def test_hamrah_extracts_type_and_zero_mileage(self):
        html = """<a href="/cars-for-sale/x/y/1/"><div class="carCard_card-container__n8oCD">
          <div class="carCard_card-container__car-name__OoBDR">پژو ۲۰۶</div>
          <div class="carCard_card-container__car-name-year-type-container__GgYDd"><div>پژو ۲۰۶</div><div>۱۴۰۰</div><div class="carCard_card-container__large-text__wTMUf">EX</div></div>
          <div class="carCard_image-container__zero-kilometer-badge__YQjTS">صفر کیلومتر</div></div></a>"""
        _args, kwargs = self.capture(HamrahMechanicCrawler(), html)
        self.assertEqual(kwargs["car_type"], "EX")
        self.assertEqual(kwargs["mileage"], 0)

    def test_hamrah_ignores_data_uri_image_placeholder(self):
        html = """<a href="/cars-for-sale/x/y/1/"><div class="carCard_card-container__n8oCD">
          <div class="carCard_card-container__car-name__OoBDR">پژو ۲۰۶</div>
          <img src="data:image/gif;base64,placeholder"><img src="https://ncdn.hamrah-mechanic.com/car.jpg?width=475">
          </div></a>"""
        _, kwargs = self.capture(HamrahMechanicCrawler(), html)
        self.assertEqual(kwargs["image"], "https://ncdn.hamrah-mechanic.com/car.jpg?width=475")

    def test_bama_extracts_type(self):
        html = """<a href="https://bama.ir/car/detail-test"><span class="text-base font-semibold truncate">پژو ۲۰۶</span>
          <span class="text-sm font-normal truncate text-neutral-10">اتوماتیک توربو ساده</span><span>۱۴۰۰ صفر کیلومتر</span></a>"""
        _, kwargs = self.capture(BamaCrawler(), html)
        self.assertEqual(kwargs["car_type"], "اتوماتیک توربو ساده")
        self.assertEqual(kwargs["mileage"], 0)

    def test_karnameh_separates_model_and_year(self):
        html = """<article><a href="https://karnameh.com/used-cars/abc"><h2>پژو 206 مدل 1397</h2><p class="MuiTypography-root">تیپ ۲</p><p>100,000 کیلومتر</p></a></article>"""
        args, kwargs = self.capture(KarnamehCrawler(), html)
        self.assertEqual(args[2], "پژو 206")
        self.assertEqual(kwargs["year"], 1397)
        self.assertEqual(kwargs["car_type"], "تیپ ۲")

    def test_karnameh_accepts_links_without_article_wrapper(self):
        html = """<div><a href="https://karnameh.com/used-cars/abc"><h2>پژو 206 مدل 1397</h2>
          <p class="MuiTypography-root">تیپ ۲</p></a></div>"""
        rows = list(KarnamehCrawler().records(html))
        self.assertEqual(len(rows), 1)

    def test_karnameh_cash_price_and_missing_type(self):
        html = """<article><a href="https://karnameh.com/used-cars/abc"><h2>دنا مدل 1400</h2>
          <p>قیمت نقدی</p><span class="MuiTypography-root MuiTypography-body1 muirtl-26h4um">525</span></a></article>"""
        _, kwargs = self.capture(KarnamehCrawler(), html)
        self.assertIsNone(kwargs["car_type"])
        self.assertEqual(kwargs["price"], 525_000_000)

    def test_karnameh_dynamic_type_and_split_cash_price(self):
        html = """<a href="https://karnameh.com/used-cars/abc"><h2 class="MuiTypography-root">تارا دنده‌ای مدل 1402</h2>
          <p class="MuiTypography-root MuiTypography-body1 muirtl-t81sjj">V1</p>
          <div><p>قیمت نقدی</p><span class="MuiTypography-root muirtl-26h4um">1,896</span><span class="MuiTypography-root muirtl-12g707e">,000,000</span></div></a>"""
        args, kwargs = self.capture(KarnamehCrawler(), html)
        self.assertEqual(args[2], "تارا دنده ای")
        self.assertEqual(kwargs["year"], 1402)
        self.assertEqual(kwargs["car_type"], "V1")
        self.assertEqual(kwargs["price"], 1_896_000_000)

    def test_khodro45_title_type_and_price(self):
        html = """<a href="https://khodro45.com/used-car/dana-plus/1"><span class="text-secondary-1000 shrink-0 whitespace-pre-line text-sm font-semibold">دنا</span>
          <span class="text-secondary-1000 block w-full min-w-0 overflow-hidden text-ellipsis text-sm font-semibold" title="پلاس">پلاس</span>
          <p class="whitespace-pre-line font-normal text-xs text-secondary-700" title="اتوماتیک توربو">اتوماتیک توربو</p>
          <p class="whitespace-pre-line font-semibold text-base text-secondary-1000">2,925,450,000</p></a>"""
        args, kwargs = self.capture(Khodro45Crawler(), html)
        self.assertEqual(args[2], "دنا پلاس")
        self.assertEqual(kwargs["car_type"], "اتوماتیک توربو")
        self.assertEqual(kwargs["price"], 2_925_450_000)

    def test_sheypoor_persian_price(self):
        html = """<a data-test-id="ad-item-1" href="https://www.sheypoor.com/x"><h2>خودرو</h2>
          <span class="text-heading-4-bolder desktop:text-heading-5-bolder">۴۹۰,۰۰۰,۰۰۰</span></a>"""
        _, kwargs = self.capture(SheypoorCrawler(), html)
        self.assertEqual(kwargs["price"], 490_000_000)

    def test_zero_mileage_tag(self):
        self.assertEqual(find_mileage("خودرو صفر"), 0)
