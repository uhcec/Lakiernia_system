from enum import Enum


class WorkOrderAttachmentCategory(str, Enum):
    """Structured discriminator for a work-order attachment (NA36).

    ``DOCUMENT`` is the catch-all for any uploaded file that is not a technical drawing (the historical
    default — every pre-NA36 attachment is a DOCUMENT). ``TECHNICAL_DRAWING`` marks a drawing that the
    office attaches at intake and the production stations view while they work. The category is enforced
    at the application layer (router/service); the column itself is a plain string, like the free-text
    ``attachment_type`` sub-label it sits alongside.
    """

    DOCUMENT = "DOCUMENT"
    TECHNICAL_DRAWING = "TECHNICAL_DRAWING"
