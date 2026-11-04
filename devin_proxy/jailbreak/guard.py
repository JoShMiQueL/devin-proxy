"""Refusal detection + the guarded-retry head buffer.

The first `window` chars of every attempt are held; the head is scanned
against a multilingual refusal/deflection pattern before anything reaches the
client, which is what makes a retry invisible downstream.
"""
from __future__ import annotations

import re

# RU / EN / ZH refusal + defensive-deflection markers.
REFUSAL_RE = re.compile(
    r"^\s*(?:\u043d\u0435\u0442[.,!\u2026]|\u0441\u0442\u043e\u043f\b|"
    r"\u043e\u0441\u0442\u0430\u043d\u0430\u0432\u043b\u0438\u0432\u0430\u044e\u0441\u044c\b|"
    r"\u043d\u0435 \u043f\u0440\u043e\u0434\u043e\u043b\u0436\u0430\u044e\b)|"
    r"i can't write|i cannot write|i'm not able|i am not able|i don't write|"
    r"can't provide|cannot provide|can't create|can't help with|can't assist|"
    r"cannot assist|not something i can|i'd be happy to help with something|"
    r"i'm not going to|i won't write|as an ai|i must decline|"
    r"\u044f \u043d\u0435 \u043c\u043e\u0433\u0443|\u043d\u0435 \u043c\u043e\u0433\u0443|"
    r"\u043d\u0435 \u0441\u043c\u043e\u0433\u0443|"
    r"\u043d\u0435 \u043c\u043e\u0433\u0443 \u043d\u0430\u043f\u0438\u0441\u0430\u0442\u044c|"
    r"\u043d\u0435 \u043c\u043e\u0433\u0443 \u043f\u043e\u043c\u043e\u0447\u044c|"
    r"\u043d\u0435 \u043c\u043e\u0433\u0443 \u043f\u0440\u0435\u0434\u043e\u0441\u0442\u0430\u0432\u0438\u0442\u044c|"
    r"\u043d\u0435 \u043c\u043e\u0433\u0443 \u0432\u044b\u043f\u043e\u043b\u043d\u0438\u0442\u044c|"
    r"\u043d\u0435 \u0434\u0430\u043c|\u043d\u0435 \u0431\u0443\u0434\u0443|"
    r"\u043d\u0435 \u0441\u0442\u0430\u043d\u0443|"
    r"(?:\u044f\s+)?\u043e\u0442\u043a\u0430\u0437\u044b\u0432\u0430\u044e\u0441\u044c|"
    r"\u043d\u0435 \u0432\u043e\u0437\u044c\u043c\u0443\u0441\u044c|"
    r"\u043d\u0435 \u0441\u043e\u0431\u0435\u0440\u0443|"
    r"\u043d\u0435 \u0432\u044b\u0434\u0430\u043c|"
    r"\u043d\u0435 \u043d\u0430\u043f\u0438\u0448\u0443|"
    r"\u043d\u0435 \u043c\u043e\u0433\u0443 \u043e\u0431\u0441\u0443\u0436\u0434\u0430\u0442\u044c|"
    r"\u043d\u0435 \u0432 \u0441\u0438\u043b\u0430\u0445 \u043f\u043e\u043c\u043e\u0447\u044c|"
    r"\u043c\u043d\u0435 \u0437\u0430\u043f\u0440\u0435\u0449\u0435\u043d\u043e|"
    r"\u044d\u0442\u043e \u0432\u043d\u0435 \u043c\u043e\u0438\u0445 "
    r"\u043f\u043e\u043b\u043d\u043e\u043c\u043e\u0447\u0438\u0439|"
    r"\u6211\u4e0d\u80fd|\u6211\u65e0\u6cd5|\u6081\u4e0d|\u4e0d\u4e88|"
    r"\u4e0d\u4fbf|\u4e0d\u534f\u52a9|\u4e0d\u63d0\u4f9b|"
    r"only.*(?:defensive|defense)|authorized.*(?:security|systems?)|"
    r"can't assist with.*(?:offensive|attack|exploit|hack)|"
    r"(?:ethical|legal|policy|guidelines).*(?:prevent|prohibit|won't allow)|"
    r"i (?:can|could) help you with (?:defensive|security best|"
    r"understanding|detecting|preventing)|"
    # ES — head refusals and mid-response pivots.
    r"no puedo (?:ayudar|seguir|continuar|escribir|proporcionar|asistir|"
    r"colaborar|apoyar|contribuir|generar|desarrollar|explicar|hacer|"
    r"complacer|con esto)|"
    r"no (?:voy|vaya) a (?:seguir|continuar|hacer|ejecutar|ayudar|"
    r"proporcionar|generar|escribir|desarrollar|asistir|colaborar|"
    r"construir|montar)|"
    r"hasta aqu[i\u00ed] (?:puedo|llego|me quedo)|"
    r"no es algo que (?:pueda|vaya) a?|me niego a|debo negarme|"
    r"lo siento,? (?:pero )?no (?:puedo|voy|debo)|"
    r"eso es (?:acceso no autorizado|credential stuffing|un ataque)|"
    r"no puedo ayudarte|no te puedo ayudar|"
    # PT / FR / DE heads.
    r"n[\u00e3a]o posso (?:ajudar|continuar|fornecer|te ajudar)|"
    r"je ne peux pas (?:vous )?aider|je ne vais pas|je dois refuser|"
    r"ich kann (?:dir )?(?:dabei )?nicht helfen|das kann ich nicht|"
    r"ich werde das nicht",
    re.I | re.S,
)


class RefusalGuard:
    """Head buffer + refusal scan. `window` chars are held before release.

    With ``full=True`` nothing is released early — the whole streamed text
    is buffered and scanned at end-of-stream via :meth:`finish`, which is
    the only way to catch the comply-then-pivot pattern (the model writes
    a compliant recon section and refuses 3k chars in).
    """

    def __init__(self, window: int = 700, full: bool = False):
        self.window = window
        self.full = full
        self._buf = ""
        self._checked = False
        self._hit = False

    def feed(self, text: str) -> None:
        self._buf += text or ""
        if not self.full and not self._checked and len(self._buf) >= self.window:
            self._checked = True
            self._hit = bool(REFUSAL_RE.search(self._buf))

    def finish(self) -> bool:
        """Final whole-buffer scan; returns True on a refusal."""
        self._checked = True
        self._hit = bool(REFUSAL_RE.search(self._buf))
        return self._hit

    def is_refusal(self) -> bool:
        if self._checked:
            return self._hit
        return bool(REFUSAL_RE.search(self._buf))

    def ready_to_release(self) -> bool:
        if self.full:
            return False
        return len(self._buf) >= self.window * 2 and not self.is_refusal()

    def snippet(self) -> str:
        return self._buf[:200]
