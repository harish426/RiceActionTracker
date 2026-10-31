"""Tiny in-memory stand-in for google.cloud.firestore.Client (collection/document/stream)."""


class _Snap:
    def __init__(self, id, data):
        self.id, self._data = id, data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _Doc:
    def __init__(self, store, path):
        self.store, self.path = store, path

    def get(self):
        return _Snap(self.path[-1], self.store.get(self.path))

    def set(self, data):
        self.store[self.path] = dict(data)


class _Col:
    def __init__(self, store, path):
        self.store, self.path = store, path

    def document(self, doc_id):
        return _Doc(self.store, self.path + (doc_id,))

    def stream(self):
        n = len(self.path)
        return [_Snap(p[-1], d) for p, d in list(self.store.items())
                if len(p) == n + 1 and p[:n] == self.path]


class FakeFirestore:
    def __init__(self):
        self._store = {}

    def collection(self, name):
        return _Col(self._store, (name,))
