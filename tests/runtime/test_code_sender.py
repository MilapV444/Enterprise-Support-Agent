"""Sign-in codes are emailed over SMTP when it is configured, and logged when it is not."""

from runtime import production


class FakeSMTP:
    sent = []

    def __init__(self, host, port, timeout):
        self.calls = [("connect", host, port)]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        FakeSMTP.sent.append(self.calls)

    def starttls(self):
        self.calls.append(("starttls",))

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def send_message(self, message):
        self.calls.append(("send", message["From"], message["To"], message["Subject"], message.get_content()))


def test_codes_are_emailed_when_smtp_is_set(monkeypatch):
    monkeypatch.setattr(production.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    send = production.code_sender({"SMTP_HOST": "smtp.example.com", "SMTP_USER": "bot@example.com"})
    send("t_us", "sarah@example.com", "042917")
    connect, tls, login, (_, sender, to, subject, body) = FakeSMTP.sent[-1]
    assert connect == ("connect", "smtp.example.com", 587) and tls == ("starttls",)
    assert login == ("login", "bot@example.com", "app-password")
    assert (sender, to) == ("bot@example.com", "sarah@example.com")
    assert "042917" in subject and "042917" in body


def test_codes_are_logged_without_smtp():
    assert production.code_sender({}) is production.log_code
