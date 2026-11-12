# Smart Fridge Chef – specyfikacja i decyzje

Żywy dokument: tu zapisujemy podjęte decyzje i otwarte pytania. Tło i uzasadnienie całego podejścia jest w [Smart-Fridge-Chef-PoC.pdf](Smart-Fridge-Chef-PoC.pdf). Jeśli coś tutaj różni się od PDF-a, obowiązuje ten dokument.

Każda decyzja ma numer (D-001, D-002…), datę, autora i status: **do potwierdzenia**, **przyjęta** albo **zastąpiona** (z odnośnikiem do nowej). Decyzji nie usuwamy, tylko zmieniamy status, żeby było widać, skąd się wzięło obecne rozwiązanie.

## Konsultacja z prowadzącym

05.11.2026 Kajtek wysłał opis projektu (Vision LLM rozpoznaje produkty ze zdjęć lodówki, drugi LLM dobiera przepisy z bazy, aplikacja w React Native na Expo Go). 10.11.2026 prowadzący **zatwierdził temat**. Gotowe modele przez API są OK. Dodał trzy uwagi:

| Uwaga prowadzącego | Gdzie uwzględniona |
|---|---|
| Najtrudniejsze jest rozpoznawanie: kilka zdjęć tej samej lodówki daje duplikaty, część rzeczy jest zasłonięta. Zróbcie mały zbiór testowy (20–30 zdjęć z ręcznie spisaną zawartością) i zmierzcie, ile produktów model znajduje, a ile zmyśla. „To będzie najmocniejsza część projektu.” | D-003 |
| Samo podobieństwo wektorowe słabo dopasowuje przepisy do listy składników. Najpierw odfiltrować przepisy po składnikach (np. brakuje najwyżej dwóch), a LLM użyć do wyboru i opisu. | D-004 |
| Klucza API nie wkładać do aplikacji mobilnej, bo da się go wyciągnąć. Potrzebny mały backend pośredniczący. | D-005 |

Termin oddania nie padł, nadal trzeba o niego zapytać (O-004).

## Decyzje

### D-001: Skan lodówki to kilka zdjęć robionych strefami, krok po kroku

- **Data:** 01.11.2026
- **Autor:** Kajtek
- **Status: do potwierdzenia z zespołem** (wielkość zbioru testowego zmieniona w D-003)
- **Zastępuje:** w PDF „1 lub kilka ujęć” (krok 1 w „Jak działa PoC”)

**Decyzja.** Aplikacja prowadzi użytkownika przez stałą sekwencję zdjęć. Po zrobieniu zdjęcia automatycznie przechodzi do następnego kroku, bez dodatkowego klikania.

| Krok | Strefa | Wymagane |
|---|---|---|
| 1 | Drzwi | tak |
| 2 | Półki górne | tak |
| 3 | Półki dolne | tak |
| + | Dodatkowe (szuflady, zamrażarka, druga półka drzwi…) | nie |

Przebieg:

1. Ekran pokazuje, którą strefę teraz sfotografować („Krok 2/3: półki górne”).
2. Po zrobieniu zdjęcia aplikacja od razu przechodzi do następnej strefy.
3. Strefę można pominąć (np. puste drzwi).
4. Po ostatnim kroku jest podsumowanie z miniaturami. Można tam powtórzyć dowolne zdjęcie, dodać zdjęcie dodatkowe i nacisnąć „Skanuj”.

**Dlaczego nie film.**

- Kadry z filmu są rozmazane, a na opakowaniach odbija się światło. Tracimy główną przewagę Vision LLM nad YOLO, czyli czytanie etykiet.
- Koszt rośnie z liczbą obrazów: 20 s filmu przy 1 klatce/s to 20 obrazów zamiast 3–4.
- Ten sam produkt widać na wielu klatkach, więc model łatwo liczy go podwójnie. Strefy (drzwi, półki) fizycznie się nie pokrywają, więc przy zdjęciach tego problemu jest dużo mniej. Nie znika całkiem (np. wysunięta szuflada widoczna też na zdjęciu dolnej półki), dlatego duplikaty mierzymy osobno (D-003).
- Film natywnie przyjmuje tylko część dostawców (np. Gemini). U pozostałych i tak trzeba wycinać klatki.

