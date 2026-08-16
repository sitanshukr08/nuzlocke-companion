from gen1_save_parser.parser import parse_save, SaveState
from gen1_save_parser.layout.gen1_species_index import get_species_name
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def run_tests():
    # Use the golden fixture
    golden_file = os.path.join("tests", "fixtures", "pokemon_blue.sav")
    
    if not os.path.exists(golden_file):
        print(f"Error: Golden fixture not found at {golden_file}")
        return
        
    print(f"--- Testing Golden Fixture: {golden_file} ---")
    state: SaveState = parse_save(golden_file)
    
    print(f"Is Valid: {state.is_valid}")
    if not state.is_valid:
        print(f"Validation Errors: {state.validation_errors}")
        return

    print(f"Player Name: {state.player_name}")
    print(f"Trainer ID: {state.player_id}")
    print(f"Rival Name: {state.rival_name}")
    print(f"Money: ₽{state.money}")
    print(f"Badges Bitfield: {state.badges} (Binary: {bin(state.badges)})")
    print(f"Current Location: {state.location_name} ({state.location_id}, map {state.current_map_id:#04x})")
    print(f"\nParty Count: {len(state.party)}")
    
    for i, p in enumerate(state.party):
        species_name = get_species_name(p.species_id)
        print(f"  Party {i+1}: {species_name} Lv.{p.level} (HP: {p.current_hp}/{p.max_hp}, Nickname: {p.nickname})")
        print(f"    Types: {' / '.join(p.type_names)}")
        print("    Moves: " + ", ".join(
            f"{move.display_name} {move.current_pp}/{move.maximum_pp} PP"
            for move in p.move_details
        ))
        if p.status_conditions:
            print(f"    Status: {', '.join(p.status_conditions)}")
        print(f"    Experience to next level: {p.experience_to_next_level}")
        
    print(f"\nCurrent Box Count: {len(state.current_box)}")
    for i, b in enumerate(state.current_box):
        species_name = get_species_name(b.species_id)
        print(f"  Boxed {i+1}: {species_name} Lv.{b.level} (HP: {b.current_hp}, Nickname: {b.nickname})")

if __name__ == "__main__":
    run_tests()
