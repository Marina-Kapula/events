# Custom QuerySets and pyrefly

Checked 2026-11-21 with pyrefly 1.3.1 and django-stubs 6.1.1.

- pyrefly types `EventQuerySet.as_manager()` and `Manager.from_queryset(EventQuerySet)()` as a
  plain `Manager[Event]`, so `Event.objects.upcoming()` is a `missing-attribute` error.
- Declare the manager as the QuerySet type, with the one ignore:

  ```python
  class EventQuerySet(models.QuerySet["Event"]):
      def upcoming(self, *, now: datetime) -> Self:
          return self.filter(starts_at__gte=now)


  class Event(models.Model):
      # pyrefly sees as_manager() as a plain Manager; the manager proxies the QuerySet's methods.
      objects: EventQuerySet = EventQuerySet.as_manager()  # pyrefly: ignore[bad-assignment]
  ```

- With it, `Event.objects.upcoming(now=now).filter(...)` is an `EventQuerySet`, `.first()` is
  `Event | None`, and `create()`/`get()` return `Event`.
- Return `Self` from QuerySet methods so they chain.
