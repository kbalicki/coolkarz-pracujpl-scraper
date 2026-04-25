# Scraper Pracuj.pl — oferty zagraniczne

Automatyczny scraper ofert pracy z zagranicy z portalu [pracuj.pl](https://www.pracuj.pl). Filtruje oferty wg krajów i wysyła codziennego maila z wynikami.

## Funkcje

- Scraping ofert zagranicznych z pracuj.pl (z obsługą Cloudflare via Playwright + stealth)
- Obsługa ofert wielolokalizacyjnych (rozwijanie ukrytych lokalizacji)
- Filtry krajów: pozytywne (tylko te) i negatywne (wyklucz te)
- Dowolna lista URLi do scrapowania (konfigurowalna z panelu)
- Email HTML z tabelą: nazwa oferty, widełki, kraj, link
- Panel webowy z tabelą ofert i ustawieniami
- Ręczne uruchamianie scrapera z poziomu panelu

## Wymagania

- Python 3.9+
- Chromium (instalowany automatycznie przez Playwright)

## Instalacja

```bash
python3 -m venv venv
source venv/bin/activate
pip install playwright python-dotenv flask playwright-stealth
playwright install chromium
```

## Konfiguracja

Skopiuj `.env.example` do `.env` i uzupełnij:

```env
# Filtry krajów (oddzielone przecinkami)
COUNTRIES_INCLUDE=
COUNTRIES_EXCLUDE=Niemcy,Francja,Holandia,Belgia,Irlandia,UK

# SMTP
SMTP_SERVER=mail.example.com
SMTP_PORT=587
SMTP_USERNAME=user@example.com
SMTP_PASSWORD=haslo
EMAIL_FROM=user@example.com
EMAIL_TO=odbiorca@example.com
SEND_EMAIL=1

# Panel webowy
APP_SECRET=zmien-na-losowy-ciag
APP_USER=coolkarz
APP_PASS=Praca1
```

Adresy URL do scrapowania definiuje się w pliku `urls.txt` (jeden URL na linię) lub z poziomu panelu webowego po zalogowaniu.

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

#### Strona główna (`/`)
Tabela z ofertami — publiczna, bez logowania.

#### Logowanie (`/login`)
Po zalogowaniu dostępne są ustawienia (`/settings`):
- **Adresy URL** — lista stron pracuj.pl do scrapowania
- **Filtry krajów** — pozytywne i negatywne
- **Scrapuj teraz** — ręczne uruchomienie scrapera z poziomu przeglądarki
- **Log scrapowania** — podgląd wyniku ostatniego uruchomienia

### Cron (codzienny scraping o 5:00)

```
0 5 * * * cd /sciezka/do/scraper && venv/bin/python3 scraper.py
```

## Struktura

```
├── scraper.py       # Główny skrypt scrapujący
├── app.py           # Panel webowy (Flask)
├── urls.txt         # Lista URLi do scrapowania
├── offers.json      # Zapisane oferty (generowany automatycznie)
├── .env             # Konfiguracja
├── .env.example     # Przykład konfiguracji
├── templates/       # Szablony HTML
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   └── settings.html
├── start.sh         # Start serwera
└── stop.sh          # Stop serwera
```
