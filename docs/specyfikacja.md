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
- **Skany z aplikacji** (dopisane 20.11.2026). Po korekcie listy przycisk „Przygotuj zapis do ewaluacji” pozwala oznaczyć `visibility` każdej pozycji, a „Zapisz skan” wysyła wszystko do `POST /scans`. Backend zapisuje w kolejnym `scan_NNN` zdjęcia, `ground_truth.json` z listy po korekcie, odpowiedź modelu bez poprawek (`pred_…_app_….json`) i metryki (`metrics_…_app_….json`). Produkty dodane z aplikacji (`custom_…`, D-011) trafiają do ręcznej listy jako `null`. **Uwaga:** lista powstaje z poprawiania odpowiedzi modelu, więc łatwo przepuścić jego błędy (zostawić halucynację, nie dopisać schowanego produktu). Listę sprawdzamy przy otwartej lodówce, a ilości przepisujemy z opakowań, tak jak przy spisywaniu ręcznym.

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

### D-009: Kontrakt `POST /recipes`

- **Data:** 17.11.2026
- **Autor:** Igor
- **Status: do potwierdzenia z zespołem** (szczególnie z Kajtkiem: wejście korzysta z `DetectedItem`)
- **Doprecyzowuje:** D-004 (kto przelicza porcje), D-005 (nazwa i kształt endpointu)

**Decyzja.** Schematy są w `src/smart_fridge_chef/recipes/schema.py`, w tym samym stylu co `vision/schema.py` (Pydantic, `Field(description=...)`, wspólny typ `Unit`).

- **Wejście** `RecipeRequest`: `items` (lista po ekranie korekty, kształt `DetectedItem`; `confidence` opcjonalne, więc przechodzi też pozycja dodana ręcznie) i `profile` (alergeny, wykluczone składniki, maksymalna trudność, maksymalny czas, liczba porcji). JSON, nie multipart. Backend jest bezstanowy: aplikacja wysyła listę i profil za każdym razem.
- **Wyjście** `RecipeResponse`: do 3 przepisów. Każdy składnik ma status `in_fridge`, `missing` albo `pantry`, więc lista zakupów to filtr po statusie. `candidates_considered` mówi, ile przepisów przeszło filtr SQL.
- **LLM do wyboru** zwraca tylko `RecipeSelection` (ID przepisu, opis, zamienniki). Resztę przepisu składa kod z bazy i sprawdza, że wybrane ID jest wśród kandydatów.
- **Tłumaczenie** tytułu, kroków i linii składników (D-010) na polski: osobne wywołanie `TranslatedRecipe`, tylko dla wybranych przepisów, nie dla ~20 kandydatów.
- `Allergen` to dokładnie te wartości, które są w słowniku (sprawdza test).

**Odstępstwo od D-004** (zastąpione przez D-010). Ilości są dokładne, z danych, i na PoC nie są przeliczane na porcje z profilu. Przeliczanie zostaje w kodzie (nie w LLM), jeśli je dodamy: tylko dla przepisów z liczbą porcji.

**Do ustalenia.**

- Dieta: słownik nie ma flagi wegetariańskiej. Na PoC zastępuje ją `excluded_ingredients`.
- Kalorie (O-011): słownik nie ma kcal. Na PoC `kcal_per_serving` z Food.com, pole może być `null`.
- Ilość w lodówce na PoC się nie liczy, tylko obecność (D-004).
- Pozycje z `ingredient_id = null` są pomijane przy dopasowaniu.
- `max_missing` (2) to stała backendu, nie parametr API.

### D-010: Przepisy z Food.com: kroki z RAW_recipes, ilości z Karo8870

- **Data:** 17.11.2026
- **Autorzy:** Igor, Kajtek
- **Status: przyjęta** (Igor i Kajtek)
- **Zamyka:** O-003
- **Zmienia:** D-009 (porcje, składniki w odpowiedzi)

**Decyzja.** LLM **nie szacuje ilości**. Przepis pokazujemy dokładnie tak, jak w źródle.

