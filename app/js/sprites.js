// Original pixel sprites as char grids. '.' is transparent; every other char is a PALETTE key.
// All art here is original (no Mojang assets). Rows of one sprite must all have the same width
// (checked by tests/js/sprites.test.mjs).
// In the optional local "real" art mode (docs/textures.md) a MAPPED sprite is drawn from the real texture instead, by
// spriteImage(); the hand-drawn grid still defines the logical size (spriteSize) so layouts never move.
import { getTexture, getTextures } from "./mctextures.js";

export const PALETTE = {
  k: "#1b1b1b", w: "#f4f4f4", g: "#9a9a9a", G: "#5c5c5c",
  s: "#f1c27d", S: "#c68e55", h: "#5a3a1e", H: "#2b1d12",
  b: "#3a6fd8", B: "#2646a0", c: "#3fd0d0", C: "#1d8f9a",
  r: "#d8403a", R: "#8f2420", y: "#f5d33a", Y: "#c99a14",
  o: "#f08a24", O: "#b8631a", p: "#f5a3b8", P: "#d97a95",
  n: "#8b5a2b", N: "#5f3b1a", t: "#c89a5a", T: "#9a6b33",
  e: "#2fd06b", E: "#17803d", l: "#6fcf5c", L: "#3f9a38",
  m: "#6b4a8c", M: "#3a2a52", f: "#ffb02e", a: "#2a2a2a",
  i: "#d9b79a", z: "#8a8a8a", Z: "#6e6e6e", u: "#5fb04a", U: "#3f8a33",
  q: "#3d8be0", Q: "#2c6cb5",
  j: "#a67c52", F: "#f6d3b8", W: "#cfd4dc", x: "#c9c2ae", d: "#b9bbc0", v: "#1f2a5c",
  // sand block: pale yellow, lighter and yellower than dirt
  A: "#ecdc9c", V: "#cdb674", I: "#f8efc4",
};

// Shared 12x12 ore template: 'o'/'O' are the ore colours, swapped per ore below.
const ORE = [
  "zzzzzzzzzzzz", "zZzzzzzZzzzz", "zzzoozzzzZzz", "zzooOozzzzzz",
  "zzzoOzzzooZz", "zZzzzzzzoOoz", "zzzzzzzzzozz", "zzoozzzZzzzz",
  "zooOozzzzzzz", "zzzoozzzoozz", "zZzzzzzzoOoz", "zzzzZzzzzzzz",
];

