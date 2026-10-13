"""Source-specific browser crawlers for the public vehicle listings."""

import os
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .models import Car, CarCard

HEADERS = {"User-Agent": "CarNab catalog bot/1.0 (public listings; contact: local-admin)"}
PROXY = os.environ.get("CRAWLER_HTTP_PROXY", "http://127.0.0.1:2081")
DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
JUNK_SOURCES = {"divar", "sheypoor"}
UNSET = object()


def normalize_text(value):
    value = (
        (value or "").translate(DIGITS).replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ")
    )
    return re.sub(r"\s+", " ", value.replace("-", " ")).strip()


def parse_number(value):
    value = re.sub(r"[^0-9]", "", (value or "").translate(DIGITS))
    return int(value) if value else None


def find_year(value):
    match = re.search(r"(?<!\d)(1[34]\d{2}|20\d{2})(?!\d)", (value or "").translate(DIGITS))
    return int(match.group(1)) if match else None


def find_mileage(value):
    text = (value or "").translate(DIGITS)
    if re.search(r"صفر\s*کیلومتر|خودرو\s*صفر", text):
        return 0
    match = re.search(r"([\d,]+)\s*(?:کیلومتر|km)", text, re.IGNORECASE)
    return parse_number(match.group(1)) if match else None


def generic_details(text):
    text = normalize_text(text)
    prices = re.findall(r"([\d,]+)\s*تومان", text.translate(DIGITS))
    return {
        "year": find_year(text),
        "mileage": find_mileage(text),
        "price": parse_number(prices[-1]) if prices else None,
        "transmission": "اتوماتیک" if "اتومات" in text else ("دنده‌ای" if "دنده" in text else ""),
        "fuel": "بنزینی" if "بنزین" in text else "",
    }


def model_parts(title, car_type=""):
    title = normalize_text(title).strip(" |،")
    title = re.sub(r"^خرید\s+اقساطی\s+", "", title)
    # Listing titles from Divar/Sheypoor contain model/year/colour; retain only
    # the model portion for matching while preserving the original title below.
    model = re.split(r"\s+(?:مدل\s*)?(?:1[34]\d{2}|20\d{2})\b", title, maxsplit=1)[0].strip()
    if not model:
        model = title
    typed = normalize_text(car_type)
    full = model if typed and typed in model else " ".join(x for x in (model, typed) if x).strip()
    return (
        full[:255],
        model[:120],
        (normalize_text(car_type)[:255] if car_type is not None else None),
    )


def upsert_record(
    source,
    href,
    title,
    text,
    car_type="",
    year=None,
    mileage=None,
    image="",
    price=UNSET,
    preserve_title=False,
):
    details = generic_details(text)
    title, model, car_type = (
        (
            normalize_text(title)[:255],
            normalize_text(title)[:120],
            normalize_text(car_type)[:255] if car_type is not None else None,
        )
        if preserve_title
        else model_parts(title, car_type)
    )
    if year is not None:
        details["year"] = year
    if mileage is not None:
        details["mileage"] = mileage
    if price is not UNSET:
        details["price"] = price
    defaults = {
        "source": source,
        "title": title,
        "type": car_type,
        "brand": model.split()[0] if model else "",
        "model_name": model,
        "image_url": image,
        "is_active": True,
        **details,
    }
    # A marketplace can change the canonical listing URL between crawls.  The
    # image URL is the stable identity used by recrawling, but only within one
    # source so identical CDN assets on different marketplaces remain distinct.
    car = Car.objects.filter(source_url=href).first()
    if car is None and image:
        car = Car.objects.filter(source=source, image_url=image).first()
    if car is None:
        return Car.objects.create(source_url=href, **defaults)
    if car.source_url != href:
        car.source_url = href
    for field, value in defaults.items():
        setattr(car, field, value)
    car.save()
    return car


