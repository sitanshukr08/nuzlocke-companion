"use strict";

let dashboard = null;
const $ = id => document.getElementById(id);
const sprite = dex => `https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/versions/generation-i/red-blue/${dex}.png`;
const bossSprites = {
  Brock: "brock.png", Misty: "misty.png", "Lt Surge": "lt.surge.png", Erika: "erika.png",
  Koga: "koga.png", Sabrina: "sabrina.png", Blaine: "blaine.png", Giovanni: "giovanni.png",
  Lorelei: "lorelei.png", Bruno: "bruno.png", Agatha: "agatha.png", Lance: "lance.png",
  Champion: "rival3.png"
};
const progressionRoster = [
  ["Brock", "brock.png"], ["Misty", "misty.png"], ["Lt. Surge", "lt.surge.png"], ["Erika", "erika.png"],
  ["Koga", "koga.png"], ["Sabrina", "sabrina.png"], ["Blaine", "blaine.png"], ["Giovanni", "giovanni.png"],
  ["Lorelei", "lorelei.png"], ["Bruno", "bruno.png"], ["Agatha", "agatha.png"], ["Lance", "lance.png"], ["Champion", "rival3.png"]
];
const trainerClassSprites = {
  "jr. trainer♂": "jr.trainerm.png", "jr. trainer♀": "jr.trainerf.png", "lt. surge": "lt.surge.png",
  "prof. oak": "prof.oak.png", "super nerd": "supernerd.png", "bird keeper": "birdkeeper.png",
  "blackbelt": "blackbelt.png", "cooltrainer♂": "cooltrainerm.png", "cooltrainer♀": "cooltrainerf.png",
  "rival": "rival1.png"
};
function clear(node) { node.replaceChildren(); }
function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function addLine(root, label, value) {
  const line = element("div");
  line.append(element("span", "detail-label", label), document.createTextNode(String(value)));
  root.append(line);
}
function openDialog(title, rows) {
  $("dialogTitle").textContent = title.toUpperCase();
  const body = $("dialogBody"); clear(body);
  for (const row of rows) {
    if (typeof row === "string") body.append(element("p", "dialog-line", row));
    else addLine(body, row[0], row[1]);
  }
  $("dialog").classList.remove("hidden");
  $("dialogClose").focus();
}
function closeDialog() { $("dialog").classList.add("hidden"); }

function partyEncounterOrigin(mon) {
  if (mon.encounter_origin) return mon.encounter_origin;
  if (!dashboard) return null;
  const caught = combinedEncounterHistory().filter(record => record.status === "caught");
  const nicknameMatch = caught.find(record => record.nickname && record.nickname.toLowerCase() === mon.nickname.toLowerCase());
  const match = nicknameMatch || (() => {
    const speciesMatches = caught.filter(record => record.species_id === mon.species_id);
    return speciesMatches.length === 1 ? speciesMatches[0] : null;
  })();
  return match ? {area_id: match.area_id, map_name: match.map_name, caught_level: match.level, method: match.method, source: match.source, recorded_species_name: match.species_name, match_basis: nicknameMatch ? "nickname" : "unique_species", evidence: "user_confirmed_manual_history"} : null;
}

function renderParty(data) {
  const root = $("partyStack"); clear(root);
  $("partyCount").textContent = `${data.party.length} / 6`;
  data.party.forEach(mon => {
    const card = element("button", "party-card"); card.type = "button";
    const img = element("img"); img.src = sprite(mon.dex_number); img.alt = mon.species_name;
    const info = element("div", "party-info");
    const top = element("div"); top.append(element("span", "party-name", mon.nickname.toUpperCase()), element("span", "party-level", ` :L${mon.level}`));
    const meta = element("div", "party-meta", `${mon.species_name} · ${[...new Set(mon.types)].join(" / ")}`);
    const origin = partyEncounterOrigin(mon);
    const caughtAt = element("div", `party-origin ${origin ? "confirmed" : "unknown"}`, origin ? `CAUGHT L${origin.caught_level ?? "?"} · ${origin.map_name}` : "CAUGHT LEVEL · NOT RECORDED");
    const track = element("div", "hp-track"); const fill = element("i"); fill.style.width = `${Math.max(0, Math.min(100, Math.round(mon.current_hp / Math.max(mon.max_hp, 1) * 100)))}%`; track.append(fill);
    const hp = element("div", "hp-readout"); hp.append(element("span", "", "HP:"), element("span", "", `${mon.current_hp}/${mon.max_hp}`));
    info.append(top, meta, caughtAt, track, hp); card.append(img, info);
    card.addEventListener("click", () => openDialog(mon.nickname, [
      ["Species", mon.species_name], ["Level", mon.level], ["HP", `${mon.current_hp}/${mon.max_hp}`],
      ["Types", [...new Set(mon.types)].join(" / ")], ["Caught at", origin ? `${origin.map_name}, level ${origin.caught_level ?? "unknown"}` : "Not stored in the Gen I save; add it in Encounters"], ["History evidence", origin ? "User-confirmed manual record" : "Unavailable"], ["Move slots", `${mon.moves.length}/4 occupied in save`], ["Moves", mon.moves.map(move => `${move.display_name} ${move.current_pp}/${move.maximum_pp} PP`).join(", ") || "None"]
    ]));
    root.append(card);
  });
  renderFullParty(data);
}

