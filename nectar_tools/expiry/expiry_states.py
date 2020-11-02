ACTIVE = 'active'

WARNING = 'warning'

RESTRICTED = 'restricted'

STOPPED = 'stopped'

ARCHIVING = 'archiving'

ARCHIVED = 'archived'

DELETED = 'deleted'

ARCHIVE_ERROR = 'archive error'

RENEWED = 'renewed'

ADMIN = 'admin'


# Deprecated States
QUOTA_WARNING = 'quota warning'

PENDING_SUSPENSION = 'pending suspension'

SUSPENDED = 'suspended'

DEPRECATED_STATE_MAP = {
    PENDING_SUSPENSION: RESTRICTED,
    QUOTA_WARNING: WARNING,
    SUSPENDED: STOPPED,
}

ALL_STATES = [ACTIVE, WARNING, RESTRICTED, STOPPED, ARCHIVING,
              ARCHIVED, DELETED, ARCHIVE_ERROR, RENEWED, ADMIN,
              QUOTA_WARNING, PENDING_SUSPENSION, SUSPENDED]
