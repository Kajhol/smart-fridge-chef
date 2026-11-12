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

**Zastrzeżenia**

- To jeden skan, więc liczby pokazują kierunek, a nie wynik. Wnioski wyciągamy dopiero z całego zbioru (D-003).
- Przy spisywaniu przyjęliśmy regułę: produkt spoza słownika, który w przepisie da się zamienić na inny, wpisujemy pod ID tego najbliższego (mandarynki jako `orange`). Inne produkty spoza słownika mają `ingredient_id = null` (np. mleczko zagęszczone, dżem, katering).
