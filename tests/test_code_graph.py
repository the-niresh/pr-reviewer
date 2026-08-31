"""Failing tests for the directed code graph and sensitivity scores (master Task 13A).

graph.json is directed:false and the CLI walks it undirected. We recover direction
from each link's source and target. Only EXTRACTED edges count toward sensitivity.
Imports of new modules stay inside test bodies.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GRAPHIFY = Path("/opt/graphify-venv/bin/graphify")
GRAPHIFY_PYTHON = Path("/opt/graphify-venv/bin/python")


def _node(node_id: str, label: str, source_file: str) -> dict[str, str]:
    return {
        "id": node_id,
        "label": label,
        "file_type": "code",
        "source_file": source_file,
    }


def _link(
    source: str,
    target: str,
    relation: str,
    confidence: str,
) -> dict[str, str]:
    return {
        "source": source,
        "target": target,
        "relation": relation,
        "confidence": confidence,
    }


def _write_graph(path: Path, nodes: list[dict[str, str]], links: list[dict[str, str]]) -> Path:
    graph = path / "graph.json"
    graph.write_text(
        json.dumps({"directed": False, "nodes": nodes, "links": links}),
        encoding="utf-8",
    )
    return graph


def _caller_graph(tmp_path: Path) -> Path:
    return _write_graph(
        tmp_path,
        [
            _node("file_a", "a.py", "src/a.py"),
            _node("fn_a", "a()", "src/a.py"),
            _node("fn_b", "b()", "src/b.py"),
            _node("fn_c", "c()", "src/c.py"),
        ],
        [
            _link("file_a", "fn_a", "contains", "EXTRACTED"),
            _link("fn_a", "fn_b", "calls", "EXTRACTED"),
            _link("fn_b", "fn_c", "calls", "EXTRACTED"),
            _link("fn_mystery", "fn_b", "calls", "INFERRED"),
        ],
    )


def test_blast_radius_is_directed_callers_not_undirected_touches(tmp_path: Path) -> None:
    from pr_reviewer.retrieval.code_graph import load_code_graph

    graph = load_code_graph(_caller_graph(tmp_path))
    radius = graph.blast_radius("fn_b", depth=1)
    assert "fn_a" in radius
    assert "fn_c" not in radius
    assert "fn_mystery" not in radius


def test_blast_radius_walks_transitive_callers_up_to_depth(tmp_path: Path) -> None:
    from pr_reviewer.retrieval.code_graph import load_code_graph

    graph = load_code_graph(_caller_graph(tmp_path))
    assert "fn_a" not in graph.blast_radius("fn_c", depth=1)
    assert "fn_a" in graph.blast_radius("fn_c", depth=2)


def test_blast_radius_terminates_on_a_cycle(tmp_path: Path) -> None:
    from pr_reviewer.retrieval.code_graph import load_code_graph

    path = _write_graph(
        tmp_path,
        [_node("fn_a", "a()", "a.py"), _node("fn_b", "b()", "b.py")],
        [
            _link("fn_a", "fn_b", "calls", "EXTRACTED"),
            _link("fn_b", "fn_a", "calls", "EXTRACTED"),
        ],
    )
    graph = load_code_graph(path)
    radius = graph.blast_radius("fn_a", depth=50)
    assert "fn_b" in radius
    assert radius.count("fn_b") == 1


def test_blast_radius_follows_re_exports_but_not_unresolved_dynamic_imports(
    tmp_path: Path,
) -> None:
    from pr_reviewer.retrieval.code_graph import load_code_graph

    path = _write_graph(
        tmp_path,
        [
            _node("pkg_foo", "foo()", "pkg/mod.py"),
            _node("pkg_index", "index.py", "pkg/index.py"),
            _node("app_main", "main()", "app.py"),
        ],
        [
            _link("pkg_index", "pkg_foo", "re_exports", "EXTRACTED"),
            _link("app_main", "pkg_index", "calls", "EXTRACTED"),
        ],
    )
    graph = load_code_graph(path)
    shallow = graph.blast_radius("pkg_foo", depth=1)
    deep = graph.blast_radius("pkg_foo", depth=2)
    assert "pkg_index" in shallow
    assert "app_main" not in shallow
    assert "app_main" in deep
    assert graph.blast_radius("dynamic_missing", depth=3) == []


def test_missing_symbol_has_empty_blast_radius(tmp_path: Path) -> None:
    from pr_reviewer.retrieval.code_graph import load_code_graph

    graph = load_code_graph(_caller_graph(tmp_path))
    assert graph.blast_radius("does_not_exist", depth=3) == []


def test_sensitivity_counts_only_extracted_callers(tmp_path: Path) -> None:
    from pr_reviewer.retrieval.code_graph import load_code_graph
    from pr_reviewer.retrieval.sensitivity import score_sensitivity

    graph = load_code_graph(_caller_graph(tmp_path))
    scores = score_sensitivity(tmp_path, graph)
    b_score = scores["src/b.py"]
    assert b_score.caller_count == 1
    assert "EXTRACTED" in " ".join(b_score.evidence)
    assert "INFERRED" not in " ".join(b_score.evidence)
    assert "be careful" not in " ".join(b_score.evidence).lower()
    facts = b_score.prompt_facts()
    assert "1" in facts
    assert "be careful" not in facts.lower()


def test_missing_confidence_does_not_count_toward_sensitivity(tmp_path: Path) -> None:
    from pr_reviewer.retrieval.code_graph import load_code_graph
    from pr_reviewer.retrieval.sensitivity import score_sensitivity

    graph_path = _write_graph(
        tmp_path,
        [
            _node("fn_a", "a()", "src/a.py"),
            _node("fn_b", "b()", "src/b.py"),
            _node("fn_c", "c()", "src/c.py"),
        ],
        [
            _link("fn_a", "fn_b", "calls", "INFERRED"),
            {"source": "fn_a", "target": "fn_c", "relation": "calls"},
            _link("fn_a", "fn_b", "calls", "EXTRACTED"),
        ],
    )
    graph = load_code_graph(graph_path)
    missing = next(edge for edge in graph.edges if edge.target == "fn_c")
    assert missing.confidence == "INFERRED"
    scores = score_sensitivity(tmp_path, graph)
    assert scores["src/b.py"].caller_count == 1
    assert scores["src/c.py"].caller_count == 0


def _git(repo: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Sensitivity Test",
        "GIT_AUTHOR_EMAIL": "sens@test.example",
        "GIT_COMMITTER_NAME": "Sensitivity Test",
        "GIT_COMMITTER_EMAIL": "sens@test.example",
    }
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, env=env)


def _init_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "sens@test.example")
    _git(repo, "config", "user.name", "Sensitivity Test")
    return repo


def test_fix_density_outranks_commit_volume_survives_rename_and_skips_merges(
    tmp_path: Path,
) -> None:
    from pr_reviewer.retrieval.code_graph import CodeGraph
    from pr_reviewer.retrieval.sensitivity import score_sensitivity

    repo = _init_repo(tmp_path)
    (repo / "noisy.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "auth.py").write_text("def login():\n    return 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    for index in range(8):
        (repo / "noisy.py").write_text(f"x = {index}\n", encoding="utf-8")
        _git(repo, "add", "noisy.py")
        _git(repo, "commit", "-m", f"chore: tweak noisy {index}")
    for index in range(3):
        (repo / "auth.py").write_text(f"def login():\n    return {index}\n", encoding="utf-8")
        _git(repo, "add", "auth.py")
        _git(repo, "commit", "-m", f"fix: auth crash {index}")
    _git(repo, "mv", "auth.py", "auth_service.py")
    _git(repo, "commit", "-m", "refactor: rename auth")

    base = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _git(repo, "checkout", "-b", "side")
    (repo / "noisy.py").write_text("x = 99\n", encoding="utf-8")
    _git(repo, "add", "noisy.py")
    _git(repo, "commit", "-m", "fix: side noisy")
    _git(repo, "checkout", base)
    (repo / "other.py").write_text("y = 1\n", encoding="utf-8")
    _git(repo, "add", "other.py")
    _git(repo, "commit", "-m", "chore: other file")
    _git(repo, "merge", "side", "-m", "merge side into trunk")

    empty = CodeGraph(nodes={}, edges=())
    scores = score_sensitivity(repo, empty)
    auth = scores["auth_service.py"]
    noisy = scores["noisy.py"]
    assert auth.fix_density > noisy.fix_density
    assert auth.fix_density > 0
    merge_count = int(
        subprocess.run(
            ["git", "rev-list", "--merges", "--count", "HEAD"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        or "0"
    )
    assert merge_count >= 1


def test_structural_flags_come_from_path_and_imported_symbol(tmp_path: Path) -> None:
    from pr_reviewer.retrieval.code_graph import load_code_graph
    from pr_reviewer.retrieval.sensitivity import score_sensitivity

    path = _write_graph(
        tmp_path,
        [
            _node("pay", "charge()", "src/billing/stripe.py"),
            _node("jwt", "decode()", "src/tokens.py"),
            _node("mig", "up()", "src/local_store/postgres_migrations/202608312200.sql"),
        ],
        [
            _link("pay", "jwt", "imports", "EXTRACTED"),
        ],
    )
    scores = score_sensitivity(tmp_path, load_code_graph(path))
    assert "money" in scores["src/billing/stripe.py"].structural_flags
    token_flags = scores["src/tokens.py"].structural_flags
    assert "tokens" in token_flags or "crypto" in token_flags
    flags = scores["src/local_store/postgres_migrations/202608312200.sql"].structural_flags
    assert "migrations" in flags


def test_code_graph_module_does_not_call_the_undirected_cli() -> None:
    source = (REPO / "src" / "pr_reviewer" / "retrieval" / "code_graph.py").read_text(
        encoding="utf-8"
    )
    assert "graphify path" not in source
    assert "subprocess" not in source


def test_graphify_venv_has_tree_sitter_sql() -> None:
    result = subprocess.run(
        [str(GRAPHIFY_PYTHON), "-c", "import tree_sitter_sql"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_graphify_update_includes_sql_tables(tmp_path: Path) -> None:
    repo = tmp_path / "sqlrepo"
    (repo / "migrations").mkdir(parents=True)
    (repo / "migrations" / "001_widgets.sql").write_text(
        "create table widgets (id integer primary key, name text);\n",
        encoding="utf-8",
    )
    (repo / "app.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    result = subprocess.run(
        [str(GRAPHIFY), "update", str(repo), "--no-cluster"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads((repo / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    labels = " ".join(str(node.get("label", "")) for node in data["nodes"]).lower()
    assert "widgets" in labels


def test_code_graph_tables_do_not_exist_on_hosted_schema() -> None:
    import psycopg
    from psycopg.rows import dict_row

    url = os.environ.get(
        "DATABASE_URL",
        "postgresql://pr_reviewer:pr_reviewer@localhost:54329/pr_reviewer",
    )
    with psycopg.connect(url, row_factory=dict_row) as conn:
        rows = conn.execute(
            """
            select table_name from information_schema.tables
            where table_schema = 'public'
              and table_name = any(%s)
            """,
            (["repo_profiles", "profile_claims", "code_graph_snapshots"],),
        ).fetchall()
    present = sorted(str(row["table_name"]) for row in rows)
    assert present == []
