#!/usr/bin/env python3
"""Install the Magic Chest shrine and the village-name signs in a running Minecraft server (idempotent).

    python3 tools/minecraft_install.py --mc-dir DIR --session NAME [--config config/minecraft.json] [--survey-only]

What it builds (design: tools/shrine_blocks.json, rules and code: tools/shrine.py, spec Addenda 5 and 6):
  * a pagoda shrine with a beacon around Magic Chest 1 at config `shrine`; the overflow chest spots in config `chests`
    are inside it; Magic Chest 1 itself, its floating label and an entrance sign with the village name;
  * a standing village-name sign (config/family.json village_name) on a free cell next to the world spawn point (never on it).

Safety, in this order, before ANY block is placed:
  1. config `chests` must equal the shrine's chest spots, and config `forbidden` must contain the world spawn point read
     from <mc-dir>/world/level.dat (read-only);
  2. EVERY target cell is surveyed: only air or a replaceable plant is acceptable (foundations: air or a plant, down to
     solid ground; a plant is overwritten only through a guarded `execute if block <cell> <that plant> run setblock`). Anything else refuses the whole build, lists the blocked cells and places nothing;
  0. server.properties spawn-protection must not cover the shrine, chests or spawn sign (non-ops could not open the chest);
  3. a spot for the spawn sign is found by survey too.
Then it builds. A re-run finds the marker armor stand (tag reading_village_shrine) and only fills what is missing.
No datapack: loot tables are inline (docs/design.md, "Villager shop and Magic Chest"). The server must be running in
the given screen session. Any problem prints a FAILED banner and exits non-zero.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import minecraft_bridge as mcb  # noqa: E402
import server  # noqa: E402
import shrine  # noqa: E402


def fail(msg):
    print(f"\n*** FAILED: {msg}", file=sys.stderr)
    sys.exit(1)


def chunk_probe_cells(cells):
    """One cell per 16x16 chunk column touched by `cells` (what `forceload add` needs)."""
    return sorted({(x >> 4, z >> 4): (x, z) for x, _y, z in cells}.values())


def check_config_matches_shrine(cfg, plan, config_path):
    """config.chests must be exactly the shrine's spots (same order): the worker places overflow chests there."""
    if cfg["chests"] != plan.chests:
        fail(f"{config_path}: `chests` does not match the shrine at {cfg['shrine']}.\n"
             f"  config: {cfg['chests']}\n  shrine: {plan.chests}\n"
             f"  (python3 tools/shrine.py --chests prints the list to paste)")


def check_spawn_is_forbidden(cfg, spawn, config_path):
    if not any(f["x"] == spawn["x"] and f["y"] == spawn["y"] and f["z"] == spawn["z"] for f in cfg.get("forbidden", [])):
        fail(f"{config_path}: `forbidden` must contain the world spawn point {spawn['x']} {spawn['y']} {spawn['z']} "
             f"(from level.dat); add it and run again")


def read_spawn_protection(mc_dir):
    """spawn-protection (int >= 0) from <mc_dir>/server.properties; a missing file, key or non-integer value is a loud error."""
    path = Path(mc_dir) / "server.properties"
    try:
        lines = path.read_text().splitlines()
    except OSError as e:
        fail(f"cannot read {path}: {e}. The spawn-protection setting must be checked before building")
    vals = [ln.split("=", 1)[1].strip() for ln in lines if ln.split("=", 1)[0].strip() == "spawn-protection" and "=" in ln]
    if not vals:
        fail(f"{path} has no `spawn-protection` key; set `spawn-protection=0` there (and restart via mc.sh)")
    try:
        r = int(vals[-1])
        if r < 0:
            raise ValueError
    except ValueError:
        fail(f"{path}: spawn-protection={vals[-1]!r} is not a non-negative integer")
    return r


def spawn_protected(cells, spawn, radius):
    """Cells inside the protected square. Assumed rule (vanilla/Paper isUnderSpawnProtection, not verifiable offline here):
    protected when radius > 0 and max(|x - spawnX|, |z - spawnZ|) <= radius, i.e. a square of side 2r+1 in x and z, any y."""
    if radius <= 0:
        return []
    return sorted(c for c in cells if max(abs(c[0] - spawn["x"]), abs(c[2] - spawn["z"])) <= radius)


def check_spawn_protection(mc_dir, plan, spawn):
    """Refuse (before anything is built) when non-ops could not use the shrine because of spawn-protection: they cannot
    interact with blocks near world spawn, which stopped the child opening the Magic Chest.
    The spawn sign always stands within 2 cells of spawn (shrine.spawn_sign_candidates), so it counts as affected at r >= 1."""
    radius = read_spawn_protection(mc_dir)
    hit = spawn_protected(plan.all_cells() | {(c["x"], c["y"], c["z"]) for c in plan.chests}, spawn, radius)
    sign_hit = radius >= 1
    if not hit and not sign_hit:
        return radius
    lines = [f"{len(hit)} shrine/chest cells, e.g. " + ", ".join("%d %d %d" % c for c in hit[:6])] if hit else []
    if sign_hit:
        lines.append(f"the spawn sign (stands within 2 cells of spawn {spawn['x']} {spawn['y']} {spawn['z']})")
    fail(f"server.properties spawn-protection={radius} (square of side {2 * radius + 1} centred on world spawn, x and z). "
         f"Non-op players (the child) cannot open chests or use blocks inside it. Affected: " + "; ".join(lines) +
         f"\n  Fix: set `spawn-protection=0` in {Path(mc_dir) / 'server.properties'} and restart with ./mc.sh stop then ./mc.sh start; "
         f"then run again. Nothing was built.")