function renderFullParty(data) {
  const root = $("fullParty"); clear(root);
  data.party.forEach((mon, index) => {
    const origin = partyEncounterOrigin(mon);
    const card = element("article", "full-party-card");
    const heading = element("div", "full-party-heading");
    const image = element("img"); image.src = sprite(mon.dex_number); image.alt = mon.species_name;
    const names = element("div"); names.append(element("div", "slot-number", `SLOT ${index + 1}`), element("h2", "", mon.nickname.toUpperCase()), element("p", "", `${mon.species_name} · ${mon.types.join(" / ")}`));
    heading.append(image, names);
    const stats = element("div", "party-detail-stats");
    [["LEVEL", mon.level], ["HP", `${mon.current_hp}/${mon.max_hp}`], ["STATUS", mon.status_conditions.join(", ") || "OK"], ["CAUGHT AT", origin ? `${origin.map_name} · L${origin.caught_level ?? "?"} · USER CONFIRMED` : "NOT RECORDED IN ENCOUNTER HISTORY"], ["MOVE SLOTS", `${mon.moves.length}/4 OCCUPIED IN SAVE`]].forEach(([label, value]) => addLine(stats, label, value));
    const moves = element("div", "move-grid");
    mon.moves.forEach(move => { const moveRow = element("div", "move-detail"); moveRow.append(element("strong", "", move.display_name.toUpperCase()), element("span", "", `${move.current_pp}/${move.maximum_pp} PP`)); moves.append(moveRow); });
    if (!mon.moves.length) moves.append(element("p", "", "No moves decoded."));
    card.append(heading, stats, element("div", "subheading", "CURRENT MOVES"), moves); root.append(card);
  });
}

function openBoxPokemon(mon, box) {
  const stats = mon.calculated_stats;
  const dvs = mon.dvs;
  openDialog(mon.nickname, [
    ["Storage", `Box ${box.display_number} · slot ${box.members.indexOf(mon) + 1}`],
    ["Species", mon.species_name], ["Level", mon.level],
    ["HP", `${mon.current_hp}/${mon.calculated_max_hp}`],
    ["Status", mon.status_conditions.join(", ") || "OK"],
    ["Types", mon.types.join(" / ")],
    ["Original Trainer", `${mon.original_trainer_name} · ID ${mon.original_trainer_id}`],
    ["Experience", `${mon.experience}${mon.experience_to_next_level == null ? " · level 100" : ` · ${mon.experience_to_next_level} to next level`}`],
    ["Calculated stats", `HP ${stats.hp} · ATK ${stats.attack} · DEF ${stats.defense} · SPD ${stats.speed} · SPC ${stats.special}`],
    ["DVs stored in save", `HP ${dvs.hp} · ATK ${dvs.attack} · DEF ${dvs.defense} · SPD ${dvs.speed} · SPC ${dvs.special}`],
    ["Moves", mon.moves.map(move => `${move.display_name} ${move.current_pp}/${move.maximum_pp} PP`).join(", ") || "None"],
    ["Stat accuracy", "Final box stats are calculated from stored level, DVs and stat experience; Gen I stores final battle stats only for party Pokémon."],
  ]);
}

function renderBox(boxIndex) {
  const boxes = dashboard.boxes.entries || [];
  const box = boxes.find(item => item.index === boxIndex) || boxes[0];
  const tabs = $("boxTabs");
  tabs.querySelectorAll("button").forEach(button => {
    const active = Number(button.dataset.boxIndex) === box?.index;
    button.classList.toggle("active", active); button.setAttribute("aria-selected", String(active));
  });
  const summary = $("boxSummary"), root = $("boxPokemonGrid"); clear(summary); clear(root);
  if (!box) { root.append(element("p", "empty-state", "No box structures were decoded.")); return; }
  const labels = {current_cache: "CURRENT BOX CACHE", stored: "STORED BOX", uninitialized: "UNINITIALIZED STORAGE"};
  summary.append(
    element("strong", "", `BOX ${box.display_number}`),
    element("span", "", `${box.pokemon_count} / ${dashboard.boxes.capacity_per_box} POKÉMON`),
    element("span", `box-state ${box.status}`, labels[box.status] || box.status.toUpperCase()),
    element("span", "", box.checksum_verified === true ? "CHECKSUM VERIFIED" : box.checksum_verified === false ? "CHECKSUM FAILED" : "NO BOX CHECKSUM AVAILABLE")
  );
  if (box.status === "uninitialized") {
    root.append(element("p", "empty-state", "This storage block is uninitialized. It is unknown storage—not evidence that the box was deliberately emptied."));
    return;
  }
  if (!box.members.length) {
    root.append(element("p", "empty-state", box.status === "current_cache"
      ? "The valid current-box cache contains no Pokémon in the loaded save."
      : "This initialized box contains no Pokémon in the loaded save."));
    return;
  }
  box.members.forEach((mon, index) => {
    const card = element("button", "pc-pokemon-card"); card.type = "button";
    const image = element("img"); image.src = sprite(mon.dex_number); image.alt = mon.species_name;
    const info = element("div");
    info.append(
      element("span", "pc-slot", `SLOT ${index + 1}`),
      element("strong", "", mon.nickname.toUpperCase()),
      element("span", "", `${mon.species_name} · L${mon.level}`),
      element("small", "", `${mon.current_hp}/${mon.calculated_max_hp} HP · ${mon.status_conditions.join(", ").toUpperCase() || "OK"}`)
    );
    card.append(image, info); card.addEventListener("click", () => openBoxPokemon(mon, box)); root.append(card);
  });
}

function renderBoxes(data) {
  $("boxPokemonTotal").textContent = `${data.boxes.observed_pokemon} POKÉMON`;
  $("boxAccuracyNote").textContent = data.boxes.accuracy_note;
  const tabs = $("boxTabs"); clear(tabs);
  (data.boxes.entries || []).forEach(box => {
    const count = box.status === "uninitialized" ? "UNKNOWN" : `${box.pokemon_count}/20`;
    const button = element("button", `box-tab ${box.status}`, `BOX ${box.display_number}\n${count}`);
    button.type = "button"; button.role = "tab"; button.dataset.boxIndex = box.index;
    button.addEventListener("click", () => renderBox(box.index)); tabs.append(button);
  });
  const preferred = (data.boxes.entries || []).find(box => box.is_current)
    || (data.boxes.entries || []).find(box => box.status !== "uninitialized")
    || data.boxes.entries?.[0];
  renderBox(preferred?.index);
}

function formatUploadTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString([], {dateStyle: "medium", timeStyle: "medium"});
}

function renderRunHistory(data) {
  const history = data.run_history || {total_snapshots: 0, entries: [], time_explanation: "No snapshot repository is available."};
  $("runHistoryTotal").textContent = `${history.total_snapshots} ${history.total_snapshots === 1 ? "LOAD" : "LOADS"}`;
  $("runHistoryExplanation").textContent = `${history.time_explanation} Each entry is an immutable, validated observation; manual encounter records remain in Encounters.`;
  const root = $("runHistoryList"); clear(root);
  if (!history.entries.length) { root.append(element("p", "empty-state", "No accepted save snapshots recorded for this run.")); return; }
  history.entries.forEach(entry => {
    const card = element("article", `run-history-card${entry.is_latest ? " latest" : ""}`);
    const head = element("div", "run-history-head");
    const title = element("div"); title.append(element("strong", "", `LOAD #${entry.sequence}`), element("span", "", formatUploadTime(entry.uploaded_at)));
    head.append(title, element("b", "", entry.is_latest ? "LATEST" : "ARCHIVED"));
    const facts = element("div", "run-history-facts");
    [["LOCATION", `${entry.location.name} · (${entry.location.x}, ${entry.location.y})`], ["BADGES", entry.badges.length], ["PARTY", entry.party.length], ["PC", entry.boxed_pokemon], ["POKÉDEX", entry.pokedex_owned], ["MONEY", `¥${entry.money}`]].forEach(([label, value]) => {
      const fact = element("div"); fact.append(element("span", "", label), element("strong", "", value)); facts.append(fact);
    });
    const team = element("div", "run-history-party");
    entry.party.forEach(mon => team.append(element("span", "", `${mon.nickname} · ${mon.species_name} L${mon.level}`)));
    const changes = element("ul", "run-history-changes"); entry.changes.forEach(change => changes.append(element("li", "", change)));
    card.append(head, facts, team, element("div", "subheading", "CHANGES FROM PREVIOUS LOAD"), changes); root.append(card);
  });
}

function renderSharing(data) {
  const sharing = data.sharing, card = $("shareRunCard");
  card.classList.toggle("hidden", !sharing?.username);
  if (!sharing?.username) return;
  const viewer = sharing.role === "viewer";
  $("shareRole").textContent = viewer ? "VIEWING FRIEND'S RUN" : "INVITE VIEWERS";
  $("shareUsername").textContent = `@${sharing.username}`;
  $("shareNote").textContent = viewer ? "READ-ONLY SPECTATOR MODE" : "Friends search this username. Your password stays private.";
  $("copyShareBtn").classList.toggle("hidden", viewer);
  $("encounterForm").classList.toggle("hidden", viewer);
  document.body.classList.toggle("viewer-mode", viewer);
}

function renderArea(index) {
  const area = dashboard.areas[index];
  const notice = $("encounterNotice");
  if (!area) { notice.textContent = "NO NEARBY AREA DATA"; clear($("encounters")); return; }
  const labels = {unknown: "ENCOUNTER HISTORY UNKNOWN", available: "FIRST ENCOUNTER AVAILABLE", consumed: "ENCOUNTER ALREADY USED"};
  notice.textContent = labels[area.encounter_status];
  notice.dataset.state = area.encounter_status;
  if (!area.progression_accessible) notice.textContent = `LOCKED · ${area.blocked_reason}`;
  const root = $("encounters"); clear(root);
  area.encounters.forEach(enc => {
    const row = element("button", "encounter-row"); row.type = "button";
    const img = element("img"); img.src = sprite(enc.dex_number); img.alt = enc.species_name;
    const info = element("div"); info.append(element("div", "encounter-name", enc.species_name.toUpperCase()), element("div", "encounter-meta", [...new Set(enc.type_names)].join(" / ")));
    row.append(img, info, element("div", "encounter-meta", `L${enc.levels.join("/")}`));
    row.addEventListener("click", () => openDialog(`${enc.species_name} · ${area.map_name}`, [["Levels", enc.levels.join(", ")], ["Slot chance", `${Math.round(enc.slot_weight / enc.slot_weight_denominator * 100)}%`], ["Encounter rate", `${enc.encounter_rate}/255 per step check`], ["Method", enc.method]]));
    root.append(row);
  });
  const remaining = area.items.filter(item => !item.collected);
  const itemRoot = $("itemList"); clear(itemRoot);
  if (!remaining.length) itemRoot.append(element("div", "", "No remaining mapped items detected."));
  remaining.forEach(item => {
    const line = element("div", `item-access ${item.access_status}`);
    const state = item.access_status === "available" ? "AVAILABLE NOW" : item.access_status === "locked" ? "LOCKED" : "PATH UNVERIFIED";
    line.append(element("strong", "", `${state} · ${item.hidden ? "Hidden" : "Visible"} ${item.item_name}`), element("span", "", `(${item.x}, ${item.y}) · ${item.access_requirement}`));
    itemRoot.append(line);
  });
}

