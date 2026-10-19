**1. Parametry Wewnętrzne Łazika (Stan Agenta)**
Każdy obiekt łazika (`Pioneer3DXAgent`) musi posiadać zainicjalizowane następujące parametry śledzące jego stan fizyczny i psychologiczny:

* `battery` (float): Aktualny poziom energii (startowo 100.0).
* `battery_prev` (float): Poziom energii z poprzedniego kroku symulacji (niezbędny do wyliczania zmiennej $\Delta B$ w homeostacie).
* `current_speed` (float): Rzeczywista prędkość przemieszczania się ($V_{akt}$).
* `target_speed` (float): Prędkość zadana przez systemy sterowania ($V_{zad}$), służy do wyliczania uślizgu na piasku.
* `wheel_condition` (float): Stan techniczny kół/zawieszenia ($C_{kola}$), wartość od 100.0 (idealny) do 0.0 (zniszczone).
* `hull_condition` (float): Stan techniczny kadłuba ($C_{kadlub}$), wartość od 100.0 (idealny) do 0.0 (zniszczony).
* `stress_level` (float): Bieżący poziom napięcia w module homeostatu (startowo 0.0).


* `anxiety_memory` (set): Pamięć krótkotrwała/Baza Traum przechowująca niebezpieczne sygnatury wizualne.


* `vision_range` (int): Aktualny zasięg w heksagonach dla kamer RGB (startowo 3), modyfikowany przez burze pyłowe.


* `shadow_exposure_time` (int): Licznik tur spędzonych nieprzerwanie w obszarze `DeepShadow`.
* `dust_exposure_time` (int): Licznik tur spędzonych nieprzerwanie w obszarze `DustStorm`.
* `gyro_alarm` (bool): Flaga włączająca się, gdy nachylenie terenu stwarza ryzyko wywrotki.


* `is_overturned` (bool): Flaga oznaczająca fizyczną wywrotkę na stromym zboczu.


* `is_destroyed` (bool): Flaga oznaczająca całkowite zatrzymanie i wyłączenie łazika z dalszej symulacji w wyniku krytycznych uszkodzeń.

**2. Moduł Sensoryczny (Percepcja Środowiska)**
Zaimplementuj dwa odrębne systemy wizyjne symulujące dysonans sensoryczny:

* `read_lidar()`: Skanuje teren i zwraca listę współrzędnych fizycznych przeszkód blokujących ruch (np. duże głazy). Ignoruje podłoże płaskie i jego teksturę.


* `read_rgb_cameras()`: Zwraca sygnaturę wizualną w postaci krotki wartości kolorów `(R, G, B)` z heksagonów znajdujących się przed łazikiem. Zasięg działania jest limitowany przez `vision_range`.



**3. Cybernetyczny Umysł i Emocje (Homeostat i Baza Traum)**
Rdzeń mechanizmu lęku warunkowego:

* `update_homeostat(delta_battery, target_speed, current_speed, hull_condition, wheel_condition, current_slope)`: Funkcja monitorująca spadek wydajności i uszkodzenia. Aktualizuje zmienną `stress_level` zgodnie ze zdefiniowanym wzorem matematycznym.


* `learn_fear(signature)`: Funkcja wyzwalana natychmiast, gdy `stress_level` przekroczy próg $S_{crit} = 75.0$. Zapisuje przekazaną krotkę `(R, G, B)` do `anxiety_memory` (wdrukowanie).



**4. Moduł Komunikacji Roju (Swarm Intelligence)**

* `broadcast_danger(signature, position)`: Funkcja tworząca obiekt `RadioPacket` zawierający sygnaturę `(R, G, B)` oraz pozycję nadawcy. Zasięg rozgłaszania $R_{radio}$ ustala się na 20 heksagonów.


* `receive_signal(packet)`: Funkcja wywoływana za pomocą zapytania do środowiska Mesa (`model.grid.get_neighbors(pos, radius=R_radio)`). Zmusza odbiorców w zasięgu do wywołania własnego `learn_fear(packet.signature)`, dodając wektor lęku do ich pamięci bez konieczności doświadczenia uszkodzeń.



**5. Główna Pętla Decyzyjna (Metoda `step`)**
Każdy agent łazika wykonuje operacje w ścisłej kolejności, integrując się z zewnętrznym modułem nawigacji:

1. Pobranie danych sensorycznych przez `read_lidar()` oraz `read_rgb_cameras()`.
2. Przekazanie danych z sensorów oraz `anxiety_memory` do zewnętrznego modułu nawigacji i wykonanie przemieszczenia na siatce (właściwe algorytmy ruchu implementuje oddzielny zespół).
3. Zresetowanie liczników środowiskowych (`shadow_exposure_time`, `dust_exposure_time`), jeśli po ruchu łazik zmienił typ heksagonu na bezpieczny.
4. Wywołanie na łaziku efektów środowiskowych obecnego heksagonu (np. `current_patch.apply_effect(self)`).
5. Przeliczenie napięcia w systemie poprzez wywołanie `update_homeostat(...)` z nowymi parametrami fizycznymi.


6. Jeśli wyliczony `stress_level` $\ge S_{crit}$, wywołanie `learn_fear(current_signature)` oraz `broadcast_danger(current_signature, self.pos)`.



**6. Model Matematyczny Homeostatu i Kalibracja**
Wzór na chwilowy poziom stresu ($S_{chwilowy}$):

$$S_{chwilowy} = w_1 \cdot \Delta B + w_2 \cdot \max\left(0, 1 - \frac{V_{akt}}{V_{zad}}\right) + w_3 \cdot (e^{k \cdot (100-C_{kadlub})} - 1) + w_4 \cdot (e^{k \cdot (100-C_{kola})} - 1) + w_5 \cdot \max(0, \alpha - \alpha_{bezp})$$

Wzór na całkowity poziom stresu z wygładzaniem:

$$S_{calkowity} = \beta \cdot S_{poprzedni} + (1 - \beta) \cdot S_{chwilowy}$$

Zalecane stałe konfiguracyjne do inicjalizacji w module konfiguracyjnym:

* $w_1 = 5.0$ (Waga skoków poboru prądu)
* $w_2 = 15.0$ (Waga uślizgu kół)
* $w_3 = 3.0$ (Waga uszkodzeń kadłuba)
* $w_4 = 2.5$ (Waga uszkodzeń kół)
* $w_5 = 2.0$ (Waga nachylenia)
* $k = 0.05$ (Współczynnik skali wykładniczej dla uszkodzeń)
* $\alpha_{bezp} = 15.0^\circ$ (Bezpieczny kąt nachylenia)


* $\beta = 0.7$ (Współczynnik wygładzania stresu)
* $S_{crit} = 75.0$ (Próg aktywacji wdrukowania lęku)