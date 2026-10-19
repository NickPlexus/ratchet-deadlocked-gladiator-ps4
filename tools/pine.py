"""Minimal PINE client for PCSX2 (Settings: EnablePINE=true, PINESlot=28011, TCP on Windows)."""
import socket, struct

READ8, READ16, READ32, READ64 = 0, 1, 2, 3
WRITE8, WRITE16, WRITE32, WRITE64 = 4, 5, 6, 7
VERSION, SAVESTATE, LOADSTATE, TITLE, ID, UUID, GAMEVER, STATUS = 8, 9, 10, 11, 12, 13, 14, 15


class Pine:
    def __init__(self, port=28011, host='127.0.0.1'):
        self.s = socket.create_connection((host, port), timeout=10)

    def _cmd(self, payload):
        self.s.sendall(struct.pack('<I', len(payload) + 4) + payload)
        hdr = self._recv(4)
        size = struct.unpack('<I', hdr)[0]
        body = self._recv(size - 4)
        if body[0] != 0:
            raise RuntimeError(f'PINE command failed: {payload[:1].hex()}')
        return body[1:]

    def _recv(self, n):
        b = b''
        while len(b) < n:
            c = self.s.recv(n - len(b))
            if not c:
                raise ConnectionError('PINE closed')
            b += c
        return b

    def r32(self, a):
        return struct.unpack('<I', self._cmd(struct.pack('<BI', READ32, a)))[0]

    def r64(self, a):
        return struct.unpack('<Q', self._cmd(struct.pack('<BI', READ64, a)))[0]

    def w32(self, a, v):
        self._cmd(struct.pack('<BII', WRITE32, a, v & 0xFFFFFFFF))

    def read_block(self, a, n):
        return b''.join(struct.pack('<Q', self.r64(a + i)) for i in range(0, n, 8))

    def save(self, slot):
        self._cmd(struct.pack('<BB', SAVESTATE, slot))

    def load(self, slot):
        self._cmd(struct.pack('<BB', LOADSTATE, slot))

    def _str(self, op):
        d = self._cmd(struct.pack('<B', op))
        n = struct.unpack('<I', d[:4])[0]
        return d[4:4 + n].rstrip(b'\0').decode('latin-1')

    def title(self):
        return self._str(TITLE)

    def game_id(self):
        return self._str(ID)

    def status(self):
        return {0: 'running', 1: 'paused', 2: 'shutdown'}.get(struct.unpack('<I', self._cmd(struct.pack('<B', STATUS)))[0], '?')
