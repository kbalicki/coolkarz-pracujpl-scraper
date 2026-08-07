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
- Ostrzeżenie w panelu i endpoint `/health`, gdy dane przestaną się odświeżać
- Własny katalog przeglądarek Playwrighta (odporny na kolizje z innymi projektami)

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
APP_PORT=5000

# Po ilu godzinach bez świeżych danych panel pokazuje ostrzeżenie
STALE_AFTER_HOURS=30

# Katalog przeglądarek Playwrighta (puste = .playwright w katalogu projektu)
PLAYWRIGHT_BROWSERS_PATH=
```

Adresy URL do scrapowania definiuje się w pliku `urls.txt` (jeden URL na linię) lub z poziomu panelu webowego po zalogowaniu.

### Katalog przeglądarek Playwrighta

Scraper domyślnie trzyma Chromium w `.playwright/` wewnątrz projektu, a nie we
wspólnym `~/.cache/ms-playwright`. Wspólny cache jest współdzielony przez wszystkie
projekty na koncie i `playwright install` uruchomiony w innym projekcie potrafi
usunąć stamtąd binarkę potrzebną temu scraperowi - wtedy scraper wywala się
komunikatem `Executable doesn't exist ...` i przestaje odświeżać oferty.

Po pierwszym wdrożeniu (albo po aktualizacji pakietu `playwright`) trzeba pobrać
przeglądarkę do katalogu projektu:

```bash
cd /sciezka/do/scraper
PLAYWRIGHT_BROWSERS_PATH=$PWD/.playwright venv/bin/python3 -m playwright install chromium
```

Scraper i tak spróbuje zrobić to sam: jeśli przy starcie wykryje brak binarki,
uruchamia `playwright install chromium` i ponawia próbę.

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
Tabela z ofertami — publiczna, bez logowania. Jeśli dane są starsze niż
`STALE_AFTER_HOURS`, na górze pojawia się czerwone ostrzeżenie z wiekiem danych
i treścią ostatniego błędu scrapera.

#### Health check (`/health`)
JSON ze stanem: `ok`, `stale`, `age_hours`, `last_update`, `count`, `last_run_error`.
Zwraca HTTP 200 gdy dane są świeże, 503 gdy nie - można podpiąć pod monitoring.

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
├── last_run.json    # Wynik ostatniego uruchomienia scrapera (generowany automatycznie)
├── .playwright/     # Chromium dla Playwrighta (generowany automatycznie)
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

## Wdrożenie produkcyjne

- Serwer: `s4.k4.pl`, konto `k4`, katalog `/home/k4/pracuj.k4.pl/scraper`
- Panel: usługa systemd użytkownika `pracuj-scraper` na porcie `8112` (`systemctl --user status pracuj-scraper`)
- Cron: `0 5 * * *` -> `venv/bin/python3 scraper.py >> cron.log 2>&1`
- Na produkcji `SEND_EMAIL=0`, czyli oferty trafiają wyłącznie do panelu

Aktualizacja kodu:

```bash
rsync -av scraper.py app.py .env.example s4-k4:~/pracuj.k4.pl/scraper/
rsync -av templates/ s4-k4:~/pracuj.k4.pl/scraper/templates/
ssh s4-k4 'systemctl --user restart pracuj-scraper'
```

## Rozwiązywanie problemów

**Panel pokazuje stare oferty / czerwone ostrzeżenie o nieaktualnych danych**

Sprawdź log crona i wynik ostatniego uruchomienia:

```bash
ssh s4-k4 'tail -50 ~/pracuj.k4.pl/scraper/cron.log; cat ~/pracuj.k4.pl/scraper/last_run.json'
```

**`Executable doesn't exist at .../chromium_headless_shell-XXXX/...`**

Brakuje binarki Chromium dla zainstalowanej wersji pakietu `playwright`. Zdarzyło się
to 2026-08-06: inny projekt na tym samym koncie (`scraper.tools.k4.pl`) zainstalował
Playwrighta 1.60.0 i jego `playwright install` wyczyścił ze wspólnego cache
`~/.cache/ms-playwright` przeglądarkę `chromium-1208` używaną przez ten scraper
(playwright 1.58.0). Scraper przestał się wykonywać, a panel pokazywał w kółko dane
z ostatniego udanego przebiegu. Dlatego przeglądarka trzyma się teraz w `.playwright/`
w katalogu projektu. Ręczna naprawa:

```bash
ssh s4-k4 'cd ~/pracuj.k4.pl/scraper && PLAYWRIGHT_BROWSERS_PATH=$PWD/.playwright venv/bin/python3 -m playwright install chromium'
```

**Scraper nie pobrał żadnego URL-a**

Kończy się kodem 1 i celowo NIE nadpisuje `offers.json`, żeby awaria nie wyglądała
w panelu jak „brak ofert". Zwykle oznacza blokadę Cloudflare - sprawdź `cron.log`.
