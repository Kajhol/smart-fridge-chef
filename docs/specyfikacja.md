# Smart Fridge Chef – specyfikacja i decyzje

Żywy dokument: tu zapisujemy podjęte decyzje i otwarte pytania. Tło i uzasadnienie całego podejścia jest w [Smart-Fridge-Chef-PoC.pdf](Smart-Fridge-Chef-PoC.pdf). Jeśli coś tutaj różni się od PDF-a, obowiązuje ten dokument.

Każda decyzja ma numer (D-001, D-002…), datę, autora i status: **do potwierdzenia**, **przyjęta** albo **zastąpiona** (z odnośnikiem do nowej). Decyzji nie usuwamy, tylko zmieniamy status, żeby było widać, skąd się wzięło obecne rozwiązanie.

## Decyzje

### D-001: Skan lodówki to kilka zdjęć robionych strefami, krok po kroku

- **Data:** 01.11.2026
- **Autor:** Kajtek
- **Status: do potwierdzenia z zespołem**
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
- Ten sam produkt widać na wielu klatkach, więc model łatwo liczy go podwójnie. Strefy (drzwi, półki) fizycznie się nie pokrywają, więc przy zdjęciach tego problemu prawie nie ma.
- Film natywnie przyjmuje tylko część dostawców (np. Gemini). U pozostałych i tak trzeba wycinać klatki.

Na później (poza PoC): użytkownik nagrywa film, a aplikacja sama wybiera z niego 4–6 ostrych, różnych klatek. Wygoda filmu, koszt jak przy zdjęciach.

**Konsekwencje.**

- **API:** skan to lista zdjęć, każde z etykietą strefy (`door`, `shelves_upper`, `shelves_lower`, `extra`).
- **Backend:** zdjęcia zmniejszamy przed wysłaniem do modelu (rozdzielczość do ustalenia, patrz pytanie O-005).
- **Ewaluacja:** ręcznie spisana lista „co tu jest i ile” dotyczy całego skanu, nie pojedynczego zdjęcia. Zbiór testowy to mniej lodówek, ale więcej zdjęć każdej z nich: około 15–20 lodówek po 3–4 zdjęcia zamiast 30–50 luźnych zdjęć. Metryki (F1, błąd ilości, powtarzalność, czas, koszt) liczymy na skan.
- **Zbieranie zdjęć (krok 2 planu w PDF):** każdy fotografuje swoją lodówkę według tych samych stref i dorzuca jedno zdjęcie całej lodówki do eksperymentu z pytania O-006.

## Otwarte pytania

| Nr | Pytanie | Propozycja | Kto / do kiedy |
|---|---|---|---|
| O-001 | Czy zaczynamy od PoC z dwoma LLM-ami, a o YOLO decydujemy po PoC? | Tak (PDF) | Zespół |
| O-002 | Które Vision LLM porównujemy? | Po jednym tańszym i mocniejszym od 2–3 dostawców (PDF) | Zespół |
| O-003 | Źródło przepisów: RecipeNLG czy Food.com? | Food.com z Kaggle; licencję sprawdzić przed importem (PDF) | Zespół |
| O-004 | Kto pyta prowadzącego o termin i o frontend w TypeScript? | — | Zespół |
| O-005 | Do jakiej rozdzielczości zmniejszamy zdjęcia? | Zmierzyć 1000 i 1500 px na dłuższym boku i wybrać najniższą, przy której etykiety są czytelne | Kajtek |
| O-006 | Jedno zdjęcie całej lodówki czy strefy: ile zyskujemy? | Eksperyment na tych samych lodówkach: F1, koszt, czas | Kajtek |
| O-007 | Jedno wywołanie LLM ze wszystkimi zdjęciami czy osobne na każdą strefę (równolegle)? | Zmierzyć oba warianty w PoC | Kajtek |
| O-008 | Kanoniczna jednostka każdego składnika (szt., g, ml) | Pole w słowniku; bez tego nie policzymy błędu ilości | Zespół, przy słowniku (krok 1) |
| O-009 | Jak w ewaluacji liczymy pozycje „inny” i produkty widoczne częściowo? | Ustalić przed spisywaniem ręcznych list | Kajtek |
| O-010 | Przyprawy podstawowe (sól, olej, pieprz) w rankingu przepisów | Zakładać, że zawsze są, i nie liczyć ich do odsetka | Osoba 2 (backend) |
| O-011 | Kalorie: z Food.com czy liczone przez backend ze słownika? | Źródłem prawdy jest backend; Food.com służy do sprawdzenia normalizacji | Osoba 2 (backend) |
| O-012 | Testowe profile użytkowników z alergiami do sprawdzenia progu „0 przepisów z alergenem” | 3–5 profili z typowymi alergenami | Osoba 2 (backend) |
