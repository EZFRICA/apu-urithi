"""
The APU memory on both sides (docs/decisions/0015): L1 cache, L2 Doubly Linked List, L3 LanceDB.

Target: apu/mmu/*, guardian/memory/mmu.py, learner/memory/mmu.py

Proves:
  1. DLL insertion positions by block type (temporary at HEAD, project and knowledge right after
     HEAD, fundamental just before TAIL), fixed vs dynamic separation, and pointer integrity.
  2. Dynamic block capacity (MAX_DYNAMIC_BLOCKS = 5) evicts the least recently used dynamic block
     from L2 while keeping its row in L3 LanceDB.
  3. Semantic Page Fault Check (page_in_block): when a paged-out block in L3 is matched by
     search_memory, it is brought back into L2 and promoted to HEAD while evicting the oldest L2
     dynamic block.
  4. L1 cache honours per-type TTL, LRU capacity (MAX_ENTRIES), and invalidation on update.
  5. BMJ promotes only the first relevant result that is a DLL node, on the caller's DLL handle.
  6. L3 LanceDB refuses excluded block types (escalation_event, distress_event) and verifies
     embedding space dimensions and model stamps.
  7. Block proposals and heuristic block opportunity detection share one validated shape.
  8. Guardian's learned pupil threshold lives in their fixed fundamental block and persists from
     one knowledge to the next across dynamic block evictions.
  9. Organisation and side isolation across L1, L2, and L3.
"""

import asyncio
import time

import pytest

from apu import config
from apu.mmu import block_detector, block_proposal, block_types, cache_l1, dll, lance_driver
from guardian.engine import questions
from guardian.memory.mmu import GuardianMmuStore, set_guardian_mmu
from guardian.memory.working import SqliteWorkingMemories
from learner.memory.mmu import LearnerMmuStore


def _fake_embedder(monkeypatch, dim: int = 8):
    """Deterministic vectors keyed by distinctive words so semantic search is fast and exact."""
    keywords = ("safety", "lockout", "voltage", "gloves", "grounding", "breaker", "arc", "thermal")
    monkeypatch.setattr(config, "EMBEDDING_DIM", dim)

    class FakeEmbedder:
        def embed(self, texts: list[str]) -> list[list[float]]:
            out = []
            for text in texts:
                low = (text or "").lower()
                vec = [0.02] * dim
                for idx, kw in enumerate(keywords[:dim]):
                    if kw in low:
                        vec[idx] = 1.0
                norm = sum(x * x for x in vec) ** 0.5
                out.append([x / norm for x in vec])
            return out

    monkeypatch.setattr("apu.embeddings.get_embedder", lambda: FakeEmbedder())


def _assert_dll_integrity(mem: dict) -> None:
    fwd = dll._head_to_tail_order(mem)
    bwd = dll._tail_to_head_order(mem)
    assert fwd == list(reversed(bwd)), f"DLL links broken: fwd={fwd}, bwd={bwd}"
    assert set(fwd) == set(mem["nodes"].keys())
    assert mem["nodes"][mem["head_id"]]["prev"] is None
    assert mem["nodes"][mem["tail_id"]]["next"] is None


