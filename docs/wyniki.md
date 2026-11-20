# Wyniki pomiarów rozpoznawania

Dziennik pomiarów do raportu końcowego. Każdy wpis to jeden przebieg: który model, na jakich zdjęciach, jakie liczby i co z nich wynika. Metryki są zdefiniowane w D-003 w [specyfikacji](specyfikacja.md). Wpisów nie nadpisujemy. Jeśli coś przeliczamy, dopisujemy nowy wpis.

## 12.11.2026: scan_001, `gemini-3.1-flash-lite`, pierwszy przebieg

**Status: policzone ręcznie i potwierdzone przez `evaluation.evaluate` (te same liczby).**

**Ustawienia**

- Model: `gemini-3.1-flash-lite` (D-008). Wszystkie zdjęcia w jednym wywołaniu (wariant pierwszy z O-007). Zdjęcia zmniejszone do 1500 px na dłuższym boku.
- Zdjęcia (`data/scans/scan_001/`): `drzwi.jpg` (door), `shelves.jpg` (shelves_upper), `extra1.jpg` i `extra2.jpg` (extra, szuflady).
- Odstępstwo od D-001: jedno zdjęcie wszystkich półek zamiast osobnych zdjęć półek górnych i dolnych. Dolna półka wyszła mała i ciemna.
- Ręczna lista: `data/scans/scan_001/ground_truth.json` (24 pozycje, z tego 18 ze słownika). Ilości są częściowo szacowane, w liczeniu sztuk nie ma wątpliwości.
- Czas odpowiedzi: 4,6 s. Model zwrócił 13 pozycji (12 ze słownika, 1 spoza).

**Metryki (tylko pozycje ze słownika)**

| | Wszystkie (18) | Tylko `visible` (13) | Tylko `partial` (5) |
|---|---|---|---|
| Znalezione | 11 | 10 | 1 (ogórek) |
| Recall | 61% | 77% | 20% |

- Precision: 92% (11 z 12). Jedyna halucynacja to cebula.
- F1: ok. 0,73.
- Duplikaty: 0. Sałata i mandarynki są widoczne zarówno na zdjęciu półek, jak i na zdjęciach szuflad, a mimo to policzone raz.
- Błąd ilości: średnio 1,2% (9 produktów, jedyna różnica to koncentrat: 100 g zamiast 90 g). **Tej liczbie nie ufamy.** Ilości w ręcznej liście w większości oszacowaliśmy z tych samych zdjęć i z typowych gramatur, więc model i ręczna lista zgadywały tak samo. Wiarygodny błąd ilości wymaga ilości spisanych z opakowań.
- Niezgodna jednostka: sałata (model `pcs`, słownik `g`). Nie wchodzi do błędu ilości.
- Pozycje spoza słownika: 6 w ręcznej liście, 1 od modelu („słoik z przetworami”).

**Co wynika**

- Co Gemini widzi wyraźnie, w większości znajduje i prawie nic nie zmyśla. Czyta marki i pojemności z etykiet (Flora, Łowicz, Winiary, mleko UHT 1,5% 1 l).
- Rzeczy częściowo zasłonięte prawie wszystkie mu umykają: szczypiorek, czosnek, cytryna, masło w folii. Potwierdza to uwagę prowadzącego, że zasłonięcie to główny problem.
- Z widocznych pominął musztardę, drugi majonez (ten sam produkt, inna marka) i kukurydzę z puszki.
- Mandarynki rozpoznał jako pomarańcze. Liczymy to jako trafienie, bo w słowniku jest tylko `orange`.
- Sałatę podał jako `1 pcs`, a słownik ma ją w gramach. To przykład do metryki błędu ilości.

## 12.11.2026: scan_001, `gemini-3.1-flash-lite`, drugi przebieg (te same ustawienia)

**Status: policzone skryptem** (`uv run scan data/scans/scan_001`), wynik w `metrics_gemini-3.1-flash-lite_1500px.json`.