class BaseCrawler:
    source = ""
    start_url = ""
    allowed_hosts = ()
    link_selector = "a[href]"

    def browser(self):
        from playwright.sync_api import sync_playwright

        return sync_playwright()

    def fetch_html(self, limit):
        """Render a listing feed, retaining cards removed by virtualized UIs."""
        try:
            with self.browser() as playwright:
                browser = playwright.chromium.launch(headless=True, proxy={"server": PROXY})
                page = browser.new_page(
                    user_agent=HEADERS["User-Agent"], viewport={"width": 1440, "height": 1000}
                )
                try:
                    page.goto(self.start_url, wait_until="domcontentloaded", timeout=90000)
                    page.wait_for_timeout(2500)
                    cards = {}
                    idle = 0
                    for _ in range(600):
                        # Divar, Sheypoor, Bama, and Khodro45 virtualize their feeds:
                        # previously loaded cards may disappear from page.content() while
                        # scrolling.  Save each anchor as it appears instead.
                        visible = page.locator(self.link_selector).evaluate_all("""
                            nodes => nodes.map(node => ({href: node.href, html: node.outerHTML}))
                        """)
                        for card in visible:
                            if card["href"]:
                                cards[card["href"]] = card["html"]
                        if len(cards) >= limit:
                            break
                        before = len(cards)
                        page.evaluate(
                            "window.scrollBy(0, Math.max(window.innerHeight * 0.85, 700))"
                        )
                        page.wait_for_timeout(850)
                        visible = page.locator(self.link_selector).evaluate_all("""
                            nodes => nodes.map(node => ({href: node.href, html: node.outerHTML}))
                        """)
                        for card in visible:
                            if card["href"]:
                                cards[card["href"]] = card["html"]
                        if len(cards) <= before:
                            idle += 1
                        else:
                            idle = 0
                        if idle >= 25:
                            break
                    return "<html><body>" + "".join(cards.values()) + "</body></html>"
                finally:
                    browser.close()
        except ImportError:
            response = requests.get(
                self.start_url, headers=HEADERS, proxies={"http": PROXY, "https": PROXY}, timeout=60
            )
            response.raise_for_status()
            return response.text

    def records(self, html):
        soup = BeautifulSoup(html, "html.parser")
        for anchor in soup.select(self.link_selector):
            href = urljoin(self.start_url, anchor.get("href", ""))
            if not href or not any(host in href for host in self.allowed_hosts):
                continue
            yield anchor, href

    def fetch_detail(self, href):
        try:
            response = requests.get(
                href, headers=HEADERS, proxies={"http": PROXY, "https": PROXY}, timeout=10
            )
            response.raise_for_status()
            return BeautifulSoup(response.text, "html.parser")
        except requests.RequestException:
            return BeautifulSoup("", "html.parser")

    def crawl(self, limit=500):
        seen = set()
        html = self.fetch_html(limit)
        for anchor, href in self.records(html):
            if href in seen:
                continue
            seen.add(href)
            self.parse_and_save(anchor, href)
            if len(seen) >= limit:
                break
        return min(len(seen), limit)

    def parse_and_save(self, anchor, href):
        text = anchor.get_text(" ", strip=True)
        image = anchor.select_one("img")
        upsert_record(self.source, href, text, text, image=image.get("src", "") if image else "")

    def image_url(self, root):
        """Return a real remote image URL, never a lazy-loader data URI."""
        for image in root.select("img"):
            candidates = [image.get("src"), image.get("data-src"), image.get("data-lazy-src")]
            candidates.extend((image.get("srcset") or "").split(","))
            for candidate in candidates:
                candidate = (candidate or "").strip()
                if not candidate:
                    continue
                candidate = candidate.split()[0]
                if candidate.startswith(("http://", "https://")):
                    return candidate
        return ""