function openTrainerPokemon(trainer, mon) {
  const stats = mon.stats || {};
  const rows = [
    ["Trainer", trainer.trainer_class], ["Location", trainer.map_name],
    ["Level", mon.level], ["Types", mon.types.join(" / ")],
    ["HP", stats.hp ?? "—"], ["Attack", stats.attack ?? "—"],
    ["Defense", stats.defense ?? "—"], ["Speed", stats.speed ?? "—"],
    ["Special", stats.special ?? "—"],
    ["Stat basis", "Trainer DVs 9/8/8/8 · zero stat experience"],
  ];
  (mon.moves || []).forEach(move => rows.push([
    move.move_name,
    `${move.type} · ${move.category} · POW ${move.power || "—"} · ACC ${move.accuracy}% · PP ${move.pp}`,
  ]));
  openDialog(`${mon.species_name} · L${mon.level}`, rows);
}

function encounterStorageKey() {
  return dashboard ? `nuzlocke-encounters:${dashboard.trainer.version}:${dashboard.trainer.trainer_id}` : "nuzlocke-encounters";
}

function loadManualEncounters() {
  try {
    const value = JSON.parse(localStorage.getItem(encounterStorageKey()) || "[]");
    return Array.isArray(value) ? value : [];
  } catch (_) { return []; }
}

function combinedEncounterHistory() {
  const records = new Map((dashboard.encounter_history || []).map(record => [record.area_id, {...record, persistent: true}]));
  if (dashboard.sharing?.role === "viewer") return [...records.values()].sort((a, b) => a.map_name.localeCompare(b.map_name));
  loadManualEncounters().forEach(record => { if (!records.has(record.area_id)) records.set(record.area_id, {...record, persistent: false}); });
  return [...records.values()].sort((a, b) => a.map_name.localeCompare(b.map_name));
}

function applyEncounterHistory() {
  const records = new Map(combinedEncounterHistory().map(record => [record.area_id, record]));
  dashboard.areas.forEach(area => {
    const record = records.get(area.area_id);
    if (record) area.encounter_status = record.status === "unclaimed" ? "available" : "consumed";
  });
}

function selectedEncounterArea() {
  return dashboard?.encounter_catalog.find(area => area.area_id === $("historyArea").value);
}

function populateEncounterSpecies() {
  const area = selectedEncounterArea(), method = $("historyMethod").value;
  const root = $("historySpecies"); clear(root);
  (area?.choices || []).filter(choice => choice.method === method).forEach(choice => {
    const option = element("option", "", choice.species_name); option.value = choice.species_id; root.append(option);
  });
  const choice = area?.choices.find(item => item.method === method && String(item.species_id) === root.value);
  $("historyLevel").value = choice?.valid_levels?.[0] || "";
}

function populateEncounterForm() {
  const area = selectedEncounterArea(), methods = $("historyMethod"); clear(methods);
  (area?.methods || []).forEach(method => { const option = element("option", "", method.replaceAll("_", " ").toUpperCase()); option.value = method; methods.append(option); });
  populateEncounterSpecies();
}

function renderEncounterHistory() {
  const records = combinedEncounterHistory(), root = $("encounterHistoryList"); clear(root);
  $("encounterHistoryCount").textContent = String(records.length);
  if (!records.length) { root.append(element("p", "empty-state", "No route encounters recorded yet. Use the form above to confirm the first encounter for an area.")); return; }
  records.forEach(record => {
    const row = element("article", `encounter-history-row ${record.status}`);
    const image = element("img");
    if (record.dex_number) { image.src = sprite(record.dex_number); image.alt = record.species_name; } else { image.classList.add("history-empty-sprite"); image.alt = "No Pokémon recorded"; }
    const details = element("div");
    details.append(element("strong", "", record.map_name.toUpperCase()), element("span", "", `${record.status.toUpperCase()}${record.species_name ? ` · ${record.nickname || record.species_name} · L${record.level || "?"}` : ""}`), element("small", "", record.method ? record.method.replaceAll("_", " ").toUpperCase() : "NO ENCOUNTER METHOD"));
    const action = element(record.persistent ? "span" : "button", record.persistent ? "history-saved" : "history-remove", record.persistent ? "SAVED" : "REMOVE");
    if (!record.persistent) {
      action.type = "button";
      action.addEventListener("click", () => {
        const remaining = loadManualEncounters().filter(item => item.area_id !== record.area_id);
        localStorage.setItem(encounterStorageKey(), JSON.stringify(remaining)); applyEncounterHistory(); renderEncounterHistory(); renderArea(Number($("areaSelect").value || 0));
      });
    }
    row.append(image, details, action); root.append(row);
  });
}

