# Instrukcja implementacji algorytmów ruchu łazika

## 1. Cel zadania

Należy zaimplementować moduł nawigacji łazika poruszającego się **on-line** po
heksagonalnej mapie Marsa. Algorytm nie może zakładać, że łazik zna całą mapę
przed rozpoczęciem ruchu. W każdym kroku może korzystać wyłącznie z:

* bieżącej pozycji i celu,
* informacji zwróconych przez czujniki,
* historii własnych ruchów,
* stanu fizycznego i emocjonalnego,
* informacji otrzymanych od innych łazików (w wariancie roju).

Implementacja ma umożliwić porównanie trzech wariantów:

1. **zwykły algorytm online** bez pamięci emocjonalnej,
2. **algorytm online z emocjami**, który zapamiętuje stresujące miejsca i
   ogranicza ryzyko ich ponownego odwiedzenia,
3. **algorytm roju łazików z emocjami**, w którym lęk jest przekazywany przez
   radio innym agentom.

Każdy z powyższych wariantów musi dodatkowo działać w dwóch trybach
zadaniowych:

* **ekspansja** — łazik poznaje nieznany obszar, zwiększa pokrycie mapy i
  zbiera dane sensoryczne; nie ma obowiązku podążania do jednego celu,
* **dojście do celu** — łazik ma wskazaną pozycję docelową i wybiera ruchy,
  które prowadzą do niej z uwzględnieniem przeszkód, kosztu terenu oraz lęku.

Tryb zadaniowy (`exploration` albo `goal_navigation`) jest niezależny od
wariantu algorytmu (`online`, `emotional` albo `swarm_emotional`). Nie należy
tworzyć sześciu niezależnych implementacji całego agenta. Wspólna strategia
powinna otrzymać tryb zadaniowy jako część konfiguracji i zmieniać funkcję
oceny następnego pola.

Moduł nawigacji powinien być oddzielony od fizyki terenu, homeostatu i modelu
Mesa. Łazik wybiera następny heksagon, natomiast teren określa konsekwencje
wykonanego ruchu.

## 2. Stan obecnego projektu

Najważniejsze elementy, z którymi trzeba się zintegrować:

* `Pioneer3DXAgent` w `src/agents/rover.py` jest agentem Mesa. Obecny prototyp
  losowo wybiera sąsiednie pole inne niż `Boulders`, porusza agenta i nakłada
  efekt terenu.
* `MarsSimulation` w `src/model/model.py` tworzy `mesa.space.HexGrid`,
  rozmieszcza pola terenu i uruchamia agentów przez scheduler Mesa.
* `TerrainPatch` i klasy pochodne w `src/environment/terrain.py` reprezentują
  pola terenu oraz ich efekty fizyczne.
* `MarsMapGenerator` w `src/environment/generator.py` generuje spójną
  przestrzennie mapę na podstawie szumu Perlina.

Docelowo należy zachować wywoływanie `TerrainPatch.apply_effect(rover)` po
ruchu. Nawigacja nie może sama odejmować baterii ani uszkadzać podzespołów,
ponieważ te działania należą do klas terenu.

## 3. Model świata i reprezentacja pozycji

### 3.1. Siatka

Świat jest nieprzechodnią (`torus=False`) siatką heksagonalną. Pozycję należy
reprezentować tak samo jak Mesa, jako `tuple[int, int]`, np. `(x, y)`.

Sąsiedzi muszą być pobierani przez mechanizm siatki Mesa, a nie przez ręcznie
zdefiniowaną listę ruchów:

```python
neighbors = model.grid.get_neighborhood(
    position,
    moore=False,
    include_center=False,
)
```

Jeżeli używana wersja Mesa wymaga innego parametru dla `HexGrid`, należy użyć
jej natywnego API. Nie wolno mieszać geometrii Moore'a z geometrią
heksagonalną: obecne `moore=True` w prototypie powinno zostać zastąpione
zapytaniem zgodnym z `HexGrid`.