class HamrahMechanicCrawler(BaseCrawler):
    source, start_url, allowed_hosts = (
        "hamrah",
        "https://www.hamrah-mechanic.com/cars-for-sale/",
        ("hamrah-mechanic.com",),
    )
    link_selector = "a[href*='/cars-for-sale/']"

    def records(self, html):
        for anchor, href in super().records(html):
            if re.search(r"/cars-for-sale/[^/]+/[^/]+/\d+/?$", href):
                yield anchor, href

    def parse_and_save(self, anchor, href):
        root = anchor.select_one("[class*='carCard_card-container__n8oCD']") or anchor
        name = root.select_one("[class*='car-name__']")
        identity = root.select_one("[class*='car-name-year-type-container']")
        parts = (
            [x.get_text(" ", strip=True) for x in identity.find_all(recursive=False)]
            if identity
            else []
        )
        parts = [x for x in parts if x and x not in {"|", "-"}]
        title = (
            name.get_text(" ", strip=True)
            if name
            else (parts[0] if parts else root.get_text(" ", strip=True))
        )
        year = find_year(" ".join(parts))
        large = root.select("[class*='large-text']")
        car_type = next((x.get_text(" ", strip=True) for x in large if x is not name), "")
        text = root.get_text(" ", strip=True)
        upsert_record(
            self.source,
            href,
            title,
            text,
            car_type=car_type,
            year=year,
            mileage=0 if root.select_one("[class*='zero-kilometer-badge']") else find_mileage(text),
            image=self.image_url(root),
        )


class Khodro45Crawler(BaseCrawler):
    source, start_url, allowed_hosts = (
        "khodro45",
        "https://khodro45.com/used-car/",
        ("khodro45.com",),
    )
    link_selector = "a[href*='/used-car/']"

    def records(self, html):
        for anchor, href in super().records(html):
            if href.rstrip("/").count("/") >= 4:
                yield anchor, href

    def parse_and_save(self, anchor, href):
        text = anchor.get_text(" ", strip=True)
        typed = anchor.select_one("p.whitespace-pre-line.font-normal.text-xs.text-secondary-700")
        car_type = (typed.get("title") or typed.get_text(" ", strip=True)) if typed else ""
        make = anchor.select_one("span.text-secondary-1000.shrink-0")
        trim = anchor.select_one("span.text-secondary-1000.block.w-full")
        title = " ".join(part.get_text(" ", strip=True) for part in (make, trim) if part) or text
        price_node = anchor.select_one(
            "p.whitespace-pre-line.font-semibold.text-base.text-secondary-1000"
        )
        upsert_record(
            self.source,
            href,
            title,
            text,
            car_type=car_type,
            price=parse_number(price_node.get_text(" ", strip=True)) if price_node else None,
            image=self.image_url(anchor),
        )


class BamaCrawler(BaseCrawler):
    source, start_url, allowed_hosts = "bama", "https://bama.ir/car", ("bama.ir",)
    link_selector = "a[href*='/car/detail-']"

    def parse_and_save(self, anchor, href):
        title_node = anchor.select_one("span[class*='text-base'][class*='font-semibold']")
        typed = anchor.select_one(
            "span[class*='font-normal'][class*='truncate'][class*='text-neutral-10']"
        )
        title = (
            title_node.get_text(" ", strip=True) if title_node else anchor.get_text(" ", strip=True)
        )
        car_type = typed.get_text(" ", strip=True) if typed else ""
        text = anchor.get_text(" ", strip=True)
        image = anchor.select_one("img")
        upsert_record(
            self.source,
            href,
            title,
            text,
            car_type=car_type,
            year=find_year(text),
            mileage=find_mileage(text),
            image=image.get("src", "") if image else "",
        )


