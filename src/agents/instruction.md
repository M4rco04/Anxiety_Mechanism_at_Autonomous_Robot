**1. Moduł Sensoryczny (Percepcja Środowiska)**
Zaimplementuj dwa odrębne systemy wizyjne symulujące dysonans sensoryczny:

* `read_lidar()`: Skanuje teren i zwraca listę współrzędnych fizycznych przeszkód blokujących ruch (np. duże głazy). Ignoruje podłoże płaskie i jego teksturę.


* `read_rgb_cameras()`: Zwraca sygnaturę wizualną w postaci krotki wartości kolorów `(R, G, B)` z heksagonów znajdujących się przed łazikiem. Zasięg działania tej funkcji (ilość heksagonów do przodu) jest definiowany przez zmienną całkowitą `vision_range` (domyślnie 3), która jest dynamicznie redukowana przez zjawiska takie jak burze pyłowe.



**2. Cybernetyczny Umysł i Emocje (Homeostat i Baza Traum)**
Rdzeń mechanizmu lęku warunkowego:

* `anxiety_memory`: Struktura danych typu `set` (zbiór) przechowująca zapisane sygnatury wizualne `(R, G, B)` podłoża, które wywołały krytyczny stres.


* `update_homeostat(delta_battery, target_speed, current_speed, hull_condition, wheel_condition, current_slope)`: Funkcja monitorująca spadek wydajności i uszkodzenia. Aktualizuje zmienną `stress_level` zgodnie ze zdefiniowanym wzorem matematycznym.


* `learn_fear(signature)`: Funkcja wyzwalana natychmiast, gdy `stress_level` przekroczy próg $S_{crit} = 75.0$. Zapisuje przekazaną krotkę `(R, G, B)` do `anxiety_memory` (wdrukowanie).



**3. Algorytmy Nawigacyjne (Ruch i Reakcja)**

* `_move_standard()`: Algorytm reaktywny. Omija przeszkody wykryte przez `read_lidar()`, ale nie analizuje tekstury, przez co ignoruje sypki piasek lub ostre skały.


* `_move_fuzzy()`: Kontroler rozmyty (Mamdani/Sugeno) przetwarzający dystans i szorstkość terenu na parametry wyjściowe napędu: prędkość i kąt skrętu.


* `_move_emotional()`: Algorytm ucieczki. Działa w czasie rzeczywistym, sprawdzając, czy dla odczytanej krotki `(R, G, B)` z kamer, dystans euklidesowy $\sqrt{(R_1-R_2)^2 + (G_1-G_2)^2 + (B_1-B_2)^2}$ do jakiejkolwiek sygnatury w `anxiety_memory` jest mniejszy niż próg tolerancji (np. 15.0). Wykrycie podobieństwa wyzwala manewr wycofania przed fizycznym kontaktem z zagrożeniem.



**4. Moduł Komunikacji Roju (Swarm Intelligence)**

* `broadcast_danger(signature, position)`: Funkcja tworząca obiekt `RadioPacket` zawierający sygnaturę `(R, G, B)` oraz pozycję nadawcy. Zasięg rozgłaszania $R_{radio}$ ustala się na 20 heksagonów.


* `receive_signal(packet)`: Funkcja wywoływana za pomocą zapytania do środowiska Mesa (`model.grid.get_neighbors(pos, radius=R_radio)`). Zmusza odbiorców w zasięgu do wywołania własnego `learn_fear(packet.signature)`, dodając wektor lęku do ich pamięci bez konieczności doświadczenia uszkodzeń.



**5. Główna Pętla Decyzyjna (Metoda `step`)**
Każdy agent łazika wykonuje operacje w ścisłej kolejności:

1. Pobranie danych z `read_lidar()` oraz `read_rgb_cameras()`.
2. Porównanie odczytu kamer z `anxiety_memory`. Jeśli próg dystansu euklidesowego kolorów jest przekroczony, wykonaj `_move_emotional()`.


3. Jeśli sygnatury są bezpieczne, wykonaj `_move_fuzzy()` lub `_move_standard()` wybierając kolejny heksagon.


4. Zresetowanie liczników środowiskowych łazika (np. czasu spędzonego w cieniu), jeśli zmieniono heksagon na inny typ.
5. Wywołanie na łaziku efektów środowiskowych obecnego heksagonu (`current_patch.apply_effect(self)`).
6. Przeliczenie napięcia w systemie wywołując `update_homeostat(...)` z nowymi parametrami fizycznymi.


7. Jeśli `stress_level` $\ge S_{crit}$, wykonaj `learn_fear(current_signature)` oraz `broadcast_danger(current_signature, self.pos)`.



**6. Model Matematyczny Homeostatu i Kalibracja**
Wzór na chwilowy poziom stresu ($S_{chwilowy}$):

$$S_{chwilowy} = w_1 \cdot \Delta B + w_2 \cdot \max\left(0, 1 - \frac{V_{akt}}{V_{zad}}\right) + w_3 \cdot (e^{k \cdot (100-C_{kadlub})} - 1) + w_4 \cdot (e^{k \cdot (100-C_{kola})} - 1) + w_5 \cdot \max(0, \alpha - \alpha_{bezp})$$

Wzór na całkowity poziom stresu z wygładzaniem:

$$S_{calkowity} = \beta \cdot S_{poprzedni} + (1 - \beta) \cdot S_{chwilowy}$$

Zalecane stałe konfiguracyjne do inicjalizacji w pliku `config.py`:

* $w_1 = 5.0$ (Waga skoków poboru prądu)
* $w_2 = 15.0$ (Waga uślizgu kół)
* $w_3 = 3.0$ (Waga uszkodzeń kadłuba)
* $w_4 = 2.5$ (Waga uszkodzeń kół)
* $w_5 = 2.0$ (Waga nachylenia)
* $k = 0.05$ (Współczynnik skali wykładniczej dla uszkodzeń)
* $\alpha_{bezp} = 15.0^\circ$ (Bezpieczny kąt nachylenia)


* $\beta = 0.7$ (Współczynnik wygładzania stresu)
* $S_{crit} = 75.0$ (Próg aktywacji wdrukowania lęku)