function renderObjective(data) {
  const objective = data.objective, trainer = data.next_trainer;
  const basisLabels = {
    same_map_manhattan_distance: "SAME MAP",
    connected_map_entry_coordinate_heuristic: "REACHABLE ADJACENT MAP",
    mandatory_progression: "PROGRESSION FALLBACK"
  };
  const kickerLabels = {
    same_map_manhattan_distance: "NEAREST SAME-MAP CANDIDATE",
    connected_map_entry_coordinate_heuristic: "NEAREST ADJACENT-MAP CANDIDATE",
    mandatory_progression: "MANDATORY PROGRESSION TRAINER",
  };
  $("objectiveArea").textContent = objective ? objective.location_name.toUpperCase() : "HALL OF FAME";
  $("objectiveName").textContent = objective ? objective.boss.toUpperCase() : "RUN COMPLETE";
  $("trainerName").textContent = trainer ? trainer.trainer_class.toUpperCase() : "NO UNDEFEATED TRAINER";
  $("trainerKicker").textContent = trainer ? (kickerLabels[trainer.selection_basis] || "UNDEFEATED TRAINER") : "NO TRAINER AVAILABLE";
  $("trainerPosition").textContent = trainer ? `${basisLabels[trainer.selection_basis] || "KNOWN TRAINER"} · ${trainer.map_name} · (${trainer.x}, ${trainer.y})` : "—";
  $("partyHighest").textContent = data.party.length ? Math.max(...data.party.map(mon => mon.level)) : "—";
  $("trainerHighest").textContent = trainer?.party?.length ? Math.max(...trainer.party.map(mon => mon.level)) : "—";
  $("levelCap").textContent = objective?.level_cap ?? "—";
  $("trainerStatus").textContent = trainer ? "UNDEFEATED" : "CLEAR";
  $("trainerStatus").classList.toggle("clear", !trainer);
  const portrait = $("objectivePortrait");
  portrait.src = trainer ? `assets/trainers/${trainerImageFile(trainer.trainer_class)}` : objective ? `assets/trainers/${bossSprites[objective.boss] || "rival3.png"}` : "assets/player-red.png";
  portrait.alt = trainer ? `Generation I ${trainer.trainer_class} sprite` : objective ? `Generation I ${objective.boss} sprite` : "Generation I player character Red";
  portrait.addEventListener("error", () => { portrait.src = objective ? `assets/trainers/${bossSprites[objective.boss] || "rival3.png"}` : "assets/player-red.png"; }, {once: true});
  const team = $("trainerTeam"); clear(team);
  (trainer?.party || []).forEach(mon => {
    const row = element("button", "trainer-mon-row"); row.type = "button"; const img = element("img"); img.src = sprite(mon.dex_number); img.alt = mon.species_name;
    row.append(img, element("span", "", mon.species_name.toUpperCase()), element("b", "", `:L${mon.level}`)); team.append(row);
    row.addEventListener("click", () => openTrainerPokemon(trainer, mon));
  });
}

function renderInventory(data) {
  const renderSavedList = (rootId, entries) => {
    const root = $(rootId); clear(root);
    if (!entries.length) { root.append(element("p", "empty-state", "No items stored here.")); return; }
    entries.forEach(item => {
      const row = element("div", "inventory-row");
      row.append(element("span", "item-ball-model", ""), element("strong", "", item.display_name.toUpperCase()), element("span", "inventory-quantity", `×${item.quantity}`));
      root.append(row);
    });
  };
  renderSavedList("bagInventory", data.inventory.bag);
  renderSavedList("pcInventory", data.inventory.pc);
  const world = $("worldItemList"); clear(world);
  const groups = [{map_id: data.location.map_id, map_name: data.location.name, items: data.items_here}, ...data.areas.filter(area => area.map_id !== data.location.map_id)];
  let count = 0;
  const seenItems = new Set();
  groups.forEach(group => group.items.forEach(item => {
    const itemKey = `${group.map_id}:${item.x}:${item.y}:${item.item_id}:${item.hidden ? "hidden" : "visible"}`;
    if (seenItems.has(itemKey)) return;
    seenItems.add(itemKey);
    count += 1;
    const status = item.collected ? "collected" : item.access_status;
    const row = element("div", `world-item-row ${status}`);
    const title = item.hidden ? `HIDDEN · ${item.item_name}` : item.item_name;
    row.append(element("span", "item-ball-model", ""), element("strong", "", title.toUpperCase()), element("span", "", `${group.map_name} · (${item.x}, ${item.y})`), element("b", "", item.collected ? "COLLECTED" : String(item.access_status || "UNVERIFIED").toUpperCase()));
    world.append(row);
  }));
  if (!count) world.append(element("p", "empty-state", "No mapped item placements in the current or neighboring areas."));
}

function switchView(name) {
  if (!dashboard) return;
  $("dashboardView").classList.toggle("hidden", name !== "dashboard");
  $("partyView").classList.toggle("hidden", name !== "party");
  $("boxesView").classList.toggle("hidden", name !== "boxes");
  $("encountersView").classList.toggle("hidden", name !== "encounters");
  $("trainersView").classList.toggle("hidden", name !== "trainers");
  $("itemsView").classList.toggle("hidden", name !== "items");
  $("runHistoryView").classList.toggle("hidden", name !== "run-history");
  $("locationName").textContent = name === "dashboard" ? dashboard.location.name.toUpperCase() : name.toUpperCase();
  document.querySelectorAll("[data-view]").forEach(button => {
    const active = button.dataset.view === name; button.classList.toggle("active", active);
    button.querySelector(".pointer").textContent = active ? "▶" : " ";
  });
}

function renderBadges(data) {
  const names = ["Boulder", "Cascade", "Thunder", "Rainbow", "Soul", "Marsh", "Volcano", "Earth"];
  const root = $("badges"); clear(root);
  names.forEach((name, index) => {
    const owned = data.badges.includes(name), badge = element("div", "badge");
    const image = element("span", `trainer-card-emblem ${owned ? "owned" : "leader"}`);
    image.style.backgroundPosition = `0 -${(index * 2 + (owned ? 1 : 0)) * 32}px`;
    image.title = owned ? `${name} Badge earned` : `${name} Badge not earned`;
    image.setAttribute("role", "img"); image.setAttribute("aria-label", image.title);
    badge.append(image, element("span", "", name.toUpperCase())); root.append(badge);
  });
  $("progressText").textContent = `${data.progress.completed} / ${data.progress.total}`;
  $("progressBar").style.width = `${Math.round(data.progress.completed / data.progress.total * 100)}%`;
}

function trainerImageFile(name) {
  const normalized = name.toLowerCase();
  return trainerClassSprites[normalized] || `${normalized.replaceAll(" ", "").replace(/[^a-z0-9.]/g, "")}.png`;
}