class KarnamehCrawler(BaseCrawler):
    source, start_url, allowed_hosts = (
        "karnameh",
        "https://karnameh.com/buy-used-cars",
        ("karnameh.com",),
    )
    # Listings are links directly under a MUI layout (not necessarily <article>).
    link_selector = "a[href*='/used-cars/']"

    def fetch_html(self, limit):
        """Collect Karnameh's paginated result pages (20 listings per page)."""
        try:
            with self.browser() as playwright:
                browser = playwright.chromium.launch(headless=True, proxy={"server": PROXY})
                page = browser.new_page(
                    user_agent=HEADERS["User-Agent"], viewport={"width": 1440, "height": 1000}
                )
                cards = {}
                try:
                    for page_number in range(1, 40):
                        url = (
                            self.start_url
                            if page_number == 1
                            else f"{self.start_url}?page={page_number}"
                        )
                        page.goto(url, wait_until="domcontentloaded", timeout=90000)
                        page.wait_for_timeout(1200)
                        visible = page.locator(self.link_selector).evaluate_all("""
                            nodes => nodes.map(node => ({href: node.href, html: node.outerHTML}))
                        """)
                        before = len(cards)
                        for card in visible:
                            if re.search(r"/used-cars/[^/?#]+/?$", card["href"]):
                                cards[card["href"]] = card["html"]
                        if len(cards) >= limit or len(cards) == before:
                            break
                    return "<html><body>" + "".join(cards.values()) + "</body></html>"
                finally:
                    browser.close()
        except ImportError:
            return super().fetch_html(limit)

    def records(self, html):
        for anchor, href in super().records(html):
            if re.search(r"/used-cars/[^/?#]+/?$", href):
                yield anchor, href

    def parse_and_save(self, anchor, href):
        root = anchor.find_parent("article") or anchor
        heading = root.select_one("h2")
        # MUI generates a different hash class per deployment, so only rely on
        # the stable component classes. Type is a short non-numeric paragraph;
        # when it is absent, preserve NULL rather than using mileage/labels.
        typed = next(
            (
                node
                for node in root.select("p.MuiTypography-root")
                if (candidate := normalize_text(node.get_text(" ", strip=True)))
                and candidate not in {"قیمت نقدی", "قیمت اقساطی"}
                and not re.search(r"تومان|کیلومتر|قیمت", candidate)
                and not re.fullmatch(r"[\d,]+", candidate)
            ),
            None,
        )
        raw_title = (
            heading.get_text(" ", strip=True) if heading else anchor.get_text(" ", strip=True)
        )
        title = normalize_text(
            re.split(r"\s+مدل\s+(?:1[34]\d{2}|20\d{2})\b", raw_title, maxsplit=1)[0]
        )
        car_type = typed.get_text(" ", strip=True) if typed else ""
        text = root.get_text(" ", strip=True)
        detail = self.fetch_detail(href)
        detail_type = detail.select_one("p.MuiTypography-root.MuiTypography-body1.muirtl-wb83bv")
        if detail_type:
            car_type = detail_type.get_text(" ", strip=True)
            if normalize_text(car_type) not in normalize_text(title):
                title = f"{title} {car_type}".strip()
        detail_price = detail.select_one(
            "span.MuiTypography-root.MuiTypography-body1.muirtl-dgbnve"
        )
        detail_price_value = (
            parse_number(detail_price.get_text(" ", strip=True)) if detail_price else None
        )
        cash_label = next(
            (
                node
                for node in root.select("p")
                if normalize_text(node.get_text(" ", strip=True)) == "قیمت نقدی"
            ),
            None,
        )
        raw_price = None
        if cash_label:
            # Cash values are either one span ("525") or split over adjacent
            # spans ("1,896" + ",000,000"). Prefer the containing row so we
            # do not accidentally select the installment price later in card.
            row = cash_label.parent
            spans = [
                node.get_text("", strip=True)
                for node in row.select("span")
                if re.fullmatch(r"[\d۰-۹٠-٩,]+", node.get_text("", strip=True))
            ]
            if spans:
                raw_price = parse_number("".join(spans[:2]))
        if raw_price is None:
            value = root.select_one("span[class*='muirtl-26h4um']")
            if value:
                raw_price = parse_number(value.get_text("", strip=True))
        raw_price = detail_price_value or raw_price
        upsert_record(
            self.source,
            href,
            title,
            text,
            car_type=car_type or None,
            year=find_year(raw_title),
            price=(
                raw_price
                if raw_price and raw_price >= 100_000_000
                else raw_price * 1_000_000
                if raw_price is not None
                else None
            ),
            image=self.image_url(root),
            preserve_title=True,
        )


