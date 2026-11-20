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

## Baza przepisów (Food.com)

Danych nie ma w repo (licencja, D-010). Potrzebne są dwa pliki w `data/raw/`:

- `RAW_recipes.csv` z [Kaggle](https://www.kaggle.com/datasets/shuyangli94/food-com-recipes-and-user-interactions) (trzeba się zalogować): kroki, czas, kcal,
- `parsed_recipes.csv` z [Hugging Face](https://huggingface.co/datasets/Karo8870/food.com-parsed-dataset) (ok. 680 MB): ilości i porcje.

```
curl -L -o data/raw/parsed_recipes.csv https://huggingface.co/datasets/Karo8870/food.com-parsed-dataset/resolve/main/parsed_recipes.csv
uv run import-recipes data/raw/RAW_recipes.csv data/raw/parsed_recipes.csv --interactions data/raw/RAW_interactions.csv
```

`RAW_interactions.csv` jest w tym samym zipie z Kaggle (oceny do rankingu, opcjonalnie). Powstaje `data/recipes.sqlite` (tylko przepisy, których wszystkie składniki są w słowniku i które mają ilości) i raport `data/recipes.report.json` z najczęstszymi składnikami spoza słownika. Źródło: Majumder i in., *Generating Personalized Recipes from Historical User Preferences*, EMNLP 2019.

Endpoint `POST /recipes` czyta tę bazę (ścieżkę zmienia `RECIPES_DB` w `.env`). Bez bazy zwraca 503.

## Dodawanie paczek

Nie używamy `pip install`. Nową paczkę dodajemy przez `uv add <paczka>` (albo `uv add --dev <paczka>` dla narzędzi tylko do pracy nad kodem) i commitujemy razem `pyproject.toml` i `uv.lock`.
