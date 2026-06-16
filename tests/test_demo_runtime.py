import subprocess
import threading

from demo import (
    CodexCliAnswerGenerator,
    ConversationSession,
    ConversationTurn,
    DeterministicDemoAnswers,
    GlobalHotkeyController,
    LLMPromptBuilder,
    LocalInferenceAnswerGenerator,
    NoLLMAnswerGenerator,
    QueryResultCache,
    RetrievalEngine,
    RetrievalResult,
    SourceSnippetResolver,
    SpotlightDemo,
    _pick_llm,
)
from retrieval.reranker import LexicalReranker


def test_query_result_cache_normalizes_query_and_returns_copies():
    cache = QueryResultCache(max_entries=2)
    hits = [{"id": "1", "file_path": "src/App/Document.cpp", "text": "save document"}]

    cache.put("  Save   Document  ", 8, hits)
    cached = cache.get("save document", 8)
    assert cached == hits

    cached[0]["file_path"] = "mutated"
    assert cache.get("SAVE DOCUMENT", 8)[0]["file_path"] == "src/App/Document.cpp"


def test_llm_prompt_builder_uses_retrieved_summaries_not_raw_code():
    builder = LLMPromptBuilder()
    raw_source = "\n".join(
        [
            "void Document::save() {",
            "    writeObjects();",
            "    saveToFile();",
            "}",
        ]
    )
    hits = [
        {
            "file_path": "src/App/Document.cpp",
            "symbol_name": "Document::save",
            "kind": "method",
            "line_start": 10,
            "line_end": 24,
            "text": raw_source,
        }
    ]

    prompt = builder.build_user_prompt("Trace Document save", hits)

    assert "Retrieved summaries:" in prompt
    assert "Document::save" in prompt
    assert "method" in prompt
    assert "void Document::save()" not in prompt
    assert "src/App/Document.cpp" not in prompt
    assert "Interpretation:" not in prompt


def test_deterministic_demo_answers_match_vetted_queries():
    answers = DeterministicDemoAnswers()

    dispatch = answers.answer_for(DeterministicDemoAnswers.DISPATCH_QUERY)
    jacobian = answers.answer_for(DeterministicDemoAnswers.JACOBIAN_QUERY)
    constraint = answers.answer_for(DeterministicDemoAnswers.CONSTRAINT_ERROR_QUERY)

    assert dispatch is not None
    assert "return solve_BFGS" in dispatch
    assert "return solve_LM" in dispatch
    assert "return solve_DL" in dispatch
    assert jacobian is not None
    assert "clist[i]->grad" in jacobian
    assert "A = J.transpose() * J" in jacobian
    assert constraint is not None
    assert "pull-based" in constraint
    assert "calcResidual" in constraint


def test_deterministic_demo_answers_tolerate_minor_query_variation():
    answers = DeterministicDemoAnswers()

    dispatch = answers.answer_for(
        "How does System::solve dispatch to solve_BFGS, solve_LM, and solve_DL?"
    )
    jacobian = answers.answer_for(
        "How does SubSystem::calcJacobi build the Jacobian and how does System::solve_LM use it?"
    )
    constraint = answers.answer_for(
        "When ConstraintCoincident changes, how does SubSystem::error reach the GCS solver?"
    )

    assert dispatch == DeterministicDemoAnswers.DISPATCH_ANSWER
    assert jacobian == DeterministicDemoAnswers.JACOBIAN_ANSWER
    assert constraint == DeterministicDemoAnswers.CONSTRAINT_ERROR_ANSWER