class DivarCrawler(BaseCrawler):
    source, start_url, allowed_hosts = (
        "divar",
        "https://divar.ir/s/iran/car?map_interaction=search_this_area_disabled",
        ("divar.ir",),
    )
    link_selector = "a[href*='/v/']"

    def parse_and_save(self, anchor, href):
        root = anchor.select_one(".kt-post-card__body") or anchor
        heading = root.select_one(".kt-post-card__title")
        text = root.get_text(" ", strip=True)
        image = root.select_one("img")
        upsert_record(
            self.source,
            href,
            heading.get_text(" ", strip=True) if heading else text,
            text,
            mileage=find_mileage(text),
            image=image.get("src", "") if image else "",
            preserve_title=True,
        )


class SheypoorCrawler(BaseCrawler):
    source, start_url, allowed_hosts = (
        "sheypoor",
        "https://www.sheypoor.com/s/iran/car",
        ("sheypoor.com",),
    )
    link_selector = "a[data-test-id^='ad-item-']"

    def parse_and_save(self, anchor, href):
        heading = anchor.select_one("h2")
        text = anchor.get_text(" ", strip=True)
        image = anchor.select_one("img")
        mileage = find_mileage(text)
        year = find_year(text)
        detail = self.fetch_detail(href)
        detail_specs = detail.select("span.text-center.text-heading-4-normal")
        # Sheypoor uses the same span class for year and mileage. The first
        # value is the model year and the second value is the mileage.
        if detail_specs:
            year = find_year(detail_specs[0].get_text(" ", strip=True)) or year
        if len(detail_specs) > 1:
            mileage = parse_number(detail_specs[1].get_text(" ", strip=True))
        if mileage is None:
            heading_text = heading.get_text(" ", strip=True) if heading else ""
            numeric = [
                parse_number(x.get_text(" ", strip=True))
                for x in anchor.select("div")
                if re.fullmatch(r"[\d۰-۹,]+", x.get_text(" ", strip=True))
            ]
            mileage = next(
                (x for x in numeric if x is not None and str(x) not in heading_text), None
            )
        price_node = anchor.select_one("span.text-heading-4-bolder.desktop\\:text-heading-5-bolder")
        upsert_record(
            self.source,
            href,
            heading.get_text(" ", strip=True) if heading else text,
            text,
            year=year,
            mileage=mileage,
            price=parse_number(price_node.get_text(" ", strip=True)) if price_node else None,
            image=image.get("src", "") if image else "",
            preserve_title=True,
        )


CRAWLERS = {
    c.source: c
    for c in (
        HamrahMechanicCrawler,
        Khodro45Crawler,
        BamaCrawler,
        KarnamehCrawler,
        DivarCrawler,
        SheypoorCrawler,
    )
}


def rebuild_cards():
    """Backward-compatible entry point for callers of the old service."""
    from .card_builder import process_car_cards

    process_car_cards()
    return CarCard.objects.count()


def crawl_sources(selected="all", limit=500):
    names = list(CRAWLERS) if selected == "all" else [selected]
    total = 0
    for name in names:
        total += CRAWLERS[name]().crawl(limit=limit)
        time.sleep(2)
    # from .card_builder import process_car_cards
    # process_car_cards()
    return total


def recrawl_source(source, limit=500):
    """Refresh one marketplace and remove stale cars from comparison cards.

    Cars are retained as historical rows, but are marked inactive and detached
    from the ``cars_carcard_cars`` join table until the source crawler sees
    them again.  ``upsert_record`` reactivates an existing row by source URL or
    image URL, preventing duplicate rows when a marketplace changes a URL.
    """
    if source not in CRAWLERS:
        raise ValueError(f"Unknown source: {source}")
    Car.objects.filter(source=source).update(is_active=False)
    through = CarCard.cars.through
    through.objects.filter(car__source=source, car__is_active=False).delete()
    count = CRAWLERS[source]().crawl(limit=limit)
    from .card_builder import process_car_cards

    process_car_cards()
    return count


def recrawl_sources(selected="all", limit=500):
    names = list(CRAWLERS) if selected == "all" else [selected]
    total = 0
    for name in names:
        total += recrawl_source(name, limit=limit)
        time.sleep(2)
    return total
