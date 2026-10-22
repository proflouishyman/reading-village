# Java right-click path (consume_item advancement reward), run as the player.
advancement revoke @s only reading_village_necklace:use
execute unless dimension minecraft:overworld run return run title @s actionbar {"text":"The necklace only works in the Overworld","color":"red"}
execute if score @s cn_cd matches 1.. run return run title @s actionbar {"text":"The necklace is recharging...","color":"gray"}
execute at @s run function reading_village_necklace:go