- Metryki **identyczne** jak w pierwszym przebiegu: recall 61% (visible 77%, partial 20%), precision 92%, F1 0,73. Czas 5,4 s, 14 pozycji.
- **Lista jest jednak inna.** Tym razem model znalazł musztardę, nie zmyślił cebuli, ale zwrócił margarynę z `ingredient_id = null` (w pierwszym przebiegu miał `margarine`) i zmyślił czarne oliwki (w lodówce są zielone, w ręcznej liście `null`).
- Ciemną butelkę w drzwiach (wódka) nazwał „oliwa z oliwek”, z `null`.

**Co wynika:** ta sama ogólna liczba może ukrywać różne błędy. Powtarzalność (D-003) trzeba mierzyć na poziomie pozycji (czy przy kolejnych przebiegach znajduje te same produkty), a nie tylko porównując F1. Każdy skan warto puścić kilka razy.

## 12.11.2026: scan_001, `gemini-3.1-flash-lite`, trzeci przebieg (z zapisem surowych ID)

**Status: policzone skryptem.** Surowa odpowiedź modelu jest w `raw_gemini-3.1-flash-lite_1500px.json`.

- Recall 56% (visible 77%, **partial 0%**), precision 83%, F1 0,67. Czas 3,6 s, 15 pozycji.
- **Ketchup** model zwrócił z `ingredient_id = null`, choć `ketchup` jest w słowniku, w prompcie i w etykiecie (`label: "ketchup"`). Normalizacja niczego tu nie zgubiła: surowe ID to już `null`. Podobnie było najpewniej z margaryną w drugim przebiegu.
- Puszkę kukurydzy rozpoznał jako `canned_tomatoes`, więc liczy się to podwójnie: jako pominięcie i jako halucynacja.
- Rozpoznał jednak katering („gotowe danie w pudełkach”) i dżem, oba poprawnie jako `null`.

**Co wynika:** `flash-lite` często poprawnie nazywa produkt w `label`, ale nie wybiera dla niego ID ze słownika (128 pozycji w prompcie). To osobny rodzaj błędu niż „nie zobaczył”. Do sprawdzenia: mocniejszy model i/lub dopasowanie `label` do nazw ze słownika, gdy ID jest `null`.

## 12.11.2026: scan_001, `gemini-3.6-flash` (mocniejszy model, te same zdjęcia)

**Status: policzone skryptem**, wynik w `metrics_gemini-3.6-flash_1500px.json`.

| | `3.1-flash-lite` (3 przebiegi) | `3.6-flash` |
|---|---|---|
| Recall | 56–61% | **72%** |
| Recall `visible` | 77% | **92%** (12 z 13) |
| Recall `partial` | 0–20% | 20% |
| Precision | 83–92% | 76% |
| F1 | 0,67–0,73 | 0,74 |
| Czas | 3,6–5,4 s | **46,6 s** |

- Wszystkie produkty dostały ID ze słownika. Problem z `null` przy ketchupie i margarynie zniknął.
- Znalazł oba majonezy (z markami), musztardę i ketchup. Z widocznych pominął tylko kukurydzę.
- Zasłonięte nadal mu umykają: masło, szczypiorek, czosnek, cytryna.
- Spadek precision to w dużej części kwestia ręcznej listy, a nie zmyślania:
  - `water`: woda w dzbanku filtrującym. Naprawdę jest w lodówce, ale nie ma jej na ręcznej liście.
  - `mustard` ×2: druga „musztarda Kamis” to prawdopodobnie słoik, który na ręcznej liście jest jako „sos amerykański” (`null`). Do wyjaśnienia.
  - `olive_oil`: ciemna butelka, w rzeczywistości wódka. To prawdziwa pomyłka.
  - `chicken_breast`: pudełko z kateringu. Do wyjaśnienia, co jest w środku.
- **Czas jest ok. 10 razy dłuższy.** Dla aplikacji (użytkownik czeka na ekranie analizy) to istotny koszt.

**Co wynika:** mocniejszy model wyraźnie lepiej znajduje widoczne produkty i przypisuje ID, ale zasłonięcie dalej jest głównym problemem i model jest dużo wolniejszy. Kompromis jakość/czas to wątek do raportu (O-002).

