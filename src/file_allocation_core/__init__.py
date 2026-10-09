"""
file_allocation_core - shared POST RECEIVED filing rules.

Used by every process that files documents into POST RECEIVED (the ODC
supplier bots through lib-odc-core, automation-post-allocation,
automation-emailed-invoice-ebills-allocation) and by
automation-x-drive-post-report, which owns the customer master table this
package reads and writes.
"""

from . import customer_folders, routing

__version__ = "0.1.0"

__all__ = ["customer_folders", "routing"]
