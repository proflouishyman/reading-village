// the village: his villagers at their job-site blocks (each with its own level badge), "?" plots to unlock,
// bells, the promotion banner and picker, the "Sell to the village" stall, the unlock picker and each villager's
// trade screen. Everything he sees is small caps
// (kid helpers); the server prices and checks every purchase, this screen only shows and asks.
import { stageLayout } from "../layout.js";
import { spriteElement, itemSprite } from "../sprites.js";
import { h, inventoryRow, showFatal } from "../ui.js";
import { getVillage, postUnlock, postPromote, postBuy, postTrade } from "../api.js";
import { loadProgress, store } from "../store.js";
import { playFanfare, playJingle, playSparkle } from "../sounds.js";
import { showSurprise } from "../surprise.js";
import { mcStatusNode } from "../mcstatus.js";
import { STATIC } from "../runmode.js";
import { renderPile } from "./treasure.js";
import { badgesFor, resolveSprite, validateVillage, validatePromoteReply, villagerSprite, promotable, promotionHint, offerStatus, canTrade, unlockChoices, treasureCount } from "../villagelogic.js";
import { fam, childName, grownUpPoss } from "../family.js";

const spr = (name, scale) => spriteElement(resolveSprite(name), scale);
/** A resource shown as the ITEM it is (currency icons, trade sides), not as its ore block. */
const res = (name, scale) => spr(itemSprite(name), scale);
/** The level badge of a villager (its own level, not the village's). */
const badge = (v, p, scale) => spr(badgesFor(v.levels.names)[p.level], scale);
const money = (n) => h("span", { class: "price" }, res("emerald", 2), h("span", { class: "price-n", text: String(n) }));

/** Fetch + validate the village, and refresh the client's progress copy (the server changed inventory/village). */
async function refresh() {
  const v = validateVillage(await getVillage());
  await loadProgress();
  store.earn = v.earn;
  return v;
}

