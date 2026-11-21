# Smart Fridge Chef

Robisz telefonem kilka zdjęć lodówki, a aplikacja rozpoznaje produkty (Vision LLM, domyślnie Gemini), daje poprawić listę i proponuje do 3 przepisów z bazy Food.com, dopasowanych do tego, co masz, oraz do Twoich alergii i preferencji. Przepisy wybiera i tłumaczy na polski drugi LLM. Klucze API są tylko w backendzie (FastAPI), aplikacja (Expo) zna jedynie jego adres.

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
- Model zmienia się zmienną `VISION_MODEL` w `.env` (domyślnie `gemini-3.1-flash-lite`).

| Endpoint | Co robi |
|---|---|
| `GET /health` | Czy serwer działa i jakiego modelu używa |
| `POST /scan` | Zdjęcia (`photos`) ze strefami (`zones`) → lista produktów (`ScanResult`) |
| `GET /ingredients` | Słownik składników i produkty dodane z aplikacji (pole `custom`) |
| `POST /ingredients` | Dodaje produkt do słownika z aplikacji (D-011), zapis w `data/custom_ingredients.json` (poza gitem) |
| `POST /scans` | Zapisuje skan do ewaluacji (D-003) w kolejnym `data/scans/scan_NNN/` i zwraca metryki |
| `POST /recipes` | Lista z lodówki i profil (`RecipeRequest`) → najwyżej 3 przepisy po polsku, pytania „Masz X?” i lista zakupów (`RecipeResponse`, D-012, D-013, D-015). Wymaga bazy przepisów (niżej), bez niej zwraca 503 |

## Aplikacja mobilna (Expo)

