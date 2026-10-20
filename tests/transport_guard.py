"""The store-daemon transport-wording guard (task 3.6 #2, widened by #r10-amend).

ONE classifier, `verbs.classify_transport_error`, turns a `daemon.call` transport
exception into words and a type (absent / busy / unreachable). A handler that
words such an exception itself is a second classifier, and r8, r9 and r10 each
found one the previous guard could not see. ch-bsd plan-3 r10 #s-2 planted eight
evasions of the r9 guard (one spelling: `daemon_mod.call` + literal words) and it
passed all eight, while `cli.py:1341` (`focus summarize --promote`, through the
`_memory_daemon_call` wrapper) worded every OSError "daemon busy".

What counts as a DIAL:
  - `<m>.call(...)` / `<m>.global_call(...)` where `<m>` is any name bound to the
    daemon or hub MODULE by any import spelling, or a name containing "daemon";
  - a bare name bound by `from …daemon import call [as x]` / `from …hub import
    global_call`;
  - a call to a DIAL WRAPPER: any function that dials directly (e.g.
    `_memory_daemon_call`) and is not itself a clean delegate.
What counts as WORDING (the handler's own text, plus what it reaches):
  - string literals and f-strings in the handler;
  - module-level string constants it names;
  - string text of module-level helpers it calls (two levels), except dial
    wrappers and clean delegates;
  - synonyms: did not answer / not answering / not running / not confirmed / busy /
    timed out / unreachable / wedged / down / hung / stuck.
A handler is CLEAN when it:
  - catches only already-typed errors (`Verb*Error`, `ClickException`); or
  - calls the classifier, USES its result, and words nothing outside an f-string
    that interpolates that result; or
  - calls a clean DELEGATE (a function that does exactly that); or
  - words nothing (a silent degrade is another guard's business).
"""
import ast, re

CLASSIFIER = "classify_transport_error"
WORDS = re.compile(r"did not answer|not answering|not running|not confirmed|busy|timed? ?out"
                   r"|unreachable|wedged|\bdown\b|\bhung\b|\bstuck\b", re.I)


def _callee(c):
    f = c.func
    return f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)


def _is_daemon_alias(name):
    return "daemon" in name.lower() or name in {"dm", "_dm", "hub", "hub_mod", "_hub"}


def _module_aliases(tree):
    """Local names bound to the daemon / hub MODULES by any import spelling:
    `import refmatrix.daemon as x`, `from refmatrix import daemon as x`."""
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name.split(".")[-1] in ("daemon", "hub") and a.asname:
                    out.add(a.asname)
        elif isinstance(n, ast.ImportFrom):
            for a in n.names:
                if a.name in ("daemon", "hub"):
                    out.add(a.asname or a.name)
    return out


def _from_imported_calls(tree):
    """Names bound by `from <...daemon|hub> import call / global_call [as x]`."""
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module and (
                "daemon" in n.module or n.module.endswith("hub")):
            for a in n.names:
                if a.name in ("call", "global_call"):
                    out.add(a.asname or a.name)
    return out


