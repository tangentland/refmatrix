"""Pronoun dereferencing (anaphora resolution), heuristic and dependency-free.

The measured case for this layer (2026-09-04): prose repeats its topic through
pronouns after first mention, and pronouns are stopwords, so today they BREAK
the pair-miner's runs and contribute nothing to term frequency. Resolution
converts each pronoun occurrence into a repeat of its antecedent, which

  - raises the antecedent's tf (symbolic channel, via a dedicated `coref`
    linkage so the contribution is provenance-tagged and can be backed out),
  - repairs the pair-miner's undercounting (a resolved pronoun participates
    in windows the raw pronoun broke),
  - gives the dense channel a substituted text at embed time (materialized
    transiently from the stored resolutions -- no resolved copy of any
    document is ever persisted).

Within-document resolution adds no NEW vocabulary to a doc -- the antecedent
already appears at least once -- so it redistributes weight rather than
growing the candidate set. Cross-document resolution (the antecedent lives in
a chained earlier session) is the variant that can inject vocabulary; the
`pair_index` sidecar (see `Store.compile_pairs`) exists to supply its
candidate documents.

Deliberately heuristic: nearest-salient-antecedent within a sentence window.
Chat/prose coref is overwhelmingly recency-bound, and a wrong guess costs one
noise term against a document that carries hundreds. A model-based resolver
can replace `resolve_text` behind the same Resolution shape if the measured
ceiling ever justifies the dependency.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

# Pronouns resolved to a PERSON-like antecedent (a proper-noun candidate).
_PERSON_PRONOUNS = frozenset(
    "he him his she her hers they them their theirs".split())
# Pronouns resolved to a THING-like antecedent (a recurring content noun).
_NEUTER_PRONOUNS = frozenset("it its".split())

_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n{2,}")
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_'-]*")

# Words that look proper-noun-ish but are sentence furniture.
_CAP_STOP = frozenset(
    "the a an i but and or so if when while this that these those "
    "it he she they we you my your his her its our their".split())

# Capitalized sentence OPENERS that are adverbs/quantifiers, not names. An
# opener is capitalized by grammar, not identity, so it needs either this
# stoplist to clear or corpus recurrence to prove itself.
_OPENER_STOP = frozenset(
    "yesterday today tomorrow now then however meanwhile also finally next "
    "first second third later soon once again still after before during "
    "everything nothing something anything someone anyone everyone nobody "
    "here there maybe perhaps instead thus hence overall "
    "do does did don't doesn't didn't let let's please yes no okay ok well "
    "what why how where who which".split())

# Aux/modal/common verbs and function words that recur in any prose and would
# otherwise qualify as neuter candidates on the df>=2 rule alone. Measured on
# the MemAware corpus: without this, `it` bound to `would` and `they` to
# gerunds -- recurrence proves frequency, not referent-hood.
_VERBISH_STOP = frozenset(
    "would could should shall will can may might must have has had having "
    "was were been being are is am get got gets getting go goes going went "
    "make makes making made take takes taking took come comes coming came "
    "say says saying said know knows knew think thinks thought want wants "
    "wanted like likes liked need needs needed feel feels felt see sees saw "
    "look looks looked really very just quite about because though although "
    "pairing doing being trying going".split())


@dataclass(frozen=True)
class Resolution:
    """One pronoun occurrence resolved to an in-document antecedent.

    `offset` indexes into the exact text handed to `resolve_text`; `apply`
    substitutes against that same text, so the pair never drifts. Persisting
    a resolution against one rendering of a document and applying it to
    another is a bug in the caller.
    """
    offset: int
    pronoun: str
    antecedent: str
    confidence: float


def _sentences(text: str) -> "list[tuple[int, str]]":
    """(start_offset, sentence) pairs. Offsets index the ORIGINAL text."""
    out: list[tuple[int, str]] = []
    pos = 0
    for chunk in _SENT_SPLIT_RE.split(text):
        if not chunk:
            continue
        start = text.find(chunk, pos)
        if start < 0:
            continue
        out.append((start, chunk))
        pos = start + len(chunk)
    return out


def resolve_text(text: str, *, window: int = 3,
                 min_confidence: float = 0.0) -> "list[Resolution]":
    """Resolve pronouns to in-document antecedents, nearest-salient-first.

    PERSON pronouns bind to the most recent proper-noun-ish token (capitalized
    mid-sentence, or capitalized at sentence start AND recurring) within
    `window` sentences. NEUTER pronouns bind to the most recent lowercase
    content token that occurs at least twice in the document -- recurrence is
    the topicality guard that keeps `it` off incidental nouns.

    Confidence decays with sentence distance and is halved when two distinct
    candidates compete inside the window; callers filter with
    `min_confidence`. Unresolvable pronouns are simply skipped -- silence,
    not a guess, is the correct output for a floor heuristic.
    """
    sents = _sentences(text)
    token_df: Counter[str] = Counter()
    for _, s in sents:
        token_df.update({t.lower() for t in _TOKEN_RE.findall(s)})

    out: list[Resolution] = []
    # (sentence_index, token, is_person_candidate), most recent last
    candidates: list[tuple[int, str, bool]] = []

    for si, (s_start, sent) in enumerate(sents):
        for m in _TOKEN_RE.finditer(sent):
            tok = m.group(0)
            low = tok.lower()
            if low in _PERSON_PRONOUNS or low in _NEUTER_PRONOUNS:
                person = low in _PERSON_PRONOUNS
                pool = [
                    (c, 1.0 / (1.0 + (si - ci)))
                    for ci, c, is_person in candidates
                    if is_person == person and si - ci <= window
                ]
                if not pool:
                    continue
                ante, conf = pool[-1]
                distinct = {c.lower() for c, _conf in pool}
                if len(distinct) > 1:
                    conf *= 0.5
                if conf >= min_confidence:
                    out.append(Resolution(
                        offset=s_start + m.start(), pronoun=tok,
                        antecedent=ante, confidence=round(conf, 3)))
                continue

            at_sentence_start = m.start() == 0
            if tok[0].isupper() and low not in _CAP_STOP \
                    and low not in _VERBISH_STOP and len(tok) >= 2:
                # A sentence-opener is capitalized by grammar, not identity:
                # it qualifies only when it is not a stoplisted adverb/
                # quantifier, or when it recurs enough to prove itself.
                if not at_sentence_start or low not in _OPENER_STOP:
                    candidates.append((si, tok, True))
            elif tok.islower() and low not in _CAP_STOP \
                    and low not in _VERBISH_STOP and len(tok) >= 3 \
                    and token_df[low] >= 2:
                candidates.append((si, tok, False))

    return out


def apply(text: str, resolutions: "list[Resolution]") -> str:
    """Substitute antecedents into `text` -- the transient form the dense
    channel embeds. Applied back-to-front so earlier offsets stay valid.
    The result is never persisted; vectors are, resolutions are, text isn't."""
    out = text
    for r in sorted(resolutions, key=lambda r: -r.offset):
        end = r.offset + len(r.pronoun)
        if out[r.offset:end].lower() != r.pronoun.lower():
            continue  # text drifted from what was resolved; skip, don't guess
        out = out[:r.offset] + r.antecedent + out[end:]
    return out


def antecedent_counts(resolutions: "list[Resolution]") -> "Counter[str]":
    """Occurrence counts per antecedent term (lowercased) -- the symbolic
    channel's tf delta, emitted as the `coref` linkage at ingest."""
    c: Counter[str] = Counter()
    for r in resolutions:
        c[r.antecedent.lower()] += 1
    return c