export const SPRITES = {
  // Hero (10x16): dark-blond bowl cut with straight bangs over the ears, brown eyes, orange polo with three
  // white buttons, tan canteen bag on a diagonal brown strap (his signature item), grey shorts, navy belt/sneakers.
  hero: { rows: [
    "..jjjjjj..", ".jjjjjjjj.", "jjjjjjjjjj", "jjFFFFFFjj", "jjFNFFNFjj", ".jFFSSFFj.",
    "..FFFFFF..", "ooNoowoooo", "oooNowoooo", "FoooNwoooF", "FoooNTTTTF", ".vvvvtttt.",
    ".ddddTttT.", "..FFF.FFF.", "..vvv.vvv.", "..www.www.",
  ] },
  // Dad (10x18, taller): bald with grey stubble at the sides, clear light-grey glasses, big toothy smile,
  // clean-shaven, light pink button-up, grey trousers, dark shoes.
  dad: { rows: [
    "...FFFF...", "..FFFFFF..", ".xFFFFFFx.", ".xFFFFFFx.", ".WWWFFWWW.", ".WkFFFFkW.",
    ".WWWFFWWW.", ".FFwwwwFF.", "..FFFFFF..", "ppppFFpppp", "ppppPppppp", "ppppPppppp",
    "ppppPppppp", "FpppPppppF", ".zzzzzzzz.", "..zzz.zzz.", "..zzz.zzz.", "..aaa.aaa.",
  ] },
  // Mama (10x17): long straight medium-brown hair parted in the middle and falling past the shoulders, brown eyes,
  // fair skin, soft closed-mouth smile, soft grey sweater (darker grey hem), navy trousers, dark shoes.
  mama: { rows: [
    "..nnnnnn..", ".nnnNNnnn.", "nnnNFFNnnn", "nnFFFFFFnn", "nnFNFFNFnn", "nnFFSSFFnn",
    "nnnFFFFnnn", "nnddddddnn", "nnddddddnn", "dnddddddnd", "dddddgdddd", "FddddddddF",
    ".gggggggg.", ".vvvvvvvv.", "..vvv.vvv.", "..vvv.vvv.", "..aaa.aaa.",
  ] },
  // lighthouse (10x16): red and white tower, yellow lamp under a red cap, dark door, grey rock base.
  lighthouse: { rows: [
    "....yy....", "...yYYy...", "..RRRRRR..", "...wwww...", "...rrrr...", "...wwww...",
    "...rrrr...", "..wwwwww..", "..rrrrrr..", "..wwwwww..", "..rrrrrr..", ".wwwwwwww.",
    ".wwwkkwww.", ".wwwkkwww.", "GGGGGGGGGG", "GzGGzGGzGG",
  ] },
  // red crab (12x6): two raised claws, eyes on stalks, six legs.
  crab: { rows: [
    "rr........rr", "r..r....r..r", "..rwrrrrwr..", "..rkrrrrkr..", ".rrrrrrrrrr.", "R.R.R..R.R.R",
  ] },
  // --- Story-writer vocabulary: forest, pirates, witches (see docs/design.md "Forest, pirate and witch sprites") ---
  // pirate (10x17): silly friendly pirate: red polka-dot bandana, eye patch, big dark beard and smile, navy/white
  // striped shirt, gold belt buckle, brown trousers, black boots.
  pirate: { rows: [
    "..rrrrrr..", ".rrwrrwrr.", "rrrrrrrrrr", ".FFFFFFFF.", ".kkkFFkFF.", ".FFFFFFFF.",
    "HHFFRRFFHH", ".HHHHHHHH.", "..HHHHHH..", "vvvvvvvvvv", "wwwwwwwwww", "vvvvvvvvvv",
    "FwwwwwwwwF", "kkkkYYkkkk", ".nnnnnnnn.", "..nnn.nnn.", "..kkk.kkk.",
  ] },
  // witch (10x18): the kind neighbour witch: purple pointed hat with a gold band, ginger hair, ordinary skin,
  // big smile with teeth, green dress with a darker collar and hem, black shoes. Not green-skinned, no big nose.
  witch: { rows: [
    "....mm....", "...mmmm...", "...mmmm...", "..mmmmmm..", "..MMyyMM..", "mmmmmmmmmm",
    ".oFFFFFFo.", "oFFkFFkFFo", "oFFFFFFFFo", "oFFRwwRFFo", "o..FFFF..o", ".eeEEEEee.",
    "eeeeeeeeee", "FeeeeeeeeF", "eeeeeeeeee", "eeeeeeeeee", "EEEEEEEEEE", ".kk....kk.",
  ] },
  // owl (10x11): brown owl with big white eyes, tufted ears, tan chest, yellow feet. Sits on things (y "on").
  owl: { rows: [
    "nn......nn", "nnnnnnnnnn", "nwwwnnwwwn", "nwkwyywkwn", "nnnnooonnn", "ntnttttntn",
    "nttTtttTtn", "nntTtTttnn", ".nttttttn.", "..nnnnnn..", "..yy..yy..",
  ] },
  // mushroom (10x9): red cap with white dots, white stem.
  mushroom: { rows: [
    "...rrrr...", ".rrwrrrrr.", "rrrrrrwrrr", "rwrrrrrrrr", "RRRRRRRRRR", "...wwww...",
    "...wxxw...", "...wwww...", "..wwwwww..",
  ] },
  // berry_bush (14x9): round green bush with red berries.
  berry_bush: { rows: [
    "....LLLLLL....", "..LLllllllLL..", ".LllrlllllrllL", "LllllllrlllllL", "LlrlllllllrllL",
    "LllllrllllllLL", "LLllllllllrlLL", ".LLLllllllLLL.", "...LLLLLLLL...",
  ] },
  // deer (18x14): brown deer facing right, tan antlers, lighter belly, white tail.
  deer: { rows: [
    "..............T.T.", "..............TTT.", "............nnnnn.", "...........nnnknnN",
    "...........nnnnnnN", "..........nnnnn...", "..nnnnnnnnnnnn....", ".nnnnnnnnnnnnn....",
    "wnnnnnnnnnnnnn....", ".nnntnnnnntnnn....", "..tttttttttt......", "..nn..nn..nn.nn...",
    "..nn..nn..nn.nn...", "..NN..NN..NN.NN...",
  ] },
  // bunny (10x10): brown rabbit facing right, long ears, pink nose, pale tail and belly.
  bunny: { rows: [
    "......j.j.", "......j.j.", "......jjj.", ".....jjkjj", ".....jjjjp", "..jjjjjjj.",
    ".jjjjjjjjj", "iijjjjjjj.", ".jjiiijjj.", ".jj..jj.jj",
  ] },
  // tent (16x11): orange camping tent, shaded right side, dark doorway.
  tent: { rows: [
    ".......oO.......", "......ooOO......", ".....oooOOO.....", "....ooooOOOO....",
    "...oooooOOOOO...", "..ooooooOOOOOO..", ".oooooooOOOOOOO.", "oooooookkkkOOOOO",
    "oooooookkkkOOOOO", "oooooookkkkOOOOO", "oooooookkkkOOOOO",
  ] },
  // campfire (12x9): crossed logs, red/orange/yellow flames, a ring of stones.
  campfire: { rows: [
    ".....r......", "....rff..r..", "...rffyf.rf.", "...rfyyfrf..", "....fyyff...",
    "....fyyf....", "NN.NNNNNN.NN", ".NNtNNNNtNN.", "zzGzzzGzzzGz",
  ] },
  // pine (10x16): dark-green spruce in three tiers on a brown trunk.
  pine: { rows: [
    "....uu....", "...uuuu...", "..uuuuuu..", ".UuuuuuuU.", "...uuuu...", "..uuuuuu..",
    ".uuuUuuuu.", "uuuuuuuuuu", "..uuuuuu..", ".uuuuuuuu.", "uuuUuuuuuu", "UUUUUUUUUU",
    "....tT....", "....tT....", "....tT....", "....tT....",
  ] },
  // pirate_hat (14x6): black pirate hat with a friendly smiley face and a gold band. Worn: y "head".
  pirate_hat: { rows: [
    "....kkkkkk....", "..kkkwkkwkkk..", ".kkkwkkkkwkkk.", "kkkkkwwwwkkkkk",
    "YYYYYYYYYYYYYY", ".kkkkkkkkkkkk.",
  ] },
  // pirate_flag (12x12): black flag with a white smile on a pole (a friendly Jolly Roger, no skull).
  pirate_flag: { rows: [
    "Y...........", "Nkkkkkkkkkk.", "Nkkkwkkwkkk.", "Nkkkkkkkkkk.", "Nkkwkkkkwkk.", "Nkkkwwwwkkk.",
    "Nkkkkkkkkkk.", "N...........", "N...........", "N...........", "N...........", "N...........",
  ] },
  // flag (12x12): a red flag with a white stripe and a wavy edge on a pole (the FLAG craft word; hand-drawn on purpose).
  flag: { rows: [
    "Y...........", "NrrrrrR.....", "NrrrrrrrrR..", "NwwwwwwwwwwR", "NrrrrrrrrrR.", "NrrrrrrR....",
    "N...........", "N...........", "N...........", "N...........", "N...........", "N...........",
  ] },
  // polly (8x12), a parrot: red head, yellow beak, green body, blue tail, yellow feet.
  polly: { rows: [
    "..rrr...", ".rrwkyy.", ".rrrryy.", "..rrrr..", ".llllll.", "lllLLlll",
    "lLlllLll", "lllllll.", ".llllll.", "..bbbb..", "..bccb..", "..y..y..",
  ] },
  // spyglass (12x5): brass telescope in three segments, cyan lens at the right end. Held (TOOLS in scenes.js).
  spyglass: { rows: [
    ".......YYYYc", "...TTTTYYYYc", "NNNTTTTYYYYc", "...TTTTYYYYc", ".......YYYYc",
  ] },
  // plank (16x4): a wooden plank (walk the plank).
  plank: { rows: [
    "NNNNNNNNNNNNNNNN", "tttttTtttttttTtt", "ttTtttttttTttttt", "TTTTTTTTTTTTTTTT",
  ] },
  // witch_hat (12x8): purple pointed hat with a bent tip and a gold band. Worn: y "head".
  witch_hat: { rows: [
    ".......mm...", "......mmm...", ".....mmmm...", "....mmmmmm..", "....mmmmmm..", "....MMyyMM..",
    "mmmmmmmmmmmm", ".MMMMMMMMMM.",
  ] },
  // broom (16x6): thin wooden handle on the left with a gold binding, straw bristles on the right. Held upright
  // (TOOLS in scenes.js) or sat on (pose sit_on).
  broom: { rows: [
    "............tTTT", "...........tTtTT", "TTTTTTTTTTYtTtTT", "NNNNNNNNNNYtTtTT", "...........tTtTT", "............tTTT",
  ] },
  // flask (8x10), a potion bottle: glass flask of purple potion with a cork.
  flask: { rows: [
    "...tt...", "...ww...", "...ww...", "..wmmw..", ".wmmmMw.", "wmmpmmmw",
    "wmmmmMmw", "wmMmmmmw", ".wmmmmw.", "..wwww..",
  ] },
  // black_cat (10x9): black cat sitting, front view, yellow eyes, pink nose, tail up.
  black_cat: { rows: [
    "..a....a..", "..aa..aa..", "..aaaaaa..", "..ayaaya..", "..aaPPaa..", "...aaaa..a",
    "..aaGaaa.a", "..aaaaaaaa", "..aa..aa..",
  ] },
  pig: { rows: [
    ".pppppppp.....", "pppppppppppp..", "ppppppppppkpp.", "pppppppppppppp", "ppppppppppPPPP",
    "pppppppppppPkP", ".pppppppppppp.", ".PP..PP..PP.PP", ".PP..PP..PP.PP",
  ] },
  creeper: { rows: [
    ".llllllll.", ".lLllllLl.", ".lkkllkkl.", ".lkkllkkl.", ".lllkklll.", ".llkkkkll.",
    ".llkkkkll.", ".lLllllLl.", "..llllll..", "..lLllLl..", "..llllll..", "..llllll..",
    ".llll.llll", ".llll.llll", ".LLLL.LLLL",
  ] },
  bat: { rows: [
    "m..........m", "mm..m..m..mm", "mmm.mmmm.mmm", "mmmmmymmymmm",
    ".mmmmmmmmmm.", "..mm..mm..mm", "...m..m..m..",
  ] },
  chest: { rows: [
    "NNNNNNNNNNNN", "NttttttttttN", "NttttttttttN", "NNNNNNNNNNNN", "NtttyyyytttN",
    "NtttykkytttN", "NtttyyyytttN", "NttttttttttN", "NTTTTTTTTTTN", "NNNNNNNNNNNN",
  ] },
  torch: { rows: [
    ".ff.", "fyyf", ".yf.", ".tT.", ".tT.", ".tT.", ".tT.", ".tT.", ".TT.", ".NN.",
  ] },
  coal: { rows: ORE, swap: { o: "a", O: "k" } },
  iron: { rows: ORE, swap: { o: "i", O: "n" } },
  gold: { rows: ORE, swap: { o: "y", O: "Y" } },
  diamond: { rows: ORE, swap: { o: "c", O: "C" } },
  emerald: { rows: ORE, swap: { o: "e", O: "E" } },
  wood: { rows: [
    "NNNNNNNNNNNN", "NttttttttttN", "NttTtttttttN", "NNNNNNNNNNNN", "NtttttttTttN", "NttttttttttN",
    "NNNNNNNNNNNN", "NtTtttttttNN", "NttttttttttN", "NNNNNNNNNNNN", "NttttTttttNN", "NNNNNNNNNNNN",
  ] },
  stone: { rows: [
    "zzzzzzzzzzzz", "zZzzzzzgzzzz", "zzzzZzzzzZzz", "zzgzzzzzzzzz", "zzzzzzZzzzgz", "zZzzgzzzzzzz",
    "zzzzzzzzZzzz", "zzZzzzzzzzzz", "zzzzzgzzzzZz", "zgzzzzZzzzzz", "zzzzzzzzzgzz", "ZZZZZZZZZZZZ",
  ] },
  dirt: { rows: [
    "nnnnnnnnnnnn", "nNnnnnnnNnnn", "nnnnNnnnnnnn", "nnnnnnnNnnNn", "nNnnnnnnnnnn", "nnnnnNnnnnnn",
    "nnnNnnnnnNnn", "nnnnnnnnnnnn", "nNnnnnNnnnnn", "nnnnnnnnnnNn", "nnNnnnnnnnnn", "NNNNNNNNNNNN",
  ] },
  door: { rows: [
    "NNNNNNNNNNNN", "NttttttttttN", "NttttttttttN", "NttttttttttN", "NttttttttttN", "NttttttttttN",
    "NttttttttyyN", "NttttttttttN", "NttttttttttN", "NttttttttttN", "NttttttttttN", "NNNNNNNNNNNN",
  ] },
  bed: { rows: [
    "NN..............", "NN..............", "NNwwrrrrrrrrrNN.", "NNwwrrrrrrrrrNN.", "NNwwRRRRRRRRRNN.",
    "NNNNNNNNNNNNNNN.", "NN...........NN.", "NN...........NN.",
  ] },
  pup: { rows: [
    "......TT..", "t....tttt.", ".tttttktkk", ".ttttttttt", ".ttttttttt", ".tttttttt.", ".t.t..t.t.", ".T.T..T.T.",
  ] },
  hen: { rows: [
    "............rr..", "...........rrrr.", "..w........wkwwy", "..ww.......wwwwr",
    "...wwwwwwwwwwww.", ".wwwgggwwwwwwww.", ".wwwwgggggwwwww.", "..wwwwgggggwwww.",
    "...wwwwwwwwwww..", "....wwwwwwwww...", "......y..y......", ".....yyy.yyy....",
  ] },
  fox: { rows: [
    "..www..........o..o.",
    ".wwwww.........ooooo",
    ".wwwooo........ookoo",
    ".wooooo.......oooook",
    "woooooo.......owwwww",
    "woooooooOoooooowwwww",
    "woooooooOoooooowwww.",
    "woooooooOooooooowww.",
    ".ooooooOoooooooww...",
    "..OOOOO..kk.kk......",
    ".........kk.kk......",
    ".........kk.kk......",
  ] },
  duck: { rows: [
    "..........yyyy....",
    ".........yyyyyy...",
    ".........yykyooooo",
    ".........yyyyOOOO.",
    "..y......yyyy.....",
    ".yyyyyyyyyyyyyy...",
    ".yyyYYYYYyyyyyy...",
    "..yyYYYYYYyyyy....",
    "..yyyyyyyyyyyy....",
    "...yyyyyyyyyy.....",
    ".......o..o.......",
    "......ooo.ooo.....",
  ] },
  fish: { rows: [
    "...........UU.....", "..U.......UUUU....", "..UU...uuuuuuuuu..", "..UUUuuuuuuuwwuuu.",
    "...UUuuuuuuukwuuuu", "...UUuuuuuuuuuuuk.", "..UUUlllllllllllu.", "..UU..llllllll....",
    "..U....UUU........",
  ] },
  stink: { rows: [
    "..u...u", "...u...", "..u...u", ".u...u.", "..u.u..", ".u...u.", "..u.u..",
  ] },
  // small wooden rowing boat with a white sail; open hull, raised bow and stern, seat plank (18x8, same size as before so the 'boat' scenes keep their layout).
  // small wooden rowing boat with a white sail; open hull, raised bow and stern, seat plank (18x8, same size as before so the 'boat' scenes keep their layout).
  boat: { rows: [
    "........Nrr.......",
    "........Nw........",
    "........NwwW......",
    "........NwwwwW....",
    "NN..TTTTTNTTTT..NN",
    "NNNNNNNNNNNNNNNNNN",
    ".tttttttttttttttt.",
    "..TTTTTTTTTTTTTT..",
  ] },
  tree: { rows: [
    "...UUUUUU...", "..UuuuUuuU..", ".UuuuuuuuuU.", ".uuUuuuuuuu.", ".uuuuuUuuuu.", "..uuuuuuuu..",
    "....uuuu....", ".....tT.....", ".....tT.....", ".....tT.....", ".....tT.....", ".....tT.....",
    ".....tT.....", ".....tT.....",
  ] },
  sun: { rows: [
    "...yyyy...", "..yyyyyy..", ".yyyyyyyy.", "yyyyyyyyyy", "yyyyyyyyyy",
    "yyyyyyyyyy", "yyyyyyyyyy", ".yyyyyyyy.", "..yyyyyy..", "...yyyy...",
  ] },
  moon: { rows: [
    "..wwww..", ".ww.....", "ww......", "ww......", "ww......", "ww......", ".ww.....", "..wwww..",
  ] },
  cloud: { rows: [
    "....wwww......", "..wwwwwwww.ww.", "wwwwwwwwwwwwww", ".wwwwwwwwwwww.",
  ] },
  pickaxe: { rows: [
    "..gggggg..", ".gGgggggG.", "gG...tG.gG", ".....tT...", "....tT....",
    "....tT....", "...tT.....", "...tT.....", "..tT......", "..tT......",
  ] },
  crown: { rows: [
    "y...yy...y", "yy.yyyy.yy", "yyyyyyyyyy", "yyrYyyYryy", "YYYYYYYYYY",
  ] },

  // --- Prop sprites (added for composable page art; see docs/design.md "Composable page art") ---
  // hat: Dad's RED cap, wide enough to sit on a head.
  hat: { rows: [
    "....rrrr....", "..rrrrrrrr..", ".rrPrrrrrrr.", "rrrrrrrrrrrr", "RRRRRRRRRRRR", ".RRRRRRRRRR.",
  ] },
  mud: { rows: [
    "....nnnn....", "..nnnnnnnn..", ".nnNnnnnnNn.", "nnnnnnNnnnnn", ".NNNNNNNNNN.",
  ] },
  hut: { rows: [
    "......NN......", "....NNNNNN....", "..NNNNNNNNNN..", ".NNNNNNNNNNNN.", "NNNNNNNNNNNNNN",
    ".tttttttttttt.", ".tTtttttttTtt.", ".tttthhhhtttt.", ".tttthhhhtttt.", ".tttthhyhtttt.",
    ".tttthhhhtttt.", "NNNNNNNNNNNNNN",
  ] },
  // jam bun: round golden-brown bun with a dark crust outline, sugar dusting and a red jam swirl on top (12x8).
  // jam bun: round golden-brown bun with a dark crust outline, sugar dusting and a red jam swirl on top (12x8).
  bun: { rows: [
    "....NNNN....",
    "..NNffffNN..",
    ".NffffffffoN",
    "NfwfrrrfffoN",
    "NfffrRrffooN",
    "NfffffrffooN",
    "NtffffffffoN",
    "NttttttttttN",
    ".NTTTTTTTTN.",
    "..NNNNNNNN..",
  ] },
  sock: { rows: [
    "rrrrrr......", "wwwwww......", "rrrrrr......", "wwwwww......", "rrrrrr......", "wwwwww......",
    "rrrrrr......", "wwwwwwww....", "rrrrrrrrrr..", "RwRwRwRwRwRw", ".RRRRRRRRRR.",
  ] },
  rod: { rows: [
    "............", "............", "...........N", "..........nG", ".........n.G", "........n..G",
    ".......n...G", "......n....G", ".....n.....G", "....n......G", "...n.....g.g", "..k.......gg",
    ".k..........", "k...........",
  ] },
  pot: { rows: [
    "...W....W...", "....W..W....", "..rrrrrrrr..", ".aaaaaaaaaa.", "aGGGGGGGGGGa", "kGgGGGGGGGGk",
    ".GgGGGGGGGG.", ".GGGGGGGGGG.", "..GGGGGGGG..", "..aa....aa..",
  ] },
  map: { rows: [
    "TTTTTTTTTTTT", "TxxxxxxxxxxT", "TxllxxxxxxxT", "TllllxrxxrxT", "TxllxxxrrxxT",
    "TxxxqxxrrxxT", "TxxqqqrxxrxT", "TxxxqxxxxxxT", "TTTTTTTTTTTT",
  ] },
  bow: { rows: [
    "....nn......", "...w.nn.....", "...w..nn....", "...w...n....", "...w...nn...", "...w....n...",
    "rrrwtttntttg", "...w....n...", "...w...nn...", "...w...n....", "...w..nn....", "...w.nn.....",
    "....nn......",
  ] },
  pan: { rows: [
    "..kkkkkkkk......", ".kGGGGGGGGk.....", "kGGwwwwGGGGkhhhh", "kGwwwyywGGGkhhhh",
    "kGGwwwwGGGGk....", ".kGGGGGGGGk.....", "..kkkkkkkk......",
  ] },
  nut: { rows: [
    "...hh...", ".NNNNNN.", "NNnNNnNN", "NNNNNNNN", ".tttttt.", ".ttTttt.", ".tttttt.",
    "..tttt..", "...tt...", "....T...",
  ] },
  // spider web: 8 radial spokes with a hub and three rings (13x13, same size as before).
  // spider web: 8 radial spokes with a hub and three rings (13x13, same size as before).
  web: { rows: [
    ".....wgw.....",
    "....w.g.w....",
    "..gw.wgw.wg..",
    "..wgw.g.wgw..",
    "..wwg.gwgw.w.",
    ".ww..gggw.w.w",
    "ggggggGgggggg",
    ".w.w.gggw.w..",
    "..w.gwgwgw...",
    "..wg..g..g...",
    "..gww.gww.g..",
    ".....wg......",
    "......g......",
  ] },
  raft: { rows: [
    "NNNNNNNNNNNNNNNN", "TtttYYtttttYYttt", "NNNNYYNNNNNYYNNN", "TtttYYtttttYYttt",
    "NNNNYYNNNNNYYNNN", "TtttYYtttttYYttt", "NNNNNNNNNNNNNNNN",
  ] },
  log: { rows: [
    ".NNNNNNNNNNNN.", "NtttttTttttNiN", "NttttttttttNiN", "NtTttttttttNiN", "NttttttttttNiN",
    ".NNNNNNNNNNNN.",
  ] },
  bell: { rows: [
    "....yy....", "...yyyy...", "..ywyyyy..", "..ywyyyy..", ".yywyyyyY.", ".yyyyyyyY.",
    "yyyyyyyyYY", "YYYYYYYYYY", "....oo....", "....oo....",
  ] },
  junk: { rows: [
    "....t....ee...", "....tt..eeee..", "..zzzt..eeee..", ".zZZZzt.ewee..", ".zZkZz.rrrrr..",
    ".zzzzz.rrRrrt.", "zzzzzzrrrRrrtt", "nnnnnnnnrrnnnn", ".GGnnnnnnnGGG.",
  ] },
  // --- Added by E1 (missing story sprites) ---
  // treasure chest with the lid propped open behind it, a heap of gold and a white glint inside (12x13).
  chest_open: { rows: [
    ".NNNNNNNNNN.",
    ".NTTTTTTTTN.",
    "NNTTTTTTTTNN",
    "NNNNNNNNNNNN",
    "NaayywyyaayN",
    "NayyywyyywyN",
    "NyyYyyyyYyyN",
    "NNNNNNNNNNNN",
    "NtttyyyytttN",
    "NtttykkytttN",
    "NtttyyyytttN",
    "NTTTTTTTTTTN",
    "NNNNNNNNNNNN",
  ] },
  // dark hole in the ground seen as a side cut: grass lips, dirt walls, black bottom; 14 pixels of opening so a person fits (20x10).
  pit: { rows: [
    "lllaaaaaaaaaaaaaalll",
    "nNnaaaaaaaaaaaaaanNn",
    "nnNaaaaaaaaaaaaaaNnn",
    "nnNaaaaaaaaaaaaaaNnn",
    "nNnaaaaaaaaaaaaaanNn",
    "nnNaaaaaaaaaaaaaaNnn",
    "nnNkkkkkkkkkkkkkkNnn",
    "nNnkkkkkkkkkkkkkkNnn",
    "nnNkkkkkkkkkkkkkkNnn",
    "NNNNNNNNNNNNNNNNNNNN",
  ] },
  // cloth sack: tan, tied at the neck with brown rope, floppy top, stitched patch (10x11).
  bag: { rows: [
    "..tt..tt..",
    "...tttt...",
    "...NNNN...",
    "..tttttt..",
    ".tttttttt.",
    "tttttiitTt",
    "ttttiiitTt",
    "ttttttttTT",
    "tttttttTTT",
    ".TTTTTTTT.",
    "..TTTTTT..",
  ] },
  // red rug: yellow border, dark-red diamond pattern, white fringe at the ends (16x7).
  rug: { rows: [
    "wyyyyyyyyyyyyyyw",
    ".yrrrrrrrrrrrry.",
    "wyrrRRrryyrrRRyw",
    ".yrRyyRrrRyyRry.",
    "wyrrRRrryyrrRRyw",
    ".yrrrrrrrrrrrry.",
    "wyyyyyyyyyyyyyyw",
  ] },
  // white clawfoot bathtub: rim, blue water line, grey tap on the left, four gold claw feet; clearly not a boat (18x11).
  bathtub: { rows: [
    "gg................",
    ".g................",
    "WWWWWWWWWWWWWWWWWW",
    "wqqqqqqqqqqqqqqqqw",
    "wwwwwwwwwwwwwwwwww",
    "wwwwwwwwwwwwwwwwWW",
    "wwwwwwwwwwwwwwwWWW",
    ".wwwwwwwwwwwwwWWW.",
    "..WWwwwwwwwwWWW...",
    "..yy..........yy..",
    ".yy............yy.",
  ] },
  // steam: two wavy rising white lines with a grey edge, for hot water (10x12).
  steam: { rows: [
    ".wW...wW..",
    "..wW.wW...",
    "..wW.wW...",
    ".wW...wW..",
    "wW.....wW.",
    "wW.....wW.",
    ".wW...wW..",
    "..wW.wW...",
    "..wW.wW...",
    ".wW...wW..",
    "wW.....wW.",
    "wW.....wW.",
  ] },
  // catnip: leafy green plant with a few lilac flowers in a small terracotta pot (10x14).
  catnip: { rows: [
    "...m..m...",
    "..mlmmlm..",
    ".l.lLll.l.",
    "ll.lLll.ll",
    ".llLllLll.",
    "ll.llLll.l",
    ".lllLlllL.",
    "...lLll...",
    "....L.....",
    "....L.....",
    "OOOOOOOOOO",
    ".oooooooo.",
    ".ooooooOo.",
    "..oooooO..",
  ] },
  // sand block: pale yellow with light and dark grains, clearly paler and yellower than dirt (12x12).
  sand: { rows: [
    "AAAAAAAAAAAA",
    "AIAAAAAVAAAA",
    "AAAAVAAAAAIA",
    "AAIAAAAAAVAA",
    "AAAAAAIAAAAA",
    "AVAAAAAAAAIA",
    "AAAAIAAVAAAA",
    "AAVAAAAAAAAA",
    "AAAAAAIAAVAA",
    "AIAAVAAAAAAA",
    "AAAAAAAAIAAA",
    "VVVVVVVVVVVV",
  ] },
  // big red X, two-pixel-thick diagonals with a dark-red edge, for a wall (12x12).
  x_mark: { rows: [
    "rR........rr",
    "rrR......rrr",
    ".rrR....rrR.",
    "..rrR..rrR..",
    "...rrrrrR...",
    "....rrrR....",
    "....rrrR....",
    "...rrrrrR...",
    "..rrR..rrR..",
    ".rrR....rrR.",
    "rrR......rrr",
    "rR........rr",
  ] },
  // big water splash: a tall crown of blue water with white tips and flying drops (18x14). The existing splash fx is only a small low fountain.
  splash_big: { rows: [
    "........ww........",
    ".w......wq......w.",
    "..q.....qq.....q..",
    ".qq.....qq.....qq.",
    ".qQ.....qq.....Qq.",
    "..qq....qq....qq..",
    "..qQq...qq...qQq..",
    "...qq..qqqq..qq...",
    "...qQqqqQQqqqQq...",
    "....qqqqqqqqqq....",
    "..wwqqqqqqqqqqww..",
    "wwwwwwwwwwwwwwwwww",
    "qqqqqqqqqqqqqqqqqq",
    "QQQQQQQQQQQQQQQQQQ",
  ] },
  // --- end E1 ---
};