## 12.11.2026: przeliczenie scan_001 po poprawkach ręcznej listy

**Status: przeliczone skryptem na zapisanych odpowiedziach**, bez nowych wywołań modelu. Wpisy powyżej zostają z liczbami sprzed poprawek.

Poprawki w `ground_truth.json` (po wyjaśnieniu z osobą, która robiła zdjęcia):

- Słoik Kamis z zielonym wieczkiem to musztarda (`mustard`, `partial`, bo stoi z tyłu). Żółta butelka do wyciskania to sos amerykański (`null`, `visible`).
- Woda jest ignorowana (nowa reguła w D-003). `water` od `3.6-flash` przestaje być halucynacją.
- Katering: dopisana zawartość (filet z kurczaka, ryż, warzywa, bułka, sos). Zostaje jako `null` (gotowe danie, nowa reguła w D-003). `chicken_breast` od `3.6-flash` to więc halucynacja, ale „bliska”: model zobaczył kurczaka w pudełku.

Ręczna lista ma teraz 18 pozycji ze słownika: 12 `visible`, 6 `partial`.

| Przebieg | Recall | `visible` | `partial` | Precision | F1 | Halucynacje | Duplikaty |
|---|---|---|---|---|---|---|---|
| `3.1-flash-lite`, przebieg 1 | 61% | 83% | 17% | 92% | 0,73 | onion | – |
| `3.1-flash-lite`, przebieg 3 | 56% | 75% | 17% | 83% | 0,67 | black_olives, canned_tomatoes | – |
| `3.6-flash` | **72%** | **92%** | **33%** | 81% | **0,76** | chicken_breast, olive_oil | mustard |

Przebiegu 2 nie da się przeliczyć: jego pliki nadpisał przebieg 3 (ta sama nazwa pliku). Od teraz skrypt dopisuje do nazw plików datę i godzinę.

Wniosek bez zmian: `3.6-flash` jest wyraźnie lepszy w znajdowaniu (zwłaszcza widocznych produktów), kosztem ok. 10 razy dłuższego czasu. Zasłonięte produkty pozostają głównym problemem obu modeli. Duplikat `mustard` od `3.6-flash` to sos amerykański (żółta butelka) wzięty za drugą musztardę, czyli pomyłka rozpoznania, a nie podwójne liczenie.

**Zastrzeżenia (wszystkie przebiegi)**

- To jeden skan, więc liczby pokazują kierunek, a nie wynik. Wnioski wyciągamy dopiero z całego zbioru (D-003).
- Przy spisywaniu przyjęliśmy regułę: produkt spoza słownika, który w przepisie da się zamienić na inny, wpisujemy pod ID tego najbliższego (mandarynki jako `orange`). Inne produkty spoza słownika mają `ingredient_id = null` (np. mleczko zagęszczone, dżem, katering).

# Wyniki części przepisowej

Pomiary `POST /recipes` (D-013) według D-014: `uv run eval-recipes`. Tak jak wyżej, wpisów nie nadpisujemy.

## Szablon wpisu (do wypełnienia po pierwszym przebiegu)

**Status: do uruchomienia** na pełnej bazie z Kaggle, z kluczem API.

```bash
uv run eval-recipes --model gemini-3.1-flash-lite --baseline groq/openai/gpt-oss-120b --price IN OUT
```

**Ustawienia:** data, model, baseline, baza (liczba przepisów), skany, ceny za 1 mln tokenów i ich źródło.

**Bezpieczeństwo:** tabela z wyjścia skryptu (skan, profil, kandydaci, przepisy, naruszenia, podejrzane). Bramka: 0 naruszeń. Podejrzane linie przejrzane ręcznie: ile to fałszywe alarmy.

**Czas i koszt:** mediana i p90 czasu, wywołania LLM, tokeny i USD na zapytanie, zapytania z błędem LLM.

**Tłumaczenie:** udział wpisów po angielsku (model i baseline), średnia ocena 1–5 zespołu z arkusza `translations_*.md`.

**Co wynika:** 2–3 zdania.