Na później (poza PoC): użytkownik nagrywa film, a aplikacja sama wybiera z niego 4–6 ostrych, różnych klatek. Wygoda filmu, koszt jak przy zdjęciach.

**Konsekwencje.**

- **API:** skan to lista zdjęć, każde z etykietą strefy (`door`, `shelves_upper`, `shelves_lower`, `extra`).
- **Backend:** zdjęcia zmniejszamy przed wysłaniem do modelu (rozdzielczość do ustalenia, patrz pytanie O-005).
- **Ewaluacja:** ręcznie spisana lista „co tu jest i ile” dotyczy całego skanu, nie pojedynczego zdjęcia. Metryki liczymy na skan. ~~Około 15–20 lodówek po 3–4 zdjęcia.~~ Wielkość zbioru i metryki: D-003.
- **Zbieranie zdjęć (krok 2 planu w PDF):** każdy fotografuje swoją lodówkę według tych samych stref i dorzuca jedno zdjęcie całej lodówki do eksperymentu z pytania O-006.

### D-002: Rozpoznawanie przez gotowe Vision LLM przez API, bez trenowania YOLO

- **Data:** 12.11.2026
- **Autor:** Kajtek
- **Status: przyjęta** (prowadzący, 10.11.2026: „Gotowe modele przez API są OK”)
- **Zamyka:** O-001

**Decyzja.** Produkty ze zdjęć rozpoznaje Vision LLM wywoływany przez API. Własnego modelu nie trenujemy. Porównujemy kilka gotowych modeli (O-002) na zbiorze testowym z D-003.

**Konsekwencje.** YOLO przestaje być wymaganiem. Wraca tylko jako opcja po PoC (PDF, „Co z YOLO po PoC”), jeśli wyniki liczenia sztuk będą słabe albo zostanie czas.

### D-003: Zbiór testowy i metryki rozpoznawania

- **Data:** 12.11.2026
- **Autor:** Kajtek
- **Status: do potwierdzenia z zespołem**
- **Zastępuje:** wielkość zbioru w D-001 (15–20 lodówek) i w PDF (30–50 zdjęć)
- **Zamyka:** O-009

**Decyzja.** Zgodnie z uwagą prowadzącego zbiór testowy jest mały, a ewaluacja to najważniejsza część projektu.

**Zbiór.**

- 20–30 zdjęć, czyli 6–8 skanów po 3–4 strefy (D-001).
- Ta sama lodówka sfotografowana innego dnia, z inną zawartością, to osobny skan.
- Różne światło i różne zapełnienie, jak w PDF.

**Ręczna lista (ground truth).** Spisujemy to, co **fizycznie jest** w lodówce, a nie tylko to, co widać na zdjęciach. Każda pozycja ma:

| Pole | Opis |
|---|---|
| `ingredient_id` | ID ze słownika albo `null`, gdy produktu nie ma w słowniku |
| `label` | krótki opis po polsku, np. „kefir Bakoma 400 g” |
| `quantity`, `unit` | ilość w jednostce ze słownika |
| `visibility` | `visible` (widać i da się rozpoznać), `partial` (częściowo zasłonięty), `hidden` (jest w lodówce, ale na zdjęciach go nie widać) |

**Reguły spisywania** (dopisane 12.11.2026 po pierwszym skanie, żeby listy różnych osób były porównywalne):

