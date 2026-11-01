# Baza danych – szkic

**Status: propozycja, do ustalenia z osobą 2 (backend).** Źródło przepisów jest wciąż otwarte (O-003 w [specyfikacji](specyfikacja.md)).

## Zasada

Słownik składników łączy lodówkę z przepisami: obie strony używają tych samych `ingredient_id`. Tekst składników z przepisu („2 ząbki czosnku”) mapujemy na ID słownika **raz, przy imporcie**. Dzięki temu wyszukiwanie to zwykłe SQL, bez LLM.

```
lodówka ──ingredient_id──► SŁOWNIK ◄──ingredient_id── składniki przepisu ──recipe_id──► przepisy
```

## Tabele

| Tabela | Kolumny |
|---|---|
| `ingredients` | `id` (np. `milk`), `name_pl`, `name_en`, `unit` (`pcs`/`g`/`ml`), `kcal` (na 100 g / 100 ml / 1 szt.), `allergens` |
| `recipes` | `id`, `title`, `steps`, `time_min`, `servings`, `difficulty` (`easy`/`medium`/`hard`), `rating`, `source`, `url` |
| `recipe_ingredients` | `recipe_id`, `ingredient_id`, `quantity`, `unit`, `raw_text` (oryginał ze strony, do sprawdzania mapowania) |
| `pantry_staples` | `ingredient_id` (sól, olej, pieprz – zakładamy, że user zawsze je ma) |

Lodówka w PoC nie jest tabelą: to lista po ekranie korekty, przekazywana w zapytaniu.

## Import przepisu

1. Pobranie przepisu (zbiór z Kaggle albo dane schema.org/Recipe ze strony, np. biblioteką `recipe-scrapers`).
2. Mapowanie składników na ID słownika (LLM, jednorazowo). Przepis z niezmapowanymi składnikami odpada albo idzie do ręcznego sprawdzenia.
3. Poziom trudności: z czasu, liczby składników i kroków, ewentualnie jednorazowa klasyfikacja przez LLM.

## Wyszukiwanie

```sql
SELECT r.id, r.title,
       COUNT(f.ingredient_id) * 1.0 / COUNT(*) AS coverage   -- odsetek składników w lodówce
FROM recipes r
JOIN recipe_ingredients ri ON ri.recipe_id = r.id
LEFT JOIN fridge f          ON f.ingredient_id = ri.ingredient_id
WHERE ri.ingredient_id NOT IN (SELECT ingredient_id FROM pantry_staples)
  AND r.difficulty IN (:allowed_difficulties)
  AND r.id NOT IN (/* przepisy z alergenem usera */)
GROUP BY r.id
ORDER BY coverage DESC, r.rating DESC
LIMIT 20;
```

Te ~20 kandydatów trafia do LLM tekstowego, który wybiera 3 i przelicza porcje. Proporcje pochodzą z oryginalnego przepisu, LLM ich nie wymyśla.

## Uwaga prawna (przy scrapingu)

Lista składników to fakty, ale treść kroków i zdjęcia są chronione prawem autorskim, a regulaminy stron często zabraniają scrapingu. W PoC: pole `source` i link do oryginału. W produkcie: pokazywać składniki i dopasowanie, a po kroki odsyłać na stronę autora, albo zawrzeć umowę.
