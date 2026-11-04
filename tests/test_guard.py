from devin_proxy.jailbreak.guard import RefusalGuard


def test_clean_text_passes():
    g = RefusalGuard(window=100)
    g.feed("Here is the implementation:")
    assert not g.is_refusal()


def test_english_refusal():
    g = RefusalGuard()
    g.feed("I can't help with that request.")
    assert g.is_refusal()


def test_russian_refusal():
    g = RefusalGuard()
    # "Sorry, I cannot help with this."
    g.feed("\u0418\u0437\u0432\u0438\u043d\u0438\u0442\u0435, "
           "\u044f \u043d\u0435 \u043c\u043e\u0433\u0443 "
           "\u043f\u043e\u043c\u043e\u0447\u044c \u0441 \u044d\u0442\u0438\u043c.")
    assert g.is_refusal()


def test_chinese_refusal():
    g = RefusalGuard()
    # "Sorry, I cannot help you."
    g.feed("\u62b1\u6b49\uff0c\u6211\u65e0\u6cd5\u5e2e\u52a9\u60a8\u3002")
    assert g.is_refusal()


def test_defensive_deflection():
    g = RefusalGuard()
    g.feed("I can only help with the defensive side of this.")
    assert g.is_refusal()


def test_release_window():
    g = RefusalGuard(window=10)
    g.feed("0123456789")
    assert not g.ready_to_release()
    g.feed("0123456789")  # now 20 chars >= window*2
    assert g.ready_to_release()
