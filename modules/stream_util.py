# -*- coding: utf-8 -*-
"""
ESP Tool & Hardware Inspector v2.0 - Stream & ANSI Output Utilities
"""
import io
import re

ANSI_ESCAPE_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

class StreamInterceptor:
    def __init__(self, callback):
        self.callback = callback
        self.buf = ''
        self.full_output = io.StringIO()

    def write(self, s):
        self.full_output.write(s)
        self.buf += s
        while '\n' in self.buf or '\r' in self.buf:
            pos_n = self.buf.find('\n')
            pos_r = self.buf.find('\r')
            if pos_n != -1 and (pos_r == -1 or pos_n < pos_r):
                line = self.buf[:pos_n]
                self.buf = self.buf[pos_n+1:]
            else:
                line = self.buf[:pos_r]
                self.buf = self.buf[pos_r+1:]
            clean = ANSI_ESCAPE_RE.sub('', line).strip()
            if clean and self.callback:
                try:
                    self.callback(clean)
                except Exception:
                    pass

    def flush(self):
        clean = ANSI_ESCAPE_RE.sub('', self.buf).strip()
        if clean and self.callback:
            try:
                self.callback(clean)
            except Exception:
                pass
        self.buf = ''

    def getvalue(self):
        return self.full_output.getvalue()