// gold_pig: the same grid as pig, recoloured gold (swap map, so pig itself is untouched).
SPRITES.gold_pig = { rows: SPRITES.pig.rows, swap: { p: "y", P: "Y" } };

// --- Village art (Minecraft Magic Chest village) ---
// All original char grids. The villagers share one 14x24 base (bald head, big nose, single unibrow, green eyes,
// robe, arms folded in a band) and differ in outfit. Added after the sprites above; none of those are changed.
// spawn_egg and the badge_* tiers are one grid each, recoloured with the engine's swap map.
const VILLAGE_SPRITES = {
  // villager_librarian: white robe, brown apron, flat book-hat, dark glasses
  villager_librarian: { rows: [
    "....NNNNNN....", "...NhhhhhhN...", "...wwwwwwww...", "...iiiiiiii...",
    "...iiiiiiii...", "...iHHHHHHi...", "...kwLkkLwk...", "...iiijjiii...",
    "...iiijjiii...", "...iiijjiii...", "...iiinniii...", "...iiiiiiii...",
    "..wwwhwwhwww..", "..wwwhwwhwww..", "..gggggggggg..", "..gwwiiiiwwg..",
    "..gggggggggg..", "...whhhhhhw...", "...whhhhhhw...", "...whhhhhhw...",
    "...whhhhhhw...", "...whhhhhhw...", "...whhhhhhw...", "...hhhhhhhh...",
  ] },
  // villager_armorer: grey apron, black welding goggles (glowing lenses) on the forehead
  villager_armorer: { rows: [
    "..............", "..............", "...iiiiiiii...", "...aaaaaaaa...",
    "...aGcGGcGa...", "...iHHHHHHi...", "...iwLiiLwi...", "...iiijjiii...",
    "...iiijjiii...", "...iiijjiii...", "...iiinniii...", "...iiiiiiii...",
    "..nnnannannn..", "..nnnannannn..", "..NNNNNNNNNN..", "..NnniiiinnN..",
    "..NNNNNNNNNN..", "...nGGGGGGn...", "...nGGGGGGn...", "...nGGGGGGn...",
    "...nGGGGGGn...", "...nGGGGGGn...", "...nGGGGGGn...", "...GGGGGGGG...",
  ] },
  // villager_weaponsmith: black eye-patch with strap, black apron
  villager_weaponsmith: { rows: [
    "..............", "..............", "...iiiiiiii...", "...iiiiiiii...",
    "...kkkkkkkk...", "...iHHHHkki...", "...iwLiikki...", "...iiijjiii...",
    "...iiijjiii...", "...iiijjiii...", "...iiinniii...", "...iiiiiiii...",
    "..nnnannannn..", "..nnnannannn..", "..NNNNNNNNNN..", "..NnniiiinnN..",
    "..NNNNNNNNNN..", "...naaaaaan...", "...naaaaaan...", "...naaaaaan...",
    "...naaaaaan...", "...naaaaaan...", "...naaaaaan...", "...aaaaaaaa...",
  ] },
  // villager_toolsmith: black apron with a tool in the pocket, black gloves
  villager_toolsmith: { rows: [
    "..............", "..............", "...iiiiiiii...", "...iiiiiiii...",
    "...iiiiiiii...", "...iHHHHHHi...", "...iwLiiLwi...", "...iiijjiii...",
    "...iiijjiii...", "...iiijjiii...", "...iiinniii...", "...iiiiiiii...",
    "..nnnannannn..", "..nnnannannn..", "..NNNNNNNNNN..", "..NnnaaaanN...",
    "..NNNNNNNNNN..", "...nazzaaan...", "...naTTaaan...", "...naaaaaan...",
    "...naaaaaan...", "...naaaaaan...", "...naaaaaan...", "...aaaaaaaa...",
  ] },
  // villager_farmer: wide straw hat, tan robe, green apron
  villager_farmer: { rows: [
    "....AAAAAA....", "...AYYYYYYA...", "yyyyyyyyyyyyyy", "...iiiiiiii...",
    "...iiiiiiii...", "...iHHHHHHi...", "...iwLiiLwi...", "...iiijjiii...",
    "...iiijjiii...", "...iiijjiii...", "...iiinniii...", "...iiiiiiii...",
    "..tttttttttt..", "..tttttttttt..", "..TTTTTTTTTT..", "..TttiiiittT..",
    "..TTTTTTTTTT..", "...tuuuuuut...", "...tuuuuuut...", "...tuuuuuut...",
    "...tuuuuuut...", "...tuuuuuut...", "...tuuuuuut...", "...uuuuuuuu...",
  ] },
  // villager_fletcher: brown feathered hat (white feather), green apron
  villager_fletcher: { rows: [
    "....hhhhhh.ww.", "...hhhhhhhhww.", "..NNNNNNNNNN..", "...iiiiiiii...",
    "...iiiiiiii...", "...iHHHHHHi...", "...iwLiiLwi...", "...iiijjiii...",
    "...iiijjiii...", "...iiijjiii...", "...iiinniii...", "...iiiiiiii...",
    "..nnnnnnnnnn..", "..nnnnnnnnnn..", "..NNNNNNNNNN..", "..NnniiiinnN..",
    "..NNNNNNNNNN..", "...nLLLLLLn...", "...nLLLLLLn...", "...nLLLLLLn...",
    "...nLLLLLLn...", "...nLLLLLLn...", "...nLLLLLLn...", "...LLLLLLLL...",
  ] },
  // villager_cleric: purple robe with gold trim
  villager_cleric: { rows: [
    "..............", "..............", "...iiiiiiii...", "...iiiiiiii...",
    "...iiiiiiii...", "...iHHHHHHi...", "...iwLiiLwi...", "...iiijjiii...",
    "...iiijjiii...", "...iiijjiii...", "...iiinniii...", "...iiiiiiii...",
    "..yyyyyyyyyy..", "..mmmmmmmmmm..", "..MMMMMMMMMM..", "..MmmiiiimmM..",
    "..MMMMMMMMMM..", "...mmmmmmmm...", "...mmmmmmmm...", "...mmmmmmmm...",
    "...mmmmmmmm...", "...mmmmmmmm...", "...mmmMMmmm...", "...yyyyyyyy...",
  ] },
  // villager_cartographer: gold monocle, gold-trimmed cognac robe
  villager_cartographer: { rows: [
    "..............", "..............", "...iiiiiiii...", "...iiiiiiii...",
    "...iiiiiiii...", "...iHHHHyyi...", "...iwLiyLwy...", "...iiijjyyi...",
    "...iiijjiii...", "...iiijjiii...", "...iiinniii...", "...iiiiiiii...",
    "..yyyyyyyyyy..", "..TTTTTTTTTT..", "..NNNNNNNNNN..", "..NTTiiiiTTN..",
    "..NNNNNNNNNN..", "...TTTTTTTT...", "...TTTTTTTT...", "...TTTTTTTT...",
    "...TTTTTTTT...", "...TTTTTTTT...", "...TTTNNTTT...", "...yyyyyyyy...",
  ] },
  // villager_shepherd: brown wide-brim hat, light robe, tall crook staff on the left
  villager_shepherd: { rows: [
    "..............", "....hhhhhh....", ".hhhhhhhhhhhh.", "...iiiiiiii...",
    "...iiiiiiii...", "TT.iHHHHHHi...", "T..iwLiiLwi...", "T..iiijjiii...",
    "T..iiijjiii...", "T..iiijjiii...", "T..iiinniii...", "T..iiiiiiii...",
    "T.jjjjjjjjjj..", "T.jjjjjjjjjj..", "T.NNNNNNNNNN..", "T.NjjiiiijjN..",
    "T.NNNNNNNNNN..", "T..jjjjjjjj...", "T..jjjjjjjj...", "T..jjjjjjjj...",
    "T..jjjjjjjj...", "T..jjjjjjjj...", "T..jjjNNjjj...", "T..NNNNNNNN...",
  ] },
  // villager_butcher: white headband, white apron with red stains
  villager_butcher: { rows: [
    "..............", "..............", "...iiiiiiii...", "...iiiiiiii...",
    "...wwwwwwww...", "...iHHHHHHi...", "...iwLiiLwi...", "...iiijjiii...",
    "...iiijjiii...", "...iiijjiii...", "...iiinniii...", "...iiiiiiii...",
    "..nnnwnnwnnn..", "..nnnwnnwnnn..", "..NNNNNNNNNN..", "..NnniiiinnN..",
    "..NNNNNNNNNN..", "...nwwwwwwn...", "...nwwwwwwn...", "...nwrwwwwnr..",
    "...nwwwwwwn...", "...nwrwwwwn...", "...nwwwwwwn...", "...wwwwwwww...",
  ] },
  // villager_fisherman: teal bucket fishing hat, blue robe
  villager_fisherman: { rows: [
    "..............", "....CCCCCC....", ".CCCCCCCCCCCC.", "...iiiiiiii...",
    "...iiiiiiii...", "...iHHHHHHi...", "...iwLiiLwi...", "...iiijjiii...",
    "...iiijjiii...", "...iiijjiii...", "...iiinniii...", "...iiiiiiii...",
    "..qqqqqqqqqq..", "..qqqqqqqqqq..", "..QQQQQQQQQQ..", "..QqqiiiiqqQ..",
    "..QQQQQQQQQQ..", "...qqqqqqqq...", "...qqqqqqqq...", "...qqqqqqqq...",
    "...qqqqqqqq...", "...qqqqqqqq...", "...qqqQQqqq...", "...QQQQQQQQ...",
  ] },
  // villager_mason: light-grey stone apron
  villager_mason: { rows: [
    "..............", "..............", "...iiiiiiii...", "...iiiiiiii...",
    "...iiiiiiii...", "...iHHHHHHi...", "...iwLiiLwi...", "...iiijjiii...",
    "...iiijjiii...", "...iiijjiii...", "...iiinniii...", "...iiiiiiii...",
    "..nnnznnznnn..", "..nnnznnznnn..", "..NNNNNNNNNN..", "..NnniiiinnN..",
    "..NNNNNNNNNN..", "...nddddddn...", "...nddddddn...", "...nddddddn...",
    "...nddddddn...", "...nddddddn...", "...nddddddn...", "...dddddddd...",
  ] },
  // villager_leatherworker: brown leather apron with stitched pocket
  villager_leatherworker: { rows: [
    "..............", "..............", "...iiiiiiii...", "...iiiiiiii...",
    "...iiiiiiii...", "...iHHHHHHi...", "...iwLiiLwi...", "...iiijjiii...",
    "...iiijjiii...", "...iiijjiii...", "...iiinniii...", "...iiiiiiii...",
    "..nnnhnnhnnn..", "..nnnhnnhnnn..", "..NNNNNNNNNN..", "..NnniiiinnN..",
    "..NNNNNNNNNN..", "...nhhhhhhn...", "...nhhhhhhn...", "...nhTTTThn...",
    "...nhhhhhhn...", "...nhhhhhhn...", "...nhhhhhhn...", "...hhhhhhhh...",
  ] },
  // wandering_trader: blue hood and robe, cream collar, belt
  wandering_trader: { rows: [
    "....BBBBBB....", "...BbbbbbbbB..", "..BbbbbbbbbB..", "..BiiiiiiiiB..",
    "..BiiiiiiiiB..", "..BiHHHHHHiB..", "..BiwLiiLwiB..", "..BiiijjiiiB..",
    "..BiiijjiiiB..", "..BiiijjiiiB..", "..BiiinniiiB..", "..BiiiiiiiiB..",
    "..xxxxxxxxxx..", "..bbbbbbbbbb..", "..BBBBBBBBBB..", "..BbbiiiibbB..",
    "..BBBBBBBBBB..", "...NNNNNNNN...", "...bbbbbbbb...", "...bbbbbbbb...",
    "...bbbbbbbb...", "...bbbbbbbb...", "...bbbBBbbb...", "...BBBBBBBB...",
  ] },
  // villager_locked: dark silhouette of the villager base (plot not unlocked yet)
  villager_locked: { rows: [
    "..............", "..............", "...MMMMMMMM...", "...MMMMMMMM...",
    "...MMMMMMMM...", "...MaaaaaaM...", "...MMMMMMMM...", "...MMMaaMMM...",
    "...MMMaaMMM...", "...MMMaaMMM...", "...MMMaaMMM...", "...MMMMMMMM...",
    "..aaaaaaaaaa..", "..aaaaaaaaaa..", "..aaaaaaaaaa..", "..aaaMMMMaaa..",
    "..aaaaaaaaaa..", "...aaaaaaaa...", "...aaaaaaaa...", "...aaaaaaaa...",
    "...aaaaaaaa...", "...aaaaaaaa...", "...aaaaaaaa...", "...aaaaaaaa...",
  ] },
  trader_llama: { rows: [
    "...........x.x..", "..........xxxxx.", "..........xkxxxi", "..........xxxxxi",
    "..........xxxxx.", "..........xxx...", "..........xxx...", ".xxxxxxxxxxxx...",
    "xxbbwbbwbbxxx...", "xxBBBBBBBBxxx...", ".xxxxxxxxxxx....", ".xxxxxxxxxxx....",
    ".xx.xx...xx.xx..", ".xx.xx...xx.xx..", ".ii.ii...ii.ii..", ".kk.kk...kk.kk..",
  ] },
  lectern: { rows: [
    "............", "..TTTTTTTT..", ".TwwwwrwwwT.", ".TwkkwrwkkT.",
    "..TwwwrwwT..", "...TTTTTT...", "....TNNT....", "....tNNt....",
    "....tNNt....", "....tNNt....", "..TTTNNTTT..", "..NNNNNNNN..",
  ] },
  blast_furnace: { rows: [
    "zzzzzzzzzzzz", "zGGGGGGGGGGz", "zGaaaaaaaaGz", "zGaffffoofGz",
    "zGafyyyyofGz", "zGaffooffoGz", "zGGGGGGGGGGz", "zggggggggggz",
    "zZZZZZZZZZZz", "zGGkGGGGkGGz", "zggggggggggz", "ZZZZZZZZZZZZ",
  ] },
  grindstone: { rows: [
    "............", ".....gg.....", "...NNggNN...", "..NN.gg.NN..",
    "..NggggggNN.", "..NgwggwgNN.", "..NggggggNN.", "..NgGggGgNN.",
    "..NNggggNNN.", "...NN.gg.NN.", "..TTTTTTTTT.", "..NNNNNNNNN.",
  ] },
  smithing_table: { rows: [
    "aaaaaaaaaaaa", "aGGaGGGaaGGa", "aGzaGzzaGzza", "aaaaaaaaaaaa",
    "NnnnnnnnnnnN", "NnnNnnnnNnnN", "NNNNNNNNNNNN", "NnnnnnnnnnnN",
    "NnnnnnnnnnnN", "NNNNNNNNNNNN", "NN........NN", "NN........NN",
  ] },
  composter: { rows: [
    "TTTTTTTTTTTT", "TNNNNNNNNNNT", "TNhNuNhNNuNT", "TNNhNNNuNhNT",
    "TtttttttttTT", "TTTTTTTTTTTT", "TNNNNNNNNNNT", "TNuNNhNNuNNT",
    "TTTTTTTTTTTT", "TNNhNNNNhNNT", "TNNNNuNNNNNT", "TTTTTTTTTTTT",
  ] },
  fletching_table: { rows: [
    "NNNNNNNNNNNN", "NttttttttttN", "NtwwwtkkkttN", "NtwwtkkkkttN",
    "NtwtttkkttNN", "NNNNNNNNNNNN", "NttttttttttN", "NtkttttkttkN",
    "NttttttttttN", "NNNNNNNNNNNN", "NN........NN", "NN........NN",
  ] },
  brewing_stand: { rows: [
    "............", "....yy......", "....yy..yy..", "..qq.yy.qq..",
    "..qq.yy.qq..", "..qq.yy.qq..", "...qqyyqq...", "....yyy.....",
    "gggggggggggg", "gGGGGGGGGGGg", "gggggggggggg", "ZZZZZZZZZZZZ",
  ] },
  cartography_table: { rows: [
    "TTTTTTTTTTTT", "TxxxxxxxxxxT", "TxllxxqqxxxT", "TxlllxqqxrxT",
    "TxxllxxxrrxT", "TTTTTTTTTTTT", "TnnnnnnnnnnT", "TnNnnnnnnNnT",
    "TTTTTTTTTTTT", "TN........NT", "TN........NT", "NN........NN",
  ] },
  loom: { rows: [
    "NNNNNNNNNNNN", "NrwbrwbrwbNN", "NrwbrwbrwbwN", "NrwbrwbrwbwN",
    "NNNNNNNNNNNN", "NttttttttttN", "NtTtttttttTN", "NttttttttttN",
    "NNNNNNNNNNNN", "NN........NN", "NN........NN", "NN........NN",
  ] },
  smoker: { rows: [
    "nnnnnnnnnnnn", "nNNNNNNNNNNn", "nNaaaaaaaaNn", "nNaffffffaNn",
    "nNafyyyyfaNn", "nNaaaaaaaaNn", "nNNNNNNNNNNn", "nnnnnnnnnnnn",
    "nZZZZZZZZZZn", "nZzzzzzzzzZn", "nZZZZZZZZZZn", "nnnnnnnnnnnn",
  ] },
  barrel: { rows: [
    "..NNNNNNNN..", ".NtTtTtTtTN.", "NtTtTtTtTtTN", "GGGGGGGGGGGG",
    "NtTtTtTtTtTN", "NtTtTtTtTtTN", "NtTtTtTtTtTN", "NtTtTtTtTtTN",
    "GGGGGGGGGGGG", "NtTtTtTtTtTN", ".NtTtTtTtTN.", "..NNNNNNNN..",
  ] },
  stonecutter: { rows: [
    "............", "....gwwg....", "...gwGGwg...", "..gwG..Gwg..",
    "..gG.kk.Gg..", "..gwG..Gwg..", "...gwGGwg...", "....gwwg....",
    "zzzzzzzzzzzz", "zZZZZZZZZZZz", "zzzzzzzzzzzz", "ZZZZZZZZZZZZ",
  ] },
  // witch's pot: round black belly wider than its rim, bubbling bright green brew, little legs (12x12)
  cauldron: { rows: [
    "....l...e...", "..kkkkkkkk..", "..keleelek..", ".kGGGGGGGGk.",
    "kaaaaaaaaaak", "kaGaaaaaaaak", "kaGaaaaaaaak", "kaaaaaaaaaak",
    "kaaaaaaaaaak", ".kaaaaaaaak.", "..kkkkkkkk..", ".kk......kk.",
  ] },
  village_bell: { rows: [
    "..NNNNNNNNNN..", "..N........N..", "..N...yy...N..", "..N..yyyy..N..",
    "..N.ywyyyy.N..", "..N.ywyyyyYN..", "..NyywyyyyYYN.", "..NyyyyyyyyYN.",
    "..NYYYYYYYYYN.", "..N...oo...N..", "..N...oo...N..", "..N........N..",
    ".NNN......NNN.", ".NNN......NNN.",
  ] },
  enchanted_book: { rows: [
    "..p......p..", ".MMMMMMMMM..", ".MmmmmmmmMw.", ".MmmmyymmMw.",
    ".MmmyppymMw.", ".MmmmyymmMw.", ".MmmmmmmmMw.", ".MmpmmmmpMw.",
    ".MmmmmmmmMw.", ".MMMMMMMMMw.", "..wwwwwwwww.", "..........p.",
  ] },
  spawn_egg: { rows: [
    "....llll....", "...llllll...", "..lllLllll..", "..lkklllll..",
    ".llkkllllLl.", ".lllllllkkl.", ".lllLllkkkl.", ".lkklllllll.",
    ".lkkllllLll.", "..llllllll..", "...llllLl...", "....LLLL....",
  ] },
  diamond_sword: { rows: [
    "..........cC", ".........cwC", "........cwcC", ".......cwcC.",
    "......cwcC..", ".....cwcC...", ".T..cwcC....", "..TTcCC.....",
    "...TTT......", "..NNTT......", ".NN.........", "NN..........",
  ] },
  diamond_chestplate: { rows: [
    "..cc....cc..", ".cCCc..cCCc.", "cCwcCccCcwCc", "cCcccCCcccCc",
    "CcwccccccCcC", ".CccccccccC.", ".CcwcccccCC.", ".CccccccccC.",
    ".CcccwcccCC.", ".CCcccccCCC.", "..CCccccCC..", "...CCCCCC...",
  ] },
  elytra: { rows: [
    "...ZZ..ZZ...", "..ZzzZZzzZ..", ".ZzzzzzzzzZ.", "ZzzzMzzMzzzZ",
    "ZzzzzzzzzzzZ", "ZzMzzzzzzMzZ", ".ZzzzzzzzzZ.", ".ZzzZ..ZzzZ.",
    "..Zz....zZ..", "..Z......Z..", "..Z......Z..", "...Z....Z...",
  ] },
  golden_apple: { rows: [
    ".....L......", "....LN.LL...", "...yyNyyy...", "..yywyyyyY..",
    ".yywyyyyyyY.", ".yyyyyyyyyY.", ".yyyyyyyyyY.", ".yyyyyyyyYY.",
    "..yyyyyyYY..", "..YyyyyYYY..", "...YYYYYY...", "............",
  ] },
  totem: { rows: [
    "...yyyyyy...", "..yyeyyeyy..", ".yyyyyyyyyy.", ".ykyyyyyyky.",
    ".yyyyyyyyyy.", ".yyyykkyyyy.", ".yyyyyyyyyy.", "..yeyyyyey..",
    "..yyeyyeyy..", "...yyeeyy...", "....yyyy....", "....YYYY....",
  ] },
  netherite_ingot: { rows: [
    "............", "............", "....GGGGGGG.", "..GGNNNNNNGa",
    "..GNNaaaNNGa", ".GNNNaaaNGaa", ".GNNNNNNGaa.", ".GGGGGGGaa..",
    "..aaaaaaa...", "............", "............", "............",
  ] },
  name_tag: { rows: [
    "............", "...TTTTTTTT.", "..TttttttttT", ".TtkkttxxxxT",
    "TtkkkttttttT", ".TtttttxxxxT", "..TttttttttT", "...TTTTTTTT.",
    "..k.........", ".k..........", "k...........", "............",
  ] },
  saddle: { rows: [
    "............", "....nnnn....", "..nnnnnnnn..", ".nnTnnnnTnn.",
    "nnnnnnnnnnnn", "TTTTTTTTTTTT", "nnnnnnnnnnnn", ".TT..yy..TT.",
    ".T...yy...T.", ".y........y.", ".yy......yy.", "............",
  ] },
  trident: { rows: [
    "C..C..C.....", "C..C..C.....", "CC.CC.CC....", ".CCCCCC.....",
    "..CCCC......", "...CC.......", "...NN.......", "...NN.......",
    "...NN.......", "...NN.......", "...NN.......", "...NN.......",
  ] },
  xp_bottle: { rows: [
    "....TT......", "....ww......", "....ww......", "...wllw.....",
    "..wllllw....", "..wlllLw....", "..wlylLw....", "..wllllw....",
    "..wlLllw....", "...wllw.....", "....ww......", "............",
  ] },
  ender_pearl: { rows: [
    "...CCCCCC...", "..CEEEEEEC..", ".CEEwEEEEEC.", "CEEwwEEEEEEC",
    "CEEEEEEEEEEC", "CEEEkkEEEEEC", "CEEkkkkEEEEC", "CEEEkkEEEEEC",
    ".CEEEEEEEEC.", "..CEEEEEEC..", "...CCCCCC...", "............",
  ] },
  sapling: { rows: [
    "............", "....LLL.....", "...LllLLL...", "..LllllllL..",
    "..LlLllLlL..", "...LllLLL...", "....LNL.....", ".....N......",
    ".....N......", "....NNN.....", "...nnnnn....", "...nnnnn....",
  ] },
  music_disc: { rows: [
    "....kkkk....", "..kkaaaakk..", ".kaaaaaaaak.", "kaaaaGaaaaak",
    "kaaaarraaaak", "kaaaarwraaak", "kaaaaarraaak", "kaaaaaaaaaak",
    ".kaaGaaaaak.", "..kkaaaakk..", "....kkkk....", "............",
  ] },
};
Object.assign(SPRITES, VILLAGE_SPRITES);
// Level badges (12x12): one medal grid, recoloured per tier (o/O = body/shade, w = shine).
const BADGE = [
    "...OOOOOO...", "..OoooooooO.", ".OoowwwwooO.", ".OoowwwwooO.",
    ".OowwwwwwoO.", ".OoowwwwooO.", ".OoowwwwooO.", "..OoooooooO.",
    "...OOOOOO...", "....O..O....", "....O..O....", "....OOOO....",
];
SPRITES.badge_stone = { rows: BADGE, swap: { o: "z", O: "Z" } };
SPRITES.badge_iron = { rows: BADGE, swap: { o: "d", O: "G" } };
SPRITES.badge_gold = { rows: BADGE, swap: { o: "y", O: "Y" } };
SPRITES.badge_emerald = { rows: BADGE, swap: { o: "e", O: "E" } };
SPRITES.badge_diamond = { rows: BADGE, swap: { o: "c", O: "C" } };
// Currency/inventory ICONS. In hand mode these are the very same grids as the ore sprites (nothing changes); in real
// texture mode they use the ITEM textures (emerald, diamond, ingots) instead of the ore BLOCKS, because a wallet,
// a price or a Sell button means the item, while the mine grid (coal/iron/gold/diamond/emerald) means the ore.
SPRITES.coal_item = SPRITES.coal;
SPRITES.iron_item = SPRITES.iron;
SPRITES.gold_item = SPRITES.gold;
SPRITES.diamond_item = SPRITES.diamond;
SPRITES.emerald_item = SPRITES.emerald;
const RESOURCE_ITEM = { coal: "coal_item", iron: "iron_item", gold: "gold_item", diamond: "diamond_item", emerald: "emerald_item" };
/** The sprite for a resource meaning the ITEM (wallet, price, Sell, inventory counts); other names pass through. */
export const itemSprite = (name) => RESOURCE_ITEM[name] ?? name;
// diamond_pickaxe: the existing pickaxe grid with a diamond head (no new grid).
SPRITES.diamond_pickaxe = { rows: SPRITES.pickaxe.rows, swap: { g: "c", G: "C" } };