- **Kroki, ID, czas, kcal:** `RAW_recipes.csv` z Kaggle (`shuyangli94/food-com-recipes-and-user-interactions`, ok. 231 tys. przepisów). Z ID robimy link do food.com.
- **Ilości, jednostki, porcje:** `parsed_recipes.csv` z Hugging Face (`Karo8870/food.com-parsed-dataset`, 490 tys. przepisów z Food.com ze składnikami rozbitymi na ilość, jednostkę i nazwę). Ten zbiór nie ma ID, a w 32% przepisów zamiast kroków ma linki do zdjęć, więc nie wystarcza sam.
- **Łączenie** po nazwie (tylko `[a-z0-9]`, małe litery) i kcal zaokrąglonych do 0,1. Przepis bez jednoznacznej pary odpada. Odpada też przepis, w którym jakiś składnik nie ma ilości (poza solą, pieprzem, wodą i olejem).
- **Porcje** (1–24) są w ok. połowie przepisów. Przepis bez porcji zostaje: ilości są dokładne, tylko nie wiadomo, na ile osób (`Recipe.servings = null`).
- **Statusy** `in_fridge`/`missing`/`pantry` liczymy ze składników z RAW_recipes (mapowanie na słownik przy imporcie, D-004). Linie z Karo8870 służą tylko do wyświetlenia (`Recipe.ingredient_lines`), więc nie trzeba ich parować ze składnikami. W ok. 13% przepisów liczba linii różni się od liczby składników (np. „1/3 cup butter or margarine” to jedna linia).
- **LLM tłumaczy** linie składników na polski w tym samym wywołaniu co tytuł i kroki (`TranslatedRecipe.ingredient_lines_pl`): liczby zostają bez zmian, jednostki po polsku (szklanka, łyżka, łyżeczka), bez przeliczania na g/ml.

**Alergeny** (audyt 18.11.2026). Alergeny przepisu są liczone przy imporcie do tabeli `recipe_allergens`: suma alergenów zmapowanych składników plus alergeny przypraw pomijanych przy mapowaniu (`celery salt`, `celery seed` → seler; bez tego 33 przepisy z selerem przechodziły u alergika). W słowniku dopisane: sos Worcestershire → gluten (słód jęczmienny w wersji UK), rodzynki → siarczyny. `uv run audit-allergens` szuka w liniach składników słów sugerujących alergen spoza `recipe_allergens`. Po poprawkach na kopii HF zostają tylko fałszywe alarmy (np. „peanut butter” przy mleku, „cream of tartar”), zwykły i jabłkowy ocet (przyjmujemy: bez siarczynów) oraz ok. 40 przepisów z alternatywą w linii („vanilla or almond extract”). Alternatyw nie liczymy jako alergenu przepisu, bo podstawowa wersja jest bezpieczna.

**Licencja.** Żaden ze zbiorów nie ma otwartej licencji (RAW_recipes: „Data files © Original Authors”; Karo8870: brak opisu i licencji). Oba to dane z Food.com opublikowane do badań z artykułem: Majumder, Li, Ni, McAuley, *Generating Personalized Recipes from Historical User Preferences*, EMNLP 2019. W projekcie: cytujemy artykuł, podajemy link do obu zbiorów, **danych nie commitujemy** (tylko skrypt importu), przy każdym przepisie jest link do food.com.

**Pokrycie** (pomiar 17.11.2026 na kopii HF `KingName1/food.com`, 87 862 przepisy, bez ID): 7 274 przepisy mają wszystkie składniki w słowniku, z tego 6 624 (91%) łączy się jednoznacznie z Karo8870, a **5 823** ma też ilości. 3 287 z nich ma liczbę porcji. Losowa próba 20 połączonych przepisów: wszystkie to te same dania (te same składniki w tej samej kolejności). Na pełnym RAW_recipes z Kaggle powinno wyjść ok. 2,5 razy więcej.

### D-011: Użytkownik dodaje produkty do słownika z aplikacji

- **Data:** 20.11.2026
- **Autor:** Kajtek
- **Status: do potwierdzenia z Igorem** (dotyczy `/recipes`)
- **Doprecyzowuje:** D-006 (ekran korekty), D-009 (`ingredient_id` w `RecipeRequest`)

**Decyzja.** Na ekranie korekty użytkownik może zmienić nazwę pozycji (np. model rozpoznał „owoce w folii”, a to mandarynki) i wybrać produkt ze słownika. Jeśli produktu w słowniku nie ma, dodaje go z aplikacji: nazwa po polsku i jednostka (`pcs`, `g`, `ml`).