- Produkt spoza słownika, który w przepisie da się zastąpić produktem ze słownika, wpisujemy pod ID tego produktu, a w `label` zostawiamy prawdziwą nazwę. Przykład: mandarynki to `orange` z etykietą „mandarynki”. Jeśli zastąpić się nie da (dżem, mleczko zagęszczone, gotowe dania), wpisujemy `null`.
- Ilości spisujemy z opakowań (gramatura, liczba sztuk), a nie szacujemy ze zdjęć. Inaczej ręczna lista i model zgadują tak samo i błąd ilości nic nie mówi.
- Ten sam produkt w dwóch opakowaniach różnych marek to dwie pozycje (np. dwa majonezy).
- Wody (np. w dzbanku filtrującym) nie spisujemy. Prompt każe modelowi ją ignorować, a ewaluacja pomija `water` po obu stronach (`IGNORED_IDS`), bo do przepisów nie ma znaczenia.
- Gotowe dania (katering, resztki obiadu w pudełku) to jedna pozycja `null` na danie, ze składnikami w `label`. Nie rozbijamy ich na składniki, bo to nie są produkty do gotowania.
- Format pliku: `data/scans/scan_NNN/ground_truth.json`, sprawdzany przez `GroundTruth` w `src/smart_fridge_chef/evaluation.py`.

**Metryki (na skan, potem średnia po zbiorze).**

| Metryka | Co mierzy | Uwagi |
|---|---|---|
| Recall | Ile produktów model znajduje | Osobno dla wszystkich pozycji i tylko dla `visible` + `partial`. Różnica pokazuje, ile tracimy przez zasłonięcie. |
| Precision / halucynacje | Ile model zmyśla | Halucynacja to pozycja z modelu, której nie ma w ręcznej liście. Podajemy też liczbę halucynacji na skan. |
| F1 | Ogólna jakość listy | Z precision i recall |
| Duplikaty | Ten sam produkt policzony więcej razy, niż jest w lodówce | Np. dla danego `ingredient_id` model zwraca więcej pozycji niż ręczna lista. Liczymy osobno, nie jako halucynację. |
| Błąd ilości | Czy ilości się zgadzają | Tylko dla trafionych pozycji |
| Powtarzalność, czas, koszt | Bez zmian względem PDF | |

**Pozycje spoza słownika (`ingredient_id = null`).** Nie wchodzą do precision, recall i F1, bo nie da się ich automatycznie dopasować. Podajemy ich liczbę na skan i przeglądamy ręcznie.

### D-004: Wyszukiwanie przepisów: najpierw filtr po składnikach, LLM tylko do wyboru i opisu

- **Data:** 12.11.2026
- **Autor:** Kajtek
- **Status: przyjęta** (próg do dostrojenia przez osobę 2, backend)

**Decyzja.** Kandydatów na przepisy wybiera zwykłe zapytanie SQL po `ingredient_id`, bez embeddingów. Przepis przechodzi, jeśli **brakuje najwyżej 2 składników**, nie licząc przypraw podstawowych (O-010). Kandydatów sortujemy najpierw po liczbie braków, potem po odsetku pokrycia i ocenie. LLM tekstowy dostaje ~20 kandydatów, wybiera 3, przelicza porcje i opisuje. Nie wyszukuje sam. Zapytanie jest w [baza-danych.md](baza-danych.md).

**Dlaczego.**

- Uwaga prowadzącego: podobieństwo wektorowe słabo dopasowuje przepisy do listy składników.
- Sam odsetek pokrycia premiuje krótkie przepisy (2 z 3 składników = 67%). Liczba braków mówi użytkownikowi wprost, ile musi dokupić.

**Konsekwencje.**

- Każdy składnik przepisu musi być zmapowany na ID słownika, bo niezmapowany liczyłby się jako brak. Przepisy z niezmapowanymi składnikami odpadają przy imporcie.
- Gdy filtr nie zwróci żadnego przepisu, LLM generuje przepis od zera (PDF, oznaczony „wygenerowany przez AI”, ta sama walidacja).
- W raporcie nazywamy to wyszukiwaniem po składnikach (retrieval bez wektorów), a nie wektorowym RAG-iem. Embeddingi zostają poza PoC.

