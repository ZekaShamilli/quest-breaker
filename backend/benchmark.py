"""Labeled benchmark: generated quest graphs with known planted bugs and look-alike traps.

Each graph has 6 acts: hub_i -> (a_i | b_i) -> hub_{i+1}. Four storylines are planted per graph:
  flag_bug    entity destroyed on branch a_i, needed at a later hub; ALSO encoded as state flags
  text_bug    same contradiction, but only in the prose (no flags) - what real scripts look like
  safe_spare  look-alike trap: the entity is spared on a_i, then needed later   -> no bug
  safe_order  look-alike trap: the entity is needed BEFORE it is destroyed       -> no bug
Ground truth = the hub where the contradiction shows up (plus the branch that caused it).
"""
import random

from models import QuestGraph

ENTITIES = [
    dict(key="garrick", title="The Smith's Debt",
         kill="You execute Garrick the blacksmith in the square for his unpaid debts.",
         spare="You fine Garrick the blacksmith and let him keep his forge.",
         need="Garrick the blacksmith forges the silver blade you need for what lies ahead."),
    dict(key="ysolde", title="The Rebel's Fate",
         kill="You hand Ysolde the rebel leader to the Baron, who hangs her at dawn.",
         spare="You warn Ysolde the rebel leader and she slips away into the hills.",
         need="Ysolde the rebel leader rides beside you at the head of her fighters."),
    dict(key="bridge", title="The Old Bridge",
         kill="You burn the old stone bridge so the pursuing soldiers cannot follow; it collapses into the gorge.",
         spare="You post guards on the old stone bridge to keep it safe.",
         need="Your caravan crosses the gorge over the old stone bridge."),
    dict(key="aydan", title="The Mocking Song",
         kill="You throw Aydan the minstrel into the dungeon; weeks later he dies of fever in his cell.",
         spare="You pay Aydan the minstrel's fine and he sings you a song of thanks.",
         need="Aydan the minstrel performs the royal wedding song for the court."),
    dict(key="oracle", title="The Oracle's Crystal",
         kill="You shatter the Oracle's crystal and the Oracle of the Marsh falls silent forever.",
         spare="You leave an offering at the shrine of the Oracle of the Marsh.",
         need="The Oracle of the Marsh speaks and reveals where the lost crown lies."),
    dict(key="lambert", title="Splitting the Bounty",
         kill="You refuse to share the bounty; Lambert, your sword-brother, leaves for the far north, swearing never to fight beside you again.",
         spare="You split the bounty with Lambert, your sword-brother, and he laughs and claps your shoulder.",
         need="Lambert, your sword-brother, guards your back through the whole fight."),
    dict(key="gull", title="The Smugglers' Ship",
         kill="You scuttle the Gull's Wing in the harbor so the smugglers can never use her again.",
         spare="You inspect the smugglers' ship, the Gull's Wing, and find her hull sound and seaworthy.",
         need="The smugglers' ship, the Gull's Wing, carries you across the strait to the island fortress."),
    dict(key="mirza", title="The Poisoned Feast",
         kill="Elder Mirza drinks from the poisoned cup at the feast and dies before morning.",
         spare="You swap the poisoned cup and Elder Mirza survives the feast.",
         need="Elder Mirza blesses the new alliance in front of both clans."),
]
PLACES = ["the border village", "a ruined watchtower", "the river crossing", "the merchant city", "the mountain pass",
          "the old monastery", "the royal capital"]
NEUTRAL = ["You stay out of it and keep moving.", "You decide this is none of your business and ride on.",
           "You spend the evening resting and mending your gear.", "You ask around for work and find little."]
ACTS = 6


def make_graph(seed: int) -> tuple[QuestGraph, list[dict]]:
    rng = random.Random(seed)
    entities = rng.sample(ENTITIES, 4)
    kinds = ["flag_bug", "text_bug", "safe_spare", "safe_order"]
    hubs = {i: [f"You arrive at {PLACES[i]}."] for i in range(ACTS + 1)}
    branch_a = {i: None for i in range(ACTS)}
    pre, mut, init, labels = {}, {}, {}, []

    for ent, kind in zip(entities, kinds):
        while True:  # one planted event per branch, one requirement per hub
            if kind == "safe_order":
                j = rng.randrange(0, ACTS)
                i = rng.randrange(j, ACTS)
            else:
                i = rng.randrange(0, ACTS - 1)
                j = rng.randrange(i + 1, ACTS + 1)
            if branch_a[i] is None and len(hubs[j]) == 1:
                break
        branch_a[i] = (ent["title"], ent["spare" if kind == "safe_spare" else "kill"])
        hubs[j].append(ent["need"])
        if kind == "flag_bug":
            init[ent["key"]] = "present"
            mut[f"a{i}"] = {ent["key"]: "gone"}
            pre[f"hub{j}"] = {ent["key"]: "present"}
        if kind.endswith("bug"):
            labels.append(dict(kind=kind, need=f"hub{j}", cause=f"a{i}", entity=ent["key"]))

    nodes = []
    for i in range(ACTS + 1):
        nodes.append(dict(id=f"hub{i}", title=f"Act {i + 1}: {PLACES[i].title()}", description=" ".join(hubs[i]),
                          pre_conditions=pre.get(f"hub{i}", {}), next_nodes=[f"a{i}", f"b{i}"] if i < ACTS else []))
        if i < ACTS:
            title, text = branch_a[i] or ("A Quiet Detour", rng.choice(NEUTRAL))
            nodes.append(dict(id=f"a{i}", title=title, description=text, state_mutations=mut.get(f"a{i}", {}),
                              next_nodes=[f"hub{i + 1}"]))
            nodes.append(dict(id=f"b{i}", title="Moving On", description=rng.choice(NEUTRAL), next_nodes=[f"hub{i + 1}"]))
    return QuestGraph(name=f"bench_{seed:02d}", start="hub0", initial_state=init, nodes=nodes), labels


def benchmark(n: int = 16, offset: int = 0) -> list[tuple[QuestGraph, list[dict]]]:
    return [make_graph(s) for s in range(offset, offset + n)]