Przed rozważeniem pola trzeba sprawdzić, czy znajduje się ono w granicach
mapy. Siatka nie jest torusem, więc wyjście poza mapę oznacza ruch
niedozwolony.

### 3.2. Odczyt terenu

Na danym polu mogą znajdować się agent łazika i agent `TerrainPatch`.
Przydatny jest wspólny pomocniczy interfejs:

```python
def terrain_at(model, position) -> TerrainPatch | None:
    contents = model.grid.get_cell_list_contents([position])
    return next(
        (agent for agent in contents if isinstance(agent, TerrainPatch)),
        None,
    )
```

Do nawigacji trzeba rozróżniać co najmniej następujące klasy:

| Klasa | Znaczenie dla ruchu |
|---|---|
| `SafeRegolith` | preferowane podłoże, mały koszt energii |
| `Boulders` | fizyczna przeszkoda; nie wybierać jako celu ruchu |
| `LooseSand` | możliwy ruch, ale ryzyko uślizgu i duży koszt energii |
| `Ventifacts` | możliwy ruch, ryzyko uszkodzenia kół |
| `SteepSlope` | możliwy ruch, ryzyko wywrócenia |
| `DeepShadow` | możliwy ruch, szybko rośnie koszt baterii |
| `DustStorm` | możliwy ruch, ograniczona widoczność RGB |

LIDAR wykrywa fizyczne przeszkody, przede wszystkim `Boulders`. RGB nie
powinno zastępować LIDAR-u: rozpoznaje sygnaturę koloru terenu, ale nie
gwarantuje wykrycia przeszkody.

## 4. Kontrakt modułu nawigacji

Rekomendowane jest zdefiniowanie wspólnego interfejsu dla wszystkich trzech
trybów:

```python
class NavigationStrategy(Protocol):
    def choose_next(
        self,
        rover: Pioneer3DXAgent,
        observation: Observation,
    ) -> tuple[int, int] | None:
        ...
```

`Observation` powinien zawierać co najmniej:

```python
@dataclass
class Observation:
    position: tuple[int, int]
    target: tuple[int, int] | None
    navigation_mode: Literal["exploration", "goal_navigation"]
    visible_cells: dict[tuple[int, int], TerrainObservation]
    lidar_obstacles: set[tuple[int, int]]
    rgb_signatures: dict[tuple[int, int], tuple[int, int, int]]
    visited: set[tuple[int, int]]
    anxiety_memory: dict[tuple[int, int, int], FearRecord]
```

W trybie `exploration` `target` może mieć wartość `None`. W trybie
`goal_navigation` cel jest wymagany i musi znajdować się na mapie. Brak celu
jest błędem konfiguracji, a nie powodem do losowego ruchu.

Nazwy typów można dostosować do projektu, ale odpowiedzialności muszą pozostać
rozdzielone. Strategia ma wybrać ruch albo zwrócić `None`, gdy nie ma
bezpiecznego ruchu. Nie może cicho teleportować agenta, usuwać przeszkód ani
zmieniać stanu terenu.

Ruch jest dozwolony tylko wtedy, gdy:

1. sąsiad jest w granicach siatki,
2. nie jest przeszkodą wykrytą przez LIDAR,
3. pole nie jest zajęte przez innego łazika, jeżeli przyjęty model nie
   dopuszcza współdzielenia pola,
4. łazik nie jest `is_overturned`, zniszczony ani pozbawiony baterii,
5. pole nie jest wykluczone przez aktywny tryb emocjonalny, chyba że jest to
   jedyna droga lub cel.

## 5. Wspólna pętla kroku agenta

`Pioneer3DXAgent.step()` powinien wykonywać operacje w stałej kolejności:

1. Jeśli agent jest wywrócony, zniszczony albo nie ma baterii, zakończyć krok.
2. Zachować `battery_prev`, poprzednią pozycję i poprzedni typ terenu.
3. Odczytać LIDAR oraz kamery RGB w zasięgu `vision_range`.
4. Zbudować `Observation`.
5. Wywołać wybraną strategię `choose_next`.
6. Jeżeli strategia zwróci ruch, wykonać `model.grid.move_agent`.
7. Odczytać teren z nowej pozycji i wywołać dokładnie raz
   `terrain.apply_effect(self)`.