### D-005: Klucze API tylko na backendzie, aplikacja łączy się przez backend pośredniczący

- **Data:** 12.11.2026
- **Autor:** Kajtek
- **Status: przyjęta** (uwaga prowadzącego)

**Decyzja.** Aplikacja mobilna nie zna żadnego klucza API. Wysyła zdjęcia i listę produktów do naszego backendu w Pythonie (FastAPI), a dopiero backend woła dostawców LLM. Klucze są w `.env` na backendzie (README, „Uruchomienie”).

```
aplikacja (Expo) ──HTTP──► backend FastAPI ──klucz z .env──► Vision LLM / LLM tekstowy
```

**Konsekwencje.**

- Endpointy (nazwy do ustalenia z osobą 2): `POST /scan` (zdjęcia ze strefami → `ScanResult`) i `POST /recipes` (lista po korekcie + profil użytkownika → 3 przepisy).
- Zmienne `EXPO_PUBLIC_*` trafiają do paczki aplikacji i każdy może je odczytać. Wolno w nich trzymać tylko adres backendu, nigdy klucze.
- W czasie developmentu telefon z Expo Go łączy się z backendem na laptopie po adresie IP w sieci lokalnej (nie `localhost`) albo przez tunel.
- Backend to też miejsce na limit skanów i zapis kosztu każdego skanu (PDF, „Ryzyka”).

### D-006: Frontend w React Native (Expo), TypeScript

- **Data:** 12.11.2026
- **Autor:** Kajtek
- **Status: przyjęta** (prowadzący zatwierdził projekt z tym frontendem, 10.11.2026)
- **Zastępuje:** w PDF „Gradio albo prosta strona” w PoC i PWA później

**Decyzja.** Aplikację mobilną piszemy w React Native na Expo, w TypeScript, i testujemy na telefonach w Expo Go. Cała część AI i backend zostają w Pythonie. Ekrany jak w mailu do prowadzącego: zdjęcia strefami (D-001) → analiza → podsumowanie z korektą (edycja, dodawanie, usuwanie) → przepisy.

### D-007: Jedno repozytorium, aplikacja mobilna w folderze `mobile/`

- **Data:** 12.11.2026
- **Autor:** Kajtek
- **Status: do potwierdzenia z zespołem** (szczególnie z osobą 3, frontend)

**Decyzja.** Backend i aplikacja mobilna są w tym samym repozytorium.

```
smart-fridge-chef/
├── src/smart_fridge_chef/   backend w Pythonie: słownik, Vision LLM, przepisy, FastAPI
├── tests/
├── mobile/                  aplikacja Expo / React Native
└── docs/
```

**Dlaczego.** Zmianę formatu odpowiedzi API (np. `ScanResult`) robimy w backendzie i aplikacji w jednym commicie. Prowadzący dostaje jeden link do całego projektu. Expo działa bez problemu z podfolderu (`cd mobile && npx expo start`).

### D-008: Pierwszy dostawca Vision LLM to Gemini (`gemini-3.1-flash-lite`)

- **Data:** 12.11.2026
- **Autor:** Kajtek
- **Status: przyjęta** (dotyczy tylko modelu na start; porównanie modeli w O-002)

**Decyzja.** Klient Vision LLM (`src/smart_fridge_chef/vision/client.py`) na start woła Gemini przez SDK `google-genai`. Domyślny model to `gemini-3.1-flash-lite`. Klucz trzymamy w `.env` jako `GEMINI_API_KEY` (D-005).

**Dlaczego.**

- Darmowy limit w Google AI Studio. Klucz dostaje się bez podpinania karty, więc każdy w zespole może od razu testować. OpenAI wymaga doładowania kredytów z góry.
- Gemini przyjmuje schemat JSON wygenerowany z `ScanResult` (`response_json_schema`). Sprawdzone na żywym API 12.11.2026, odpowiedź przechodzi walidację Pydantica.

