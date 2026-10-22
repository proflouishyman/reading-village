# Runs every tick. Cooldown countdown, then per-player necklace logic.
scoreboard players remove @a[scores={cn_cd=1..}] cn_cd 1
execute as @a at @s run function reading_village_necklace:player
