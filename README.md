# Scraper Pracuj.pl — oferty zagraniczne

Automatyczny scraper ofert pracy z zagranicy z portalu [pracuj.pl](https://www.pracuj.pl). Filtruje oferty wg krajów i wysyła codziennego maila z wynikami.

## Funkcje

- Scraping ofert zagranicznych z pracuj.pl (z obsługą Cloudflare via Playwright + stealth)
- Obsługa ofert wielolokalizacyjnych (rozwijanie ukrytych lokalizacji)
- Filtry krajów: pozytywne (tylko te) i negatywne (wyklucz te)
- Konfigurowalna liczba stron do przeszukania
- Email HTML z tabelą: nazwa oferty, widełki, kraj, link
- Panel webowy z tabelą ofert i ustawieniami filtrów

## Wymagania

- Python 3.9+
- Chromium (instalowany automatycznie przez Playwright)

## Instalacja

```bash
python3 -m venv venv
source venv/bin/activate
pip install playwright python-dotenv flask
playwright install chromium
```

## Konfiguracja

Skopiuj `.env.example` do `.env` i uzupełnij:

```env
# Filtry krajów (oddzielone przecinkami)
COUNTRIES_INCLUDE=
COUNTRIES_EXCLUDE=Niemcy,Francja,Holandia,Belgia,Irlandia,UK

# Scraper
PAGES=3
BASE_URL=https://www.pracuj.pl/praca/zagranica;r,17?sc=0

# SMTP
SMTP_SERVER=mail.example.com
SMTP_PORT=587
SMTP_USERNAME=user@example.com
SMTP_PASSWORD=haslo
EMAIL_FROM=user@example.com
EMAIL_TO=odbiorca@example.com
```

## Użycie

### Scraper (CLI / cron)

```bash
source venv/bin/activate
python3 scraper.py
```

### Panel webowy

```bash
source venv/bin/activate
python3 app.py
# http://localhost:5000
```

Login do ustawień: `/login`

### Cron (codzienny scraping o 5:00)

```
0 5 * * * cd /home/k4/pracuj.k4.pl/scraper && venv/bin/python3 scraper.py
```

## Struktura

```
├── scraper.py       # Główny skrypt scrapujący
├── app.py           # Panel webowy (Flask)
├── offers.json      # Zapisane oferty (generowany automatycznie)
├── .env             # Konfiguracja
├── .env.example     # Przykład konfiguracji
├── templates/       # Szablony HTML
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   └── settings.html
└── start.sh         # Skrypt startowy serwera
```