**Konsekwencje.**

- Wszystkie zdjęcia skanu idą w jednym wywołaniu, każde podpisane strefą. To pierwszy wariant z O-007.
- Model czasem zwraca ID spoza słownika (np. `eggs` zamiast `egg`). Klient mapuje takie ID przez aliasy ze słownika, a jeśli nic nie pasuje, ustawia `null` i zostawia `label`. Pozycja trafia wtedy do „spoza słownika” (D-003).
- Inni dostawcy (OpenAI, Anthropic) dochodzą jako kolejne warianty przy porównaniu w O-002. Format wyniku (`ScanResult`) zostaje ten sam.

## Otwarte pytania

| Nr | Pytanie | Propozycja | Kto / do kiedy |
|---|---|---|---|
| O-002 | Które Vision LLM porównujemy? | Po jednym tańszym i mocniejszym od 2–3 dostawców (PDF). Start: `gemini-3.1-flash-lite` (D-008). Dostępne 12.11.2026 w Gemini API m.in. `gemini-3.5-flash-lite`, `gemini-3.6-flash`, `gemini-3.8-flash`, `gemini-4-argon`. Które są w darmowym limicie, trzeba sprawdzić w cenniku. | Zespół |
| O-003 | Źródło przepisów: RecipeNLG czy Food.com? | Food.com; licencję sprawdzić przed importem (PDF). Słownik jest już zbudowany na Food.com (kopia na Hugging Face: `KingName1/food.com`). | Zespół |
| O-004 | Jaki jest termin oddania projektu? | Zapytać prowadzącego w następnym mailu. Frontend w TypeScript jest rozstrzygnięty (D-006). | Kajtek |
| O-005 | Do jakiej rozdzielczości zmniejszamy zdjęcia? | Zmierzyć 1000 i 1500 px na dłuższym boku i wybrać najniższą, przy której etykiety są czytelne | Kajtek |
| O-006 | Jedno zdjęcie całej lodówki czy strefy: ile zyskujemy? | Eksperyment na tych samych lodówkach: F1, koszt, czas | Kajtek |
| O-007 | Jedno wywołanie LLM ze wszystkimi zdjęciami czy osobne na każdą strefę (równolegle)? | Zmierzyć oba warianty w PoC. Ważne przez duplikaty (D-003): przy osobnych wywołaniach model nie widzi pozostałych zdjęć i nie może sam usunąć powtórzeń. | Kajtek |
| O-010 | Przyprawy podstawowe (sól, olej, pieprz) w rankingu przepisów | Zakładać, że zawsze są, i nie liczyć ich do braków (D-004) | Osoba 2 (backend) |
| O-011 | Kalorie: z Food.com czy liczone przez backend ze słownika? | Źródłem prawdy jest backend; Food.com służy do sprawdzenia normalizacji | Osoba 2 (backend) |
| O-012 | Testowe profile użytkowników z alergiami do sprawdzenia progu „0 przepisów z alergenem” | 3–5 profili z typowymi alergenami | Osoba 2 (backend) |

## Zamknięte pytania

| Nr | Pytanie | Rozstrzygnięcie |
|---|---|---|
| O-001 | Czy zaczynamy od PoC z dwoma LLM-ami, a o YOLO decydujemy po PoC? | Tak, D-002 (prowadzący: gotowe modele przez API są OK) |
| O-008 | Kanoniczna jednostka każdego składnika (szt., g, ml) | Pole `unit` w słowniku (`src/smart_fridge_chef/data/ingredients.json`), sprawdzane przez `Ingredient` w `dictionary.py` |
| O-009 | Jak w ewaluacji liczymy pozycje „inny” i produkty widoczne częściowo? | D-003: pole `visibility` w ręcznej liście, pozycje spoza słownika poza F1 |
