from serialterminal.terminal import encode_line


def test_encode_line_lf():
    assert encode_line("status") == b"status\n"


def test_encode_line_crlf():
    assert encode_line("status", "\r\n") == b"status\r\n"


def test_encode_line_unicode():
    assert encode_line("привет") == "привет\n".encode("utf-8")
