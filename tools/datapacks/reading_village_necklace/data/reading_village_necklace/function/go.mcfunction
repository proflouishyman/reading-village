# Teleport @s (running at @s) to the shrine entrance with effects at both ends, then start cooldown.
particle minecraft:portal ~ ~1 ~ 0.4 0.8 0.4 0.5 60
particle minecraft:enchant ~ ~1 ~ 0.5 0.8 0.5 0.5 40
playsound minecraft:entity.enderman.teleport player @a ~ ~ ~ 1 1
playsound minecraft:block.amethyst_block.chime player @a ~ ~ ~ 1 1.2
# EXAMPLE destination: set this to your shrine entrance (config/minecraft.json shrine; arrival point).
tp @s 100 68 104 180 0
execute at @s run particle minecraft:portal ~ ~1 ~ 0.4 0.8 0.4 0.5 60
execute at @s run particle minecraft:enchant ~ ~1 ~ 0.5 0.8 0.5 0.5 40
execute at @s run playsound minecraft:entity.enderman.teleport player @a ~ ~ ~ 1 1
execute at @s run playsound minecraft:block.amethyst_block.chime player @a ~ ~ ~ 1 1.2
scoreboard players set @s cn_cd 100
scoreboard players set @s cn_sneak 0
