#!/usr/bin/env python3

import json
import os
import subprocess
import sys
import time
import smtplib
import traceback
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# Własny katalog przeglądarek Playwrighta.
# Domyślny wspólny cache (~/.cache/ms-playwright) bywa czyszczony przez
# `playwright install` uruchomiony w innym projekcie na tym samym koncie -
# wtedy znika binarka Chromium i scraper przestaje działać bez ostrzeżenia.
if not os.getenv("PLAYWRIGHT_BROWSERS_PATH"):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(BASE_DIR / ".playwright")

URLS_FILE = BASE_DIR / "urls.txt"
STATUS_FILE = BASE_DIR / "last_run.json"
DEFAULT_URLS = [
    "https://www.pracuj.pl/praca/zagranica;r,17?sc=0",
    "https://www.pracuj.pl/praca/zagranica;r,17?sc=0&pn=2",
    "https://www.pracuj.pl/praca/zagranica;r,17?sc=0&pn=3",
]

COUNTRIES_INCLUDE = [c.strip().lower() for c in os.getenv("COUNTRIES_INCLUDE", "").split(",") if c.strip()]
COUNTRIES_EXCLUDE = [c.strip().lower() for c in os.getenv("COUNTRIES_EXCLUDE", "").split(",") if c.strip()]

SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")


def load_urls():
    if URLS_FILE.exists():
        urls = [u.strip() for u in URLS_FILE.read_text(encoding="utf-8").splitlines() if u.strip() and not u.strip().startswith("#")]
        if urls:
            return urls
    return DEFAULT_URLS


