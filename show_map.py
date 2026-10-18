import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.colors as mcolors
import numpy as np

# Importujemy nasz model
from src.model.model import MarsSimulation
from src.environment.terrain import TerrainPatch

def visualize_map():
    width, height = 50, 50

    print("Generowanie świata za pomocą szumu Perlina. Proszę czekać...")
    model = MarsSimulation(width=width, height=height, num_rovers=0)

    # Przygotowanie danych na dwa wykresy
    image_data = np.zeros((height, width, 3)) # Kolory kategorii
    slope_data = np.zeros((height, width))    # Wartości stromości w stopniach

    legend_labels = {
        "#d2b48c": "Bezpieczny regolit",
        "#4d4d4d": "Duże głazy",
        "#e6cc80": "Sypki piasek",
        "#8b4513": "Ostre skały",
        "#ff6666": "Strome zbocza",
        "#1a1a1a": "Głębokie cienie",
        "#b38b6d": "Burza pyłowa"
    }

    for x in range(width):
        for y in range(height):
            agents = model.grid.get_cell_list_contents([(x, y)])
            terrain = next((a for a in agents if isinstance(a, TerrainPatch)), None)

            if terrain:
                rgb = mcolors.to_rgb(terrain.color)
                image_data[y, x] = rgb
                # Pobieramy konkretną wartość kąta nachylenia heksagonu
                slope_data[y, x] = terrain.slope

                # Rysowanie map (1 wiersz, 2 kolumny)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 7))

    # ==========================================
    # PANEL 1: KATEGORIE TERENU (Lewa strona)
    # ==========================================
    ax1.imshow(image_data, origin='lower')
    ax1.set_title("Mapa Zagrożeń (Typy terenu)")
    ax1.set_xlabel("Oś X")
    ax1.set_ylabel("Oś Y")

    patches = [mpatches.Patch(color=c, label=l) for c, l in legend_labels.items()]
    # Przenosimy legendę pod wykres, żeby nie zasłaniała drugiej mapy
    ax1.legend(handles=patches, bbox_to_anchor=(0.5, -0.1), loc='upper center', ncol=3)

    # ==========================================
    # PANEL 2: HEATMAP STROMOŚCI (Prawa strona)
    # ==========================================
    # Używamy mapy kolorów 'magma' (czarny -> fioletowy -> pomarańczowy -> żółty)
    im2 = ax2.imshow(slope_data, origin='lower', cmap='magma')
    ax2.set_title("Analiza Stromości (Kąt nachylenia)")
    ax2.set_xlabel("Oś X")

    # Dodajemy pasek legendy dla wartości w stopniach
    cbar = fig.colorbar(im2, ax=ax2, fraction=0.046, pad=0.04)
    cbar.set_label('Nachylenie w stopniach (°)', rotation=270, labelpad=15)

    # Dodatkowe: rysujemy linie konturowe dla krytycznych nachyleń (np. 15, 30 i 45 stopni)
    contours = ax2.contour(slope_data, levels=[15, 30, 45], colors='white', alpha=0.6)
    ax2.clabel(contours, inline=True, fontsize=10, fmt='%d°')

    # Kosmetyka okna
    plt.tight_layout()
    plt.subplots_adjust(bottom=0.2) # Robimy miejsce na legendę z pierwszego panelu

    print("Wyświetlanie mapy...")
    plt.show()

if __name__ == "__main__":
    visualize_map()