- **`GET /ingredients`** zwraca słownik (`id`, `name_pl`, `unit`) i produkty dodane z aplikacji, z polem `custom`.
- **`POST /ingredients`** (`name_pl`, `unit`) zapisuje produkt w `data/custom_ingredients.json` na backendzie, z `id` w postaci `custom_<nazwa>` (np. `custom_mandarynka`). Plik nie jest w gicie. `ingredients.json` się nie zmienia, bo to słownik zespołu z aliasami do przepisów.
- **Bez duplikatów:** nazwy porównujemy bez wielkich liter, ogonków i znaków. Drugie „Mandarynka!” zwraca istniejącą pozycję, a „jablko” zwraca słownikowe `apple`, zamiast tworzyć nową.

**Ograniczenie.** Dodany produkt **nie dopasuje się do żadnego przepisu**. Baza z D-010 zawiera tylko przepisy, których wszystkie składniki są w słowniku, a nowy produkt nie ma angielskich aliasów. Żeby zaczął działać w przepisach, trzeba przenieść go do `ingredients.json` z aliasami (np. `tangerine`, `mandarin orange`) i zaimportować przepisy ponownie. `data/custom_ingredients.json` służy więc też jako lista produktów do dopisania.

**Skutek dla `/recipes`.** `RecipeRequest.items` może zawierać `ingredient_id` w stylu `custom_…`. Backend nie powinien zwracać wtedy błędu, tylko traktować taką pozycję jak produkt, którego nie ma w żadnym przepisie.

### D-012: Wyszukiwanie kandydatów i `POST /recipes` bez LLM

- **Data:** 20.11.2026
- **Autor:** Igor
- **Status: przyjęta** (Igor; do wiadomości zespołu)
- **Doprecyzowuje:** D-004 (filtr i ranking), D-009 (endpoint), D-011 (pozycje `custom_…`)

**Decyzja.** `find_candidates` (`src/smart_fridge_chef/recipes/search.py`) to jedno zapytanie SQL, bez LLM. Endpoint `POST /recipes` (`recipes/router.py`, podpięty w `api.py` jedną linią) zwraca 3 najlepsze przepisy w formacie `RecipeResponse`. W M3 LLM wybiera spośród tych samych kandydatów i tłumaczy (D-013); bez LLM tytuł, kroki i linie składników są po angielsku, a opis jest z szablonu („Masz 3 z 4 głównych składników. Brakuje: cebula.”).

- **Lodówka** to `ingredient_id` z listy. Pozycje z `null` i dodane z aplikacji (`custom_…`) nie pasują do żadnego przepisu, ale nie powodują błędu.
- **Filtr:** najwyżej 2 braki (`MAX_MISSING`), przyprawy z `pantry_staples` się nie liczą. Przepis musi mieć co najmniej 3 główne składniki i co najmniej 2 z lodówki, żeby nie wygrywały „jajko na twardo” ani „microwave cleaner”. Odpadają przepisy z alergenem z profilu (`recipe_allergens`), z wykluczonym składnikiem, trudniejsze niż `max_difficulty` i dłuższe niż `max_time_min` (przepis bez czasu przechodzi).
- **Ranking:** liczba produktów z lodówki minus 1,5 za każdy brak. Przepis na 5 produktów z lodówki i 1 brak wygrywa z 3 produktami bez braków. Przy remisie decyduje mniej braków, potem ocena.
- **Ocena:** z `RAW_interactions.csv` (opcja `--interactions` importu), średnia bayesowska z wagą 5, żeby jedna piątka nie biła setki ocen 4,8. Ocena 0 (recenzja bez gwiazdek) jest pomijana.
- **Brak bazy:** `503` z instrukcją importu. Ścieżkę zmienia zmienna `RECIPES_DB`.

**Pomiar** (20.11.2026, kopia HF, 5 823 przepisy, lodówka ze `scan_001`): 215 kandydatów bez ograniczeń, 38 przy alergii na jajka, 24 przy mleku, glutenie i 30 min. Zapytanie trwa ok. 20 ms.

**Ograniczenie.** Ilość w lodówce się nie liczy, tylko obecność (D-004): jedno jajko wystarczy do przepisu na sześć.

### D-013: LLM w `POST /recipes`: wybór, tłumaczenie, przepis od AI

- **Data:** 20.11.2026
- **Autor:** Igor
- **Status: przyjęta** (Igor; do wiadomości zespołu)
- **Doprecyzowuje:** D-004 (LLM tylko wybiera i opisuje), D-009 (kontrakt bez zmian), D-010 (tłumaczenie linii), D-012