def test_dll_invariants_and_insertion_order_by_block_type(tmp_path, monkeypatch):
    _fake_embedder(monkeypatch)
    dll_path = str(tmp_path / "links.json")
    db_path = str(tmp_path / "lancedb")
    stamp_path = str(tmp_path / "stamp.json")

    mem = asyncio.run(dll.init_dll(
        path=dll_path,
        fixed_blocks=dll.GUARDIAN_FIXED_BLOCKS,
        organisation="urithi",
        person_id="sabine",
    ))
    assert dll._head_to_tail_order(mem) == [
        "current_class", "active_knowledge", "teaching_preferences", "guardian_profile",
    ]
    _assert_dll_integrity(mem)

    # 1. temporary inserts at HEAD
    mem = asyncio.run(dll.create_dynamic_block(
        "dyn_temp", "Temp Note", "temporary", "safety check today", ["safety"], "guardian",
        mem, vector=[1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        path=dll_path, db_path=db_path, stamp_path=stamp_path,
    ))
    assert mem["head_id"] == "dyn_temp"
    _assert_dll_integrity(mem)

    # 2. project inserts right after HEAD
    mem = asyncio.run(dll.create_dynamic_block(
        "dyn_proj", "Project Audit", "project", "lockout audit", ["lockout"], "guardian",
        mem, vector=[0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        path=dll_path, db_path=db_path, stamp_path=stamp_path,
    ))
    order = dll._head_to_tail_order(mem)
    assert order[:2] == ["dyn_temp", "dyn_proj"]
    _assert_dll_integrity(mem)

    # 3. knowledge inserts right after HEAD
    mem = asyncio.run(dll.create_dynamic_block(
        "dyn_know", "Voltage Knowledge", "knowledge", "voltage testing", ["voltage"], "guardian",
        mem, vector=[0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        path=dll_path, db_path=db_path, stamp_path=stamp_path,
    ))
    order = dll._head_to_tail_order(mem)
    assert order[:3] == ["dyn_temp", "dyn_know", "dyn_proj"]
    _assert_dll_integrity(mem)

    # 4. fundamental inserts just before TAIL (never at TAIL)
    mem = asyncio.run(dll.create_dynamic_block(
        "dyn_fund", "Core Rule", "fundamental", "gloves always", ["gloves"], "guardian",
        mem, vector=[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0],
        path=dll_path, db_path=db_path, stamp_path=stamp_path,
    ))
    order = dll._head_to_tail_order(mem)
    assert order[-2:] == ["dyn_fund", "guardian_profile"]
    _assert_dll_integrity(mem)

    reloaded = asyncio.run(dll.load_dll(path=dll_path, fixed_blocks=dll.GUARDIAN_FIXED_BLOCKS))
    assert dll._head_to_tail_order(reloaded) == order


def test_dynamic_block_cap_evicts_lru_from_l2_while_keeping_l3(tmp_path, monkeypatch):
    _fake_embedder(monkeypatch)
    store = GuardianMmuStore(str(tmp_path / "guardian_mmu"))
    words = ["safety", "lockout", "voltage", "gloves", "grounding", "breaker"]

    for idx, word in enumerate(words):
        store.create_dynamic_block(
            "urithi", "sabine", f"b{idx}", f"Block {idx}", "knowledge", f"{word} procedure",
        )
        time.sleep(0.002)

    mem = store.load_dll("urithi", "sabine")
    dynamic_ids = [nid for nid, n in mem["nodes"].items() if not n.get("is_fixed", False)]
    assert len(dynamic_ids) == config.MAX_DYNAMIC_BLOCKS
    assert "b0" not in dynamic_ids
    assert set(dynamic_ids) == {"b1", "b2", "b3", "b4", "b5"}
    _assert_dll_integrity(mem)

    # Fixed blocks are never evicted
    for fixed_id, *_ in dll.GUARDIAN_FIXED_BLOCKS:
        assert fixed_id in mem["nodes"]

    # Evicted b0 ("safety procedure") remains in L3 LanceDB
    l3_text = asyncio.run(lance_driver.get_block_content("b0", db_path=store.db_path("urithi", "sabine")))
    assert l3_text == "safety procedure"


def test_page_in_block_restores_evicted_l3_block_into_l2_head(tmp_path, monkeypatch):
    _fake_embedder(monkeypatch)
    store = GuardianMmuStore(str(tmp_path / "guardian_mmu"))
    words = ["safety", "lockout", "voltage", "gloves", "grounding", "breaker"]

    for idx, word in enumerate(words):
        store.create_dynamic_block(
            "urithi", "sabine", f"b{idx}", f"Block {idx}", "knowledge", f"{word} procedure",
        )
        time.sleep(0.002)

    mem = store.load_dll("urithi", "sabine")
    assert "b0" not in mem["nodes"]

    # Searching for "safety procedure" finds b0 in L3, triggers Semantic Page Fault Check
    # (page_in_block) to bring b0 back into L2, evicts the oldest dynamic block (b1), and
    # promotes b0 to HEAD via BMJ.
    hits = store.search("urithi", "sabine", "safety procedure")
    mem = store.load_dll("urithi", "sabine")
    assert any(h["block_id"] == "b0" for h in hits)
    assert "b0" in mem["nodes"]
    assert mem["head_id"] == "b0"
    assert "b1" not in mem["nodes"]
    dynamic_ids = [nid for nid, n in mem["nodes"].items() if not n.get("is_fixed", False)]
    assert len(dynamic_ids) == config.MAX_DYNAMIC_BLOCKS
    _assert_dll_integrity(mem)


def test_bmj_promotes_only_first_dll_hit_on_callers_handle(tmp_path, monkeypatch):
    _fake_embedder(monkeypatch)
    store = GuardianMmuStore(str(tmp_path / "guardian_mmu"))
    store.create_dynamic_block("urithi", "sabine", "b_safety", "Safety", "knowledge", "safety lockout rule")
    time.sleep(0.002)
    store.create_dynamic_block("urithi", "sabine", "b_voltage", "Voltage", "knowledge", "voltage lockout rule")
    time.sleep(0.002)
    store.create_dynamic_block("urithi", "sabine", "b_gloves", "Gloves", "knowledge", "gloves rule")

    mem = store.load_dll("urithi", "sabine")
    before = dll._head_to_tail_order(mem)
    assert before[0] != "b_safety"

    # Search for "safety": both b_safety and b_voltage match, with b_safety ranked first.
    # Only b_safety moves to HEAD and is persisted on disk.
    hits = store.search("urithi", "sabine", "safety")
    assert hits and hits[0]["block_id"] == "b_safety"

    reloaded = store.load_dll("urithi", "sabine")
    assert reloaded["head_id"] == "b_safety"


def test_l1_cache_ttl_lru_and_flush():
    cache_l1.flush_all()
    assert cache_l1.get("guardian:urithi:sabine:b1") is None
    cache_l1.set("guardian:urithi:sabine:b1", "Isolate energy", block_type="knowledge")
    assert cache_l1.get("guardian:urithi:sabine:b1") == "Isolate energy"

    # Expired entry is dropped on get() and on sweep()
    cache_l1._cache["guardian:urithi:sabine:b1"] = ("Isolate energy", time.monotonic() - 1.0)
    assert cache_l1.get("guardian:urithi:sabine:b1") is None

    # LRU capacity bound (MAX_ENTRIES)
    for i in range(cache_l1.MAX_ENTRIES + 10):
        cache_l1.set(f"k_{i}", f"v_{i}", block_type="temporary")
    assert len(cache_l1._cache) <= cache_l1.MAX_ENTRIES
    assert cache_l1.get("k_0") is None

    cache_l1.flush_all()
    assert cache_l1.get_summary()["cached_blocks"] == 0


def test_lance_driver_rejects_excluded_types_and_mismatched_embedding_space(tmp_path, monkeypatch):
    _fake_embedder(monkeypatch, dim=8)
    db_path = str(tmp_path / "lancedb")
    stamp_path = str(tmp_path / "stamp.json")

    for forbidden in ("escalation_event", "distress_event"):
        with pytest.raises(block_types.ForbiddenBlockType):
            asyncio.run(lance_driver.upsert_local_block(
                "bad_1", "sensitive event", forbidden, "local", "local",
                [1.0] * 8, db_path=db_path, stamp_path=stamp_path,
            ))

    asyncio.run(lance_driver.upsert_local_block(
        "k1", "safety procedure", "knowledge", "local", "local",
        [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], db_path=db_path, stamp_path=stamp_path,
    ))
    db = lance_driver.get_db(db_path)
    table = db.open_table("user_memory")
    lance_driver.verify_embedding_space(table, "user_memory", stamp_path=stamp_path, db_path=db_path)

    # 1. Arrow schema dimension check catches a dimension mismatch even when no stamp file exists
    monkeypatch.setattr(config, "EMBEDDING_DIM", 16)
    with pytest.raises(lance_driver.EmbeddingMismatch):
        lance_driver.verify_embedding_space(
            table, "user_memory", stamp_path=str(tmp_path / "missing_stamp.json"), db_path=db_path,
        )

    # 2. Stamp check catches a different embedding model even when the vector dimension is the same
    monkeypatch.setattr(config, "EMBEDDING_DIM", 8)
    monkeypatch.setattr(config, "EMBEDDING_MODEL", "other-embedder-v2")
    with pytest.raises(lance_driver.EmbeddingMismatch):
        lance_driver.verify_embedding_space(table, "user_memory", stamp_path=stamp_path, db_path=db_path)


def test_block_proposal_contract_and_detector_rules():
    mem = {"dynamic_block_count": 0, "dynamic_block_max": 5, "nodes": {}}
    history = [
        {"role": "user", "content": "Explain why we test voltage first"},
        {"role": "assistant", "content": "Because a circuit can stay live."},
        {"role": "user", "content": "I don't understand how the grounding clamp works"},
        {"role": "assistant", "content": "It discharges residual current."},
    ]
    proposal = block_detector.detect_new_block_opportunity(history, mem)
    assert proposal is not None
    assert block_proposal.validate(proposal) is None

    assert block_proposal.validate({}) is not None
    assert block_proposal.validate({"proposed_id": "x", "label": "L", "type": "knowledge", "initial_content": ""}) is not None


def test_guardian_mmu_persists_learned_pupil_threshold_across_knowledges_and_evictions(tmp_path, monkeypatch):
    """The guardian's threshold lives in their fixed fundamental block in GuardianMmuStore:
    it survives dynamic block evictions and applies immediately to the next knowledge they teach."""
    _fake_embedder(monkeypatch)
    g_mmu = GuardianMmuStore(str(tmp_path / "guardian_mmu"))
    set_guardian_mmu(g_mmu)
    wm = SqliteWorkingMemories(str(tmp_path / "working.sqlite3"))

    # On knowledge 1, guardian Sabine passes two questions of importance 3 -> general threshold becomes 4
    # and reason threshold becomes 4.
    mem_one = wm.load("urithi", "map_one")
    questions.record_pass(mem_one, "reason", 3,
                          organisation="urithi", guardian_id="Sabine")
    questions.record_pass(mem_one, "limit", 3,
                          organisation="urithi", guardian_id="sabine")

    level, by_kind, passed = g_mmu.load_threshold("urithi", "sabine")
    assert level == 4 and by_kind["reason"] == 4 and passed == 2
    assert g_mmu.load_threshold("urithi", "Sabine") == (level, by_kind, passed)

    # Push 7 dynamic blocks into Sabine's GuardianMmuStore so dynamic blocks are evicted to L3.
    words = ["safety", "lockout", "voltage", "gloves", "grounding", "breaker", "arc"]
    for idx, word in enumerate(words):
        g_mmu.create_dynamic_block(
            "urithi", "sabine", f"dyn_{idx}", f"Topic {idx}", "knowledge", f"{word} step {idx}",
        )
        time.sleep(0.002)

    # Fixed block `teaching_preferences` is never evicted: on a brand-new knowledge (`map_two`),
    # Sabine's learned threshold is still 4!
    mem_two = wm.load("urithi", "map_two")
    new_level, new_by_kind = questions.threshold_for(
        mem_two, organisation="urithi", guardian_id="sabine",
    )
    assert new_level == 4 and new_by_kind["reason"] == 4
    assert not questions.should_ask(
        questions.QuestionKind.REASON, 3, mem_two,
        organisation="urithi", guardian_id="sabine",
    )
    assert questions.should_ask(
        questions.QuestionKind.REASON, 4, mem_two,
        organisation="urithi", guardian_id="sabine",
    )


def test_mmu_isolates_organisations_and_sides(tmp_path, monkeypatch):
    _fake_embedder(monkeypatch)
    g_mmu = GuardianMmuStore(str(tmp_path / "guardian_mmu"))
    l_mmu = LearnerMmuStore(str(tmp_path / "learner_mmu"))

    g_mmu.save_threshold("urithi", "sabine", threshold=5, by_kind={"reason": 5}, passed=4)
    assert g_mmu.load_threshold("urithi", "sabine")[0] == 5
    assert g_mmu.load_threshold("acme", "sabine")[0] == 3

    l_mmu.record_session_event(
        "urithi", "ada", "body_elec",
        on="unit_1",
        asked={"unit_id": "unit_1", "question": "Why test voltage before grounding?"},
    )
    _, urithi_ctx, _ = l_mmu.tutor_turn("urithi", "ada", "body_elec", "voltage grounding")
    _, acme_ctx, _ = l_mmu.tutor_turn("acme", "ada", "body_elec", "voltage grounding")
    assert "voltage" in urithi_ctx["text"].lower()
    assert "voltage" not in acme_ctx["text"].lower()

    # Direct DLL update without l1_prefix still scopes L1 keys by (organisation, person_id)
    cache_l1.flush_all()
    mem_u = asyncio.run(dll.init_dll(
        path=str(tmp_path / "u.json"), fixed_blocks=dll.GUARDIAN_FIXED_BLOCKS,
        organisation="urithi", person_id="sabine",
    ))
    mem_a = asyncio.run(dll.init_dll(
        path=str(tmp_path / "a.json"), fixed_blocks=dll.GUARDIAN_FIXED_BLOCKS,
        organisation="acme", person_id="sabine",
    ))
    asyncio.run(dll.update_node_content(
        "current_class", "urithi secret", mem_u,
        path=str(tmp_path / "u.json"), db_path=str(tmp_path / "u_db"), stamp_path=str(tmp_path / "u_st.json"),
    ))
    asyncio.run(dll.update_node_content(
        "current_class", "acme secret", mem_a,
        path=str(tmp_path / "a.json"), db_path=str(tmp_path / "a_db"), stamp_path=str(tmp_path / "a_st.json"),
    ))
    assert cache_l1.get("urithi:sabine:current_class") == "urithi secret"
    assert cache_l1.get("acme:sabine:current_class") == "acme secret"

    # Quotes in block_id or filter strings are escaped rather than breaking or widening the WHERE clause
    leaked = asyncio.run(lance_driver.get_block_content(
        "current_class' OR '1'='1", db_path=str(tmp_path / "u_db"),
    ))
    assert leaked is None


def test_mmu_write_back_is_scheduled_after_the_reply_on_both_sides(tmp_path, monkeypatch):
    """Measured in the v1 review: synchronous MMU write-back added ~850 ms to /tell and delayed /ask.
    Both routes schedule the MMU write-back in FastAPI BackgroundTasks so the reply returns first."""
    from fastapi import BackgroundTasks
    from apu import meter
    from exchange.questions import Questions, set_questions
    from guardian.api import routes as guardian_routes
    from guardian.engine.workmap import WorkMapStore
    from guardian.memory.store import get_maps, set_maps
    from learner.api import routes as learner_routes
    from learner.memory.mmu import set_learner_mmu
    from learner.tutor import answer as answering, guard
    from library import store as lib_store
    from tests.support import BODY, community

    _fake_embedder(monkeypatch)
    set_maps(WorkMapStore(str(tmp_path / "maps.sqlite3")))
    g_mmu = GuardianMmuStore(str(tmp_path / "guardian_mmu"))
    l_mmu = LearnerMmuStore(str(tmp_path / "learner_mmu"))
    set_guardian_mmu(g_mmu)
    set_learner_mmu(l_mmu)

    # 1. Guardian /tell schedules record_class_moment in BackgroundTasks
    wmap = get_maps().new("Lockout procedure", "Sabine", "en", organisation="urithi")
    get_maps().save(wmap)
    bg_guardian = BackgroundTasks()
    guardian_reply = guardian_routes.tell(
        guardian_routes.TellBody(map_id=wmap.map_id, said="Close the upstream valve first."),
        bg_guardian,
    )
    assert guardian_reply["proposal"]["number"] == 1
    assert len(bg_guardian.tasks) == 1, "scheduled for after the HTTP reply, not run inside /tell"
    assert g_mmu.read_context("urithi", "sabine")["text"] == ""
    asyncio.run(bg_guardian())
    assert "Close the upstream valve first" in g_mmu.read_context("urithi", "sabine")["text"]

    # 2. Learner /ask schedules write_back in BackgroundTasks with the learner's meter Principal
    lib = lib_store.MemoryKnowledgeStore()
    lib.publish(community())
    lib_store.set_store(lib)
    set_questions(Questions(str(tmp_path / "q.sqlite3")))
    monkeypatch.setattr(guard, "call_extraction_model", lambda *a, **k: "TOPIC")
    monkeypatch.setattr(answering, "call_main_model", lambda *a, **k: "Two organisers handle it [1].")
    principals_seen = []
    orig_write_back = l_mmu.write_back

    def tracked_write_back(*a, **k):
        principals_seen.append(meter._acting.get())
        return orig_write_back(*a, **k)

    monkeypatch.setattr(l_mmu, "write_back", tracked_write_back)
    try:
        bg_learner = BackgroundTasks()
        learner_reply = learner_routes.ask(
            learner_routes.AskBody(person_id="member", organisation="urithi", body_id=BODY,
                                   question="who handles a code of conduct report"),
            bg_learner,
        )
        assert learner_reply["kind"] == "worded"
        assert len(bg_learner.tasks) == 1 and principals_seen == [], "scheduled for after the reply"
        asyncio.run(bg_learner())
        assert len(principals_seen) == 1 and principals_seen[0].person_id == "member"
        assert "who handles a code of conduct report" in l_mmu.read_context("urithi", "member")["text"]
    finally:
        lib_store.set_store(None)
        set_questions(None)


def test_concurrent_background_mmu_write_and_save_threshold_never_lose_the_learned_threshold(
    tmp_path, monkeypatch
):
    """A background MMU write and a concurrent save_threshold keep both the moment and the threshold."""
    import threading
    import time
    import apu.mmu.store as mmu_store_mod
    from apu.mmu.store import MemoryMmuLocks, get_mmu_locks, set_mmu_locks
    from guardian.memory.mmu import GuardianMmuStore

    _fake_embedder(monkeypatch)
    custom_locks = MemoryMmuLocks()
    set_mmu_locks(custom_locks)
    assert get_mmu_locks() is custom_locks

    g_mmu = GuardianMmuStore(str(tmp_path / "guardian_mmu"))
    extractor_started = threading.Event()
    threshold_four_saved = threading.Event()
    inside_write_back_lock = threading.Event()

    def slow_extractor(*_a, **_k):
        extractor_started.set()
        threshold_four_saved.wait(timeout=5.0)
        return (
            '{"current_class": "Bleed residual line pressure.", '
            '"active_knowledge": "Step two: bleed residual line pressure."}'
        )

    monkeypatch.setattr(mmu_store_mod, "_extractor_ready", lambda: True)
    monkeypatch.setattr(mmu_store_mod, "call_extraction_model", slow_extractor)

    orig_load_dll = g_mmu.load_dll
    load_calls_after_extractor = 0

    def tracked_load_dll(org, pid):
        nonlocal load_calls_after_extractor
        res = orig_load_dll(org, pid)
        if threshold_four_saved.is_set() and threading.current_thread().name == "bg-mmu":
            load_calls_after_extractor += 1
            if load_calls_after_extractor == 1:
                inside_write_back_lock.set()
                time.sleep(0.05)
        return res

    monkeypatch.setattr(g_mmu, "load_dll", tracked_load_dll)

    t_bg = threading.Thread(
        name="bg-mmu",
        target=g_mmu.record_class_moment,
        args=("urithi", "sabine", "Lockout procedure"),
        kwargs={"said": "Step two: bleed residual line pressure before opening."},
    )
    t_bg.start()

    assert extractor_started.wait(timeout=5.0)
    # 1. Guardian passes a question while the slow extraction model is in flight -> threshold 4
    g_mmu.save_threshold("urithi", "sabine", threshold=4, by_kind={"order": 3}, passed=3)
    assert g_mmu.load_threshold("urithi", "sabine")[0] == 4
    threshold_four_saved.set()

    # 2. Guardian passes another question while write_back holds the per-person lock -> threshold 5
    assert inside_write_back_lock.wait(timeout=5.0)
    g_mmu.save_threshold("urithi", "sabine", threshold=5, by_kind={"order": 6}, passed=6)

    t_bg.join(timeout=5.0)
    assert not t_bg.is_alive()

    level, by_kind, passed = g_mmu.load_threshold("urithi", "sabine")
    assert (level, by_kind, passed) == (5, {"order": 6}, 6)
    ctx = g_mmu.read_context("urithi", "sabine")["text"]
    assert "Bleed residual line pressure" in ctx


def test_save_threshold_between_record_class_moment_lock_and_search_never_loses_threshold(
    tmp_path, monkeypatch
):
    """When save_threshold runs after record_class_moment leaves its initial lock and before
    search performs BMJ promotion, search re-reads the DLL under the lock instead of overwriting
    the threshold with a DLL read earlier."""
    import threading
    from apu import embeddings
    import apu.mmu.store as mmu_store_mod
    from guardian.memory.mmu import GuardianMmuStore

    _fake_embedder(monkeypatch)
    base_embedder = embeddings.get_embedder()
    g_mmu = GuardianMmuStore(str(tmp_path / "guardian_mmu"))

    said_line = "Step one: lockout the main breaker and verify zero voltage."
    between_lock_and_search = threading.Event()
    threshold_saved = threading.Event()

    class SlowQueryEmbedder:
        def embed(self, texts: list[str]) -> list[list[float]]:
            if (
                threading.current_thread().name == "bg-search-race"
                and texts == [said_line]
                and not between_lock_and_search.is_set()
            ):
                between_lock_and_search.set()
                threshold_saved.wait(timeout=5.0)
            return base_embedder.embed(texts)

    monkeypatch.setattr("apu.embeddings.get_embedder", lambda: SlowQueryEmbedder())
    monkeypatch.setattr(mmu_store_mod, "_extractor_ready", lambda: False)

    t_bg = threading.Thread(
        name="bg-search-race",
        target=g_mmu.record_class_moment,
        args=("urithi", "sabine", "Lockout procedure"),
        kwargs={"said": said_line},
    )
    t_bg.start()

    assert between_lock_and_search.wait(timeout=5.0)
    g_mmu.save_threshold("urithi", "sabine", threshold=4, by_kind={"order": 3}, passed=3)
    assert g_mmu.load_threshold("urithi", "sabine")[0] == 4
    threshold_saved.set()

    t_bg.join(timeout=5.0)
    assert not t_bg.is_alive()

    level, by_kind, passed = g_mmu.load_threshold("urithi", "sabine")
    assert (level, by_kind, passed) == (4, {"order": 3}, 3)
