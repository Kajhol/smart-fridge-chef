# Smart Fridge Chef

Dokumentacja: [docs/specyfikacja.md](docs/specyfikacja.md) (decyzje i otwarte pytania), [docs/Smart-Fridge-Chef-PoC.pdf](docs/Smart-Fridge-Chef-PoC.pdf) (założenia PoC).

## Uruchomienie

1. Zainstaluj [uv](https://docs.astral.sh/uv/getting-started/installation/).
2. Zainstaluj zależności wpisując: uv sync
3. Skopiuj `.env.example` do `.env` i wpisz swoje klucze API. Pliku `.env` nie commitujemy.

## Skan zdjęć z linii poleceń

```
uv run scan data/scans/scan_001
uv run scan data/scans/scan_001 --model gemini-3.6-flash --max-side 1000
```

Zapisuje w folderze skanu surową odpowiedź modelu (`raw_*.json`), wynik po normalizacji ID (`pred_*.json`), a jeśli jest `ground_truth.json`, to też metryki (`metrics_*.json`).

## Backend (FastAPI)

```
uv run fastapi dev src/smart_fridge_chef/api.py
```

- `http://127.0.0.1:8000/docs`: strona do testowania. Przy `POST /scan` kliknij „Try it out”, dodaj zdjęcia i do każdego wpisz strefę (`door`, `shelves_upper`, `shelves_lower`, `extra`), w tej samej kolejności.
- `GET /health`: czy serwer działa i jakiego modelu używa.
- Model zmienia się zmienną `VISION_MODEL` w `.env` (domyślnie `gemini-3.1-flash-lite`).

**Z telefonu (Expo Go):** telefon i laptop muszą być w tej samej sieci Wi-Fi. Uruchom serwer na wszystkich interfejsach:

```
uv run fastapi dev src/smart_fridge_chef/api.py --host 0.0.0.0
```

W aplikacji jako adres backendu wpisz IP laptopa w sieci lokalnej (Windows: `ipconfig`, pole „IPv4 Address”), np. `http://192.168.1.23:8000`, a nie `localhost`. Za pierwszym razem Windows może zapytać o dostęp przez zaporę. Zezwól dla sieci prywatnej.

## Dodawanie paczek

Nie używamy `pip install`. Nową paczkę dodajemy przez `uv add <paczka>` (albo `uv add --dev <paczka>` dla narzędzi tylko do pracy nad kodem) i commitujemy razem `pyproject.toml` i `uv.lock`.