// magic_portal (16x22): glowing golden-rimmed oval with a purple/cyan swirl, for the Send scene.
SPRITES.magic_portal = { rows: [
    "......yyyy......",
    "w...fyyyyfyy....",
    "...fyymmmmyyy...",
    "..fymmmmmmmMfy.w",
    "..ymMMcmmqmmMy..",
    ".yyMMccccmqmmyy.",
    ".yMMccmcccqqmMf.",
    ".yMMmmwwppmqmMy.",
    "yyMcqwwwwppqqMyy",
    "yfMmqwwwwppqqMyy",
    "fMMqqwpwwppqqMMf",
    "yMMqqppwwpwqqMMy",
    "yyMqqppwwwwqmMyy",
    "yyMqqppwwwwqcMyy",
    ".fMmqmppwwmmMMy.",
    ".yMmqqcccmccMMy.",
    ".yymmqmccccMMyf.",
    "..yMmmqmmcMMmf..",
    "..fyMmmmmmmmfy..",
    ".w.yyymmmmyfy...",
    "....yfyyyyfy..w.",
    "......yyyf......",
  ] };

export const SPRITE_NAMES = Object.keys(SPRITES);

/** Resolve a char to a colour via the optional swap map; throws on an unknown char. */
function colour(ch, swap, name) {
  const key = swap && swap[ch] ? swap[ch] : ch;
  const c = PALETTE[key];
  if (!c) throw new Error(`sprite "${name}": unknown palette char "${ch}"`);
  return c;
}