Aplikacja jest w `mobile/` (Expo SDK 58, TypeScript). Testujemy ją na telefonie w [Expo Go](https://expo.dev/go). Potrzebny jest [Node.js](https://nodejs.org/) (LTS).

**1. Backend na wszystkich interfejsach**, żeby telefon go widział (z głównego folderu repo):

```
uv run fastapi dev src/smart_fridge_chef/api.py --host 0.0.0.0
```

Za pierwszym razem Windows może zapytać o dostęp przez zaporę. Zezwól dla sieci prywatnej.

**2. Adres backendu.** Utwórz plik `mobile/.env.local` (jest w `.gitignore`, każdy ma swój) z IP laptopa w sieci lokalnej (Windows: `ipconfig`, pole „IPv4 Address”):

```
EXPO_PUBLIC_API_URL=http://192.168.1.23:8000
```

Nie `localhost`, bo dla telefonu `localhost` to sam telefon. Nie wpisuj tu kluczy API: zmienne `EXPO_PUBLIC_*` trafiają do aplikacji i każdy może je odczytać (D-005).

**3. Aplikacja:**

```
cd mobile
npm install
npx expo start --clear
```

Na telefonie zeskanuj kod QR (Android: w Expo Go, iPhone: aparatem). Telefon musi być w tej samej sieci Wi-Fi co laptop. `--clear` jest potrzebne przy pierwszym uruchomieniu i po zmianie `.env.local`, później wystarczy `npx expo start`.

**Co robi aplikacja:** sprawdza połączenie z backendem, prowadzi przez zdjęcia trzech stref (D-001; aparat albo galeria), wysyła je do `POST /scan` i pokazuje listę do korekty: ilości, usuwanie, zmiana nazwy przez wyszukiwarkę słownika, dodawanie produktów (D-006, D-011). Po korekcie skan można zapisać do ewaluacji (niżej).

Przycisk „Szukaj przepisów” na dole ekranu otwiera przepisy z `POST /recipes`: czas, trudność, kcal, składniki w kolorach (zielone: masz, czerwone: brakuje, szare: podstawy z szafki), a po rozwinięciu składniki z ilościami, kroki i link do oryginału. Przepisy ułożone przez AI, gdy z bazy nic nie pasuje, mają osobną plakietkę. „⚙ Profil” w nagłówku ustawia alergie, składniki, których nie jesz, maksymalny czas, trudność i liczbę porcji. Profil zapisuje się na telefonie i trafia do każdego wyszukiwania.

Jedno wyszukiwanie przepisów to do 4 wywołań LLM, a darmowy Gemini ma limit 15 zapytań na minutę na model. Kilka wyszukiwań pod rząd może skończyć się błędem 429; wtedy odczekaj minutę.

**Jeśli nie działa:**

- „Brak EXPO_PUBLIC_API_URL”: `.env.local` nie jest w `mobile/` albo Expo nie został uruchomiony z `--clear`.
- „Brak odpowiedzi z … po 5 s”: otwórz `http://<IP>:8000/health` w przeglądarce telefonu. Jeśli też nie działa, to sieć (inne Wi-Fi, zapora albo serwer bez `--host 0.0.0.0`), a nie aplikacja.

## Zbieranie skanów do ewaluacji (D-003)

Po korekcie listy w aplikacji kliknij „Przygotuj zapis do ewaluacji”, przy każdym produkcie zaznacz, czy widać go na zdjęciach (`widać` / `częściowo` / `schowane`), dopisz produkty schowane i kliknij „Zapisz skan”. Backend zapisze w kolejnym `data/scans/scan_NNN/`:

- zdjęcia (poza gitem, jak w `scan_001`),
- `ground_truth.json`: lista po korekcie, czyli wzorzec (commitujemy),
- `pred_…_app_….json`: odpowiedź modelu bez poprawek,
- `metrics_…_app_….json`: recall, precision, F1, halucynacje, duplikaty i czas.

Listę sprawdzaj przy otwartej lodówce, a ilości przepisuj z opakowań. Lista powstaje z poprawiania odpowiedzi modelu, więc łatwo przepuścić jego błędy (reguły w D-003). Ten sam skan można potem przeliczyć innym modelem: `uv run scan data/scans/scan_NNN --model ...`.

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

Z kluczem dla modelu z `RECIPE_MODEL` (`GEMINI_API_KEY` albo `GROQ_API_KEY` dla `groq/...`) LLM wybiera 3 z 20 najlepszych kandydatów, opisuje je i tłumaczy na polski, a gdy żaden przepis nie pasuje, pisze własny (`source: "ai_generated"`). Bez klucza albo przy błędzie LLM endpoint zwraca ranking z SQL po angielsku (D-013).

`uv run eval-recipes` mierzy `/recipes` na skanach z `data/scans/*/ground_truth.json` i 5 profilach z alergenami (D-014): naruszenia alergenów, czas, tokeny i koszt (`--price IN OUT`, USD za 1 mln tokenów), a z `--baseline groq/openai/gpt-oss-120b` także arkusz do oceny tłumaczeń. Wyniki trafiają do `data/eval/` (poza gitem). `uv run eval-recipes-share` robi z najnowszego wyniku plik do wysłania: same liczby, bez tekstów przepisów, i odmawia zapisu, jeśli w środku jest klucz API z `.env`.

Odpowiedź `POST /recipes` ma też `questions` (do 3 produktów do dopytania, np. „Masz masło?”, z liczbą przepisów, które odblokują) i `shopping_list` (braki ze zwróconych przepisów), D-015. `uv run eval-questions` mierzy pytania bez LLM i zapisuje do `data/eval/` same liczby.

`uv run eval-clash` porównuje modele na tych samych skanach i profilach (D-016) i zapisuje jedną tabelę do `data/eval/clash_*.md`: `--models gemini-3.1-flash-lite groq/openai/gpt-oss-120b`, ceny przez `--price MODEL IN OUT`. Modele lokalne dodaje `--local ollama/qwen2.5:7b`; idą tylko przy karcie NVIDIA (`nvidia-smi`) i działającej Ollamie z pobranym modelem. Każde wywołanie LLM ma limit 15 s, a całe `/recipes` 45 s (`LLM_TIMEOUT_S`, `RECIPES_BUDGET_S` w `.env`).

`uv run audit-allergens` sprawdza gotową bazę: wypisuje linie składników, które sugerują alergen, którego przepis nie ma w tabeli `recipe_allergens` (wynik czyta człowiek, są fałszywe alarmy).

## Testy

Backend (z głównego folderu repo):

```
uv run pytest -q
```

Aplikacja (z `mobile/`): sprawdzenie typów i lint.

```
npx tsc --noEmit
npx expo lint
```

## Dodawanie paczek

Nie używamy `pip install`. Nową paczkę dodajemy przez `uv add <paczka>` (albo `uv add --dev <paczka>` dla narzędzi tylko do pracy nad kodem) i commitujemy razem `pyproject.toml` i `uv.lock`.

W aplikacji (`mobile/`) paczki dodajemy przez `npx expo install <paczka>`, a nie `npm install <paczka>`: Expo dobiera wtedy wersję zgodną z SDK. Commitujemy `package.json` i `package-lock.json`.
