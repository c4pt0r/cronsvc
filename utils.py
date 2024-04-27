import pytz
import threading
from datetime import datetime, timezone

def local_time_to_utc(dt: datetime, tz: str = '') -> datetime:
    if tz == '':
        local_tz = datetime.now().astimezone().tzinfo
        local_dt = dt.replace(tzinfo=local_tz)
    else:
        local_tz = timezone(tz)
        local_dt = local_tz.localize(dt)
    utc_dt = local_dt.astimezone(timezone.utc)
    return utc_dt

def utc_to_local_time(dt: datetime, tz: str = None) -> datetime:
    utc_tz = pytz.utc
    utc_dt = utc_tz.localize(dt)

    if tz is None:
        local_tz = pytz.timezone(datetime.now().astimezone().tzname())
    else:
        local_tz = pytz.timezone(tz)
    local_dt = utc_dt.astimezone(local_tz)
    return local_dt

class ThreadSafeMap:
    def __init__(self):
        self._map = {}
        self._lock = threading.Lock()

    def __getitem__(self, key):
        with self._lock:
            return self._map[key]

    def __setitem__(self, key, value):
        with self._lock:
            self._map[key] = value

    def __delitem__(self, key):
        with self._lock:
            del self._map[key]

    def __contains__(self, key):
        with self._lock:
            return key in self._map

    def __len__(self):
        with self._lock:
            return len(self._map)

    def keys(self):
        with self._lock:
            return list(self._map.keys())

    def values(self):
        with self._lock:
            return list(self._map.values())

    def items(self):
        with self._lock:
            return list(self._map.items())

    def get(self, key, default=None):
        with self._lock:
            return self._map.get(key, default)

    def filter(self, predicate):
        with self._lock:
            return {k: v for k, v in self._map.items() if predicate(k, v)}

    def remove_if(self, predicate):
        ret = []
        with self._lock:
            keys_to_remove = [k for k, v in self._map.items() if predicate(k, v)]
            for key in keys_to_remove:
                ret.append(self._map[key])
                del self._map[key]
        return ret