8. Zaktualizować licznik ekspozycji. Licznik `shadow_exposure_time` lub
   `dust_exposure_time` zeruje się po opuszczeniu odpowiedniego typu terenu.
9. Zaktualizować homeostat na podstawie różnicy baterii, prędkości,
   uszkodzeń i nachylenia.
10. Jeżeli stres osiągnął próg krytyczny, zapisać traumę, a w wariancie roju
    rozgłosić sygnał.
11. Zapisać metryki kroku: pozycję, koszt ruchu, stres, baterię, odwiedzone
    pola i przyczynę wybranego ruchu.

Nie wolno nakładać efektu pola przed ruchem i po ruchu jednocześnie. Obecny
prototyp robi to w `move()`, dlatego przy przenoszeniu logiki do strategii
należy pozostawić w jednym miejscu odpowiedzialność za wywołanie efektu.

## 6. Tryby zadaniowe łazika

### 6.1. Tryb ekspansji

Ekspansja służy do poznawania terenu. Łazik nie kieruje się do pojedynczego
`target`, tylko wybiera lokalny cel eksploracyjny, np.:

1. najbliższe nieodwiedzone pole,
2. pole na granicy znanego i nieznanego obszaru,
3. obszar o największej wartości informacyjnej,
4. bezpieczny punkt wymagający przejścia przez nową strefę terenu.

Wartość kandydata można określić jako:

```text
ocena_ekspansji =
    + w_nowe * informacja_o_nowym_polu
    + w_granica * kontakt_z_nieznanym
    + w_pokrycie * wzrost_pokrycia_mapy
    - w_koszt * koszt_terenu
    - w_ryzyko * ryzyko_uszkodzeń
    - w_lęk * kara_emocjonalna
```

Wariant bazowy może używać `OnlineSearch` do systematycznego odwiedzania
nieznanych pól. `visited` oznacza wtedy pola odwiedzone przez konkretnego
łazika, a osobno należy utrzymywać zbiór pól poznanych przez cały rój, jeśli
mapa ma być współdzielona.

Ekspansja kończy się, gdy:

* osiągnięto `exploration_budget` kroków,
* pokrycie obszaru przekroczyło `coverage_target`,
* nie ma osiągalnych nieodwiedzonych pól,
* bateria, stan techniczny lub stres nie pozwalają bezpiecznie kontynuować.

Brak nieodwiedzonego pola nie powinien powodować losowania. Agent ma zwrócić
status `exploration_complete` albo przełączyć się do dojścia do celu, jeśli
konfiguracja definiuje cel następczy.

### 6.2. Tryb dojścia do celu

W tym trybie łazik otrzymuje `target` przed rozpoczęciem epizodu. Celem może
być punkt startowy misji, stacja, próbka albo pozycja wskazana przez model.
Strategia:

1. odrzuca pola zablokowane przez LIDAR,
2. ocenia odległość do celu i koszt przejścia,
3. uwzględnia poznane przeszkody oraz pola nieznane,
4. w wariantach emocjonalnych dodaje karę za zapamiętane zagrożenia,
5. wybiera ruch zmniejszający koszt dojścia, niekoniecznie samą odległość.

Pozycja `target` jest osiągnięta, gdy `rover.pos == target`. Wtedy agent nie
wykonuje kolejnych ruchów i zapisuje status `goal_reached`. Jeżeli cel stanie
się niedostępny, agent powinien zgłosić `no_path` albo przejść do eksploracji
tylko wtedy, gdy jawnie zezwala na to konfiguracja.

### 6.3. Przełączanie trybów

Tryb powinien być jawny i zmieniany przez kontroler misji, a nie przypadkowo
przez strategię. Zalecany stan:

```python
self.navigation_mode = "exploration"
self.target: tuple[int, int] | None = None
self.exploration_budget = 500
self.coverage_target = 0.8
```

Przykładowe przejścia:

```text
exploration
    -> goal_navigation, gdy kontroler przydzieli cel
exploration
    -> exploration_complete, gdy osiągnięto budżet lub pokrycie
goal_navigation
    -> goal_reached, gdy osiągnięto target
goal_navigation
    -> exploration, wyłącznie przy allow_exploration_fallback=True
```

Przełączenie nie może kasować `visited`, poznanych kosztów, heurystyki ani
`anxiety_memory`. W LRTA* heurystyka celu może wymagać osobnej inicjalizacji
po ustawieniu nowego celu, ale pamięć obserwacji i traum pozostaje wspólna.

## 7. Wariant A: zwykły algorytm online

### 7.1. Założenia

Wariant bazowy nie zna mapy i nie używa pamięci lęku. Ma służyć jako punkt
odniesienia dla pozostałych metod. Powinien wybierać ruch na podstawie
lokalnych obserwacji i odległości do celu, np.:

```text
koszt = 1
       + kara_za_nieznane_pole
       + kara_za_teren
       + kara_za_odległość_od_celu
```

Współczynniki muszą być konfigurowalne. Przeszkoda ma koszt nieskończony, a
`SafeRegolith` powinien mieć najmniejszy koszt.

### 7.2. Kod referencyjny przekazanych algorytmów

Poniższe dwie klasy są punktem wyjścia dostarczonym dla projektu. Pokazują
różne strategie ruchu online i należy zachować ich podstawową logikę:

* `LRTA_star` aktualizuje heurystykę lokalnie i wybiera najlepiej ocenionego
  sąsiada,
* `OnlineSearch` eksploruje nieodwiedzone pola, a po wyczerpaniu możliwości
  cofa się po zapamiętanej ścieżce.

```python
class LRTA_star:
    def __init__(self, board):
        self.board = board
        self.path = []

    def solve(self):
        self.moves = 0
        self._search()
        return self.path

    def _search(self):
        self.board.prepare_heuristic()
        self.visited = set()

        position = self.board.source
        self.visited.add(position)
        self.path.append(position)

        while position != self.board.target:
            actions = self.board.actions(*position)
            if not actions:
                raise ValueError("Wyjście z labiryntu nie istnieje")

            self.board.h[position] = min(
                1 + self.board.h[action] for action in actions
            )
            position = min(
                actions,
                key=lambda action: 1 + self.board.h[action],
            )

            self.moves += 1
            if position in self.path:
                index = self.path.index(position)
                self.path = self.path[:index + 1]
            else:
                self.path.append(position)
            self.visited.add(position)
```

```python
class OnlineSearch:
    def __init__(self, board):
        self.board = board
        self.path = []
        self.visited = set()

    def solve(self):
        self.moves = 0
        self._search()
        return self.path

    def _search(self):
        position = self.board.source
        self.path = [position]
        self.visited.add(position)

        while position != self.board.target:
            actions = self.board.actions(*position)
            actions = [
                action
                for action in reversed(actions)
                if action not in self.visited
            ]

            if not actions:
                if len(self.path) == 1:
                    raise ValueError("Wyjście z labiryntu nie istnieje")

                index = len(self.path) - 1 - self.path[::-1].index(position)
                position = self.path[index - 1]
                self.moves += len(self.path[index:])
                self.path = self.path[:index]
            else:
                position = actions.pop()
                self.path.append(position)
                self.visited.add(position)
                self.moves += 1
```

W oryginalnym kodzie `Board` dostarcza trzy elementy:

| `Board` | Odpowiednik w projekcie Mesa |
|---|---|
| `source` | bieżąca pozycja łazika, np. `rover.pos` |
| `target` | cel zapisany w `rover.target` albo w konfiguracji epizodu |
| `actions(x, y)` | poprawni sąsiedzi z `HexGrid`, po filtracji LIDAR-em i terenem |
| `h` | słownik heurystyki strategii, np. `dict[position, float]` |
| `path` | historia pozycji łazika |
| `visited` | zbiór odwiedzonych pozycji |
| `moves` | liczba wykonanych przemieszczeń, łącznie z cofaniem |

