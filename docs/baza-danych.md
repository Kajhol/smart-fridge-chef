# Baza danych – szkic

**Status: propozycja, do ustalenia z osobą 2 (backend).** Zasada wyszukiwania jest przyjęta (D-004 w [specyfikacji](specyfikacja.md)). Źródło przepisów jest wciąż otwarte (O-003), ale słownik jest już zbudowany na Food.com.

## Zasada

Słownik składników łączy lodówkę z przepisami: obie strony używają tych samych `ingredient_id`. Tekst składników z przepisu („2 ząbki czosnku”) mapujemy na ID słownika **raz, przy imporcie**. Dzięki temu wyszukiwanie to zwykłe SQL, bez LLM.

```
lodówka ──ingredient_id──► SŁOWNIK ◄──ingredient_id── składniki przepisu ──recipe_id──► przepisy
```

## Tabele

| Tabela | Kolumny |
|---|---|
| `ingredients` | `id` (np. `milk`), `name_pl`, `name_en`, `unit` (`pcs`/`g`/`ml`), `allergens`, `aliases` (nazwy z przepisów, np. `eggs`, `egg yolks` → `egg`) |
| `recipes` | `id`, `title`, `steps`, `time_min`, `servings`, `kcal_per_serving` (ze źródła przepisu), `difficulty` (`easy`/`medium`/`hard`), `rating`, `source`, `url` |
| `recipe_ingredients` | `recipe_id`, `ingredient_id`, `quantity`, `unit`, `raw_text` (oryginał ze strony, do sprawdzania mapowania) |
| `pantry_staples` | `ingredient_id` (sól, olej, pieprz – zakładamy, że user zawsze je ma) |

Lodówka w PoC nie jest tabelą: to lista po ekranie korekty, przekazywana w zapytaniu.

## Import przepisu

1. Pobranie przepisu (zbiór z Kaggle albo dane schema.org/Recipe ze strony, np. biblioteką `recipe-scrapers`).
2. Mapowanie składników na ID słownika (LLM, jednorazowo). Przepis z niezmapowanymi składnikami odpada albo idzie do ręcznego sprawdzenia.
3. Poziom trudności: z czasu, liczby składników i kroków, ewentualnie jednorazowa klasyfikacja przez LLM.

## Wyszukiwanie

Zasada z decyzji D-004 w [specyfikacji](specyfikacja.md): najpierw twardy filtr po składnikach (brakuje najwyżej `:max_missing`, domyślnie 2), bez embeddingów.

```sql
SELECT r.id, r.title,
       COUNT(*) - COUNT(f.ingredient_id)       AS missing,    -- ilu składników brakuje
       COUNT(f.ingredient_id) * 1.0 / COUNT(*) AS coverage    -- odsetek składników w lodówce
FROM recipes r
JOIN recipe_ingredients ri ON ri.recipe_id = r.id
LEFT JOIN fridge f          ON f.ingredient_id = ri.ingredient_id
WHERE ri.ingredient_id NOT IN (SELECT ingredient_id FROM pantry_staples)
  AND r.difficulty IN (:allowed_difficulties)
  AND r.id NOT IN (/* przepisy z alergenem usera */)
GROUP BY r.id
HAVING COUNT(*) - COUNT(f.ingredient_id) <= :max_missing
ORDER BY missing ASC, coverage DESC, r.rating DESC
LIMIT 20;
```

Te ~20 kandydatów trafia do LLM tekstowego, który wybiera 3, przelicza porcje i je opisuje. Proporcje pochodzą z oryginalnego przepisu, LLM ich nie wymyśla. Gdy zapytanie nic nie zwróci, LLM generuje przepis od zera (oznaczony „wygenerowany przez AI”).

Sortowanie najpierw po `missing`, a nie po `coverage`, bo sam odsetek premiuje krótkie przepisy (2 z 3 składników = 67%), a liczba braków mówi użytkownikowi, ile musi dokupić.

## Uwaga prawna (przy scrapingu)

Lista składników to fakty, ale treść kroków i zdjęcia są chronione prawem autorskim, a regulaminy stron często zabraniają scrapingu. W PoC: pole `source` i link do oryginału. W produkcie: pokazywać składniki i dopasowanie, a po kroki odsyłać na stronę autora, albo zawrzeć umowę.
