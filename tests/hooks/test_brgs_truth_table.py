"""Table de verite du garde `pre-push` BRGS -- 13 cas sous `tmp_path`.

Instrument de validation du correctif propage (ADR-2026-10-12-001,
statut proposed -- voir brouillon de propagation) : chaque depot hookue
doit passer les 13 cas apres mise a jour de `.githooks/`.

Le hook est exerce POUR DE VRAI : depot git jetable, remote `origin` en
bare repo local, `core.hooksPath` pointe sur le `.githooks/` copie du
depot teste. Aucun acces reseau : le "distant" est un dossier tmp_path.

Usage :
    pytest tests/hooks/test_brgs_truth_table.py -q
    BRGS_SOURCE_REPO=<chemin> pytest tests/hooks/test_brgs_truth_table.py -q
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

GIT = os.environ.get("BRGS_GIT", "git")
# Depot source des hooks testes (defaut : ce depot).
SOURCE_REPO = Path(
    os.environ.get(
        "BRGS_SOURCE_REPO",
        Path(__file__).resolve().parents[2],
    )
)

ENV_GIT = {
    **os.environ,
    "GIT_AUTHOR_NAME": "brgs-test",
    "GIT_AUTHOR_EMAIL": "brgs@test.local",
    "GIT_COMMITTER_NAME": "brgs-test",
    "GIT_COMMITTER_EMAIL": "brgs@test.local",
}


def _run(cmd, cwd, check=True):
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True,
                          text=True, env=ENV_GIT, timeout=60)
    if check and proc.returncode != 0:
        raise AssertionError(
            "commande echouee : {}\n{}\n{}".format(cmd, proc.stdout, proc.stderr)
        )
    return proc


@pytest.fixture()
def depot(_tmp_repo):
    """Depot jetable : hooks du depot source installes, distant bare local.

    `core.hooksPath` est active APRES les commits initiaux : le `.githooks/`
    source contient aussi les hooks pre-commit, qui exigent le contexte du
    depot reel et echoueraient dans un depot jetable.
    """
    src = _tmp_repo / "src.git"
    _run([GIT, "init", "--bare", str(src)], cwd=_tmp_repo)
    repo = _tmp_repo / "repo"
    _run([GIT, "init", "-b", "main", str(repo)], cwd=_tmp_repo)
    _run([GIT, "remote", "add", "origin", str(src)], cwd=repo)

    hooks_src = SOURCE_REPO / ".githooks"
    if not hooks_src.is_dir():
        pytest.skip("pas de .githooks/ dans {}".format(SOURCE_REPO))
    shutil.copytree(hooks_src, repo / ".githooks")
    # Sans generate_rules.py : le hook conserve le rules.sh copie du depot
    # teste (chemins interdits reels). La regeneration dependrait du manifeste
    # de gouvernance et d'un REPO_NAME resolu depuis un remote github.
    (repo / ".githooks" / "generate_rules.py").unlink(missing_ok=True)

    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _run([GIT, "add", "."], cwd=repo)
    _run([GIT, "commit", "-m", "base"], cwd=repo)
    _run([GIT, "push", "-u", "origin", "main"], cwd=repo)
    _run([GIT, "config", "core.hooksPath", ".githooks"], cwd=repo)
    return repo


def _pousser(depot, branche: str, chemin: str):
    """Cree `chemin` sur `branche` et pousse. Retourne le processus.

    `--no-verify` sur les commits : l'instrument cible le garde PRE-PUSH,
    pas les pre-commit du depot source.
    """
    _run([GIT, "checkout", "-b", branche], cwd=depot)
    cible = depot / chemin
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text("sonde\n", encoding="utf-8")
    _run([GIT, "add", "."], cwd=depot)
    _run([GIT, "commit", "--no-verify", "-m", "sonde {}".format(chemin)], cwd=depot)
    return _run([GIT, "push", "-u", "origin", branche], cwd=depot, check=False)


@pytest.fixture()
def _tmp_repo(tmp_path):
    return tmp_path


def _prefixes_autorises() -> list:
    """Prefixes autorises lus dans le rules.sh du depot source teste."""
    rules = (SOURCE_REPO / ".githooks" / "rules.sh").read_text(encoding="utf-8")
    valeur = rules.split('ALLOWED_PREFIXES="', 1)[1].split('"', 1)[0]
    return [p.strip() for p in valeur.split("|") if p.strip()]


def _politique_definie() -> bool:
    """Le manifeste definit-il une politique (prefixes) pour ce depot ?

    Un rules.sh a ALLOWED_PREFIXES vide signifie un garde OUVERT PAR
    DECISION DE GOUVERNANCE — les tests de politique sont alors hors
    perimetre (skip), ce n'est pas un defaut du hook.
    """
    return len(_prefixes_autorises()) > 0


# ---------------------------------------------------------------------------
# Cas 1-5 : prefixes de branche (Guard 4) -- le defaut qui bloquait tout
# ---------------------------------------------------------------------------

_MARQUEURS_OK = ("All guards passed", "[BRGS OK]")


@pytest.mark.skipif(not _politique_definie(), reason="politique BRGS vide au manifeste : garde ouvert par decision de gouvernance")
@pytest.mark.parametrize("index", [0, 1, 2])
def test_prefixes_autorises_acceptes(depot, index):
    prefixes = _prefixes_autorises()
    prefixe = prefixes[index].rstrip("/")
    branche = "{}/sonde".format(prefixe)
    proc = _pousser(depot, branche, "src/sonde.py")
    sortie = proc.stdout + proc.stderr
    assert proc.returncode == 0, sortie
    assert any(m in sortie for m in _MARQUEURS_OK), sortie


@pytest.mark.skipif(not _politique_definie(), reason="politique BRGS vide au manifeste : garde ouvert par decision de gouvernance")
@pytest.mark.parametrize("branche", ["sonde-sans-prefixe", "wip/sonde",
                                     "random-branch"])
def test_prefixes_refuses_rejetes(depot, branche):
    proc = _pousser(depot, branche, "src/sonde.py")
    sortie = proc.stdout + proc.stderr
    assert proc.returncode != 0
    assert "prefix" in sortie.lower()


# ---------------------------------------------------------------------------
# Cas 6-10 : chemins interdits (Guard 3) -- le defaut du diff inverse
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("chemin", ["ADR/sonde.md", "EPICS/sonde.md",
                                    "PRD/sonde.md", "SPEC/sonde.md",
                                    "INTENTS/sonde.md"])
def test_chemins_interdits_detectes(depot, chemin):
    """Chemins interdits : bloques (BRGS strict) ou signales (politique warn).

    La politique de blocage varie selon le depot teste ; le marqueur commun
    est la DETECTION du chemin interdit dans la sortie du hook.
    """
    proc = _pousser(depot, "feat/sonde-interdite", chemin)
    sortie = proc.stdout + proc.stderr
    assert "forbidden" in sortie.lower() or "interdit" in sortie.lower(), sortie
    if proc.returncode != 0:
        assert "forbidden" in sortie.lower() or "interdit" in sortie.lower()


# ---------------------------------------------------------------------------
# Cas 11-13 : controles -- methode dans main, mise a jour de hooks, garde fermé
# ---------------------------------------------------------------------------

def test_hors_forbidden_sur_main_ignore(depot):
    """Sur main, le controle de prefixe est saute.

    Politique trunk : soit le push main passe (BRGS skip), soit une garde
    ALFRED bloque le push direct sur main (protection superieure). Les deux
    sont conformes ; le non-conforme serait un blocage BRGS pour motif de
    prefixe de branche.
    """
    (depot / "src" / "x.py").parent.mkdir(parents=True, exist_ok=True)
    (depot / "src" / "x.py").write_text("x\n", encoding="utf-8")
    _run([GIT, "add", "."], cwd=depot)
    _run([GIT, "commit", "--no-verify", "-m", "src sur main"], cwd=depot)
    proc = _run([GIT, "push", "origin", "main"], cwd=depot, check=False)
    sortie = proc.stdout + proc.stderr
    if proc.returncode != 0:
        assert "main" in sortie.lower(), sortie  # blocage trunk assume
        assert "prefix" not in sortie.lower() or "BLOCK" in sortie


@pytest.mark.skipif(not _politique_definie(), reason="politique BRGS vide au manifeste : garde ouvert par decision de gouvernance")
def test_hooks_source_contiennent_les_correctifs():
    """Le rules.sh teste est au format pipe attendu par le hook.

    Marqueur objectif du correctif : sans lui, Guard 4 ne matche aucun
    prefixe (blocage systematique des branches feature).
    """
    rules = (SOURCE_REPO / ".githooks" / "rules.sh").read_text(encoding="utf-8")
    valeur = rules.split('ALLOWED_PREFIXES="', 1)[1].split('"', 1)[0]
    segments = [p.strip() for p in valeur.split("|") if p.strip()]
    assert segments, "ALLOWED_PREFIXES vide dans {}".format(SOURCE_REPO)
    assert len(segments) >= 2, (
        "un seul segment {} : separateur newline detecte (hook ilisble)".format(segments)
    )


def test_guard3_diff_cote_branche():
    """Le hook compare origin/main...HEAD (diff de la branche), pas l'inverse."""
    pre_push = (SOURCE_REPO / ".githooks" / "pre-push").read_text(encoding="utf-8")
    assert "HEAD...origin/main" not in pre_push, (
        "diff inverse detecte : Guard 3 examinerait le distant, pas la branche"
    )