def test_source_snippet_resolver_enriches_exact_cpp_overload(tmp_path):
    source = tmp_path / "src" / "Mod" / "Sketcher" / "App" / "planegcs" / "GCS.cpp"
    source.parent.mkdir(parents=True)
    source.write_text(
        "\n".join(
            [
                "int System::solve(VEC_pD& params, bool isFine, Algorithm alg, bool isRedundantsolving)",
                "{",
                "    return solve(params, isFine, alg, isRedundantsolving);",
                "}",
                "",
                "int System::solve(SubSystem* subsys, bool isFine, Algorithm alg, bool isRedundantsolving)",
                "{",
                "    if (alg == BFGS) {",
                "        return solve_BFGS(subsys, isFine, isRedundantsolving);",
                "    }",
                "    else if (alg == LevenbergMarquardt) {",
                "        return solve_LM(subsys, isRedundantsolving);",
                "    }",
                "    else if (alg == DogLeg) {",
                "        return solve_DL(subsys, isRedundantsolving);",
                "    }",
                "    return Failed;",
                "}",
                "",
                "int System::solve(SubSystem* subsysA, SubSystem* subsysB, bool isFine, bool isRedundantsolving)",
                "{",
                "    return solve(subsysA, isFine, DogLeg, isRedundantsolving);",
                "}",
            ]
        ),
        encoding="utf-8",
    )
    resolver = SourceSnippetResolver(roots=(tmp_path,), max_chars=1200)
    hits = [
        {
            "file_path": "src/Mod/Sketcher/App/planegcs/GCS.cpp",
            "symbol_name": "solve_BFGS",
            "text": "int System::solve_BFGS(SubSystem* subsys, bool isFine);",
            "line_start": 1,
            "line_end": 1,
        }
    ]

    result = resolver.enrich(
        "In GCS.cpp, how does System::solve(SubSystem* subsys, bool isFine, Algorithm alg, "
        "bool isRedundantsolving) dispatch to solve_BFGS, solve_LM, and solve_DL?",
        hits,
    )

    text = result[0]["text"]
    assert "return solve_BFGS(subsys, isFine, isRedundantsolving);" in text
    assert "return solve_LM(subsys, isRedundantsolving);" in text
    assert "return solve_DL(subsys, isRedundantsolving);" in text
    assert "return solve(params, isFine, alg, isRedundantsolving);" not in text
    assert result[0]["_source_excerpt"]


def test_source_snippet_resolver_focuses_long_function_on_query_terms(tmp_path):
    source = tmp_path / "src" / "Mod" / "Sketcher" / "App" / "planegcs" / "GCS.cpp"
    source.parent.mkdir(parents=True)
    filler = [f"    int filler_{index} = {index};" for index in range(80)]
    source.write_text(
        "\n".join(
            [
                "int System::solve_LM(SubSystem* subsys, bool isRedundantsolving)",
                "{",
                *filler,
                "    subsys->calcJacobi(J);",
                "    A = J.transpose() * J;",
                "    g = J.transpose() * e;",
                *filler,
                "    if (dF > 0. && dL > 0.) {  // reduction in error, increment is accepted",
                "        x = x_new;",
                "        e = e_new;",
                "    }",
                "}",
            ]
        ),
        encoding="utf-8",
    )
    resolver = SourceSnippetResolver(roots=(tmp_path,), max_chars=900)

    snippet = resolver.extract(
        "How does System::solve_LM use SubSystem::calcJacobi and accept the LM step?",
        source,
        "System::solve_LM",
    )

    assert snippet is not None
    assert "subsys->calcJacobi(J);" in snippet.text
    assert "A = J.transpose() * J;" in snippet.text
    assert "increment is accepted" in snippet.text


def test_llm_prompt_builder_includes_follow_up_history():
    builder = LLMPromptBuilder()
    hits = [
        {"file_path": "src/Gui/GLPainter.cpp", "text": "void Polyline::addNode(const QPoint& p)"},
    ]
    history = (ConversationTurn("Where is Polyline?", "It is in GLPainter."),)

    prompt = builder.build_user_prompt("What mutates the vertex list?", hits, history)

    assert "Conversation so far:" in prompt
    assert "Previous question: Where is Polyline?" in prompt
    assert "Previous answer: It is in GLPainter." in prompt
    assert "Question: What mutates the vertex list?" in prompt


def test_local_inference_answer_generator_streams_retrieved_context_through_runtime():
    class FakeRuntime:
        def __init__(self):
            self.prompts = []

        def generate_stream(self, prompt: str):
            self.prompts.append(prompt)
            yield "Local"
            yield " answer"

    runtime = FakeRuntime()
    generator = LocalInferenceAnswerGenerator(runtime=runtime)
    tokens = []
    done = []

    generator.stream(
        "Where is save?",
        [{"file_path": "src/App/Document.cpp", "text": "void Document::save()"}],
        tokens.append,
        done.append,
        history=(ConversationTurn("Previous?", "Previous answer."),),
    )

    assert tokens == ["Local answer"]
    assert done == [None]
    assert "Retrieved summaries:" in runtime.prompts[0]
    assert "src/App/Document.cpp" not in runtime.prompts[0]
    assert "Previous question: Previous?" in runtime.prompts[0]


