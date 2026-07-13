import queue
import threading
import time
from datetime import datetime


class EventBus:
    def __init__(self, max_backlog=300):
        self._lock = threading.Lock()
        self._subscribers = {}
        self._backlog = []
        self._max_backlog = max_backlog
        self._next_id = 1
        self._sub_counter = 0

    def publish(self, event_type, data=None):
        event = {
            "id": self._next_id,
            "type": event_type,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "data": data or {},
        }
        self._next_id += 1
        with self._lock:
            self._backlog.append(event)
            if len(self._backlog) > self._max_backlog:
                self._backlog = self._backlog[-self._max_backlog:]
            dead = []
            for sub_id, sub in self._subscribers.items():
                filters = sub.get("filters")
                if filters and event_type not in filters:
                    continue
                try:
                    sub["queue"].put_nowait(event)
                except queue.Full:
                    dead.append(sub_id)
            for sub_id in dead:
                self._subscribers.pop(sub_id, None)
        return event

    def subscribe(self, filters=None, maxsize=100, client_info=None):
        with self._lock:
            self._sub_counter += 1
            sub_id = f"sub-{self._sub_counter}-{threading.get_ident()}-{int(time.time() * 1000)}"
            self._subscribers[sub_id] = {
                "queue": queue.Queue(maxsize=maxsize),
                "filters": set(filters or []),
                "client_info": client_info or {},
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
        return sub_id

    def unsubscribe(self, sub_id):
        with self._lock:
            return self._subscribers.pop(sub_id, None) is not None

    def get(self, sub_id, timeout=15.0):
        sub = self._subscribers.get(sub_id)
        if not sub:
            return None
        try:
            return sub["queue"].get(timeout=timeout)
        except queue.Empty:
            return None

    def recent(self, since_id=0, types=None, limit=100):
        types_set = set(types or [])
        with self._lock:
            events = [
                e for e in self._backlog
                if e["id"] > since_id and (not types_set or e["type"] in types_set)
            ]
        if limit:
            events = events[-limit:]
        return events

    def stats(self):
        with self._lock:
            return {
                "subscriber_count": len(self._subscribers),
                "backlog_size": len(self._backlog),
                "next_id": self._next_id,
                "max_backlog": self._max_backlog,
                "subscribers": {
                    sub_id: {
                        "filters": sorted(sub.get("filters", [])),
                        "client_info": sub.get("client_info", {}),
                        "created_at": sub.get("created_at"),
                        "queue_size": sub["queue"].qsize(),
                    }
                    for sub_id, sub in self._subscribers.items()
                },
            }

    def reset(self):
        with self._lock:
            self._subscribers.clear()
            self._backlog.clear()
            self._next_id = 1


bus = EventBus()