def main():
    ap = argparse.ArgumentParser(description="Install the Magic Chest shrine into a running Minecraft server")
    ap.add_argument("--mc-dir", required=True, help="server directory (contains mc.sh, world/level.dat, logs/latest.log)")
    ap.add_argument("--session", required=True, help="the server's screen session name (MC_SESSION)")
    ap.add_argument("--config", default=str(ROOT / "config" / "minecraft.json"))
    ap.add_argument("--blocks", default=str(shrine.BLOCKS_FILE))
    ap.add_argument("--survey-only", action="store_true", help="survey and report; place nothing")
    args = ap.parse_args()
    try:
        words = [w["word"] for w in json.loads((ROOT / "app/data/craft_words.json").read_text())["words"]]
        cfg = mcb.load_config(args.config, craft_words=words)
    except mcb.ConfigError as e:
        fail(f"invalid config {args.config}: {e}")
    if "shrine" not in cfg:
        fail(f"{args.config} has no `shrine` (the cell of chest 1)")
    try:
        spec = shrine.load_spec(args.blocks)
        family = server.load_family_config()
        plan = shrine.Plan(spec, cfg["shrine"], family["village_name"])
        spawn = shrine.read_spawn(args.mc_dir)
    except (shrine.ShrineError, server.FamilyConfigError) as e:
        fail(str(e))
    check_config_matches_shrine(cfg, plan, args.config)
    check_spawn_is_forbidden(cfg, spawn, args.config)
    check_spawn_protection(args.mc_dir, plan, spawn)
    transport = mcb.ScreenTransport(args.mc_dir, args.session)
    bridge = mcb.Bridge(transport, cfg["chests"], log=lambda m: print(f"  {m}"), forbidden=cfg["forbidden"])
    pos = cfg["chests"][0]
    where = f"{pos['x']} {pos['y']} {pos['z']}"
    say = lambda m: print(f"  {m}", flush=True)  # noqa: E731
    try:
        if not transport.server_running():
            fail(f"Minecraft is not running in {args.mc_dir} (screen session {args.session}); start it first")
        print(f"Shrine at {where} (spawn point {spawn['x']} {spawn['y']} {spawn['z']}, forbidden) in {args.mc_dir}, "
              f"session {args.session}")
        for x, z in chunk_probe_cells(plan.all_cells() | {(spawn["x"], 0, spawn["z"])}):
            bridge.ensure_forceload({"x": x, "z": z})
        say("chunks forceloaded")
        had_marker = shrine.marker_exists(bridge, plan)
        say(f"shrine marker: {'found (re-run: repairing only what is missing)' if had_marker else 'not found (fresh build)'}")
        sv = shrine.survey(bridge, plan, had_marker, log=say, forbidden=cfg["forbidden"])
        say(f"survey: {len(sv.modes)} cells + {len(sv.foundation)} foundation cells checked with {sv.commands} commands; "
            f"{len(sv.blocked)} blocked")
        if sv.blocked:
            fail(shrine.format_blocked(sv.blocked, sv.stopped_early))
        found = shrine.find_spawn_sign(bridge, spawn, plan.all_cells() | set(sv.foundation), cfg["forbidden"],
                                        first_line=plan.sign["lines"][0])
        say(f"spawn sign: {found[0]} at {found[1][0]} {found[1][1]} {found[1][2]}")
        state = bridge.chest_state(pos)
        if state == "other":
            fail(f"{where} is occupied by something that is not a Magic Chest; refusing to replace it")
        if args.survey_only:
            print("\nOK (survey only): nothing was placed")
            return
        counts = shrine.build(bridge, plan, sv, log=say)
        say(f"shrine: {counts['placed']} blocks placed, {counts['kept']} already there, {counts['foundation']} foundation, "
            f"{counts['sign']} sign")
        if state == "air":
            if not bridge.place_chest(pos, 1):
                fail(f"{where} is not usable for Magic Chest 1 after the build (air with solid ground below required)")
            say("chest 1: placed")
        else:
            say("chest 1: already a Magic Chest, left as is")
        say(f"label: {'created' if bridge.ensure_label(pos, 1) else 'already there'}")
        say(f"spawn sign: {shrine.place_spawn_sign(bridge, found, plan.sign['lines'])}")
        say(f"beacon: active, Levels={shrine.beacon_levels(bridge, plan)}")
        snap = bridge.snapshot(pos)
        say(f"chest 1 holds {snap['slots']} of {mcb.CHEST_SLOTS} slots")
    except (mcb.McError, shrine.ShrineError) as e:
        fail(str(e))
    print("\nOK: Magic Chest shrine installed")


if __name__ == "__main__":
    main()
