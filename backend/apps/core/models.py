import uuid

from django.db import models


class TimeStampedModel(models.Model):
    """Abstract base: public UUID plus created/updated timestamps."""

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