def write_status(ok, count=0, error=None):
    STATUS_FILE.write_text(json.dumps({
        "finished": datetime.now().isoformat(),
        "ok": ok,
        "count": count,
        "error": error,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def install_browser():
    print("  Brak binarki Chromium - instaluję do "
          f"{os.environ['PLAYWRIGHT_BROWSERS_PATH']}")
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True, text=True, timeout=1800,
    )
    print(result.stdout[-2000:])
    if result.returncode != 0:
        print(result.stderr[-2000:])
        raise RuntimeError(f"playwright install chromium zakończone kodem {result.returncode}")
    print("  Chromium zainstalowany")


def launch_browser(p):
    try:
        return p.chromium.launch(headless=True)
    except Exception as e:
        if "Executable doesn't exist" not in str(e):
            raise
        install_browser()
        return p.chromium.launch(headless=True)


def extract_country(region_text):
    if not region_text:
        return ""
    parts = [p.strip() for p in region_text.split(",")]
    return parts[-1]


def country_matches(country):
    country_lower = country.lower()
    if COUNTRIES_INCLUDE:
        if not any(inc in country_lower for inc in COUNTRIES_INCLUDE):
            return False
    if COUNTRIES_EXCLUDE:
        if any(exc in country_lower for exc in COUNTRIES_EXCLUDE):
            return False
    return True


def dismiss_overlays(page):
    page.evaluate('''() => {
        document.querySelectorAll(
            'dialog, [id="popupContainer"], [class*="cookie"], [class*="modal"]'
        ).forEach(el => el.remove());
    }''')


def expand_multi_location_offers(page):
    page.evaluate('''() => {
        document.querySelectorAll('[data-test-location="multiple"] [role="button"]')
            .forEach(btn => btn.click());
    }''')
    page.wait_for_timeout(3000)


def scrape_offers(page):
    dismiss_overlays(page)
    expand_multi_location_offers(page)

    return page.evaluate('''() => {
        const results = [];
        const selectors = ['[data-test="default-offer"]', '[data-test="promoted-offer"]'];
        for (const sel of selectors) {
            const offers = document.querySelectorAll(sel);
            for (const offer of offers) {
                const isMulti = offer.getAttribute('data-test-location') === 'multiple';

                if (isMulti) {
                    const titleEl = offer.querySelector('[data-test="offer-title"]');
                    const salaryEl = offer.querySelector('[data-test="offer-salary"]');
                    const title = titleEl ? titleEl.textContent.trim() : '';
                    const salary = salaryEl ? salaryEl.textContent.trim().replace(/\\u00a0/g, ' ') : '';
                    const locationLinks = offer.querySelectorAll('[data-test="link-offer"]');
                    const locations = [];
                    for (const loc of locationLinks) {
                        locations.push({
                            region: loc.textContent.trim(),
                            link: loc.getAttribute('href') || '',
                        });
                    }
                    if (locations.length > 0) {
                        results.push({
                            title: title,
                            salary: salary,
                            multi: true,
                            locations: locations,
                        });
                    }
                } else {
                    const titleEl = offer.querySelector('[data-test="offer-title"] a')
                        || offer.querySelector('[data-test="link-offer-title"]');
                    const salaryEl = offer.querySelector('[data-test="offer-salary"]');
                    const regionEl = offer.querySelector('[data-test="text-region"]');
                    results.push({
                        title: titleEl ? titleEl.textContent.trim() : '',
                        link: titleEl ? titleEl.getAttribute('href') : '',
                        salary: salaryEl ? salaryEl.textContent.trim().replace(/\\u00a0/g, ' ') : '',
                        region: regionEl ? regionEl.textContent.trim() : '',
                        multi: false,
                    });
                }
            }
        }
        return results;
    }''')


def send_email(offers):
    if not all([SMTP_SERVER, SMTP_USERNAME, SMTP_PASSWORD, EMAIL_FROM, EMAIL_TO]):
        print("BŁĄD: Brak konfiguracji SMTP w .env")
        sys.exit(1)

    today = datetime.now().strftime("%Y-%m-%d")
    subject = f"Pracuj.pl — nowe oferty zagraniczne ({today})"

    lines = []
    for o in offers:
        salary = o["salary"] if o["salary"] else "BRAK"
        if o.get("multi"):
            countries = ", ".join(loc["region"] for loc in o["locations"])
            links = " | ".join(loc["link"] for loc in o["locations"])
            lines.append(f'{o["title"]};{salary};WIELE LOKALIZACJI ({countries});{links}')
        else:
            country = extract_country(o["region"])
            lines.append(f'{o["title"]};{salary};{country};{o["link"]}')

    body = "\n".join(lines)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    html_rows = ""
    for o in offers:
        salary = o["salary"] if o["salary"] else "BRAK"
        if o.get("multi"):
            countries = ", ".join(loc["region"] for loc in o["locations"])
            links_html = "<br>".join(
                f'<a href="{loc["link"]}">{loc["region"]}</a>'
                for loc in o["locations"]
            )
            html_rows += f"""<tr>
            <td style="padding:6px;border:1px solid #ddd">{o["title"]}</td>
            <td style="padding:6px;border:1px solid #ddd">{salary}</td>
            <td style="padding:6px;border:1px solid #ddd">WIELE LOKALIZACJI<br><small>{countries}</small></td>
            <td style="padding:6px;border:1px solid #ddd">{links_html}</td>
        </tr>"""
        else:
            country = extract_country(o["region"])
            html_rows += f"""<tr>
            <td style="padding:6px;border:1px solid #ddd">{o["title"]}</td>
            <td style="padding:6px;border:1px solid #ddd">{salary}</td>
            <td style="padding:6px;border:1px solid #ddd">{country}</td>
            <td style="padding:6px;border:1px solid #ddd"><a href="{o["link"]}">Link</a></td>
        </tr>"""

    html = f"""<html><body>
    <h2>Oferty zagraniczne z Pracuj.pl — {today}</h2>
    <p>Znaleziono {len(offers)} ofert spełniających kryteria.</p>
    <table style="border-collapse:collapse;width:100%">
        <tr style="background:#f0f0f0">
            <th style="padding:6px;border:1px solid #ddd;text-align:left">Nazwa oferty</th>
            <th style="padding:6px;border:1px solid #ddd;text-align:left">Widełki</th>
            <th style="padding:6px;border:1px solid #ddd;text-align:left">Kraj</th>
            <th style="padding:6px;border:1px solid #ddd;text-align:left">Link</th>
        </tr>
        {html_rows}
    </table>
    </body></html>"""

    msg.attach(MIMEText(body, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())

    print(f"Email wysłany do {EMAIL_TO}")


def main():
    all_offers = []
    seen_links = set()
    failed_urls = []
    urls = load_urls()

    stealth = Stealth()

    with stealth.use_sync(sync_playwright()) as p:
        browser = launch_browser(p)
        page = browser.new_page(viewport={"width": 1920, "height": 1080}, locale="pl-PL")

        for i, url in enumerate(urls, 1):
            print(f"[{i}/{len(urls)}] {url}")

            offers = None
            for attempt in range(1, 4):
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(10000)

                    if "Just a moment" in page.title():
                        print(f"  Cloudflare (próba {attempt}/3)")
                        if attempt < 3:
                            page.wait_for_timeout(15000)
                            continue
                        print("  BŁĄD: Cloudflare nie przepuścił — pomijam")
                        break

                    offers = scrape_offers(page)
                    break
                except Exception as e:
                    print(f"  BŁĄD (próba {attempt}/3): {e}")
                    if attempt < 3:
                        time.sleep(10 * attempt)
                        try:
                            page.close()
                            page = browser.new_page(viewport={"width": 1920, "height": 1080}, locale="pl-PL")
                        except Exception:
                            pass

            if offers is None:
                print("  Pominięto po 3 nieudanych próbach")
                failed_urls.append(url)
                continue

            print(f"  Znaleziono {len(offers)} ofert")

            for o in offers:
                if o.get("multi"):
                    locations = o["locations"]
                    new_locs = [loc for loc in locations if loc["link"] not in seen_links]
                    for loc in new_locs:
                        seen_links.add(loc["link"])

                    if not o["title"] or not new_locs:
                        continue

                    matched = [loc for loc in new_locs if country_matches(extract_country(loc["region"]))]
                    rejected = [loc for loc in new_locs if not country_matches(extract_country(loc["region"]))]

                    for loc in rejected:
                        print(f"  - {o['title']} | {extract_country(loc['region'])} (odfiltrowany)")

                    if matched:
                        o["locations"] = new_locs
                        all_offers.append(o)
                        countries = ", ".join(extract_country(loc["region"]) for loc in new_locs)
                        print(f"  + {o['title']} | WIELE LOKALIZACJI ({countries})")
                else:
                    if o["link"] in seen_links:
                        continue
                    seen_links.add(o["link"])

                    country = extract_country(o["region"])
                    if not country or not o["title"] or not o["link"]:
                        continue

                    if country_matches(country):
                        all_offers.append(o)
                        print(f"  + {o['title']} | {country}")
                    else:
                        print(f"  - {o['title']} | {country} (odfiltrowany)")

        browser.close()

    print(f"\nRazem ofert po filtrach: {len(all_offers)}")

    # Gdy żaden URL się nie udał, nie kasujemy ostatnich dobrych wyników -
    # inaczej awaria scrapera wygląda w panelu jak "brak ofert".
    if failed_urls and len(failed_urls) == len(urls):
        raise RuntimeError(f"Nie udało się pobrać żadnego z {len(urls)} adresów URL")

    offers_file = BASE_DIR / "offers.json"
    offers_file.write_text(json.dumps({
        "date": datetime.now().isoformat(),
        "count": len(all_offers),
        "offers": all_offers,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Zapisano do {offers_file}")

    if failed_urls:
        print(f"UWAGA: {len(failed_urls)} z {len(urls)} adresów nie zostało pobranych")

    if os.getenv("SEND_EMAIL", "1") == "0":
        print("Wysyłka maili wyłączona (SEND_EMAIL=0)")
    elif all_offers:
        send_email(all_offers)
    else:
        print("Brak ofert spełniających kryteria — email nie został wysłany.")

    return len(all_offers)


if __name__ == "__main__":
    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"=== Start: {started} ===")
    try:
        total = main()
    except Exception as exc:
        traceback.print_exc()
        write_status(False, error=f"{type(exc).__name__}: {exc}")
        print(f"=== Koniec z błędem: {datetime.now():%Y-%m-%d %H:%M:%S} ===")
        sys.exit(1)
    write_status(True, count=total)
    print(f"=== Koniec OK: {datetime.now():%Y-%m-%d %H:%M:%S} ===")
