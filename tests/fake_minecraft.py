"""An in-memory stand-in for a Paper 26.3 console, for tests. It answers only the commands minecraft_bridge sends,
using the reply texts captured from the real server (see the log fixtures in test_minecraft.py).

It implements the same interface as minecraft_bridge.ScreenTransport (skip_to_end, new_lines, send, server_running).
"""
import re

import minecraft_bridge as mcb

STACK = 64


class FakeMinecraft:
    def __init__(self, running=True):
        self.running = running
        self.log = []  # every "System chat" text the fake has printed
        self._ptr = 0
        self.sent = []  # every command received, in order
        self.chests = {}  # (x, y, z) -> {"name": str, "slots": [ {id,count,components(str)} ]}
        self.blocks = {}  # (x, y, z) -> block name, for non-chest blocks
        self.unsolid = set()  # (x, y, z) positions that are NOT solid ground (default: all solid)
        self.unloaded = False  # when True every position answers "That position is not loaded"
        self.drop_less = 0  # when > 0, loot insert silently inserts this many fewer items (simulates a liar)
        self.skip_ensure = False
        self.late_loot_replies = 0  # the next N loot inserts LAND but their "Dropped" reply reaches the log only on the next command
        self.swallow_loot_replies = 0  # the next N loot inserts LAND but their "Dropped" reply is never printed at all
        self.lose_loot_commands = 0  # the next N loot inserts are never executed (no reply either)
        self._late = []

    # -- transport interface
    def server_running(self):
        return self.running

    def skip_to_end(self):
        self._ptr = len(self.log)

    def new_lines(self):
        out = [f"[12:00:00] [Server thread/INFO]: System chat: {t}" for t in self.log[self._ptr:]]
        self._ptr = len(self.log)
        return out

    def log_mark(self):
        return [1, len(self.log)]

    def chat_since(self, mark):
        return list(self.log[mark[1]:])

    def send(self, cmd):
        self.sent.append(cmd)
        if not self.running:
            raise mcb.McError("could not send: no screen session")
        self.log.extend(self._late)  # a reply that was late now reaches the log
        self._late = []
        if self.lose_loot_commands and cmd.startswith("loot insert"):
            self.lose_loot_commands -= 1
            return
        before = len(self.log)
        self._handle(cmd)
        if self.swallow_loot_replies and cmd.startswith("loot insert"):
            self.swallow_loot_replies -= 1
            del self.log[before:]
        elif self.late_loot_replies and cmd.startswith("loot insert"):
            self.late_loot_replies -= 1
            self._late = self.log[before:]
            del self.log[before:]

    # -- helpers
    def say(self, text):
        self.log.append(text)

    @staticmethod
    def _xyz(cmd):
        m = re.search(r"(-?\d+) (-?\d+) (-?\d+)", cmd)
        return tuple(int(g) for g in m.groups())

    def full_chest(self, pos, name="Magic Chest"):
        """Place a chest that is completely full."""
        self.chests[pos] = {"name": name, "slots": [{"id": "minecraft:cobblestone", "count": STACK, "components": ""}
                                                    for _ in range(mcb.CHEST_SLOTS)]}

    def _handle(self, cmd):
        if self.unloaded and not cmd.startswith(("forceload", "particle", "playsound")):
            self.say("That position is not loaded")
            return
        if cmd.startswith("forceload add"):
            self.say("Marked chunk 0, 0 to be force loaded")
        elif cmd.startswith(("particle", "playsound")):
            pass
        elif cmd.startswith("execute if block") and cmd.endswith("minecraft:chest"):
            self.say("Test passed" if self._xyz(cmd) in self.chests else "Test failed")
        elif cmd.startswith("execute if block") and cmd.endswith("#minecraft:replaceable"):
            pos = self._xyz(cmd)  # free = nothing there, or a loose plant (blocks[pos] == "minecraft:short_grass")
            free = pos not in self.chests and self.blocks.get(pos, "minecraft:air") in ("minecraft:air", "minecraft:short_grass")
            self.say("Test passed" if free else "Test failed")
        elif cmd.startswith("execute if block") and cmd.endswith(("minecraft:water", "minecraft:lava")):
            self.say("Test passed" if self.blocks.get(self._xyz(cmd)) == cmd.split()[-1] else "Test failed")
        elif cmd.startswith("execute unless block") and "#minecraft:replaceable" in cmd:
            self.say("Test failed" if self._xyz(cmd) in self.unsolid else "Test passed")
        elif cmd.startswith("execute if entity"):
            self.say("Test passed" if getattr(self, "label_exists", False) else "Test failed")
        elif cmd.startswith("summon"):
            self.label_exists = True
            self.say("Summoned new Magic Chest")
        elif cmd.startswith("setblock"):
            self._setblock(cmd)
        elif cmd.startswith("data get block") and cmd.endswith("CustomName"):
            pos = self._xyz(cmd)
            if pos in self.chests:
                self.say(f'{pos[0]}, {pos[1]}, {pos[2]} has the following block data: '
                         f'{{bold: 1b, color: "gold", text: "{self.chests[pos]["name"]}"}}')
            else:
                self.say("Found no elements matching CustomName")
        elif cmd.startswith("data get block") and cmd.endswith("Items"):
            pos = self._xyz(cmd)
            if pos not in self.chests:
                self.say("The target block is not a block entity")
            else:
                items = []
                for i, s in enumerate(self.chests[pos]["slots"]):
                    comp = f", components: {s['components']}" if s["components"] else ""
                    items.append(f'{{Slot: {i}b, id: "{s["id"]}", count: {s["count"]}{comp}}}')
                self.say(f"{pos[0]}, {pos[1]}, {pos[2]} has the following block data: [{', '.join(items)}]")
        elif cmd.startswith("loot insert"):
            self._loot(cmd)
        else:
            raise AssertionError(f"FakeMinecraft got an unexpected command: {cmd}")

    def _setblock(self, cmd):
        pos = self._xyz(cmd)
        occupied = pos in self.chests or pos in self.blocks
        if "keep" in cmd.split("}")[-1] and occupied:  # keep = only into air; short grass counts as occupied here
            self.say("Could not set the block")
            return
        if "minecraft:chest" in cmd:
            name = re.search(r'text:"([^"]*)"', cmd).group(1)
            self.chests[pos] = {"name": name, "slots": []}
        else:
            self.blocks[pos] = cmd.split()[4]
        self.say(f"Changed the block at {pos[0]}, {pos[1]}, {pos[2]}")

    def _loot(self, cmd):
        pos = self._xyz(cmd)
        if pos not in self.chests:
            self.say(f"The target block at {pos[0]}, {pos[1]}, {pos[2]} is not a container")
            return
        item = re.search(r'name:"([^"]+)"', cmd).group(1)
        count = int(re.search(r"count:(\d+)\}", cmd).group(1))
        comps = ""
        parts = []
        for key in ("enchantments", "stored_enchantments"):
            m = re.search(r'"minecraft:%s":\{([^}]*)\}' % key, cmd)
            if m:
                pairs = re.findall(r'"(minecraft:\w+)":(\d+)', m.group(1))
                parts.append(f'"minecraft:{key}": {{' + ", ".join(f'"{n}": {v}' for n, v in pairs) + "}")
        m = re.search(r'"minecraft:profile":"(\w+)"', cmd)
        if m:
            parts.append(f'"minecraft:profile": {{name: "{m.group(1)}"}}')
        m = re.search(r'"minecraft:potion_contents":\{potion:"([^"]+)"\}', cmd)
        if m:
            parts.append(f'"minecraft:potion_contents": {{potion: "{m.group(1)}"}}')
        if parts:
            comps = "{" + ", ".join(parts) + "}"
        size = 1 if item in mcb.UNSTACKABLE or comps else STACK
        slots = self.chests[pos]["slots"]
        todo, placed, stacks = count - self.drop_less, 0, 0
        for s in slots:  # top up partial stacks of the same item first
            if todo and s["id"] == item and s["components"] == comps and s["count"] < size:
                n = min(todo, size - s["count"])
                s["count"] += n
                todo -= n
                placed += n
                stacks += 1
        while todo and len(slots) < mcb.CHEST_SLOTS:
            n = min(todo, size)
            slots.append({"id": item, "count": n, "components": comps})
            todo -= n
            placed += n
            stacks += 1
        placed += 0
        shown = placed + self.drop_less if self.drop_less and not todo else placed
        name = item.split(":")[1].replace("_", " ").title()
        if shown == 0:
            self.say("Dropped 0 items")
        elif stacks <= 1:
            self.say(f"Dropped {shown} [{name}]")
        else:
            self.say(f"Dropped {shown} items")