function renderTrainers(data) {
  const nextRoot = $("nextTrainerCard"); clear(nextRoot);
  if (data.next_trainer) {
    const trainer = data.next_trainer;
    const card = element("article", "objective-trainer-card next-trainer-card");
    const image = element("img"); image.src = `assets/trainers/${trainerImageFile(trainer.trainer_class)}`; image.alt = `Generation I ${trainer.trainer_class} sprite`;
    image.addEventListener("error", () => { image.src = data.objective ? `assets/trainers/${bossSprites[data.objective.boss] || "rival3.png"}` : "assets/player-red.png"; }, {once: true});
    const details = element("div");
    details.append(element("div", "next-badge", "NEXT ENCOUNTER"), element("h2", "", trainer.trainer_class.toUpperCase()), element("p", "", `${trainer.map_name} · tile (${trainer.x}, ${trainer.y}) · ${trainer.selection_basis.replaceAll("_", " ").toUpperCase()}`));
    const party = element("div", "trainer-party-models");
    trainer.party.forEach(mon => {
      const monCard = element("button", "trainer-mon-card"); monCard.type = "button"; const monImage = element("img"); monImage.src = sprite(mon.dex_number); monImage.alt = mon.species_name;
      monCard.append(monImage, element("span", "", `${mon.species_name} · L${mon.level}`)); party.append(monCard);
      monCard.addEventListener("click", () => openTrainerPokemon(trainer, mon));
    });
    details.append(party); card.append(image, details); nextRoot.append(card);
  } else {
    nextRoot.append(element("p", "empty-state", "No reachable undefeated trainer was detected from this save."));
  }
  const reachableRoot = $("reachableTrainerList"); clear(reachableRoot);
  const others = (data.reachable_trainers || []).filter(trainer => trainer.trainer_id !== data.next_trainer?.trainer_id);
  if (!others.length) reachableRoot.append(element("p", "empty-state", "No additional reachable undefeated trainers are visible from the current map."));
  others.forEach(trainer => {
    const card = element("article", "reachable-trainer-card"), image = element("img");
    image.src = `assets/trainers/${trainerImageFile(trainer.trainer_class)}`; image.alt = `Generation I ${trainer.trainer_class} sprite`;
    const details = element("div"); details.append(element("strong", "", trainer.trainer_class.toUpperCase()), element("span", "", `${trainer.map_name} · (${trainer.x}, ${trainer.y})`));
    const team = element("div", "reachable-team"); trainer.party.forEach(mon => {
      const monButton = element("button", "", `${mon.species_name} L${mon.level}`); monButton.type = "button";
      monButton.addEventListener("click", () => openTrainerPokemon(trainer, mon)); team.append(monButton);
    });
    details.append(team); card.append(image, details); reachableRoot.append(card);
  });
  const roster = $("leagueRoster"); clear(roster);
  progressionRoster.forEach(([name, file], index) => {
    const state = index < data.progress.completed ? "defeated" : index === data.progress.completed && data.objective ? "current" : "upcoming";
    const card = element("article", `league-card ${state}`), image = element("img");
    image.src = `assets/trainers/${file}`; image.alt = `Generation I ${name} sprite`;
    card.append(image, element("strong", "", name.toUpperCase()), element("span", "", state === "defeated" ? "DEFEATED" : state === "current" ? "CURRENT" : "UPCOMING"));
    roster.append(card);
  });
  const objectiveRoot = $("objectiveTrainerList"); clear(objectiveRoot);
  if (!data.objective) {
    objectiveRoot.append(element("p", "empty-state", "No mandatory trainer remains. Hall of Fame completion detected."));
    return;
  }
  data.objective.trainers.forEach(trainer => {
    const card = element("article", `objective-trainer-card ${trainer.defeated ? "defeated" : "remaining"}`);
    const image = element("img"); image.src = `assets/trainers/${trainerImageFile(trainer.trainer_class)}`; image.alt = `Generation I ${trainer.trainer_class} sprite`;
    image.addEventListener("error", () => { image.src = `assets/trainers/${bossSprites[data.objective.boss] || "rival3.png"}`; }, {once: true});
    const details = element("div");
    details.append(element("h2", "", trainer.trainer_class.toUpperCase()), element("p", "", `${trainer.map_name} · (${trainer.x}, ${trainer.y}) · ${trainer.defeated ? "DEFEATED" : "UNDEFEATED"}`));
    const party = element("div", "trainer-party-models");
    trainer.party.forEach(mon => {
      const monCard = element("button", "trainer-mon-card"); monCard.type = "button"; const monImage = element("img"); monImage.src = sprite(mon.dex_number); monImage.alt = mon.species_name;
      monCard.append(monImage, element("span", "", `${mon.species_name} · L${mon.level}`)); party.append(monCard);
      monCard.addEventListener("click", () => openTrainerPokemon(trainer, mon));
    });
    details.append(party); card.append(image, details); objectiveRoot.append(card);
  });
}

function renderEvidence(data) {
  const root = $("events"); clear(root);
  const evidence = [
    ["✓", `${data.defeated_trainer_count} trainer flags detected`, "SAVE FLAGS"],
    ["⚑", `${data.completed_story_events.length} story events detected`, "SAVE FLAGS"],
    ["□", `${data.boxes.observed_pokemon} boxed Pokémon observed`, data.boxes.initialized ? "BOXES READ" : "BOXES NOT INITIALIZED"],
    ["●", `${data.items_here.filter(item => !item.collected).length} remaining items here`, data.location.name]
  ];
  evidence.forEach(([icon, title, sub]) => { const row = element("div", "event-row"); row.append(element("div", "event-icon", icon)); const detail = element("div"); detail.append(element("div", "event-title", title), element("div", "event-sub", sub)); row.append(detail); root.append(row); });
}

function renderChecks(data) {
  const root = $("statusList"); clear(root);
  data.checks.forEach(check => { const mode = check.state === "ok" ? "ok" : "warn"; const row = element("div", "status-row"); row.append(element("div", `status-mark ${mode}`, mode === "ok" ? "✓" : "!"), element("div", "status-text", check.label), element("div", `status-state ${mode}`, check.value)); root.append(row); });
}