/** Logical box of a real-only picture (a mapped id with no hand-drawn grid: the mobs): the spawn egg's, so layouts match. */
export const REAL_ONLY_BOX = { w: 12, h: 12 };

/** True for an id that exists only as a real texture (mapped in real mode, no hand-drawn grid). */
export function isRealOnly(name) {
  return !SPRITES[name] && Boolean(getTextures()?.usesReal(name));
}

/** Width and height in sprite pixels. */
export function spriteSize(name) {
  const s = SPRITES[name];
  if (!s) {
    if (isRealOnly(name)) return { ...REAL_ONLY_BOX };
    throw new Error(`unknown sprite "${name}"`);
  }
  return { w: s.rows[0].length, h: s.rows.length };
}

const cache = new Map(); // hand canvases by name+swap
const realCache = new WeakMap(); // texture image -> Map(sprite id -> hi-res canvas); a new texture set never hits a stale entry

/** Offscreen canvas for a sprite (cached per name+swap). */
export function spriteCanvas(name, swap) {
  const s = SPRITES[name];
  if (!s) throw new Error(`unknown sprite "${name}"`);
  const key = name + JSON.stringify(swap || {});
  if (cache.has(key)) return cache.get(key);
  const merged = { ...(s.swap || {}), ...(swap || {}) };
  const { w, h } = spriteSize(name);
  const cv = document.createElement("canvas");
  cv.width = w;
  cv.height = h;
  const ctx = cv.getContext("2d");
  s.rows.forEach((row, y) => {
    [...row].forEach((ch, x) => {
      if (ch === ".") return;
      ctx.fillStyle = colour(ch, merged, name);
      ctx.fillRect(x, y, 1, 1);
    });
  });
  cache.set(key, cv);
  return cv;
}

