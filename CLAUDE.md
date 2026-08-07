# Zasady dla tego projektu

## Playwright - nie wracaj do wspólnego cache

Ten scraper trzyma Chromium w `.playwright/` **wewnątrz katalogu projektu**, a nie
w domyślnym `~/.cache/ms-playwright`. To nie jest przypadek ani nadmiarowa ostrożność:
6 sierpnia 2026 inny projekt na koncie `k4` uruchomił `playwright install` z nowszą
wersją pakietu i skasował ze wspólnego cache przeglądarkę używaną przez ten scraper.
Serwis padł na 2 dni, a panel po cichu pokazywał stare dane.

Dlatego:

- **Nie usuwaj** ustawiania `PLAYWRIGHT_BROWSERS_PATH` w `scraper.py`.
- **Nie uruchamiaj** w tym projekcie `playwright install` bez
  `PLAYWRIGHT_BROWSERS_PATH=$PWD/.playwright`.
- Po zmianie wersji pakietu `playwright` (`requirements.txt`) pobierz nową
  przeglądarkę do katalogu projektu, bo numer buildu Chromium jest powiązany
  z wersją pakietu.
- Pracując nad **innym** projektem na tym koncie pamiętaj, że `~/.cache/ms-playwright`
  jest współdzielony - `playwright install` potrafi tam skasować cudze przeglądarki.
  Ustawiaj `PLAYWRIGHT_BROWSERS_PATH` per projekt.

## Awaria ma być widoczna

Serwis nie może padać po cichu. Utrzymuj działanie tych trzech mechanizmów:

- `last_run.json` - wynik ostatniego uruchomienia scrapera,
- `/health` w panelu - HTTP 503, gdy dane są przeterminowane,
- `watchdog.py` (cron co godzinę) - restartuje panel, próbuje naprawić scraper
  i wysyła mail na `monitor@web-systems.pl`.

Gdy scraper nie pobierze żadnego URL-a, kończy kodem 1 i **nie nadpisuje**
`offers.json`. Nie „upraszczaj" tego z powrotem do zapisu pustej listy - awaria
wyglądałaby wtedy w panelu jak brak ofert.

## Crontab na s4 - nigdy przez stałą ścieżkę w /tmp

`/tmp` na s4.k4.pl jest wspólne dla wszystkich kont. Plik o przewidywalnej nazwie
(`/tmp/ct.bak` i podobne) może już tam leżeć, założony przez inne konto. Skrypt,
który buduje nowy crontab z takiego pliku, potrafi podmienić cały crontab konta
na cudzy - zdarzyło się to 2026-08-07 na koncie `k4`.

Crontab edytuj przez `crontab -e`, a gdy potrzebny jest plik pośredni, trzymaj go
w `$HOME` albo zakładaj przez `mktemp`. Przed instalacją nowego crontaba zrób kopię
(`crontab -l > ~/crontab-backup-RRRR-MM-DD.txt`) i po instalacji sprawdź `crontab -l`.

## Produkcja

`s4.k4.pl`, konto `k4`, katalog `/home/k4/pracuj.k4.pl/scraper` (alias SSH `s4-k4`).
Szczegóły wdrożenia i rozwiązywanie problemów: README.

Konto `k4` ma crontab z zadaniami wielu innych projektów (support, feedvault, lidar,
mediacapture, dmarc, paddle). Kopia z 2026-08-07: `~/crontab-k4-backup-2026-08-07.txt`.
