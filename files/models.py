from typing import override

from django.db import models


class StoredFile(models.Model):
    """An uploaded photo kept in the database (files.storage.DatabaseStorage).

    Used where the server's disk is wiped on each restart, as on Render's free plan.
    """

    name = models.CharField(max_length=255, unique=True)
    content = models.BinaryField()
    size = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    @override
    def __str__(self) -> str:
        return self.name