Nie należy kopiować klasy `Board` ani udawać, że cały teren jest z góry
znany. Trzeba utworzyć adapter, np. `HexGridBoard`, który pobiera akcje
lokalnie z Mesa:

```python
class HexGridBoard:
    def actions(self, position, observation):
        neighbors = self.model.grid.get_neighborhood(
            position,
            moore=False,
            include_center=False,
        )
        return [
            candidate
            for candidate in neighbors
            if candidate not in observation.lidar_obstacles
            and self.is_traversable(candidate)
        ]
```

Sygnatura `actions` może być inna niż w przykładzie, jeżeli dzięki temu
strategia otrzyma już gotową obserwację. Istotne jest, aby lista akcji nie
zawierała pól spoza mapy, głazów ani pól niedostępnych dla danego agenta.

### 7.3. LRTA*

Można zaimplementować wariant LRTA* jako algorytm referencyjny:

1. Zainicjalizować heurystykę `h(position)` odległością heksagonalną do celu.
2. W każdym kroku pobrać znane akcje z bieżącego pola.
3. Zaktualizować:

   ```python
   h[current] = min(1 + h[next] for next in actions)
   ```

4. Wybrać akcję minimalizującą `1 + h[next]`, z deterministycznym
   rozstrzyganiem remisów.
5. Zapisać ruch i dopiero potem wykonać go na siatce.

Nie wolno używać pełnej mapy do obliczenia kosztu pola, jeżeli pole nie zostało
jeszcze zaobserwowane. Heurystyka może znać współrzędne celu, ale nie układ
nieodkrytych przeszkód.

W przekazanym kodzie `prepare_heuristic()` oraz `board.h` zakładają, że
heurystyka jest przygotowana dla akcji zwracanych przez `Board`. W wersji
Mesa trzeba:

1. ustawić `h[target] = 0`,
2. dla nowej pozycji użyć odległości heksagonalnej jako wartości początkowej,
3. uzupełniać `h` tylko dla pól zaobserwowanych,
4. obsłużyć pustą listę `actions` przed wywołaniem `min(...)`.

Jeśli teren ma różne koszty, aktualizacja powinna używać kosztu ruchu:

```python
self.h[position] = min(
    terrain_cost(action) + self.h[action]
    for action in actions
)
```

Wariant z emocjami rozszerza ten koszt o karę lęku, a wariant roju o kary
wynikające z pamięci otrzymanej przez radio.

### 7.4. Unikanie pętli i brak drogi

Strategia musi przechowywać `visited` oraz historię `path`. Jeśli wszystkie
nieodwiedzone akcje są niedostępne:

* cofnąć się do ostatniego pola z alternatywną akcją, albo
* zwrócić `None` i oznaczyć epizod jako zakończony bez drogi.

Nie wolno wykonywać nieskończonego losowania. Limit kroków powinien wynosić
`max_steps`, domyślnie nie mniej niż liczba pól mapy pomnożona przez
konfigurowalny współczynnik.

### 7.5. Statystyki i rysowanie trasy

Metody `statistics()` i `draw_escape()` z przekazanego kodu są przydatne jako
debugowanie, ale wymagają dopasowania:

* `moves` powinno liczyć także cofnięcia, natomiast osobno trzeba raportować
  liczbę unikalnych odwiedzonych pól,
* `Path length` nie może być dzielnikiem równym zero,
* współczynnik `CR` należy opisać jako metrykę eksperymentalną, a nie
  gwarantowany competitive ratio,
* rysowanie powinno używać pozycji agentów Mesa i nie może zmieniać `path`,
  `visited` ani stanu terenu.

Przykładowa bezpieczna wersja statystyki:

