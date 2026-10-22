# Per-player, at @s. Invariant: cn_sneak only counts consecutive qualifying ticks.
# Right-click leaves a remainder copy without use_remainder; restore the full item so it is never lost.
execute if items entity @s weapon.mainhand *[custom_data~{reading_village_necklace:1b},!use_remainder] run loot replace entity @s weapon.mainhand loot reading_village_necklace:necklace
execute if items entity @s weapon.offhand *[custom_data~{reading_village_necklace:1b},!use_remainder] run loot replace entity @s weapon.offhand loot reading_village_necklace:necklace
execute unless items entity @s weapon *[custom_data~{reading_village_necklace:1b}] run return run scoreboard players set @s cn_sneak 0
execute unless predicate reading_village_necklace:sneaking run return run scoreboard players set @s cn_sneak 0
execute unless dimension minecraft:overworld run return run title @s actionbar {"text":"The necklace only works in the Overworld","color":"red"}
execute if score @s cn_cd matches 1.. run return run scoreboard players set @s cn_sneak 0
scoreboard players add @s cn_sneak 1
particle minecraft:enchant ~ ~1 ~ 0.3 0.6 0.3 0.8 4
execute if score @s cn_sneak matches 20.. run function reading_village_necklace:go