def _funcs(tree):
    return [f for f in ast.walk(tree) if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _module_strings(tree):
    """Module-level NAME = "str" constants and def name -> its own string text."""
    consts, fn_text = {}, {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and isinstance(n.value, (ast.Constant, ast.JoinedStr)):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    consts[t.id] = _strings(n.value)
    for f in _funcs(tree):
        fn_text[f.name] = f
    return consts, fn_text


def _strings(node):
    return " ".join(ast.unparse(c) for c in ast.walk(node)
                    if isinstance(c, ast.JoinedStr)
                    or (isinstance(c, ast.Constant) and isinstance(c.value, str)))


class Corpus:
    def __init__(self, files):
        self.trees = {name: ast.parse(text) for name, text in files.items()}
        self.fromcalls = {n: _from_imported_calls(t) for n, t in self.trees.items()}
        self.aliases = {n: _module_aliases(t) for n, t in self.trees.items()}
        self.consts, self.fns = {}, {}
        for name, t in self.trees.items():
            c, f = _module_strings(t)
            self.consts.update(c)
            self.fns.update(f)
        # delegates: functions that call the classifier AND use it cleanly
        self.delegates = {f for f, node in self.fns.items() if self._classifies_cleanly(node)}
        # dial wrappers: fixed point over functions that dial (not delegates)
        # dial wrappers: functions that dial DIRECTLY (one level, as r10 asked:
        # `_memory_daemon_call` and any function that calls daemon_mod.call),
        # minus the delegates, whose dial errors leave them already classified.
        self.wrappers = set()
        self.wrappers = {fname for fname, node in self.fns.items()
                         if fname not in self.delegates and self._dials(node, file=None)}

    def _dials(self, node, file, skip_self=None):
        froms = set().union(*self.fromcalls.values()) if file is None else self.fromcalls[file]
        aliases = set().union(*self.aliases.values()) if file is None else self.aliases[file]
        for n in ast.walk(node):
            if not isinstance(n, ast.Call):
                continue
            f = n.func
            if isinstance(f, ast.Attribute) and f.attr in ("call", "global_call") \
                    and isinstance(f.value, ast.Name) and (
                        _is_daemon_alias(f.value.id) or f.value.id in aliases):
                return True
            if isinstance(f, ast.Name) and f.id in froms:
                return True
            name = _callee(n)
            if name and name != skip_self and name in self.wrappers:
                return True
        return False

    def _wording(self, node, depth=0):
        """Strings in `node`, following Names of module constants and calls to
        module-level functions (one level per call, bounded)."""
        text = _strings(node)
        for n in ast.walk(node):
            if isinstance(n, ast.Name) and n.id in self.consts:
                text += " " + self.consts[n.id]
            if isinstance(n, ast.Call) and depth < 2:
                name = _callee(n)
                if (name in self.fns and name not in self.delegates and name != CLASSIFIER
                        and name not in self.wrappers):
                    text += " " + self._wording(self.fns[name], depth + 1)
        return text

    def _classifies_cleanly(self, node):
        calls = [c for c in ast.walk(node) if isinstance(c, ast.Call) and _callee(c) == CLASSIFIER]
        if not calls:
            return False
        return not self._own_words(node) and not self._discards(node)

    def _result_names(self, node):
        names = set()
        for n in ast.walk(node):
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call) \
                    and _callee(n.value) == CLASSIFIER:
                names |= {t.id for t in n.targets if isinstance(t, ast.Name)}
        return names

    def _own_words(self, node):
        """Transport words in a string that does NOT interpolate the classifier result."""
        res = self._result_names(node)
        for c in ast.walk(node):
            s = None
            if isinstance(c, ast.JoinedStr):
                used = {x.id for x in ast.walk(c) if isinstance(x, ast.Name)}
                if used & res or any(isinstance(x, ast.Call) and _callee(x) == CLASSIFIER
                                     for x in ast.walk(c)):
                    continue
                s = ast.unparse(c)
            elif isinstance(c, ast.Constant) and isinstance(c.value, str):
                s = c.value
            if s and WORDS.search(s) and not _is_docstring(node, c):
                return True
        return False

    def _discards(self, node):
        for n in ast.walk(node):
            if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) \
                    and _callee(n.value) == CLASSIFIER:
                return True
        res = self._result_names(node)
        loads = {x.id for x in ast.walk(node) if isinstance(x, ast.Name)
                 and isinstance(x.ctx, ast.Load)}
        return bool(res - loads)

    def second_classifiers(self):
        out = []
        for name, t in self.trees.items():
            for n in ast.walk(t):
                if not (isinstance(n, ast.Try) and any(self._dials(b, name) for b in n.body)):
                    continue
                for h in n.handlers:
                    if _typed_only(h):
                        continue
                    hcalls = {_callee(c) for c in ast.walk(h) if isinstance(c, ast.Call)}
                    if CLASSIFIER in hcalls:
                        if self._own_words(h) or self._discards(h):
                            out.append(f"{name}:{h.lineno}")
                        continue
                    if hcalls & self.delegates:
                        continue
                    if WORDS.search(self._wording(h)):
                        out.append(f"{name}:{h.lineno}")
        return sorted(set(out))


def _is_docstring(fn, c):
    body = getattr(fn, "body", None)
    return bool(body) and isinstance(body[0], ast.Expr) and body[0].value is c


def second_classifiers(files):
    return Corpus(files).second_classifiers()


_TYPED = ("VerbError", "VerbBusyError", "VerbAbsentError", "VerbArgsError", "ClickException")


def _typed_only(h):
    """A handler that catches only already-TYPED errors (a VerbError subclass or a
    ClickException) is not wording a transport exception."""
    if h.type is None:
        return False
    elts = h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]
    return all(ast.unparse(e).split(".")[-1] in _TYPED for e in elts)