/** Hi-res factor of a real-texture canvas: it is spriteSize * REAL_SCALE pixels (villagers are 120x216 at 14x24). */
export const REAL_SCALE = 10;

/**
 * What drawSprite/drawSpriteFit/spriteElement actually draw: the real texture fitted to the sprite's logical box
 * (integer upscale when it fits, bottom-centre aligned, no smoothing), or the hand-drawn canvas when the art mode is
 * "hand" or the id is deliberately unmapped. Real mode with a missing texture throws (getTexture), never falls back.
 * spriteCanvas() stays the logical-resolution hand-drawn canvas: scenes.js slices it by logical pixel for poses.
 */
export function spriteImage(name, swap) {
  const tex = getTexture(name);
  if (!tex) return spriteCanvas(name, swap);
  // swap recolours hand-drawn grids only; it does not apply to real textures
  if (!realCache.has(tex)) realCache.set(tex, new Map());
  const byName = realCache.get(tex);
  if (byName.has(name)) return byName.get(name);
  const { w, h } = spriteSize(name);
  const bw = w * REAL_SCALE, bh = h * REAL_SCALE;
  const tw = tex.naturalWidth || tex.width, th = tex.naturalHeight || tex.height;
  if (!tw || !th) throw new Error(`real texture for "${name}" has no size`);
  let k = Math.min(bw / tw, bh / th);
  if (k >= 1) k = Math.floor(k);
  const dw = Math.max(1, Math.round(tw * k)), dh = Math.max(1, Math.round(th * k));
  const cv = document.createElement("canvas");
  cv.width = bw;
  cv.height = bh;
  const ctx = cv.getContext("2d");
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(tex, Math.floor((bw - dw) / 2), bh - dh, dw, dh);
  byName.set(name, cv);
  return cv;
}

/** Draw a sprite with its top-left at (x, y), each sprite pixel being `scale` canvas pixels. */
export function drawSprite(ctx, name, x, y, scale = 1, swap) {
  const { w, h } = spriteSize(name);
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(spriteImage(name, swap), Math.round(x), Math.round(y), w * scale, h * scale);
}

/** Draw a sprite scaled to fit a box, keeping aspect ratio, centred. */
export function drawSpriteFit(ctx, name, x, y, boxW, boxH, swap) {
  const { w, h } = spriteSize(name);
  const k = Math.min(boxW / w, boxH / h);
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(spriteImage(name, swap), Math.round(x + (boxW - w * k) / 2), Math.round(y + (boxH - h * k) / 2),
    Math.round(w * k), Math.round(h * k));
}

/** A ready-to-insert <canvas> showing a sprite at an integer scale (pixelated via CSS). */
export function spriteElement(name, scale = 4, swap) {
  const { w, h } = spriteSize(name);
  const cv = document.createElement("canvas");
  cv.width = w * scale;
  cv.height = h * scale;
  cv.className = "sprite";
  drawSprite(cv.getContext("2d"), name, 0, 0, scale, swap);
  return cv;
}