**Decyzja.** Kod w `src/smart_fridge_chef/recipes/chef.py`, model z `RECIPE_MODEL` przez `recipes/llm.py`. LLM wybiera, opisuje i tłumaczy; kod sprawdza każdą odpowiedź. Kontrakt `RecipeResponse` się nie zmienia.

- **Wybór:** LLM dostaje 20 najlepszych kandydatów z rankingu SQL (ID, tytuł, czas, trudność, składniki z lodówki i brakujące), lodówkę i listę zakazanych składników. Zwraca `RecipeSelection`. Kod odrzuca ID spoza kandydatów i powtórzenia, a brakujące miejsca dopełnia rankingiem z SQL. Zamiennik przechodzi tylko dla składnika, który w tym przepisie naprawdę brakuje.
- **Alergeny:** kandydaci są już bez alergenów z profilu (SQL, D-012), więc LLM nie może wybrać przepisu z alergenem. Tekst od LLM (opis, zamiennik, przepis od AI) przechodzi przez filtr słów: nazwy po polsku i angielsku składników z alergenem albo wykluczonych, z odmianą („jajko” łapie „jajka”). Trafienie oznacza opis z szablonu, usunięty zamiennik albo odrzucony przepis od AI. To zabezpieczenie dodatkowe i heurystyka: nie łapie wymian w rdzeniu („masło”, „na maśle”).
- **Tłumaczenie:** osobne wywołanie `TranslatedRecipe` dla każdego z 3 przepisów, równolegle. Gdy zmieni się liczba kroków albo linii, zostaje oryginał. Linia składnika, w której zmieniły się liczby, zostaje po angielsku: ilość jest ważniejsza niż język.
- **Przepis od AI**, gdy 0 kandydatów: LLM dostaje tylko dozwolone składniki (słownikowe z lodówki i przyprawy, bez alergenów i wykluczeń) i zwraca `GeneratedRecipe` z ID użytych składników. Kod odrzuca przepis ze składnikiem spoza listy, z zakazanym słowem, trudniejszy albo dłuższy niż w profilu. Wtedy lista jest pusta. Przepis ma `source: "ai_generated"`, `id` i `url` = `null`, porcje z profilu, wszystkie składniki `in_fridge` albo `pantry`. Produkty `custom_…` (D-011) nie trafiają do listy dozwolonych, bo nie znamy ich alergenów.
- **Bez LLM:** bez klucza w `.env` (`GEMINI_API_KEY`/`GOOGLE_API_KEY` albo `GROQ_API_KEY`) i przy każdym błędzie LLM (limit, timeout, zły JSON) odpowiedź jest jak w M2: ranking z SQL, tekst po angielsku, opis z szablonu. Endpoint nie zwraca 500 z powodu LLM.

**Pomiar** (20.11.2026, kopia HF, lodówka ze `scan_001`): prompt wyboru ma ok. 3 700 znaków przy 20 kandydatach, tłumaczenie 600–1 300 znaków na przepis, czyli 4 wywołania na zapytanie. Czas i koszt z prawdziwym modelem mierzymy w M4.

**Później:** przepis od AI z produktów `custom_…`; zamienniki alergenów z kuratorowanej tabeli (opcja 2 z rozmowy o zamiennikach); cache tłumaczeń po ID przepisu.

## Otwarte pytania

| Nr | Pytanie | Propozycja | Kto / do kiedy |
|---|---|---|---|
| O-002 | Które Vision LLM porównujemy? | Po jednym tańszym i mocniejszym od 2–3 dostawców (PDF). Start: `gemini-3.1-flash-lite` (D-008). Dostępne 12.11.2026 w Gemini API m.in. `gemini-3.5-flash-lite`, `gemini-3.6-flash`, `gemini-3.8-flash`, `gemini-4-argon`. Które są w darmowym limicie, trzeba sprawdzić w cenniku. | Zespół |
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
| O-003 | Źródło przepisów: RecipeNLG czy Food.com? | Food.com: RAW_recipes (Kaggle) + ilości z Karo8870 (HF), D-010 |
| O-009 | Jak w ewaluacji liczymy pozycje „inny” i produkty widoczne częściowo? | D-003: pole `visibility` w ręcznej liście, pozycje spoza słownika poza F1 |
