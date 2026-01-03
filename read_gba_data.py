import os
from datetime import datetime

# Path to your mGBA save file
SAV_FILE = "pokemon_leafgreen.sav"

# Species ID to Name Map (Add more as you catch them!)
POKEDEX = {
    0: "Empty", 1: "Bulbasaur", 2: "Ivysaur", 3: "Venusaur",
    4: "Charmander", 5: "Charmeleon", 6: "Charizard",
    7: "Squirtle", 8: "Wartortle", 9: "Blastoise",
    16: "Pidgey", 19: "Rattata", 25: "Pikachu"
}


def get_active_slot(data):
    """LeafGreen has two 64KB slots. This finds the one with the higher sequence number."""
    # The 'Save Index' is located at offset 0x0FFC in each 4KB section
    slot_a_index = int.from_bytes(data[0x0FFC:0x1000], "little")
    slot_b_index = int.from_bytes(data[0x10FFC:0x11000], "little")
    return 0x00000 if slot_a_index > slot_b_index else 0x10000


def pull_party_data():
    if not os.path.exists(SAV_FILE):
        print("Save file not found!")
        return

    with open(SAV_FILE, "rb") as f:
        data = f.read()

    base_offset = get_active_slot(data)

    # In LeafGreen, the Party is in Section 1. 
    # Sections are 4KB. Section 1 starts 4KB after the start of the active slot.
    party_section_offset = base_offset + 0x1000

    # The party data within Section 1 starts at offset 0x0034
    party_count_addr = party_section_offset + 0x0034
    party_count = data[party_count_addr]

    # Only read if 1-6 Pokemon exist
    if 0 < party_count <= 6:
        print(f"--- Party Snapshot ({datetime.now().strftime('%Y-%m-%d')}) ---")
        party_list = []

        for i in range(party_count):
            # Each Pokemon data block is 100 bytes
            # Species ID is the first 2 bytes (Little Endian)
            start_addr = party_section_offset + 0x0038 + (i * 100)
            species_id = int.from_bytes(data[start_addr: start_addr + 2], "little")

            # Decrypt Species ID: In FireRed/LeafGreen, data is XORed, 
            # but Species ID is often readable in the first 2 bytes of the 'unpacked' block.
            # NOTE: If names come out 'Unknown', the save is currently XOR encrypted.
            name = POKEDEX.get(species_id, f"ID: {species_id}")
            party_list.append(name)
            print(f"Slot {i + 1}: {name}")

        # Log to file
        with open("daily_party_report.txt", "w") as f:
            f.write(f"DATE: {datetime.now()}\n" + "\n".join(party_list))
    else:
        print("Could not read party. Is the game saved?")


if __name__ == "__main__":
    pull_party_data()