function renderDashboard(data) {
  dashboard = data;
  document.title = `Nuzlocke Companion — ${data.trainer.name}`;
  // The selected version is part of the server-validated dashboard payload.
  // Keep a defensive fallback for older shared snapshots that predate the
  // nested trainer.version field, so a Red load cannot silently fall back to
  // the Blue upload-form default.
  const version = data.trainer?.version || data.game_version || $("gameVersion").value || "unknown";
  $("versionChip").textContent = `POKÉMON ${String(version).toUpperCase()}`;
  $("runName").textContent = `${data.trainer.name}'S RUN`;
  $("locationName").textContent = data.location.name.toUpperCase();
  $("coordinates").textContent = `(${data.location.x}, ${data.location.y})`;
  const stats = $("sideStats"); clear(stats);
  [`RUN: ${data.trainer.name}`, `BADGES: ${data.badges.length}`, `POKÉDEX: ${data.trainer.pokedex_owned}/${data.trainer.pokedex_seen}`, `MONEY: ¥${data.trainer.money}`, `HOF: ${data.trainer.hall_of_fame_teams}`].forEach(text => stats.append(element("div", "", text)));
  if (data.sharing?.role !== "viewer") applyEncounterHistory();
  renderParty(data); renderBoxes(data); renderObjective(data); renderBadges(data); renderEvidence(data); renderChecks(data); renderTrainers(data); renderInventory(data); renderRunHistory(data);
  renderSharing(data);
  const select = $("areaSelect"); clear(select);
  data.areas.forEach((area, index) => { const option = element("option", "", `${area.map_name}${area.progression_accessible ? "" : " (LOCKED)"}`); option.value = index; select.append(option); });
  renderArea(0);
  const historyArea = $("historyArea"); clear(historyArea);
  const terminalAreas = new Set(combinedEncounterHistory().filter(record => ["caught", "missed", "fled", "fainted"].includes(record.status)).map(record => record.area_id));
  data.encounter_catalog.forEach(area => { const locked = terminalAreas.has(area.area_id); const option = element("option", "", `${area.map_name}${locked ? " · RECORDED" : ""}`); option.value = area.area_id; option.disabled = locked; historyArea.append(option); });
  populateEncounterForm(); renderEncounterHistory();
  switchView("dashboard");
  $("uploadScreen").classList.add("hidden"); $("gameLayout").classList.remove("hidden");
}

async function inspectSave() {
  const file = $("saveFile").files[0], status = $("uploadStatus");
  if (!file) { status.textContent = "Choose a .sav file first."; return; }
  const username = $("ownerUsername").value.trim().toLowerCase(), password = $("ownerPassword").value;
  if (!/^[a-z0-9][a-z0-9_]{2,19}$/.test(username)) { status.textContent = "Choose a 3–20 character username using letters, numbers, or underscores."; return; }
  if (password.length < 8) { status.textContent = "Your password must contain at least 8 characters."; return; }
  status.textContent = "Validating checksum and parsing save data…"; $("inspectBtn").disabled = true;
  try {
    const headers = {"Content-Type": "application/octet-stream", "X-Run-Username": username, "X-Run-Password": password};
    const response = await fetch(`/api/inspect?version=${encodeURIComponent($("gameVersion").value)}`, {method: "POST", headers, body: await file.arrayBuffer()});
    const result = await response.json();
    if (!response.ok) {
      const details = result.diagnostics?.map(item => `${item.code}: ${item.message}`).join(" · ") || result.message || "Save could not be parsed.";
      throw new Error(details);
    }
    $("ownerPassword").value = "";
    localStorage.setItem("nuzlocke-public-username", username);
    renderDashboard(result);
    if (result.sharing?.account_created) openDialog("Run account created", [
      ["Public username", `@${result.sharing.username}`],
      ["Private password", "Saved only as a secure one-way hash. Keep your original password safe."],
      ["For friends", "Give them only your username or copy the viewer link."],
      ...(result.hosting?.storage === "ephemeral" ? [["Free preview", "This deployment uses temporary storage. A server restart can erase this run and its history."]] : []),
    ]);
  } catch (error) {
    const connectionFailure = error instanceof TypeError && /fetch/i.test(error.message);
    status.textContent = connectionFailure
      ? "Could not reach the local server. Start it in PowerShell, keep that window open, then reload this page."
      : `Could not load save: ${error.message}`;
  }
  finally { $("inspectBtn").disabled = false; }
}

async function viewSharedRun() {
  const username = $("viewerUsername").value.trim().toLowerCase();
  const status = $("viewerStatus");
  if (!/^[a-z0-9][a-z0-9_]{2,19}$/.test(username)) { status.textContent = "Enter a valid username."; return; }
  $("viewRunBtn").disabled = true; status.textContent = "Loading the latest shared progress…";
  try {
    const response = await fetch(`/api/view?username=${encodeURIComponent(username)}`);
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || "Shared run could not be loaded.");
    history.replaceState(null, "", `/?user=${encodeURIComponent(username)}`);
    renderDashboard(result);
  } catch (error) {
    status.textContent = `Could not open shared run: ${error.message}`;
  } finally { $("viewRunBtn").disabled = false; }
}