export async function run(app) {
  const L = stageLayout(app.root, { title: fam().village_name, dadHint: `${childName()} picks villagers to meet and spends emeralds. Bells come from reading.` });
  L.disableButtons();
  const mc = mcStatusNode();
  L.dad.append(mc);
  let village = await refresh();

  return new Promise((resolve) => {
    L.quitted.then(() => resolve("quit"));
    /**
     * Wrap a click handler that POSTs. While one is in flight every button on the screen is disabled and any further
     * tap is ignored (a double-tap must be exactly one request: a second Buy would spend twice, a second Unlock would
     * be refused with a 400 after the first one worked). The flag is set synchronously, so even two clicks in the same
     * tick are caught. Failures are shown loudly (never swallowed). The screen is re-rendered by the handler itself.
     */
    let busy = false;
    const act = (what, fn) => async (...a) => {
      if (busy) return;
      busy = true;
      L.play.querySelectorAll("button").forEach((b) => { b.disabled = true; });
      try { await fn(...a); } catch (e) { showFatal(`Village: ${what} failed`, e instanceof Error ? e.message : String(e)); } finally { busy = false; }
    };
    const back = (to) => h("button", { class: "btn small back-btn", kid: "◀ Back", onclick: to });
    const show = (...kids) => L.play.replaceChildren(...kids.filter(Boolean)); // a conditional piece may be null

    // ---- the village ---------------------------------------------------------------------------------------
    function plot(p) {
      const name = h("div", { class: "plot-name", kid: p.name });
      if (p.unlocked) {
        return h("button", { class: "plot have", "data-prof": p.id, "data-level": String(p.level), onclick: () => shop(p) },
          h("div", { class: "plot-row" }, spr(villagerSprite(p), 5), spr(p.job_block_sprite, 4)), name,
          h("div", { class: "plot-level" }, badge(village, p, 3), h("span", { kid: p.level_name })));
      }
      if (p.can_unlock) {
        return h("button", { class: "plot open", "data-prof": p.id, onclick: () => picker(p) },
          h("div", { class: "plot-row" }, h("div", { class: "plot-q", kid: "?" }), spr(p.job_block_sprite, 4)), name);
      }
      return h("div", { class: "plot locked", "data-prof": p.id },
        h("div", { class: "plot-row" }, spr("villager_locked", 5)),
        h("div", { class: "plot-hint", kid: "Unlock every villager to meet me!" }), name);
    }

    function hub() {
      const v = village;
      const kept = (store.progress.treasure ?? []).filter((t) => t.status === "kept").length;
      const ready = promotable(v);
      show(
        h("div", { class: "vh" },
          h("div", { class: "vh-promo" }, h("div", { class: "vh-next", id: "promo-hint", "data-spent": String(v.promotions.spent), kid: promotionHint(v.promotions) })),
          h("div", { class: "vh-bells", title: "Village Bells" }, spr("village_bell", 4), h("span", { class: "vh-n", "data-bells": String(v.bells.available), text: `× ${v.bells.available}` })),
          inventoryRow(v.wallet, ["emerald"])),
        ready.length ? h("button", { class: "btn big promo-banner", id: "promo-banner", onclick: promoPicker },
          spr("diamond", 4), h("span", { kid: "Promotion ready!" }),
          h("span", { class: "price-n", text: `× ${v.promotions.available}` })) : null,
        h("div", { class: "village-actions" },
          h("button", { class: "btn big", id: "sell-btn", onclick: sell }, res("emerald", 4), h("span", { kid: "Sell to the village" })),
          h("button", { class: "btn big", id: "pile-btn", onclick: act("opening the Treasure Pile", pile) }, spr("chest", 4), h("span", { kid: "Treasure Pile" }),
            kept ? h("span", { class: "badge-n", "data-kept": String(kept), text: String(kept) }) : null)),
        h("div", { class: "village-plots" }, v.professions.map(plot)));
      if (STATIC) readOnly();
    }

    /** Website copy: the shop is closed (Dad's Mac does the buying). Buttons stay visible but disabled, with a friendly line. */
    function readOnly() {
      L.play.querySelectorAll("button.plot, #sell-btn, #promo-banner").forEach((b) => { b.disabled = true; });
      L.play.prepend(h("div", { class: "static-note", id: "static-note", kid: `The shop opens at ${grownUpPoss()} house. Your emeralds are safe.` }));
    }

    async function pile() {
      await renderPile(app, L, () => start(), mc);
    }

    async function start() {
      village = await refresh();
      hub();
    }

    // ---- promotions: the child chooses which villager moves up one level ------------------------------------------
    function promoPicker() {
      const v = village;
      const cards = promotable(v).map((p) => h("button", { class: "plot have promo-pick", "data-prof": p.id, onclick: () => promoConfirm(p) },
        h("div", { class: "plot-row" }, spr(villagerSprite(p), 5), spr(p.job_block_sprite, 4)),
        h("div", { class: "plot-name", kid: p.name }),
        h("div", { class: "plot-level" }, badge(v, p, 3), h("span", { kid: p.level_name }), h("span", { class: "promo-arrow", text: "→" }),
          badgesFor(v.levels.names)[p.level + 1] ? spr(badgesFor(v.levels.names)[p.level + 1], 3) : null, h("span", { kid: v.levels.names[p.level + 1] }))));
      show(h("div", { class: "picker promo-picker" }, back(hub),
        h("h2", { class: "picker-name", kid: "Who gets a promotion?" }),
        h("div", { class: "village-plots" }, cards)));
    }

    function promoConfirm(p) {
      const v = village;
      const to = v.levels.names[p.level + 1];
      const promote = act("promoting a villager", async () => {
        const r = validatePromoteReply(await postPromote(p.id));
        playFanfare();
        playSparkle(0.8);
        village = await refresh();
        promoted(village.professions.find((q) => q.id === p.id), p.level);
        return r;
      });
      show(h("div", { class: "confirm" },
        h("div", { class: "picker-who" }, spr(villagerSprite(p), 10), spr(p.job_block_sprite, 7)),
        h("h2", { class: "picker-name", kid: `Make the ${p.name} ${to}?` }),
        h("div", { class: "picker-choices" },
          h("button", { class: "btn big", id: "promo-yes", onclick: promote, kid: "Yes!" }),
          h("button", { class: "btn big no", id: "promo-no", onclick: promoPicker, kid: "Not now" }))));
    }

    /** The celebration right after a promotion: the villager's new level and the trades it just opened. */
    function promoted(p, from) {
      const v = village;
      const fresh = p.offers.filter((o) => o.min_level > from && o.min_level <= p.level);
      show(h("div", { class: "picker meet promoted", "data-prof": p.id },
        h("div", { class: "picker-who" }, spr(villagerSprite(p), 10), spr(p.job_block_sprite, 7), badge(v, p, 6)),
        h("h2", { class: "picker-name", kid: `The ${p.name} is now ${p.level_name}!` }),
        h("div", { class: "meet-note", id: "new-trades", kid: "New trades!" }),
        h("div", { class: "promo-new" }, fresh.slice(0, 8).map((o) => spr(o.sprite, 4))),
        h("div", { class: "picker-choices" },
          h("button", { class: "btn big", id: "promoted-shop", onclick: () => shop(p), kid: "See what they sell" }),
          h("button", { class: "btn big", id: "promoted-hub", onclick: hub, kid: "Back to the village" }))));
    }

    // ---- unlock picker ------------------------------------------------------------------------------------
    function picker(p) {
      const v = village;
      const c = unlockChoices(v, p);
      const unlock = (pay) => act("unlocking a villager", async () => {
        const r = await postUnlock(p.id, pay);
        playFanfare();
        playSparkle(0.6);
        showSurprise([r.treasure]);
        village = await refresh();
        meet(village.professions.find((q) => q.id === p.id));
      });
      const choices = c.free
        ? [h("button", { class: "btn big pick-free", id: "pick-free", onclick: unlock("bell") }, h("span", { kid: "Meet me! It's free!" }))]
        : [
          h("button", { class: `btn big pick-bell${c.bell ? "" : " dim"}`, id: "pick-bell", ...(c.bell ? { onclick: unlock("bell") } : { disabled: "" }) },
            spr("village_bell", 4), h("span", { kid: "Use a bell" }), h("span", { class: "price-n", text: `× ${v.bells.available}` })),
          h("button", { class: `btn big pick-emeralds${c.emeralds ? "" : " dim"}`, id: "pick-emeralds", ...(c.emeralds ? { onclick: unlock("emeralds") } : { disabled: "" }) },
            res("emerald", 4), h("span", { kid: "Pay" }), money(p.unlock_emeralds)),
        ];
      show(h("div", { class: "picker" }, back(hub),
        h("div", { class: "picker-who" }, spr(villagerSprite(p), 10), spr(p.job_block_sprite, 7)),
        h("h2", { class: "picker-name", kid: `Meet the ${p.name}?` }),
        h("div", { class: "picker-choices" }, choices)));
    }

    /** The "he arrived!" moment right after an unlock. */
    function meet(p) {
      show(h("div", { class: "picker meet" },
        h("div", { class: "picker-who" }, spr(villagerSprite(p), 10), spr(p.job_block_sprite, 7)),
        h("h2", { class: "picker-name", kid: `The ${p.name} moved in!` }),
        h("div", { class: "meet-note", kid: "Their egg and block are in your Treasure Pile." }),
        h("div", { class: "picker-choices" },
          h("button", { class: "btn big", id: "meet-shop", onclick: () => shop(p), kid: "See what they sell" }),
          h("button", { class: "btn big", id: "meet-hub", onclick: hub, kid: "Back to the village" }))));
    }

    // ---- a villager's trades --------------------------------------------------------------------------------
    function shop(p, bought = null) {
      const v = village;
      const names = v.levels.names;
      const cards = p.offers.map((o) => {
        const st = offerStatus(o, v.wallet);
        const n = treasureCount(o);
        const attrs = { class: `offer ${st}`, "data-offer": o.id };
        if (st === "ok") attrs.onclick = () => confirm(p, o);
        else attrs["aria-disabled"] = "true";
        return h("button", attrs,
          h("div", { class: "offer-pic" }, spr(o.sprite, 5), n > 1 ? h("span", { class: "offer-n", text: `× ${n}` }) : null),
          h("div", { class: "offer-label", kid: o.label }),
          st === "locked" ? h("div", { class: "offer-lock", kid: `Reach ${names[o.min_level]}!` }) : money(o.price));
      });
      show(h("div", { class: "shop" },
        h("div", { class: "shop-head" }, back(hub), spr(villagerSprite(p), 6), spr(p.job_block_sprite, 4),
          h("div", { class: "shop-title", kid: p.name }), h("div", { class: "plot-level shop-level" }, badge(v, p, 3), h("span", { kid: p.level_name })),
          inventoryRow(v.wallet, ["emerald"])),
        bought ? h("div", { class: "bought", id: "bought" }, spr(bought.sprite, 4), h("span", { kid: `${bought.label} is in your Treasure Pile!` })) : null,
        h("div", { class: "offers" }, cards)));
    }

    function confirm(p, o) {
      const buy = act("buying", async () => {
        const r = await postBuy(o.id);
        playJingle();
        playFanfare();
        village = await refresh();
        shop(village.professions.find((q) => q.id === p.id), { label: o.label, sprite: o.sprite });
        return r;
      });
      show(h("div", { class: "confirm" },
        h("div", { class: "card confirm-card" }, spr(o.sprite, 12), h("div", { class: "confirm-label", kid: o.label }), money(o.price)),
        h("div", { class: "picker-choices" },
          h("button", { class: "btn big", id: "buy-yes", onclick: buy, kid: "Buy!" }),
          h("button", { class: "btn big no", id: "buy-no", onclick: () => shop(p), kid: "Not now" }))));
    }

    // ---- sell to the village --------------------------------------------------------------------------------
    function sell() {
      const inv = store.progress.inventory;
      const rows = village.trades.map((t) => {
        const ok = canTrade(t, inv);
        const side = (m) => Object.entries(m).map(([k, n]) => h("span", { class: "trade-side" }, res(k, 3), h("span", { class: "price-n", text: `× ${n}` })));
        return h("button", { class: `trade${ok ? "" : " dim"}`, "data-trade": t.id, ...(ok ? { onclick: act("selling", async () => {
          await postTrade(t.id);
          playJingle();
          village = await refresh();
          sell();
        }) } : { "aria-disabled": "true" }) }, ...side(t.give), h("span", { class: "trade-arrow", text: "→" }), ...side(t.get));
      });
      show(h("div", { class: "sell" },
        h("div", { class: "shop-head" }, back(hub), spr("villager_farmer", 6), h("div", { class: "shop-title", kid: "Sell to the village" }),
          inventoryRow(inv, ["coal", "iron", "gold", "diamond", "wood", "stone", "emerald"])),
        h("div", { class: "trades" }, rows)));
    }

    act("opening the village", start)();
  });
}