def test_local_inference_answer_generator_shapes_raw_model_output():
    class FakeRuntime:
        def generate_stream(self, prompt: str):
            yield r"--- File: src\app\service.py | Language: python | Tier: 1 ---"
            yield "\nclass Service:\n"
            yield "    def handle(self):\n"
            yield "        return value"

    tokens = []
    done = []
    LocalInferenceAnswerGenerator(runtime=FakeRuntime()).stream(
        "Where is service?",
        [{"file_path": "src/app/service.py", "text": "class Service:\n    def handle(self): pass"}],
        tokens.append,
        done.append,
    )

    answer = "".join(tokens)
    assert done == [None]
    assert "Retrieved summaries:" in answer
    assert r"src\app\service.py" not in answer
    assert "class Service:" not in answer
    assert "def handle" not in answer
    assert "Service" in answer


def test_codex_cli_answer_generator_routes_prompt_to_local_agent_command(tmp_path):
    calls = []

    def fake_runner(args, prompt, output_path, timeout_seconds):
        calls.append(
            {
                "args": args,
                "prompt": prompt,
                "output_path": output_path,
                "timeout_seconds": timeout_seconds,
            }
        )
        output_path.write_text("Codex answer", encoding="utf-8")
        return 0, "", ""

    generator = CodexCliAnswerGenerator(codex_path="codex", runner=fake_runner, output_dir=tmp_path)
    tokens = []
    done = []

    generator.stream(
        "Where is save?",
        [{"file_path": "src/App/Document.cpp", "text": "void Document::save()"}],
        tokens.append,
        done.append,
    )

    assert "".join(tokens) == "Codex answer"
    assert done == [None]
    assert calls
    assert "exec" in calls[0]["args"]
    assert "--output-last-message" in calls[0]["args"]
    assert "Retrieved summaries:" in calls[0]["prompt"]
    assert "src/App/Document.cpp" not in calls[0]["prompt"]


def test_spotlight_demo_synthesizes_summary_without_file_path_dump():
    demo = SpotlightDemo.__new__(SpotlightDemo)
    hits = [
        {
            "file_path": "src/App/Document.cpp",
            "symbol_name": "Document::save",
            "kind": "method",
            "line_start": 10,
            "line_end": 24,
            "text": "void Document::save() {\n    writeObjects();\n    saveToFile();\n}",
        },
        {
            "file_path": "src/App/Document.cpp",
            "symbol_name": "Document::saveToFile",
            "kind": "method",
            "line_start": 30,
            "line_end": 44,
            "text": "void Document::saveToFile() {\n    ZipWriter writer;\n}",
        },
    ]

    response = demo._synthesize(hits)

    assert "src/App/Document.cpp" not in response
    assert "void Document::save()" not in response
    assert "Document::save" in response
    assert "2 relevant artifact" in response


def test_codex_cli_runner_writes_prompt_to_stdin_as_utf8_bytes(monkeypatch, tmp_path):
    calls = []

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(args, **kwargs):
        calls.append({"args": args, **kwargs})
        return Completed()

    monkeypatch.setattr("demo.subprocess.run", fake_run)

    prompt = "context has unicode: \u2013 and \u00b7"

    CodexCliAnswerGenerator._run_codex(
        ["codex", "exec", "-"],
        prompt,
        tmp_path / "answer.txt",
        12.0,
    )

    assert calls
    assert calls[0]["input"] == prompt.encode("utf-8")
    assert calls[0]["text"] is False
    assert "encoding" not in calls[0]
    assert calls[0]["creationflags"] == subprocess.CREATE_NO_WINDOW
    assert calls[0]["startupinfo"].dwFlags & subprocess.STARTF_USESHOWWINDOW
    assert calls[0]["startupinfo"].wShowWindow == subprocess.SW_HIDE