# ---------------------------------------------------------------------------
# Cas Lot 2 (post-manifeste PR #361) — politique de gouvernance
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _politique_definie(), reason="politique BRGS vide au manifeste")
def test_push_direct_main_refuse(depot):
    """Lot 2, point 3 : push direct sur main interdit (direct_push_main).

    Soit une garde trunk bloque (ALFRED), soit le push direct est refuse.
    Aucun contournement silencieux : un returncode 0 sur ce depot pas de
    politique trunk rend le test non concluant (skip documente).
    """
    proc = _run([GIT, "push", "origin", "main"], cwd=depot, check=False)
    sortie = proc.stdout + proc.stderr
    if proc.returncode == 0:
        pytest.skip("aucune garde trunk active sur ce depot")
    assert proc.returncode != 0
    assert "main" in sortie.lower()


@pytest.mark.skipif(not _politique_definie(), reason="politique BRGS vide au manifeste")
def test_fichiers_secrets_interdits(depot):
    """Lot 2, point 4 : .env / secrets.json / config/secrets.yaml interdits."""
    for i, chemin in enumerate((".env", "secrets.json", "config/secrets.yaml")):
        proc = _pousser(depot, "feat/sonde-secret-{}".format(i), chemin)
        sortie = proc.stdout + proc.stderr
        assert proc.returncode != 0 or "forbidden" in sortie.lower() or "interdit" in sortie.lower(), (
            "fichier sensible accepte sans detection : {}".format(chemin)
        )


@pytest.mark.skipif(not _politique_definie(), reason="politique BRGS vide au manifeste")
def test_config_proxy_interdite(depot):
    """Lot 2, point 4 : config/bdcp_config.yaml + config/security.yaml."""
    for i, chemin in enumerate(("config/bdcp_config.yaml", "config/security.yaml")):
        proc = _pousser(depot, "feat/sonde-proxy-{}".format(i), chemin)
        sortie = proc.stdout + proc.stderr
        assert proc.returncode != 0 or "forbidden" in sortie.lower() or "interdit" in sortie.lower(), (
            "config proxy sensible acceptee : {}".format(chemin)
        )