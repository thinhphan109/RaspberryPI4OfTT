"""Small process-local read cache with per-key coalescing for threaded HTTP.

Slow reads of one key never hold up unrelated keys. Explicit invalidation also
prevents a read already in progress from repopulating the cache with old state.
"""
from collections import OrderedDict
from copy import deepcopy
import threading
import time


class ReadCache:
    def __init__(self, max_entries=32):
        self.max_entries = max_entries
        self.values = OrderedDict()
        self.loading = {}
        self.generation = 0
        self.condition = threading.Condition()

    def clear(self):
        with self.condition:
            self.generation += 1
            self.values.clear()
            self.condition.notify_all()

    def read(self, key, ttl, function):
        with self.condition:
            while True:
                old = self.values.get(key)
                if old and time.monotonic() - old[0] < ttl:
                    self.values.move_to_end(key)
                    return deepcopy(old[1])
                if key not in self.loading:
                    self.loading[key] = self.generation
                    generation = self.generation
                    break
                self.condition.wait()
        try:
            value = function()
            saved = deepcopy(value)
            with self.condition:
                if generation == self.generation:
                    self.values[key] = (time.monotonic(), saved)
                    self.values.move_to_end(key)
                    while len(self.values) > self.max_entries:
                        self.values.popitem(last=False)
            return value
        finally:
            with self.condition:
                self.loading.pop(key, None)
                self.condition.notify_all()