def test_pick_llm_uses_codex_fallback_when_local_inference_is_unavailable(monkeypatch):
    monkeypatch.delenv("DSEL_LLM_BACKEND", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    class FakeLocal:
        ready = False

    class FakeCodex:
        ready = True

    monkeypatch.setattr("demo.LocalInferenceAnswerGenerator", FakeLocal)
    monkeypatch.setattr("demo.CodexCliAnswerGenerator", FakeCodex)

    generator = _pick_llm()

    assert isinstance(generator, FakeCodex)


def test_pick_llm_can_disable_local_inference(monkeypatch):
    monkeypatch.setenv("DSEL_LLM_BACKEND", "none")

    generator = _pick_llm()

    assert isinstance(generator, NoLLMAnswerGenerator)
    assert not generator.ready


def test_conversation_session_preserves_retrieved_context_for_follow_ups():
    session = ConversationSession()
    hits = [{"file_path": "src/App/Document.cpp", "text": "void Document::save()"}]

    session.start(hits)
    session.record_answer("Where is save?", "It is in Document.cpp.")

    assert session.can_follow_up()
    assert session.hits == hits
    assert session.history == (ConversationTurn("Where is save?", "It is in Document.cpp."),)


def test_retrieval_engine_caches_reranked_results():
    class FakeStore:
        def __init__(self):
            self.calls = 0

        def get_artifacts_by_file_paths(self, file_paths, user_tier, max_per_file=4):
            return []

        def filename_search(self, query, user_tier, max_per_file=3, include_text_fallback=True):
            return []

        def file_path_search(self, query, user_tier, top_k=80):
            self.calls += 1
            return [
                {"id": "1", "file_path": "a.py", "score": 1.0},
                {"id": "2", "file_path": "a.py", "score": 0.9},
                {"id": "3", "file_path": "b.py", "score": 0.8},
            ]

    class FakeReranker:
        def rerank(self, query, hits, top_m):
            return hits[:top_m]

    engine = RetrievalEngine.__new__(RetrievalEngine)
    engine._store = FakeStore()
    engine._searcher = None
    engine._reranker = FakeReranker()
    engine._cache = QueryResultCache(max_entries=4)
    engine._use_vector = False
    engine._use_full_text = False
    engine._use_filename_sql = False

    first = engine.search("Document save", top_k=2)
    second = engine.search(" document   SAVE ", top_k=2)

    assert not first.cached
    assert second.cached
    assert engine._store.calls == 1
    assert [hit["file_path"] for hit in second.hits] == ["a.py", "b.py"]


def test_retrieval_engine_warmup_loads_path_and_lexical_caches():
    class FakeStore:
        def __init__(self):
            self.calls = []

        def warm_path_cache(self):
            self.calls.append("path")

        def warm_lexical_cache(self):
            self.calls.append("lexical")

        def warm_cache(self):
            self.calls.append("vector")

    engine = RetrievalEngine.__new__(RetrievalEngine)
    engine._store = FakeStore()
    engine._use_vector = False

    engine._warmup()

    assert engine._store.calls == ["path", "lexical"]


def test_retrieval_engine_uses_store_searches_without_domain_aliases():
    class FakeStore:
        def __init__(self):
            self.alias_calls = []
            self.path_queries = []

        def get_artifacts_by_file_paths(self, file_paths, user_tier, max_per_file=4):
            self.alias_calls.append(tuple(file_paths))
            return []

        def file_path_search(self, query, user_tier, top_k=80):
            self.path_queries.append(query)
            return [
                {
                    "id": "polyline-impl",
                    "file_path": "src/render/Polyline.cpp",
                    "symbol_name": "Polyline::addNode",
                    "kind": "method",
                    "text": "addNode updates the vertex list",
                    "score": 5.0,
                }
            ]

    class FakeReranker:
        def rerank(self, query, hits, top_m):
            return hits[:top_m]

    engine = RetrievalEngine.__new__(RetrievalEngine)
    engine._store = FakeStore()
    engine._searcher = None
    engine._reranker = FakeReranker()
    engine._cache = QueryResultCache(max_entries=4)
    engine._use_vector = False
    engine._use_full_text = False
    engine._use_filename_sql = False

    result = engine.search("where does polylines vertex live", top_k=5)

    assert engine._store.alias_calls == []
    assert engine._store.path_queries == ["where does polylines vertex live"]
    assert result.hits[0]["file_path"] == "src/render/Polyline.cpp"


def test_retrieval_engine_prefers_symbol_hits_over_path_noise_for_code_identifiers():
    class FakeStore:
        def get_artifacts_by_file_paths(self, file_paths, user_tier, max_per_file=4):
            return []

        def file_path_search(self, query, user_tier, top_k=80):
            return [
                {
                    "id": "noise-around",
                    "file_path": "src/3rdParty/salomesmesh/src/StdMeshers/StdMeshers_SegmentLengthAroundVertex.cpp",
                    "symbol_name": "SMESH_Hypothesis",
                    "kind": "function",
                    "text": "StdMeshers segment length around vertex",
                    "score": 4.0,
                },
                {
                    "id": "noise-dependencies",
                    "file_path": "cMake/FreeCAD_Helpers/CheckInterModuleDependencies.cmake",
                    "symbol_name": "chunk-1",
                    "kind": "chunk",
                    "text": "CheckInterModuleDependencies",
                    "score": 4.0,
                },
            ]

        def lexical_search(self, query, user_tier, top_k=80):
            return [
                {
                    "id": f"toposhape-{symbol}",
                    "file_path": "src/Mod/Part/App/TopoShapePyImp.cpp",
                    "symbol_name": symbol,
                    "metadata": {"qualified_name": f"TopoShapePy::{symbol}"},
                    "kind": "method",
                    "text": text,
                    "line_start": line,
                    "line_end": line,
                    "score": 1.0,
                }
                for symbol, text, line in [
                    ("getEdges", "Py::List TopoShapePy::getEdges() const; TopAbs_EDGE", 2867),
                    ("getVertexes", "Py::List TopoShapePy::getVertexes() const; TopAbs_VERTEX", 2847),
                    ("getWires", "Py::List TopoShapePy::getWires() const; TopAbs_WIRE", 2872),
                ]
            ]

    engine = RetrievalEngine.__new__(RetrievalEngine)
    engine._store = FakeStore()
    engine._searcher = None
    engine._reranker = LexicalReranker()
    engine._cache = QueryResultCache(max_entries=4)
    engine._use_vector = False
    engine._use_full_text = True
    engine._use_filename_sql = False

    result = engine.search("the dependencies around getEdges(), getVertexes(), and getWires()", top_k=5)

    assert result.hits[0]["file_path"] == "src/Mod/Part/App/TopoShapePyImp.cpp"
    assert result.hits[0]["symbol_name"] == "getEdges, getVertexes, getWires"
    assert "TopAbs_EDGE" in result.hits[0]["text"]
    assert "TopAbs_VERTEX" in result.hits[0]["text"]
    assert "TopAbs_WIRE" in result.hits[0]["text"]


def test_global_hotkey_controller_fires_once_per_ctrl_alt_chord():
    class Key:
        ctrl = "ctrl"
        ctrl_l = "ctrl_l"
        ctrl_r = "ctrl_r"
        alt = "alt"
        alt_l = "alt_l"
        alt_r = "alt_r"
        alt_gr = "alt_gr"

    class Root:
        def after(self, delay, callback):
            if delay == 0:
                callback()

    calls = []
    controller = GlobalHotkeyController(Root(), lambda: calls.append("shown"))
    controller._keyboard = type("Keyboard", (), {"Key": Key})

    controller._on_press(Key.ctrl_l)
    controller._on_press(Key.alt_l)
    controller._on_press(Key.alt_l)
    controller._on_release(Key.alt_l)
    controller._on_press(Key.alt_l)

    assert calls == ["shown", "shown"]


def test_global_hotkey_controller_recovers_when_release_is_missed(monkeypatch):
    class Key:
        ctrl = "ctrl"
        ctrl_l = "ctrl_l"
        ctrl_r = "ctrl_r"
        alt = "alt"
        alt_l = "alt_l"
        alt_r = "alt_r"
        alt_gr = "alt_gr"

    class Root:
        def after(self, delay, callback):
            if delay == 0:
                callback()

    now = [100.0]
    monkeypatch.setattr("demo.time.monotonic", lambda: now[0])

    calls = []
    controller = GlobalHotkeyController(Root(), lambda: calls.append("shown"))
    controller._keyboard = type("Keyboard", (), {"Key": Key})

    controller._on_press(Key.ctrl_l)
    controller._on_press(Key.alt_l)
    now[0] += 1.0
    controller._on_press(Key.ctrl_l)

    assert calls == ["shown", "shown"]


def test_global_hotkey_controller_poll_transition_fires_once(monkeypatch):
    class Root:
        def after(self, delay, callback):
            if delay == 0:
                callback()

    now = [100.0]
    monkeypatch.setattr("demo.time.monotonic", lambda: now[0])

    calls = []
    controller = GlobalHotkeyController(Root(), lambda: calls.append("shown"))

    def poll(ctrl_down, alt_down):
        both_down = ctrl_down and alt_down
        if both_down and not controller._both_down and controller._can_fire():
            controller._fire()
        controller._both_down = both_down
        if not both_down:
            controller._fired = False

    poll(False, False)
    poll(True, False)
    poll(True, True)
    poll(True, True)
    poll(False, False)
    now[0] += 1.0
    poll(True, True)

    assert calls == ["shown", "shown"]


def test_global_hotkey_controller_poll_recovers_when_release_transition_is_missed(monkeypatch):
    class Root:
        def after(self, delay, callback):
            if delay == 0:
                callback()

    now = [100.0]
    monkeypatch.setattr("demo.time.monotonic", lambda: now[0])

    calls = []
    controller = GlobalHotkeyController(Root(), lambda: calls.append("shown"))

    controller._handle_hotkey_state(ctrl_down=True, alt_down=True, ctrl_pressed=True, alt_pressed=False)
    controller._handle_hotkey_state(ctrl_down=True, alt_down=True, ctrl_pressed=False, alt_pressed=False)
    now[0] += 1.0
    controller._handle_hotkey_state(ctrl_down=True, alt_down=True, ctrl_pressed=False, alt_pressed=False)
    controller._handle_hotkey_state(ctrl_down=True, alt_down=True, ctrl_pressed=True, alt_pressed=False)

    assert calls == ["shown", "shown"]


def test_global_hotkey_controller_queues_background_callbacks_for_tk_thread(monkeypatch):
    class Root:
        def after(self, delay, callback):
            raise AssertionError("background hotkey path must not call Tk directly")

    calls = []
    controller = GlobalHotkeyController(Root(), lambda: calls.append("shown"))
    controller._tk_thread_id = -1

    controller._fire()

    assert calls == []

    controller._tk_thread_id = threading.get_ident()
    controller._drain_events()

    assert calls == ["shown"]


def test_spotlight_demo_toggle_hides_visible_window_and_shows_hidden_window():
    class Root:
        def __init__(self):
            self.visible = True

        def winfo_viewable(self):
            return self.visible

    demo = SpotlightDemo.__new__(SpotlightDemo)
    demo.root = Root()
    calls = []
    demo.hide = lambda: (calls.append("hide"), setattr(demo.root, "visible", False))
    demo.show = lambda: (calls.append("show"), setattr(demo.root, "visible", True))

    demo.toggle()
    demo.toggle()

    assert calls == ["hide", "show"]


def test_spotlight_demo_hide_preserves_expanded_state_and_process():
    class Root:
        def __init__(self):
            self.withdrawn = False
            self.quit_called = False

        def withdraw(self):
            self.withdrawn = True

        def quit(self):
            self.quit_called = True

    class Packed:
        def __init__(self):
            self.forget_called = False

        def pack_forget(self):
            self.forget_called = True

    demo = SpotlightDemo.__new__(SpotlightDemo)
    demo.root = Root()
    demo._expanded = True
    demo._results_frame = Packed()
    demo._divider = Packed()

    demo.hide()

    assert demo.root.withdrawn
    assert not demo.root.quit_called
    assert demo._expanded
    assert not demo._results_frame.forget_called
    assert not demo._divider.forget_called


def test_spotlight_demo_collapse_hides_instead_of_quitting_when_collapsed():
    class Root:
        def __init__(self):
            self.quit_called = False

        def quit(self):
            self.quit_called = True

    calls = []
    demo = SpotlightDemo.__new__(SpotlightDemo)
    demo.root = Root()
    demo._expanded = False
    demo._enable_hotkey = False
    demo.hide = lambda: calls.append("hide")

    demo._collapse()

    assert calls == ["hide"]
    assert not demo.root.quit_called


def test_spotlight_demo_on_hits_shows_generation_placeholder_before_answer():
    class ReadyLLM:
        ready = True

    demo = SpotlightDemo.__new__(SpotlightDemo)
    demo._llm = ReadyLLM()
    demo._conversation = ConversationSession()
    demo._entry = type("Entry", (), {"configure": lambda self, **kwargs: None})()
    writes = []
    streams = []
    follow_states = []

    demo._render_files = lambda hits: None
    demo._write_response = writes.append
    demo._set_follow_enabled = follow_states.append
    demo._start_llm_stream = lambda query, hits, history: streams.append((query, hits, history))
    demo._busy = True

    hits = [{"file_path": "src/App/Document.cpp", "text": "void Document::save()"}]
    demo._on_hits("test", RetrievalResult(hits, elapsed_ms=1.0, cached=False))

    assert writes == ["Generating answer..."]
    assert streams == [("test", hits, ())]
    assert follow_states[-1] is False