$("inspectBtn").addEventListener("click", inspectSave);
$("viewRunBtn").addEventListener("click", viewSharedRun);
$("saveFile").addEventListener("change", event => {
  const file = event.target.files[0];
  if (!file) return;
  const name = file.name.toLowerCase();
  const hintedVersion = /(^|[^a-z])red([^a-z]|$)/.test(name) ? "red" : /(^|[^a-z])blue([^a-z]|$)/.test(name) ? "blue" : null;
  if (hintedVersion) {
    $("gameVersion").value = hintedVersion;
    $("uploadStatus").textContent = `Filename suggests Pokémon ${hintedVersion.toUpperCase()}; verify GAME VERSION before inspecting.`;
  }
});
$("viewerUsername").addEventListener("input", event => { event.target.value = event.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""); });
$("viewerUsername").addEventListener("keydown", event => { if (event.key === "Enter") viewSharedRun(); });
async function copyText(value) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  // Clipboard API is unavailable on plain HTTP and older browsers. Keep the
  // share action usable for local deployments with a temporary, selected
  // textarea fallback.
  const input = element("textarea", "clipboard-fallback");
  input.value = value;
  input.setAttribute("readonly", "");
  input.style.position = "fixed";
  input.style.opacity = "0";
  document.body.append(input);
  input.select();
  const copied = document.execCommand("copy");
  input.remove();
  if (!copied) throw new Error("Clipboard access is unavailable. Copy the viewer URL from the address bar.");
}
$("copyShareBtn").addEventListener("click", async () => {
  const path = dashboard?.sharing?.viewer_path || `/?user=${dashboard?.sharing?.username || ""}`;
  try {
    await copyText(new URL(path, location.origin).href);
    $("copyShareBtn").textContent = "COPIED";
    setTimeout(() => { $("copyShareBtn").textContent = "COPY VIEWER LINK"; }, 1400);
  } catch (error) {
    openDialog("Copy unavailable", [error.message]);
  }
});
$("areaSelect").addEventListener("change", event => renderArea(Number(event.target.value)));
$("historyArea").addEventListener("change", populateEncounterForm);
$("historyMethod").addEventListener("change", populateEncounterSpecies);
$("historySpecies").addEventListener("change", () => {
  const area = selectedEncounterArea(), choice = area?.choices.find(item => item.method === $("historyMethod").value && String(item.species_id) === $("historySpecies").value);
  $("historyLevel").value = choice?.valid_levels?.[0] || "";
});
$("encounterForm").addEventListener("submit", async event => {
  event.preventDefault();
  const area = selectedEncounterArea(), method = $("historyMethod").value;
  const choice = area?.choices.find(item => item.method === method && String(item.species_id) === $("historySpecies").value);
  const status = $("historyStatus").value, nickname = $("historyNickname").value.trim(), level = Number($("historyLevel").value) || null;
  if (status === "caught" && !nickname) { openDialog("Nickname required", ["Caught Pokémon need a nickname under the active Nuzlocke rules."]); return; }
  const record = {area_id: area.area_id, map_name: area.map_name, status, species_id: choice?.species_id || null, species_name: choice?.species_name || null, dex_number: choice?.dex_number || null, nickname: nickname || null, method: method || null, level, source: "wild", notes: null};
  const button = event.submitter; button.disabled = true; button.textContent = "SAVING…";
  try {
    const response = await fetch("/api/encounters", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({...record, run_id: dashboard.run_id})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || "Encounter could not be saved.");
    dashboard.encounter_history = (dashboard.encounter_history || []).filter(item => item.area_id !== record.area_id);
    dashboard.encounter_history.push(record);
    localStorage.setItem(encounterStorageKey(), JSON.stringify(loadManualEncounters().filter(item => item.area_id !== record.area_id)));
    applyEncounterHistory(); renderEncounterHistory(); renderParty(dashboard); renderArea(Number($("areaSelect").value || 0));
    openDialog("Encounter saved", [["Area", record.map_name], ["Result", record.status], ["Pokémon", record.species_name || "None"]]);
  } catch (error) {
    openDialog("Could not save encounter", [error.message]);
  } finally {
    button.disabled = false; button.textContent = "SAVE ENCOUNTER";
  }
});
$("reloadBtn").addEventListener("click", () => { $("gameLayout").classList.add("hidden"); $("uploadScreen").classList.remove("hidden"); $("saveFile").value = ""; $("uploadStatus").textContent = "Choose another save file."; });
$("themeBtn").addEventListener("click", () => document.body.classList.toggle("classic-dark"));
$("menuBtn").addEventListener("click", () => openDialog("About", ["The dashboard separates facts decoded from the save from manual Nuzlocke history.", "Encounter use cannot be reconstructed reliably from a Generation I save alone."]));
$("partyLink").addEventListener("click", () => switchView("party"));
$("trainerLink").addEventListener("click", () => switchView("trainers"));
$("historyLink").addEventListener("click", () => openDialog("Save evidence", [["Parser", dashboard.parser.status], ["Story events", dashboard.completed_story_events.length], ["Defeated trainers", dashboard.defeated_trainer_count], ["Hall of Fame", dashboard.trainer.hall_of_fame_teams]]));
$("rulesLink").addEventListener("click", () => openDialog("Rule interpretation", dashboard.limitations));
$("dialogClose").addEventListener("click", closeDialog);
$("dialog").addEventListener("click", event => { if (event.target === $("dialog")) closeDialog(); });
document.addEventListener("keydown", event => { if (event.key === "Escape") closeDialog(); });
document.querySelectorAll("[data-view]").forEach(button => button.addEventListener("click", () => switchView(button.dataset.view)));
document.querySelectorAll("[data-planned]").forEach(button => button.addEventListener("click", () => openDialog(button.dataset.planned, ["This section is planned. Its verified save-backed facts are already summarized on the dashboard."])));

const sharedUsernameFromUrl = new URLSearchParams(location.search).get("user");
if (sharedUsernameFromUrl) { $("viewerUsername").value = sharedUsernameFromUrl.toLowerCase(); viewSharedRun(); }
else { $("ownerUsername").value = localStorage.getItem("nuzlocke-public-username") || ""; }