```python
def statistics(self):
    path_length = len(self.path)
    competitive_ratio = (
        self.moves / path_length if path_length else float("inf")
    )
    return {
        "moves": self.moves,
        "path_length": path_length,
        "visited": len(self.visited),
        "competitive_ratio": competitive_ratio,
    }
```

Kolorowanie ANSI z `draw_escape()` można zachować dla trybu terminalowego.
Dla Mesa/web UI należy zamiast tego przekazać stan trasy do funkcji
portrayal, bez wypisywania mapy w strategii.

## 8. Wariant B: algorytm online z emocjami

### 8.1. Pamięć lęku

`anxiety_memory` nie powinna być zwykłym zbiorem samych kolorów, ponieważ
trzeba ocenić siłę, świeżość i źródło lęku. Zalecany rekord:

```python
@dataclass
class FearRecord:
    signature: tuple[int, int, int]
    intensity: float
    visits: int
    last_seen_step: int
    source_position: tuple[int, int] | None
```

Sygnatura musi być zgodna z wartością RGB zwracaną przez środowisko. Jeżeli
kolor jest losowy lub zaszumiony, użyć tolerancji/odległości RGB zamiast
porównania dokładnego.

### 8.2. Wdrukowanie traumy

Po zastosowaniu efektu terenu obliczyć stres. Jeśli
`stress_level >= S_crit` (domyślnie `75.0`):

1. pobrać sygnaturę aktualnego pola,
2. zwiększyć lub utworzyć `FearRecord`,
3. zapisać pozycję i numer kroku,
4. w wariancie roju wysłać pakiet zagrożenia.

Trauma nie powinna być zapisywana przed zastosowaniem efektu, bo wtedy nie
uwzględnia rzeczywistych skutków pola. Należy też zabezpieczyć wartości stresu
przed NaN i ograniczyć je do ustalonego zakresu, np. `0..100`.

### 8.3. Koszt emocjonalny

Dla każdego rozważanego pola obliczyć:

```text
koszt_emocjonalny =
    intensywność_lęku(sygnatura_pola)
    * decay(last_seen_step, current_step)
```

Następnie dodać go do kosztu ruchu. Pole z zapamiętaną sygnaturą powinno być
omijane, jeśli istnieje alternatywa o rozsądnym koszcie. Nie należy blokować
go bezwarunkowo: jeśli pole jest celem albo wszystkie alternatywy są gorsze,
może zostać wybrane, ale decyzja musi być zapisana jako wymuszona.

Pamięć może wygasać po czasie albo zmniejszać intensywność według
konfigurowalnego współczynnika. W eksperymentach trzeba raportować, czy
użyto wygaszania, aby porównania były powtarzalne.

### 8.4. Homeostat

Poziom chwilowego stresu należy wyliczać według modelu z `instruction.md`:

```text
S_chwilowy =
    w1 * DeltaB
  + w2 * max(0, 1 - V_akt / V_zad)
  + w3 * (exp(k * (100 - C_kadlub)) - 1)
  + w4 * (exp(k * (100 - C_kola)) - 1)
  + w5 * max(0, alfa - alfa_bezpieczny)

S_calkowity = beta * S_poprzedni + (1 - beta) * S_chwilowy
```

Zalecane wartości początkowe:

| Stała | Wartość |
|---|---:|
| `w1` | `5.0` |
| `w2` | `15.0` |
| `w3` | `3.0` |
| `w4` | `2.5` |
| `w5` | `2.0` |
| `k` | `0.05` |
| `alpha_safe` | `15.0` |
| `beta` | `0.7` |
| `S_crit` | `75.0` |

Wzór musi bezpiecznie obsłużyć `V_zad == 0`. `DeltaB` powinno być jasno
zdefiniowane jako spadek baterii w danym kroku, a nie jako jej poziom
bezwzględny.

## 9. Wariant C: rój łazików z emocjami

### 9.1. Pakiet radiowy

Zdefiniować jawny, typowany pakiet:

```python
@dataclass(frozen=True)
class RadioPacket:
    signature: tuple[int, int, int]
    position: tuple[int, int]
    intensity: float
    sender_id: int
    created_at: int
```

Zasięg `R_radio` powinien być konfigurowalny, a wartość domyślna wynosić
20 heksagonów. Odległość trzeba liczyć zgodnie z geometrią heksagonalną,
nie jako niezależne różnice `x` i `y`.

### 9.2. Nadawanie i odbiór

Po wdrukowaniu traumy nadawca wywołuje `broadcast_danger`. Model albo
dedykowany `RadioModule` wyszukuje agentów w zasięgu i wywołuje
`receive_signal(packet)` u odbiorców.

Odbiorca:

1. sprawdza poprawność pakietu,
2. ignoruje własny pakiet,
3. scala sygnaturę z własną pamięcią,
4. zapisuje źródło jako pozycję nadawcy,
5. zwiększa koszt pól o tej sygnaturze.

Odbiorca nie powinien otrzymywać uszkodzeń ani zmiany baterii tylko dlatego,
że dostał pakiet. Pakiet przekazuje informację, a nie fizyczny efekt terenu.
Należy unikać wielokrotnego przekazywania tego samego pakietu w jednej turze,
np. przez klucz `(sender_id, created_at, signature)`.

### 9.3. Wpływ roju na decyzję

Wariant roju używa tego samego wyboru ruchu co wariant emocjonalny, ale
uwzględnia również traumy otrzymane radiowo. Dodatkowo można wprowadzić:

* premię za pola często wybierane przez inne łaziki,
* karę za skupienie wielu agentów na jednym polu,
* wymianę znanych bezpiecznych przejść,
* priorytet utrzymania zasięgu radiowego.

Te rozszerzenia muszą być opcjonalne, aby bazowe porównanie „emocje własne”
vs „emocje roju” było jednoznaczne.

## 10. Integracja z obecnym `rover.py`

W `Pioneer3DXAgent.__init__` należy zachować istniejące pola i uzupełnić je
co najmniej o:

```python
self.battery_prev = self.battery
self.target_speed = self.base_speed
self.hull_condition = 100.0
self.anxiety_memory = {}
self.shadow_exposure_time = 0
self.dust_exposure_time = 0
self.is_destroyed = False
self.path = []
self.visited = set()
```

Typ strategii powinien być parametrem modelu lub agenta, np.
`navigation_mode="online"`, `"emotional"` albo `"swarm"`. Nie należy tworzyć
osobnych, prawie identycznych implementacji całego `step()` dla każdego trybu.
Wspólna pętla powinna delegować wyłącznie wybór następnego pola.

Aktualny kod ma kilka ograniczeń, które implementacja powinna usunąć:

* wybiera ruch Moore'a mimo użycia `HexGrid`,
* wybiera losowo zamiast korzystać z celu i historii,
* nie ma celu (`target`),
* nie przechowuje `hull_condition`, pamięci lęku ani liczników ekspozycji,
* nakłada tylko prosty warunek na `Boulders`,
* nie rozróżnia obserwacji LIDAR i RGB,
* nie aktualizuje homeostatu zgodnie z opisanym wzorem.

## 11. Konfiguracja i powtarzalność

Parametry algorytmów powinny znajdować się w jednym miejscu, a nie w
warunkach strategii. Co najmniej:

```text
navigation_mode
mission_mode
max_steps
exploration_budget
coverage_target
allow_exploration_fallback
S_crit
R_radio
vision_range
fear_weight
fear_decay
terrain_costs
allow_forced_fear_visit
```

Seed generatora mapy i seed losowania agentów muszą być ustawialne. Wybór
remisów powinien być deterministyczny albo oparty na kontrolowanym RNG Mesa.
Dzięki temu ten sam seed pozwala odtworzyć trasę i porównać tryby.

## 12. Metryki i wizualizacja

Dla każdego epizodu zapisywać:

* czy osiągnięto cel,
* liczbę kroków i rzeczywistych przemieszczeń,
* tryb zadaniowy oraz przyczynę jego zmiany,
* pokrycie mapy i liczbę nowych pól poznanych w każdym kroku,
* długość końcowej trasy oraz liczbę cofnięć,
* zużytą baterię,
* liczbę i rodzaj uszkodzeń,
* maksymalny i średni stres,
* liczbę traum własnych i otrzymanych,
* liczbę wejść na zapamiętane niebezpieczne pola,
* liczbę kolizji, wywrotek i zniszczonych łazików,
* czas do osiągnięcia celu albo powód zakończenia.

Wizualizacja powinna odróżniać co najmniej bieżącą pozycję, trasę,
odwiedzone pola, przeszkody, pola wywołujące traumę i pola oznaczone przez
sygnał roju. Funkcje rysujące nie mogą zmieniać stanu symulacji.

## 13. Testy akceptacyjne

Przed uznaniem implementacji za gotową należy sprawdzić:

1. Łazik nigdy nie wybiera `Boulders`, jeśli istnieje poprawna alternatywa.
2. Łazik nie wychodzi poza granice nieprzechodniej siatki.
3. Algorytm kończy się na mapie bez drogi i nie wpada w nieskończoną pętlę.
4. `apply_effect` jest wykonywane dokładnie raz po udanym ruchu.
5. Efekty terenu zmieniają baterię, prędkość i uszkodzenia zgodnie z klasą
   terenu.
6. Po przekroczeniu `S_crit` sygnatura pola trafia do pamięci dokładnie raz
   dla danego zdarzenia.
7. Łazik emocjonalny preferuje bezpieczną alternatywę względem zapamiętanej
   sygnatury.
8. Odebrany pakiet tworzy lub wzmacnia pamięć, ale nie powoduje uszkodzeń.
9. Pakiet dociera tylko do agentów w `R_radio`.
10. Spadek widoczności w `DustStorm` ogranicza RGB, ale nie wyłącza LIDAR-u.
11. `DeepShadow` i `DustStorm` poprawnie zwiększają i zerują liczniki
    ekspozycji.
12. Ten sam seed i konfiguracja odtwarzają tę samą trasę.
13. Ruch do celu jest preferowany, ale bezpieczeństwo nie jest pomijane, gdy
    dostępne jest pole o wyraźnie mniejszym ryzyku.
14. W ekspansji łazik zwiększa liczbę poznanych pól i nie wymaga ustawionego
    celu.
15. W dojściu do celu łazik zatrzymuje się po osiągnięciu `target`.
16. Zmiana trybu nie usuwa historii odwiedzin ani pamięci traum.
17. Wyłączenie `allow_exploration_fallback` uniemożliwia samoczynne przejście
    z nieudanego dojścia do celu do ekspansji.

Testy należy wykonać osobno dla pojedynczego łazika i roju oraz na małych,
ręcznie zbudowanych mapach, aby wymusić głazy, piasek, strome zbocze, cień,
burzę pyłową i traumę.

## 14. Kolejność implementacji

1. Wydzielić typy obserwacji, kosztu terenu i strategii.
2. Naprawić pobieranie sąsiadów tak, aby odpowiadało `HexGrid`.
3. Dodać `mission_mode`, cel, budżet ekspansji, historię ruchu, walidację
   ruchu i limit kroków.
4. Zaimplementować bazowy algorytm online/LRTA* w obu trybach zadaniowych.
5. Dodać sensory LIDAR/RGB i rozróżnienie sygnatur terenu.
6. Dodać pełny stan fizyczny oraz homeostat.
7. Dodać pamięć lęku i emocjonalną funkcję kosztu w ekspansji i dojściu do
   celu.
8. Dodać pakiety radiowe i propagację informacji w zasięgu.
9. Dodać metryki, wizualizację i testy akceptacyjne obu trybów.
10. Uruchomić porównanie wszystkich kombinacji wariantów i trybów na tych
    samych mapach i seedach.
